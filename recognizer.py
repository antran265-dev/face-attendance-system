from __future__ import annotations
"""
recognizer.py — AI + camera, hỗ trợ đa camera.
Mỗi camera = 1 CameraWorker riêng, dùng chung 1 model InsightFace.
"""

import os, threading, time, queue
import cv2, numpy as np
from insightface.app import FaceAnalysis
from config import AI_MODEL, AI_DET_SIZE, AI_INPUT_SIZE, AI_INTERVAL, SIMILARITY_THRESHOLD
from liveness import MotionLivenessDetector

os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'


class CameraWorker:
    """
    1 luồng camera + 1 luồng AI cho mỗi camera.
    Dùng chung face_app và db từ FaceRecognizer.
    """
    def __init__(self, cam_id: str, cam_index: int, face_app, db_ref: dict,
                 result_callback):
        self.cam_id    = cam_id
        self.cam_index = cam_index
        self._face_app = face_app
        self._db       = db_ref           # tham chiếu dict — update ngay khi db đổi
        self._callback = result_callback  # fn(cam_id, result_dict)

        self._cap        = None
        self.is_running  = False
        self._cam_event  = threading.Event()
        self._frame_lock = threading.Lock()
        self._cur_frame  = None
        self._result_q   = queue.Queue(maxsize=1)
        self._liveness   = MotionLivenessDetector()

    def start(self) -> bool:
        self._cap = cv2.VideoCapture(self.cam_index, cv2.CAP_MSMF)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            return False
        self.is_running = True
        self._liveness.reset()
        with self._frame_lock:
            self._cur_frame = None
        while not self._result_q.empty():
            try: self._result_q.get_nowait()
            except queue.Empty: break
        self._cam_event.set()
        return True

    def stop(self):
        self.is_running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        with self._frame_lock:
            self._cur_frame = None

    def get_frame(self):
        with self._frame_lock:
            return self._cur_frame

    def get_result(self):
        try:    return self._result_q.get_nowait()
        except queue.Empty: return None

    def reset_liveness(self):
        self._liveness.reset()

    def run_camera_reader(self):
        """Luồng đọc camera — gọi từ thread riêng."""
        while True:
            self._cam_event.wait()
            while self.is_running:
                cap = self._cap
                if cap and cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        with self._frame_lock:
                            self._cur_frame = frame
                time.sleep(0.008)
            with self._frame_lock:
                self._cur_frame = None
            self._cam_event.clear()

    def run_ai_worker(self):
        """Luồng AI — chạy suốt vòng đời app, không bao giờ dừng."""
        while True:
            try:
                if not self.is_running:
                    time.sleep(0.05)
                    continue

                with self._frame_lock:
                    frame = self._cur_frame

                if frame is None:
                    time.sleep(AI_INTERVAL)
                    continue

                # Tạo bản sao nhỏ để AI xử lý — không giữ lock
                try:
                    small = cv2.resize(frame, AI_INPUT_SIZE)
                except Exception:
                    time.sleep(AI_INTERVAL)
                    continue

                h0, w0 = frame.shape[:2]
                sx, sy = w0 / AI_INPUT_SIZE[0], h0 / AI_INPUT_SIZE[1]

                try:
                    faces = self._face_app.get(small)
                except Exception:
                    time.sleep(AI_INTERVAL)
                    continue

                result = self._build_result(faces, sx, sy)

                # Bỏ kết quả cũ chưa đọc, đẩy kết quả mới
                if self._result_q.full():
                    try: self._result_q.get_nowait()
                    except queue.Empty: pass
                self._result_q.put(result)

            except Exception as e:
                # Watchdog: bất kỳ lỗi nào cũng không làm chết luồng
                print(f"⚠️  AI worker [{self.cam_id}] lỗi: {e}")

            time.sleep(AI_INTERVAL)

    def _build_result(self, faces, sx: float, sy: float) -> dict:
        if not faces:
            _, msg = self._liveness.update_no_face()
            return {"status": "no_face", "msg": msg, "cam_id": self.cam_id}

        face = faces[0]
        bx = face.bbox.astype(float)
        bbox = (max(0,int(bx[0]*sx)), max(0,int(bx[1]*sy)),
                max(0,int(bx[2]*sx)), max(0,int(bx[3]*sy)))

        passed, live_msg = self._liveness.update(face)
        if not passed:
            return {"status": "liveness", "msg": live_msg,
                    "bbox": bbox, "cam_id": self.cam_id}

        raw  = face.embedding
        norm = np.linalg.norm(raw)
        if norm == 0:
            return {"status": "liveness", "msg": "Loi embedding",
                    "bbox": bbox, "cam_id": self.cam_id}
        emb = raw / norm

        db = self._db
        if not db:
            return {"status": "empty_db", "bbox": bbox, "cam_id": self.cam_id}

        names   = list(db.keys())
        # Mỗi value là dict {"embedding": ..., "role": ...}
        db_embs = np.array([v.get("embedding", v.get("emb")) for v in db.values()], dtype=np.float32)
        sims    = db_embs @ emb
        idx     = int(np.argmax(sims))
        sim     = float(sims[idx])

        if sim >= SIMILARITY_THRESHOLD:
            role = db[names[idx]].get("role", "Nhân viên")
            # KHÔNG reset liveness ở đây — để UI thread điều khiển
            return {
                "status":     "recognized",
                "name":       names[idx],
                "role":       role,
                "confidence": round(sim * 100, 1),
                "bbox":       bbox,
                "cam_id":     self.cam_id,
            }
        else:
            # KHÔNG reset liveness ở đây — để UI thread điều khiển
            return {"status": "unknown", "bbox": bbox, "cam_id": self.cam_id}


