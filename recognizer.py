from __future__ import annotations
import os, queue, threading, time
import cv2, numpy as np
from insightface.app import FaceAnalysis
from config import AI_MODEL, AI_DET_SIZE, AI_INPUT_SIZE, AI_INTERVAL, SIMILARITY_THRESHOLD, CAM_WIDTH, CAM_HEIGHT
from liveness import LivenessDetector

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"


class FaceRecognizer:
    """
    Quản lý camera + AI inference.
    - Luồng camera reader: chạy mãi, dùng Event để ngủ/thức
    - Luồng AI worker: chạy mãi, có watchdog chống crash
    - Nhận diện: cosine similarity — thêm NV không cần train lại
    """

    def __init__(self):
        self._app       = None
        self._db        = {}
        self._liveness  = LivenessDetector()

        self.cap        = None
        self.is_running = False
        self._cam_event = threading.Event()
        self._lock      = threading.Lock()
        self._frame     = None
        self._queue     = queue.Queue(maxsize=1)

    # -- Setup --

    def load_model(self):
        print("⏳ Nạp InsightFace...")
        self._app = FaceAnalysis(name=AI_MODEL, providers=["CPUExecutionProvider"])
        self._app.prepare(ctx_id=-1, det_size=AI_DET_SIZE)
        threading.Thread(target=self._cam_reader, daemon=True).start()
        threading.Thread(target=self._ai_worker,  daemon=True).start()
        print("✅ Sẵn sàng.")

    def set_db(self, db: dict):
        self._db = db

    # -- Camera --

    def start_camera(self) -> bool:
        self.cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            return False
        with self._lock: self._frame = None
        while not self._queue.empty():
            try: self._queue.get_nowait()
            except queue.Empty: break
        self.is_running = True
        self._liveness.reset()
        self._cam_event.set()
        return True

    def stop_camera(self):
        self.is_running = False
        if self.cap: self.cap.release(); self.cap = None
        with self._lock: self._frame = None

    def get_frame(self):
        with self._lock: return self._frame

    def get_result(self):
        try: return self._queue.get_nowait()
        except queue.Empty: return None

    def reset_liveness(self):
        self._liveness.reset()

    # -- Luồng camera (không bao giờ chết) --

    def _cam_reader(self):
        while True:
            self._cam_event.wait()
            while self.is_running:
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        with self._lock: self._frame = frame
                time.sleep(0.008)
            with self._lock: self._frame = None
            self._cam_event.clear()

    # -- Luồng AI (watchdog: không bao giờ chết) --

    def _ai_worker(self):
        while True:
            try:
                if not self.is_running:
                    time.sleep(0.05); continue

                with self._lock: frame = self._frame
                if frame is None:
                    time.sleep(AI_INTERVAL); continue

                h, w   = frame.shape[:2]
                small  = cv2.resize(frame, AI_INPUT_SIZE)
                sx, sy = w / AI_INPUT_SIZE[0], h / AI_INPUT_SIZE[1]

                faces  = self._app.get(small)
                result = self._process(faces, sx, sy)

                if self._queue.full():
                    try: self._queue.get_nowait()
                    except queue.Empty: pass
                self._queue.put(result)

            except Exception as e:
                print(f"⚠️  AI worker: {e}")

            time.sleep(AI_INTERVAL)

    def _process(self, faces, sx, sy) -> dict:
        if not faces:
            _, msg = self._liveness.update_no_face()
            return {"status": "no_face", "msg": msg}

        face = faces[0]
        b    = face.bbox.astype(float)
        bbox = (max(0,int(b[0]*sx)), max(0,int(b[1]*sy)), max(0,int(b[2]*sx)), max(0,int(b[3]*sy)))

        ok, msg = self._liveness.update(face)
        if not ok:
            return {"status": "liveness", "msg": msg, "bbox": bbox}

        emb  = face.embedding
        norm = np.linalg.norm(emb)
        if norm == 0:
            return {"status": "liveness", "msg": "Loi embedding", "bbox": bbox}
        emb = emb / norm

        if not self._db:
            return {"status": "empty_db", "bbox": bbox}

        names   = list(self._db.keys())
        entries = list(self._db.values())
        # DB lưu dict {"emb":..., "role":..., "dept":...} hoặc array thẳng
        vecs    = np.array([e["emb"] if isinstance(e, dict) else e for e in entries], dtype=np.float32)
        sims    = vecs @ emb
        idx     = int(np.argmax(sims))
        sim     = float(sims[idx])

        if sim >= SIMILARITY_THRESHOLD:
            entry = entries[idx]
            role  = entry.get("role", "") if isinstance(entry, dict) else ""
            return {"status": "recognized", "name": names[idx], "role": role,
                    "confidence": round(sim*100, 1), "bbox": bbox}

        return {"status": "unknown", "bbox": bbox}
