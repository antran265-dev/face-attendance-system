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

    def _build_ui(self):
        ctk.CTkLabel(self, text="ĐĂNG KÝ NHÂN VIÊN MỚI",
                     font=("Arial", 20, "bold")).pack(pady=(16, 2))
        ctk.CTkLabel(self, text="Điền thông tin → Bắt đầu → Nhìn vào camera → Xoay đầu chậm",
                     font=("Arial", 12), text_color="gray").pack(pady=(0, 8))

        form = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=10)
        form.pack(fill="x", padx=24, pady=(0, 8))
        form.grid_columnconfigure(1, weight=1)

        def field(row, label, required=True):
            ctk.CTkLabel(form, text=label + (" ✱" if required else ""),
                         font=("Arial", 13, "bold" if required else "normal"),
                         text_color="white" if required else "#6b7280",
                         width=115, anchor="w").grid(row=row, column=0, padx=(16,8), pady=8, sticky="w")

        field(0, "Họ và tên")
        self.entry_name = ctk.CTkEntry(form, placeholder_text="Nguyễn Văn An",
                                       font=("Arial", 13), height=38)
        self.entry_name.grid(row=0, column=1, padx=(0,16), pady=8, sticky="ew")

        field(1, "Chức vụ")
        self.combo_role = ctk.CTkOptionMenu(form, values=ROLE_OPTIONS,
                                            font=("Arial", 13), height=38,
                                            fg_color="#2b2b2b", button_color="#3b82f6",
                                            dropdown_fg_color="#1e1e2e")
        self.combo_role.set(ROLE_OPTIONS[0])
        self.combo_role.grid(row=1, column=1, padx=(0,16), pady=8, sticky="ew")

        field(2, "Phòng ban", required=False)
        self.entry_dept = ctk.CTkEntry(form, placeholder_text="Sản xuất / IT / Kế toán...",
                                       font=("Arial", 13), height=36)
        self.entry_dept.grid(row=2, column=1, padx=(0,16), pady=(8,14), sticky="ew")

        cam = ctk.CTkFrame(self, corner_radius=12)
        cam.pack(padx=24, pady=4, fill="both", expand=True)
        self.lbl_cam = ctk.CTkLabel(cam, text="📷  Bấm BẮT ĐẦU ĐĂNG KÝ để mở camera",
                                    font=("Arial", 15), text_color="gray")
        self.lbl_cam.pack(expand=True, fill="both", padx=8, pady=8)

        prow = ctk.CTkFrame(self, fg_color="transparent")
        prow.pack(fill="x", padx=24, pady=(6,2))
        self.lbl_prog = ctk.CTkLabel(prow, text=f"0 / {REG_SAMPLES}",
                                     font=("Arial", 13), text_color="gray")
        self.lbl_prog.pack(side="left")
        self.lbl_hint = ctk.CTkLabel(prow, text="", font=("Arial", 13), text_color="cyan")
        self.lbl_hint.pack(side="right")

        self.bar = ctk.CTkProgressBar(self, height=14, corner_radius=6)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=24, pady=(0,8))

        brow = ctk.CTkFrame(self, fg_color="transparent")
        brow.pack(fill="x", padx=24, pady=(0,16))
        self.btn = ctk.CTkButton(brow, text="▶  BẮT ĐẦU ĐĂNG KÝ", height=46,
                                 font=("Arial", 15, "bold"), fg_color="green",
                                 hover_color="#059669", command=self._start)
        self.btn.pack(side="left", expand=True, fill="x", padx=(0,8))
        ctk.CTkButton(brow, text="✖  HỦY", height=46, font=("Arial", 14),
                      fg_color="#6b2020", hover_color="#8b3030",
                      command=self._close).pack(side="left", expand=True, fill="x")

    def _start(self):
        name = self.entry_name.get().strip()
        role = self.combo_role.get()
        dept = self.entry_dept.get().strip()

        if not name:
            self.lbl_hint.configure(text="⚠ Chưa nhập họ tên!", text_color="orange"); return
        if name in self._existing:
            self.lbl_hint.configure(text=f"⚠ '{name}' đã tồn tại!", text_color="orange"); return

        self._name, self._role, self._dept = name, role, dept
        self._embeds   = []
        self._scanning = True
        self._finishing= False
        self._stop.clear()

        for w in [self.entry_name, self.combo_role, self.entry_dept]:
            w.configure(state="disabled")
        self.btn.configure(state="disabled", text="⏳ Đang quét...", fg_color="gray")
        self.lbl_prog.configure(text=f"0 / {REG_SAMPLES}", text_color="white")
        self.bar.set(0)
        self.lbl_hint.configure(text="Nhìn thẳng vào camera", text_color="cyan")

        self._cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            self.lbl_hint.configure(text="❌ Không tìm thấy Camera!", text_color="red")
            self._scanning = False; return

        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        self._display()

    def _reader(self):
        while not self._stop.is_set():
            if self._cap and self._cap.isOpened():
                ret, f = self._cap.read()
                if ret:
                    with self._lock: self._frame = f
            time.sleep(0.01)

    def _worker(self):
        while self._scanning and len(self._embeds) < REG_SAMPLES:
            with self._lock: frame = self._frame
            if frame is None: time.sleep(0.05); continue
            try:
                faces = self._app.get(cv2.resize(frame, AI_INPUT_SIZE))
            except Exception: time.sleep(AI_INTERVAL); continue
            if faces:
                raw = faces[0].embedding
                n   = np.linalg.norm(raw)
                if n > 0:
                    self._embeds.append((raw/n).astype(np.float32))
                    self.after(0, self._update_bar, len(self._embeds))
            time.sleep(AI_INTERVAL)

        if self._scanning:
            self._finishing = True
            self._scanning  = False
            self.after(0, self._finish)

    def _update_bar(self, count):
        self.bar.set(count / REG_SAMPLES)
        self.lbl_prog.configure(text=f"{count} / {REG_SAMPLES}", text_color="white")
        hints = ["Nhìn thẳng vào camera", "Xoay đầu nhẹ trái / phải",
                 "Ngẩng / cúi đầu nhẹ", "Gần xong! Giữ nguyên..."]
        idx = min(int(count / REG_SAMPLES * 4), 3)
        self.lbl_hint.configure(text=hints[idx], text_color="lime" if idx == 3 else "cyan")

    def _display(self):
        if not self._scanning and not self._finishing: return
        with self._lock: frame = self._frame
        if frame is not None:
            f    = frame.copy()
            h, w = f.shape[:2]
            bw   = int(w * len(self._embeds) / REG_SAMPLES)
            cv2.rectangle(f, (0, h-10), (bw, h), (0, 200, 80), -1)
            cv2.putText(f, f"{len(self._embeds)}/{REG_SAMPLES}",
                        (w-120, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,220,100), 2)
            rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
            img = ctk.CTkImage(light_image=Image.fromarray(rgb),
                               dark_image=Image.fromarray(rgb), size=(700, 420))
            self.lbl_cam.configure(image=img, text="")
        self.after(15, self._display)

    def _finish(self):
        self._stop.set()
        if self._cap: self._cap.release(); self._cap = None

        if not self._embeds:
            self.lbl_hint.configure(text="❌ Không thu được mẫu!", text_color="red")
            self.btn.configure(state="normal", text="▶  THỬ LẠI", fg_color="green")
            for w in [self.entry_name, self.combo_role, self.entry_dept]:
                w.configure(state="normal")
            self._finishing = False; return

        emb  = np.mean(self._embeds, axis=0).astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0: emb /= norm

        self.bar.set(1.0)
        self.lbl_prog.configure(text=f"✅ HOÀN TẤT! ({REG_SAMPLES}/{REG_SAMPLES})",
                                text_color="lime")
        self.lbl_hint.configure(text=f"Đã lưu — {self._role}", text_color="lime")

        try:
            self._on_done(self._name, self._role, self._dept, emb)
        except Exception as e:
            import traceback
            print("❌ Lỗi trong callback on_done:")
            traceback.print_exc()
            self.lbl_hint.configure(text=f"❌ Lỗi lưu: {e}", text_color="red")
        finally:
            self._finishing = False
            self.after(1500, self.destroy)

    def _close(self):
        self._scanning = self._finishing = False
        self._stop.set()
        if self._cap: self._cap.release()
        self.destroy()