class FaceRecognizer:
    """
    Quản lý nhiều CameraWorker, dùng chung 1 model.
    Mặc định 1 camera (cam_index=0). Gọi add_camera() để thêm.
    """
    def __init__(self):
        self._face_app = None
        self._db: dict = {}           # {name: {"embedding": np.array, "role": str}}
        self._workers: dict = {}      # {cam_id: CameraWorker}
        # Backward compat: thuộc tính is_running cho cam đầu tiên
        self._default_cam = "cam1"

    @property
    def is_running(self) -> bool:
        w = self._workers.get(self._default_cam)
        return w.is_running if w else False

    @property
    def _is_running(self) -> bool:
        return self.is_running

    @_is_running.setter
    def _is_running(self, val: bool):
        w = self._workers.get(self._default_cam)
        if w: w.is_running = val

    def load_model(self):
        print(f"⏳ Nạp InsightFace {AI_MODEL}...")
        self._face_app = FaceAnalysis(
            name=AI_MODEL, providers=["CPUExecutionProvider"])
        self._face_app.prepare(ctx_id=-1, det_size=AI_DET_SIZE)
        print("✅ Model sẵn sàng.")
        # Tạo worker mặc định cam1
        self._create_worker(self._default_cam, 0)

    def _create_worker(self, cam_id: str, cam_index: int):
        w = CameraWorker(cam_id, cam_index, self._face_app, self._db, None)
        self._workers[cam_id] = w
        threading.Thread(target=w.run_camera_reader, daemon=True).start()
        threading.Thread(target=w.run_ai_worker,     daemon=True).start()

    def add_camera(self, cam_id: str, cam_index: int):
        """Thêm camera thứ 2, 3, 4... Gọi sau load_model()."""
        if cam_id not in self._workers:
            self._create_worker(cam_id, cam_index)
            print(f"✅ Đã thêm {cam_id} (index={cam_index})")

    def set_db(self, db: dict):
        self._db.clear()
        self._db.update(db)

    def start_camera(self, cam_id: str = None) -> bool:
        cam_id = cam_id or self._default_cam
        w = self._workers.get(cam_id)
        return w.start() if w else False

    def stop_camera(self, cam_id: str = None):
        cam_id = cam_id or self._default_cam
        w = self._workers.get(cam_id)
        if w: w.stop()

    def get_current_frame(self, cam_id: str = None):
        cam_id = cam_id or self._default_cam
        w = self._workers.get(cam_id)
        return w.get_frame() if w else None

    def get_result(self, cam_id: str = None):
        cam_id = cam_id or self._default_cam
        w = self._workers.get(cam_id)
        return w.get_result() if w else None

    def reset_liveness(self, cam_id: str = None):
        cam_id = cam_id or self._default_cam
        w = self._workers.get(cam_id)
        if w: w.reset_liveness()

    @property
    def _face_app_ref(self):
        return self._face_app
