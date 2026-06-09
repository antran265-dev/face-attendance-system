from __future__ import annotations
import threading, time
import cv2, numpy as np
import customtkinter as ctk
from PIL import Image
from config import AI_INPUT_SIZE, AI_INTERVAL, REG_SAMPLES, ROLE_OPTIONS


class RegisterWindow(ctk.CTkToplevel):
    """Cửa sổ đăng ký nhân viên: nhập tên + chức vụ -> quét mặt -> lưu."""

    def __init__(self, parent, face_app, existing: list, on_done):
        super().__init__(parent)
        self.title("ĐĂNG KÝ NHÂN VIÊN MỚI")
        self.geometry("760x680")
        self.resizable(False, False)
        self.grab_set()

        self._app       = face_app
        self._existing  = existing
        self._on_done   = on_done
        self._cap       = None
        self._scanning  = False
        self._finishing = False
        self._embeds    = []
        self._lock      = threading.Lock()
        self._frame     = None
        self._stop      = threading.Event()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)



class RegisterWindow(ctk.CTkToplevel):

    def __init__(self, parent, face_app, existing_names: list, on_done):
        super().__init__(parent)
        self.title("ĐĂNG KÝ NHÂN VIÊN MỚI")
        self.geometry("760X680")
        self.resizable(False, False)
        self.grab_set()

        self._face_app  = face_app
        self._existing  = existing_names
        self._on_done   = on_done

        self._cap         = None
        self._is_scanning = False
        self._finishing   = False          # flag: đang trong _finish, giữ display_loop sống
        self._embeddings  = []
        self._frame_lock  = threading.Lock()
        self._cur_frame   = None
        self._stop_event  = threading.Event()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        ctk.CTkLabel(self, text="ĐĂNG KÝ NHÂN VIÊN MỚI",
                     font=("Arial", 20, "bold")).pack(pady=(16, 2))
        ctk.CTkLabel(self,
                     text="Nhập thông tin → Bắt đầu → Nhìn vào camera → Xoay đầu chậm",
                     font=("Arial", 12), text_color="gray").pack(pady=(0, 8))

        # ── Form nhập liệu ────────────────────────────────────────────────
        form = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=10)
        form.pack(fill="x", padx=24, pady=(0, 8))
        form.grid_columnconfigure(1, weight=1)

        # Họ tên
        ctk.CTkLabel(form, text="Họ và tên ✱",
                     font=("Arial", 13, "bold"), text_color="white",
                     width=110, anchor="w").grid(row=0, column=0, padx=(16, 8), pady=(14, 6), sticky="w")
        self.entry_name = ctk.CTkEntry(
            form, placeholder_text="VD: Nguyễn Văn An",
            font=("Arial", 13), height=38)
        self.entry_name.grid(row=0, column=1, padx=(0, 16), pady=(14, 6), sticky="ew")

        # Chức vụ — dropdown
        ctk.CTkLabel(form, text="Chức vụ ✱",
                     font=("Arial", 13, "bold"), text_color="white",
                     width=110, anchor="w").grid(row=1, column=0, padx=(16, 8), pady=6, sticky="w")
        self.combo_role = ctk.CTkOptionMenu(
            form, values=ROLE_OPTIONS,
            font=("Arial", 13), height=38,
            fg_color="#2b2b2b", button_color="#3b82f6",
            dropdown_fg_color="#1e1e2e")
        self.combo_role.set(ROLE_OPTIONS[0])
        self.combo_role.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="ew")

        # Phòng ban (tuỳ chọn)
        ctk.CTkLabel(form, text="Phòng ban",
                     font=("Arial", 13), text_color="#6b7280",
                     width=110, anchor="w").grid(row=2, column=0, padx=(16, 8), pady=(6, 14), sticky="w")
        self.entry_dept = ctk.CTkEntry(
            form, placeholder_text="VD: Sản xuất / Kế toán / IT... (không bắt buộc)",
            font=("Arial", 13), height=36)
        self.entry_dept.grid(row=2, column=1, padx=(0, 16), pady=(6, 14), sticky="ew")

        # ── Khung camera ─────────────────────────────────────────────────
        cam_wrap = ctk.CTkFrame(self, corner_radius=12)
        cam_wrap.pack(padx=24, pady=4, fill="both", expand=True)
        self.lbl_cam = ctk.CTkLabel(
            cam_wrap,
            text="📷  Bấm  「BẮT ĐẦU ĐĂNG KÝ」  để mở camera",
            font=("Arial", 15), text_color="gray")
        self.lbl_cam.pack(expand=True, fill="both", padx=8, pady=8)

        # ── Progress ─────────────────────────────────────────────────────
        prow = ctk.CTkFrame(self, fg_color="transparent")
        prow.pack(fill="x", padx=24, pady=(6, 2))
        self.lbl_prog = ctk.CTkLabel(prow, text=f"0 / {REG_SAMPLES}",
                                     font=("Arial", 13), text_color="gray")
        self.lbl_prog.pack(side="left")
        self.lbl_hint = ctk.CTkLabel(prow, text="",
                                     font=("Arial", 13), text_color="cyan")
        self.lbl_hint.pack(side="right")

        self.prog_bar = ctk.CTkProgressBar(self, height=14, corner_radius=6)
        self.prog_bar.set(0)
        self.prog_bar.pack(fill="x", padx=24, pady=(0, 8))

        # ── Nút ──────────────────────────────────────────────────────────
        brow = ctk.CTkFrame(self, fg_color="transparent")
        brow.pack(fill="x", padx=24, pady=(0, 16))
        self.btn_start = ctk.CTkButton(
            brow, text="▶  BẮT ĐẦU ĐĂNG KÝ", height=46,
            font=("Arial", 15, "bold"), fg_color="green", hover_color="#059669",
            command=self._start_scan)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=(0, 8))
        ctk.CTkButton(
            brow, text="✖  HỦY", height=46,
            font=("Arial", 14), fg_color="#6b2020", hover_color="#8b3030",
            command=self._on_close).pack(side="left", expand=True, fill="x")

    # ── Logic ────────────────────────────────────────────────────────────

    def _start_scan(self):
        name = self.entry_name.get().strip()
        role = self.combo_role.get().strip()
        dept = self.entry_dept.get().strip()

        if not name:
            self.lbl_hint.configure(text="⚠ Chưa nhập họ tên!", text_color="orange")
            return
        if name in self._existing:
            self.lbl_hint.configure(text=f"⚠ '{name}' đã tồn tại!", text_color="orange")
            return

        self._reg_name = name
        self._reg_role = role
        self._reg_dept = dept
        self._embeddings  = []
        self._is_scanning = True
        self._finishing   = False
        self._stop_event.clear()

        self.entry_name.configure(state="disabled")
        self.combo_role.configure(state="disabled")
        self.entry_dept.configure(state="disabled")
        self.btn_start.configure(state="disabled", text="⏳ Đang quét...", fg_color="gray")
        self.lbl_prog.configure(text=f"0 / {REG_SAMPLES}", text_color="white")
        self.prog_bar.set(0)
        self.lbl_hint.configure(text="Nhìn thẳng vào camera", text_color="cyan")

        self._cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self._cap.isOpened():
            self.lbl_hint.configure(text="❌ Không tìm thấy Camera!", text_color="red")
            self._is_scanning = False
            return

        threading.Thread(target=self._cam_reader,  daemon=True).start()
        threading.Thread(target=self._scan_worker, daemon=True).start()
        self._display_loop()

    def _cam_reader(self):
        while not self._stop_event.is_set():
            if self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret:
                    with self._frame_lock:
                        self._cur_frame = frame
            time.sleep(0.01)

    def _scan_worker(self):
        while self._is_scanning and len(self._embeddings) < REG_SAMPLES:
            with self._frame_lock:
                frame = self._cur_frame
            if frame is None:
                time.sleep(0.05)
                continue

            small = cv2.resize(frame, AI_INPUT_SIZE)
            try:
                faces = self._face_app.get(small)
            except Exception:
                time.sleep(AI_INTERVAL)
                continue

            if faces:
                raw  = faces[0].embedding
                norm = np.linalg.norm(raw)
                if norm > 0:
                    self._embeddings.append((raw / norm).astype(np.float32))
                    count = len(self._embeddings)
                    self.after(0, self._update_prog, count)

            time.sleep(AI_INTERVAL)

        # Đủ mẫu hoặc bị dừng từ ngoài
        if self._is_scanning:
            self._finishing = True       # giữ display_loop sống trong lúc finish
            self._is_scanning = False
            self.after(0, self._finish)

    def _update_prog(self, count: int):
        self.prog_bar.set(count / REG_SAMPLES)
        self.lbl_prog.configure(text=f"{count} / {REG_SAMPLES}", text_color="white")
        if count < REG_SAMPLES * 0.30:
            self.lbl_hint.configure(text="Nhìn thẳng vào camera",    text_color="cyan")
        elif count < REG_SAMPLES * 0.55:
            self.lbl_hint.configure(text="Xoay đầu nhẹ trái / phải", text_color="cyan")
        elif count < REG_SAMPLES * 0.80:
            self.lbl_hint.configure(text="Ngẩng / cúi đầu nhẹ",      text_color="cyan")
        else:
            self.lbl_hint.configure(text="Gần xong! Giữ nguyên...",   text_color="lime")

    def _display_loop(self):
        # FIX: tiếp tục chạy khi _finishing=True để frame hiển thị đến lúc đóng
        if not self._is_scanning and not self._finishing:
            return

        with self._frame_lock:
            frame = self._cur_frame

        if frame is not None:
            frame = frame.copy()
            h, w  = frame.shape[:2]
            count = len(self._embeddings)
            bar_w = int(w * count / REG_SAMPLES)
            cv2.rectangle(frame, (0, h - 10), (bar_w, h), (0, 200, 80), -1)
            cv2.putText(frame, f"{count}/{REG_SAMPLES}",
                        (w - 120, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 100), 2)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = ctk.CTkImage(
                light_image=Image.fromarray(rgb),
                dark_image =Image.fromarray(rgb),
                size=(700, 420))
            self.lbl_cam.configure(image=img, text="")

        self.after(15, self._display_loop)

    def _finish(self):
        self._stop_event.set()
        if self._cap:
            self._cap.release()
            self._cap = None

        if not self._embeddings:
            self.lbl_hint.configure(text="❌ Không thu được mẫu nào!", text_color="red")
            self.btn_start.configure(state="normal", text="▶  THỬ LẠI", fg_color="green")
            self.entry_name.configure(state="normal")
            self.combo_role.configure(state="normal")
            self.entry_dept.configure(state="normal")
            self._finishing = False
            return

        mean_emb = np.mean(self._embeddings, axis=0).astype(np.float32)
        norm     = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb /= norm

        # Hiển thị HOÀN TẤT 100%
        self.prog_bar.set(1.0)
        self.lbl_prog.configure(text=f"✅ HOÀN TẤT! ({REG_SAMPLES}/{REG_SAMPLES})",
                                text_color="lime")
        self.lbl_hint.configure(
            text=f"Đã lưu {len(self._embeddings)} mẫu — {self._reg_role}",
            text_color="lime")

        # Gọi callback về cửa sổ chính
        self._on_done(self._reg_name, self._reg_role, self._reg_dept, mean_emb)

        # Đóng sau 1.5s để người dùng thấy thông báo hoàn tất
        self._finishing = False
        self.after(1500, self.destroy)

    def _on_close(self):
        self._is_scanning = False
        self._finishing   = False
        self._stop_event.set()
        if self._cap:
            self._cap.release()
        self.destroy()


    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        ctk.CTkLabel(self, text="ĐĂNG KÝ NHÂN VIÊN MỚI",
                     font=("Arial", 20, "bold")).pack(pady=(16, 2))
        ctk.CTkLabel(self,
                     text="Nhập tên → Bắt đầu → Nhìn vào camera → Xoay đầu chậm",
                     font=("Arial", 12), text_color="gray").pack(pady=(0, 10))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 4))
        ctk.CTkLabel(row, text="Họ và tên:", font=("Arial", 14, "bold"),
                     width=90, anchor="w").pack(side="left")
        self.entry_name = ctk.CTkEntry(
            row, placeholder_text="VD: Nguyễn Văn An",
            font=("Arial", 14), width=310, height=40)
        self.entry_name.pack(side="left", padx=10)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkLabel(row2, text="Chức vụ:", font=("Arial", 14, "bold"),
                     width=90, anchor="w").pack(side="left")
        self.entry_role = ctk.CTkEntry(
            row2, placeholder_text="VD: Công nhân / Nhân viên / Kỹ sư...",
            font=("Arial", 13), width=310, height=38)
        self.entry_role.pack(side="left", padx=10)

        cam_wrap = ctk.CTkFrame(self, corner_radius=12)
        cam_wrap.pack(padx=24, pady=4, fill="both", expand=True)
        self.lbl_cam = ctk.CTkLabel(
            cam_wrap,
            text="📷  Bấm  「BẮT ĐẦU ĐĂNG KÝ」  để mở camera",
            font=("Arial", 15), text_color="gray")
        self.lbl_cam.pack(expand=True, fill="both", padx=8, pady=8)

        prow = ctk.CTkFrame(self, fg_color="transparent")
        prow.pack(fill="x", padx=24, pady=(6, 2))
        self.lbl_prog = ctk.CTkLabel(prow, text=f"0 / {REG_SAMPLES}",
                                     font=("Arial", 13), text_color="gray")
        self.lbl_prog.pack(side="left")
        self.lbl_hint = ctk.CTkLabel(prow, text="",
                                     font=("Arial", 13), text_color="cyan")
        self.lbl_hint.pack(side="right")

        self.prog_bar = ctk.CTkProgressBar(self, height=14, corner_radius=6)
        self.prog_bar.set(0)
        self.prog_bar.pack(fill="x", padx=24, pady=(0, 10))

        brow = ctk.CTkFrame(self, fg_color="transparent")
        brow.pack(fill="x", padx=24, pady=(0, 16))
        self.btn_start = ctk.CTkButton(
            brow, text="▶  BẮT ĐẦU ĐĂNG KÝ", height=46,
            font=("Arial", 15, "bold"), fg_color="green",
            command=self._start_scan)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=(0, 8))
        ctk.CTkButton(
            brow, text="✖  HỦY", height=46,
            font=("Arial", 14), fg_color="#6b2020", hover_color="#8b3030",
            command=self._on_close).pack(side="left", expand=True, fill="x")

    # ── Logic ────────────────────────────────────────────────────────────

    def _start_scan(self):
        name = self.entry_name.get().strip()
        role = self.entry_role.get().strip() or "Chưa phân loại"
        if not name:
            self.lbl_hint.configure(text="⚠ Chưa nhập tên!", text_color="orange")
            return
        if name in self._existing:
            self.lbl_hint.configure(text=f"⚠ '{name}' đã tồn tại!", text_color="orange")
            return

        self._reg_name    = name
        self._reg_role    = role
        self._embeddings  = []
        self._is_scanning = True
        self._stop_event.clear()

        self.entry_name.configure(state="disabled")
        self.entry_role.configure(state="disabled")
        self.btn_start.configure(state="disabled", text="⏳ Đang quét...", fg_color="gray")
        self.lbl_prog.configure(text=f"0 / {REG_SAMPLES}", text_color="white")
        self.prog_bar.set(0)
        self.lbl_hint.configure(text="Nhìn thẳng vào camera", text_color="cyan")

        self._cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self._cap.isOpened():
            self.lbl_hint.configure(text="❌ Không tìm thấy Camera!", text_color="red")
            self._is_scanning = False
            return

        threading.Thread(target=self._cam_reader,  daemon=True).start()
        threading.Thread(target=self._scan_worker, daemon=True).start()
        self._display_loop()

    def _cam_reader(self):
        while not self._stop_event.is_set():
            if self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret:
                    with self._frame_lock:
                        self._cur_frame = frame
            time.sleep(0.01)

    def _scan_worker(self):
        while self._is_scanning and len(self._embeddings) < REG_SAMPLES:
            with self._frame_lock:
                frame = self._cur_frame
            if frame is None:
                time.sleep(0.05)
                continue

            small = cv2.resize(frame, AI_INPUT_SIZE)
            try:
                faces = self._face_app.get(small)
            except Exception:
                time.sleep(AI_INTERVAL)
                continue

            if faces:
                raw  = faces[0].embedding
                norm = np.linalg.norm(raw)
                if norm > 0:
                    self._embeddings.append((raw / norm).astype(np.float32))
                    count = len(self._embeddings)
                    self.after(0, self._update_prog, count)

            time.sleep(AI_INTERVAL)

        if self._is_scanning:
            self.after(0, self._finish)

    def _update_prog(self, count: int):
        self.prog_bar.set(count / REG_SAMPLES)
        self.lbl_prog.configure(text=f"{count} / {REG_SAMPLES}", text_color="white")
        if count < REG_SAMPLES * 0.30:
            self.lbl_hint.configure(text="Nhìn thẳng vào camera",       text_color="cyan")
        elif count < REG_SAMPLES * 0.55:
            self.lbl_hint.configure(text="Xoay đầu nhẹ trái / phải",    text_color="cyan")
        elif count < REG_SAMPLES * 0.80:
            self.lbl_hint.configure(text="Ngẩng / cúi đầu nhẹ",         text_color="cyan")
        else:
            self.lbl_hint.configure(text="Gần xong! Giữ nguyên...",      text_color="lime")

    def _display_loop(self):
        if not self._is_scanning:
            return
        with self._frame_lock:
            frame = self._cur_frame
        if frame is not None:
            frame = frame.copy()
            h, w  = frame.shape[:2]
            count = len(self._embeddings)
            bar_w = int(w * count / REG_SAMPLES)
            cv2.rectangle(frame, (0, h - 10), (bar_w, h), (0, 200, 80), -1)
            cv2.putText(frame, f"{count}/{REG_SAMPLES}",
                        (w - 120, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 100), 2)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = ctk.CTkImage(
                light_image=Image.fromarray(rgb),
                dark_image =Image.fromarray(rgb),
                size=(680, 440))
            self.lbl_cam.configure(image=img, text="")
        self.after(15, self._display_loop)

    def _finish(self):
        self._is_scanning = False
        self._stop_event.set()
        if self._cap:
            self._cap.release()
            self._cap = None

        if not self._embeddings:
            self.lbl_hint.configure(text="❌ Không thu được mẫu nào!", text_color="red")
            self.btn_start.configure(state="normal", text="▶  THỬ LẠI", fg_color="green")
            self.entry_name.configure(state="normal")
            self.entry_role.configure(state="normal")
            return

        mean_emb = np.mean(self._embeddings, axis=0).astype(np.float32)
        norm     = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb /= norm

        self.prog_bar.set(1.0)
        self.lbl_prog.configure(text="✅ HOÀN TẤT!", text_color="lime")
        self.lbl_hint.configure(
            text=f"Đã lưu {len(self._embeddings)} mẫu — [{self._reg_role}]",
            text_color="lime")

        self._on_done(self._reg_name, self._reg_role, mean_emb)
        self.after(1400, self.destroy)

    def _on_close(self):
        self._is_scanning = False
        self._stop_event.set()
        if self._cap:
            self._cap.release()
        self.destroy()
