from __future__ import annotations
"""
client_main.py — Giao diện chấm công chạy trên máy CAMERA (client).
 
Khác với main.py (chạy độc lập), file này:
  - KHÔNG load model InsightFace nặng để nhận diện (server làm việc đó)
  - CHỈ chạy model nhẹ để LẤY EMBEDDING từ khuôn mặt, rồi gửi qua HTTP
  - KHÔNG có Database local — mọi dữ liệu nằm trên server
 
Cách dùng:
    1. Sửa SERVER_URL bên dưới thành địa chỉ IP máy chủ trong mạng LAN
    2. Chạy: python client_main.py
    3. Nhiều máy camera (cổng chính, xưởng, cổng phụ) đều chạy file này,
       chỉ cần đổi CAMERA_ID cho mỗi máy.
"""
 
import os, time, threading, queue
import cv2, numpy as np
import requests
import customtkinter as ctk
from PIL import Image
 
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
 
from insightface.app import FaceAnalysis
from liveness import LivenessDetector
from config import AI_MODEL, AI_DET_SIZE, AI_INPUT_SIZE, AI_INTERVAL, CAM_WIDTH, CAM_HEIGHT, CAM_DISPLAY
 
# ============================================================
# CẤU HÌNH RIÊNG CHO CLIENT — SỬA THEO MÁY
# ============================================================
 
SERVER_URL = "http://127.0.0.1:5000"   # <-- ĐỔI thành IP máy chủ thật trong LAN
CAMERA_ID  = "cong_chinh"                   # <-- đặt tên riêng cho mỗi máy: cong_chinh / xuong / cong_phu
 
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
 
BG, PANEL, CARD = "#0d0d1a", "#111827", "#1a2035"
BLUE, GREEN, RED, ORANGE, DIM = "#3b82f6", "#10b981", "#ef4444", "#f59e0b", "#6b7280"
 
 
# ============================================================
# GIAO TIẾP VỚI SERVER
# ============================================================
 
def call_checkin(embedding: np.ndarray) -> dict | None:
    """Gửi embedding lên server, nhận kết quả nhận diện + chấm công."""
    try:
        r = requests.post(
            f"{SERVER_URL}/api/checkin",
            json={"embedding": embedding.tolist(), "camera_id": CAMERA_ID},
            timeout=3,
        )
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Không kết nối được server: {e}")
        return None
 
 
def check_server_alive() -> bool:
    try:
        r = requests.get(f"{SERVER_URL}/api/health", timeout=2)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False
 
 
# ============================================================
# ỨNG DỤNG CLIENT
# ============================================================
 
class ClientApp(ctk.CTk):
 
    def __init__(self):
        super().__init__()
        self.title(f"MÁY CHẤM CÔNG — {CAMERA_ID}")
        self.geometry("900x650")
        self.configure(fg_color=BG)
 
        self.cap        = None
        self.is_running = False
        self._lock      = threading.Lock()
        self._frame     = None
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._bbox      = None
        self._bcolor    = (100, 100, 100)
        self._blabel    = ""
        self._liveness  = LivenessDetector()
 
        self._build_ui()
        self._status("Đang kết nối server...", ORANGE)
        self.after(200, self._init)
 
    def _init(self):
        # Kiểm tra server trước
        if not check_server_alive():
            self._status(f"❌ Không kết nối được server tại {SERVER_URL}", RED)
            self.btn_cam.configure(state="disabled")
        else:
            self._status(f"✅ Đã kết nối server: {SERVER_URL}", GREEN)
 
        # Load model NHẸ chỉ để lấy embedding — không cần nhận diện ở client
        print("⏳ Nạp model nhận diện (chỉ để lấy embedding)...")
        self.face_app = FaceAnalysis(name=AI_MODEL, providers=["CPUExecutionProvider"])
        self.face_app.prepare(ctx_id=-1, det_size=AI_DET_SIZE)
        print("✅ Sẵn sàng.")
 
        threading.Thread(target=self._cam_reader, daemon=True).start()
        threading.Thread(target=self._ai_worker,  daemon=True).start()
 
    # -- Camera reader (giống bản cũ) --
 
    def _cam_reader(self):
        while True:
            while self.is_running:
                if self.cap and self.cap.isOpened():
                    ret, f = self.cap.read()
                    if ret:
                        with self._lock: self._frame = f
                time.sleep(0.008)
            time.sleep(0.05)
 
    # -- AI worker: chỉ detect + lấy embedding, GỌI SERVER để nhận diện --
 
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
 
                faces = self.face_app.get(small)
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
 
        # GỌI SERVER — đây là điểm khác biệt cốt lõi so với bản standalone
        server_result = call_checkin(emb)
 
        if server_result is None:
            return {"status": "server_error", "bbox": bbox}
 
        if not server_result.get("recognized"):
            return {"status": "unknown", "bbox": bbox}
 
        return {
            "status": "recognized",
            "name": server_result["name"],
            "role": server_result.get("role", ""),
            "confidence": server_result["confidence"],
            "logged": server_result.get("logged", False),
            "event": server_result.get("event", ""),
            "time": server_result.get("time", ""),
            "bbox": bbox,
        }
 
    # -- UI loop --
 
    def _loop(self):
        if not self.is_running:
            return
        with self._lock: frame = self._frame
        if frame is not None:
            frame = frame.copy()
            try:
                result = self._queue.get_nowait()
                self._handle(result)
            except queue.Empty:
                pass
 
            if self._bbox:
                x1,y1,x2,y2 = self._bbox
                cv2.rectangle(frame, (x1,y1), (x2,y2), self._bcolor, 2)
                if self._blabel:
                    cv2.putText(frame, self._blabel, (x1, max(20,y1-10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, self._bcolor, 2)
 
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = ctk.CTkImage(light_image=Image.fromarray(rgb),
                               dark_image=Image.fromarray(rgb), size=CAM_DISPLAY)
            self.lbl_cam.configure(image=img, text="")
        self.after(15, self._loop)
 
    def _handle(self, r: dict):
        s = r.get("status")
        if s == "no_face":
            self._bbox = None
            self.lbl_result.configure(text="---", text_color=DIM)
        elif s == "liveness":
            self._bbox, self._bcolor, self._blabel = r["bbox"], (0,165,255), r["msg"]
            self.lbl_result.configure(text="Đang xác thực...", text_color=ORANGE)
        elif s == "server_error":
            self._bbox = r["bbox"]
            self.lbl_result.configure(text="❌ Mất kết nối server!", text_color=RED)
        elif s == "recognized":
            name, conf, role = r["name"], r["confidence"], r.get("role","")
            self._bbox, self._bcolor = r["bbox"], (16,185,129)
            self._blabel = f"{name} ({conf}%)"
            if r.get("logged"):
                icon = "✅ VÀO" if r["event"]=="CHECK_IN" else "🚪 RA"
                self.lbl_result.configure(text=f"{icon}\n{name}", text_color=GREEN)
                self._status(f"{icon}  {name}  {r['time']}", GREEN)
            else:
                self.lbl_result.configure(text=f"✅ {name}", text_color=GREEN)
            self._liveness.reset()
        elif s == "unknown":
            self._bbox, self._bcolor, self._blabel = r["bbox"], (239,68,68), "Nguoi la"
            self.lbl_result.configure(text="❌ Không nhận ra", text_color=RED)
            self._liveness.reset()
 
    # -- Camera control --
 
    def _toggle_cam(self):
        if not self.is_running:
            self.cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self.cap.isOpened():
                self._status("❌ Không tìm thấy Camera!", RED); return
            self.is_running = True
            self._liveness.reset()
            self.btn_cam.configure(text="⏹  TẮT CAMERA", fg_color=RED)
            self._loop()
        else:
            self.is_running = False
            self.cap.release(); self.cap = None
            self.btn_cam.configure(text="▶  BẬT CAMERA", fg_color=GREEN)
            self.lbl_cam.configure(image=None, text="Camera đã tắt")
 
    def _status(self, text, color):
        self.lbl_status.configure(text=text, text_color=color)
 
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
 
        hdr = ctk.CTkFrame(self, fg_color=PANEL, height=50)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text=f"🎥 CLIENT: {CAMERA_ID}  →  {SERVER_URL}",
                     font=("Arial", 13, "bold")).pack(pady=12, padx=16, side="left")
 
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
 
        cam_wrap = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=14)
        cam_wrap.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        self.lbl_cam = ctk.CTkLabel(cam_wrap, text="Bấm BẬT CAMERA", font=("Arial", 16))
        self.lbl_cam.pack(expand=True, fill="both", padx=10, pady=10)
 
        right = ctk.CTkFrame(body, fg_color=CARD, corner_radius=14, width=260)
        right.grid(row=0, column=1, sticky="nsew")
 
        self.btn_cam = ctk.CTkButton(right, text="▶  BẬT CAMERA", height=46,
                                     command=self._toggle_cam, fg_color=GREEN)
        self.btn_cam.pack(fill="x", padx=14, pady=14)
 
        self.lbl_result = ctk.CTkLabel(right, text="---", font=("Arial", 20, "bold"))
        self.lbl_result.pack(pady=20)
 
        self.lbl_status = ctk.CTkLabel(right, text="Đang tải...", font=("Arial", 11),
                                       text_color=ORANGE, wraplength=220)
        self.lbl_status.pack(pady=10, padx=10)
 
 
if __name__ == "__main__":
    app = ClientApp()
    app.mainloop()