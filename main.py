from __future__ import annotations
import csv, os, pickle
import cv2, numpy as np
import customtkinter as ctk
from PIL import Image
from datetime import datetime

from config import DB_PATH, LOG_PATH, CAM_DISPLAY
from recognizer import FaceRecognizer
from attendance import AttendanceLogger
from ui_register import RegisterWindow

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Bảng màu
BG     = "#0d0d1a"
PANEL  = "#111827"
CARD   = "#1a2035"
BLUE   = "#3b82f6"
GREEN  = "#10b981"
RED    = "#ef4444"
ORANGE = "#f59e0b"
DIM    = "#6b7280"

class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("HỆ THỐNG CHẤM CÔNG AI")
        self.geometry("1280x780")
        self.minsize(1100, 680)
        self.configure(fg_color=BG)

        self.db   = self._load_db()
        self.rec  = FaceRecognizer()
        self.log  = AttendanceLogger()

        self._bbox      = None
        self._bcolor    = (100, 100, 100)
        self._blabel    = ""
        self._log_today: list[dict] = []
        self._log_dirty = False

        self._build_ui()
        self.btn_cam.configure(state="disabled", text="⏳ ĐANG TẢI...", fg_color="#374151")
        self.btn_reg.configure(state="disabled", fg_color="#374151")
        self._status("Đang nạp mô hình AI...", ORANGE)
        self.after(200, self._init)
        self.after(1000, self._tick)

    # ── Khởi tạo AI ──────────────────────────────────────────────────────

     def _init(self):
        try:
            self.rec.load_model()
            self.rec.set_db(self.db)
            self.btn_cam.configure(state="normal", text="▶  BẬT CAMERA", fg_color=GREEN, hover_color="#059669")
            self.btn_reg.configure(state="normal", fg_color=BLUE, hover_color="#2563eb")
            self._status("Sẵn sàng", GREEN)
            self._load_today_log()
        except Exception as e:
            self._status(f"Lỗi: {e}", RED)

    def _tick(self):
        now = datetime.now()
        self.lbl_clock.configure(text=now.strftime("%H:%M:%S"))
        self.lbl_date.configure(text=now.strftime("%A, %d/%m/%Y"))
        self.after(1000, self._tick)

    # -- Vòng lặp UI --

    def _loop(self):
        if not self.rec.is_running:
            return

        frame = self.rec.get_frame()
        if frame is not None:
            frame = frame.copy()
            result = self.rec.get_result()
            if result:
                self._handle(result)
            if self._bbox:
                x1,y1,x2,y2 = self._bbox
                cv2.rectangle(frame, (x1,y1), (x2,y2), self._bcolor, 2)
                if self._blabel:
                    (tw,th),_ = cv2.getTextSize(self._blabel, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                    cv2.rectangle(frame, (x1, max(0,y1-th-14)), (x1+tw+10, y1), self._bcolor, -1)
                    cv2.putText(frame, self._blabel, (x1+5, y1-5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = ctk.CTkImage(light_image=Image.fromarray(rgb),
                               dark_image=Image.fromarray(rgb), size=CAM_DISPLAY)
            self.lbl_cam.configure(image=img, text="")

        # Luôn schedule kể cả khi frame=None
        self.after(15, self._loop)

    def _handle(self, r: dict):
        s = r.get("status")

        if s == "no_face":
            self._bbox = None
            self.lbl_result.configure(text="---", text_color=DIM)
            self.lbl_hint.configure(text=r.get("msg",""), text_color=DIM)

        elif s == "liveness":
            self._bbox, self._bcolor, self._blabel = r["bbox"], (0,165,255), r["msg"]
            self.lbl_result.configure(text="Đang xác thực...", text_color=ORANGE)
            self.lbl_hint.configure(text=r["msg"], text_color=ORANGE)

        elif s == "empty_db":
            self._bbox, self._bcolor, self._blabel = r["bbox"], (0,215,255), "Chua co NV"
            self.lbl_result.configure(text="Chưa có nhân viên!", text_color=ORANGE)
            self.after(200, self.rec.reset_liveness)

        elif s == "recognized":
            name, conf, role = r["name"], r["confidence"], r.get("role","")
            self._bbox = r["bbox"]
            self._bcolor = (16,185,129)
            self._blabel = f"{name} ({conf}%)"
            entry = self.log.try_log(name, conf, role)
            if entry:
                icon  = "✅ VÀO" if entry["event"]=="CHECK_IN" else "🚪 RA"
                color = GREEN if entry["event"]=="CHECK_IN" else ORANGE
                label = f"{icon}\n{name}" + (f"\n[{role}]" if role else "")
                self.lbl_result.configure(text=label, text_color=color)
                self._status(f"{icon}  {name}  {entry['time']}", color)
                self.lbl_hint.configure(text="", text_color="white")
                self._log_today.insert(0, {**entry, "role": role})
                if not self._log_dirty:
                    self._log_dirty = True
                    self.after(80, self._refresh_log)
            else:
                self.lbl_result.configure(text=f"✅ {name}", text_color=GREEN)
            self.after(300, self.rec.reset_liveness)

        elif s == "unknown":
            self._bbox, self._bcolor, self._blabel = r["bbox"], (239,68,68), "Nguoi la"
            self.lbl_result.configure(text="❌ Không nhận ra", text_color=RED)
            self.after(500, self.rec.reset_liveness)

    # -- Camera --

    def _toggle_cam(self):
        if not self.rec.is_running:
            if not self.rec.start_camera():
                self._status("❌ Không tìm thấy Camera!", RED); return
            self._bbox = None
            self.btn_cam.configure(text="⏹  TẮT CAMERA", fg_color=RED, hover_color="#b91c1c")
            self._indicator.configure(text="● ĐANG HOẠT ĐỘNG", text_color=GREEN)
            self._status("Camera đang hoạt động", GREEN)
            self.lbl_result.configure(text="Nhuc nhich dau de cham cong", text_color=BLUE)
            self._loop()
        else:
            self.rec.stop_camera()
            self._bbox = None
            self.btn_cam.configure(text="▶  BẬT CAMERA", fg_color=GREEN, hover_color="#059669")
            self._indicator.configure(text="● ĐÃ TẮT", text_color=DIM)
            self._status("Camera đã tắt", DIM)
            self.lbl_cam.configure(image=None,
                text="📷\n\nHệ thống đang tắt\nBấm  ▶ BẬT CAMERA  để bắt đầu")

    # -- Đăng ký --

    def _open_register(self):
        was = self.rec.is_running
        if was: self.rec.is_running = False

        def done(name, role, dept, emb):
            self.db[name] = {"emb": emb, "role": role, "dept": dept}
            self._save_db()
            self.rec.set_db(self.db)
            self._status(f"✅ Đã thêm: {name} [{role}]", GREEN)
            self.lbl_emp.configure(text=str(len(self.db)))
            if was:
                self.rec.is_running = True
                self._status("Camera đang hoạt động", GREEN)

        RegisterWindow(self, self.rec._app, list(self.db.keys()), done)


    # ── Danh sách nhân viên ──────────────────────────────────────────────

    def _open_employee_list(self):
        win = ctk.CTkToplevel(self)
        win.title("DANH SÁCH NHÂN VIÊN")
        win.geometry("500x600")
        win.resizable(False, False)
        win.grab_set()
        win.configure(fg_color=C_PANEL)

        ctk.CTkLabel(win, text="👥  DANH SÁCH NHÂN VIÊN",
                     font=("Arial", 18, "bold"), text_color="white").pack(pady=(18, 2))

        # Thống kê theo chức vụ
        roles = {}
        for nm, val in self.db.items():
            r = val["role"] if isinstance(val, dict) else "Chưa phân loại"
            roles[r] = roles.get(r, 0) + 1
        role_str = "  |  ".join(f"{r}: {c}" for r, c in roles.items())
        ctk.CTkLabel(win, text=role_str or "Chưa có nhân viên",
                     font=("Arial", 11), text_color=C_ACCENT).pack(pady=(0, 10))

        # Bộ lọc chức vụ
        all_roles = ["Tất cả"] + sorted(set(
            (v["role"] if isinstance(v, dict) else "Chưa phân loại")
            for v in self.db.values()
        ))
        filter_var = ctk.StringVar(value="Tất cả")

        filter_row = ctk.CTkFrame(win, fg_color="transparent")
        filter_row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(filter_row, text="Lọc:", font=("Arial", 12),
                     text_color=C_DIM).pack(side="left")
        filter_menu = ctk.CTkOptionMenu(
            filter_row, values=all_roles, variable=filter_var,
            width=180, fg_color=C_CARD, button_color=C_ACCENT,
            command=lambda _: rebuild_list())
        filter_menu.pack(side="left", padx=8)

        scroll   = ctk.CTkScrollableFrame(win, fg_color=C_CARD,
                                          height=360, corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        selected = {"name": None}
        btn_refs = {}

        def select(n: str):
            selected["name"] = n
            for k, b in btn_refs.items():
                b.configure(fg_color=C_ACCENT if k == n else C_PANEL)
            lbl_sel.configure(text=f"Đã chọn: {n}", text_color="cyan")

        def rebuild_list():
            for w in scroll.winfo_children():
                w.destroy()
            btn_refs.clear()
            chosen_role = filter_var.get()
            filtered = {
                nm: val for nm, val in self.db.items()
                if chosen_role == "Tất cả" or
                   (val["role"] if isinstance(val, dict) else "Chưa phân loại") == chosen_role
            }
            if not filtered:
                ctk.CTkLabel(scroll, text="Không có nhân viên.",
                             text_color=C_DIM, font=("Arial", 12)).pack(pady=20)
                return
            for i, (nm, val) in enumerate(sorted(filtered.items())):
                role = val["role"] if isinstance(val, dict) else "?"
                row  = ctk.CTkFrame(scroll, fg_color=C_PANEL, corner_radius=8, height=46)
                row.pack(fill="x", pady=3, padx=4)
                row.pack_propagate(False)
                b = ctk.CTkButton(
                    row, text=f"  {i+1:02d}.  👤  {nm}",
                    font=("Arial", 13), fg_color="transparent",
                    hover_color=C_ACCENT, anchor="w",
                    command=lambda n=nm: select(n))
                b.pack(side="left", fill="both", expand=True)
                ctk.CTkLabel(row, text=role, font=("Arial", 11),
                             text_color=C_ACCENT, width=110).pack(side="right", padx=10)
                btn_refs[nm] = b

        rebuild_list()

        lbl_sel = ctk.CTkLabel(win, text="Chưa chọn ai",
                               font=("Arial", 12), text_color=C_DIM)
        lbl_sel.pack(pady=(0, 6))

        def do_delete():
            nm = selected["name"]
            if not nm:
                lbl_sel.configure(text="⚠ Hãy chọn 1 nhân viên!", text_color=C_ORANGE)
                return
            dlg = ctk.CTkInputDialog(
                text=f"Nhập tên '{nm}' để xác nhận xóa:",
                title="Xác nhận xóa")
            val = dlg.get_input()
            if val and val.strip() == nm:
                del self.db[nm]
                self._save_db()
                self.recognizer.set_db(self.db)
                self._set_status(f"Đã xóa: {nm}", C_ORANGE)
                self._refresh_employee_count()
                win.destroy()
            else:
                lbl_sel.configure(text="❌ Tên không khớp.", text_color=C_RED)

        ctk.CTkButton(
            win, text="🗑  XÓA NHÂN VIÊN ĐÃ CHỌN", height=42,
            font=("Arial", 13, "bold"), fg_color="#7a2020", hover_color="#9a3030",
            command=do_delete
        ).pack(fill="x", padx=18, pady=(0, 16))

    # ── Log ──────────────────────────────────────────────────────────────

    def _open_log(self):
        if not os.path.exists(LOG_PATH):
            self._set_status("Chưa có log nào.", C_ORANGE)
            return
        try:
            os.startfile(LOG_PATH)
        except AttributeError:
            os.system(f"xdg-open '{LOG_PATH}'")

    def _refresh_today_log(self):
        today = datetime.now().date().isoformat()
        self._today_log = []
        if not os.path.exists(LOG_PATH):
            self._refresh_log_panel()
            return
        try:
            with open(LOG_PATH, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    try:
                        d = datetime.strptime(
                            row["Thoi gian"], "%d/%m/%Y %H:%M:%S"
                        ).date().isoformat()
                        if d == today:
                            self._today_log.append({
                                "name":  row["Ten"],
                                "event": row.get("Su kien", "CHECK_IN"),
                                "time":  row["Thoi gian"],
                                "role":  row.get("Chuc vu", ""),
                            })
                    except Exception:
                        pass
        except Exception:
            pass
        self._today_log.reverse()
        self._refresh_log_panel()
        self.lbl_today_count.configure(text=str(len(self._today_log)))

    def _refresh_log_panel(self):
        for w in self.log_scroll.winfo_children():
            w.destroy()
        if not self._today_log:
            ctk.CTkLabel(self.log_scroll, text="Chưa có dữ liệu hôm nay",
                         font=("Arial", 11), text_color=C_DIM).pack(pady=16)
            return
        for entry in self._today_log[:40]:
            event    = entry.get("event", "")
            icon     = "↗" if event == "CHECK_IN" else "↙"
            color    = C_GREEN if event == "CHECK_IN" else C_ORANGE
            time_only = entry["time"].split(" ")[1] if " " in entry["time"] else entry["time"]
            role     = entry.get("role", "")

            row_f = ctk.CTkFrame(self.log_scroll, fg_color=C_PANEL,
                                 corner_radius=6, height=40)
            row_f.pack(fill="x", pady=2, padx=4)
            row_f.pack_propagate(False)

            ctk.CTkLabel(row_f, text=icon,
                         font=("Arial", 14, "bold"),
                         text_color=color, width=22).pack(side="left", padx=(8, 2))
            name_col = ctk.CTkFrame(row_f, fg_color="transparent")
            name_col.pack(side="left", fill="both", expand=True)
            ctk.CTkLabel(name_col, text=entry["name"],
                         font=("Arial", 11, "bold"),
                         text_color="white", anchor="w").pack(fill="x")
            if role:
                ctk.CTkLabel(name_col, text=role,
                             font=("Arial", 9), text_color=C_ACCENT,
                             anchor="w").pack(fill="x")
            ctk.CTkLabel(row_f, text=time_only,
                         font=("Arial", 11), text_color=C_DIM,
                         width=58).pack(side="right", padx=8)

    def _refresh_employee_count(self):
        self.lbl_emp_count.configure(text=str(len(self.db)))

    # ── Helpers ──────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str):
        self.lbl_status.configure(text=text, text_color=color)

    def _load_db(self) -> dict:
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "rb") as f:
                    data = pickle.load(f)
                # Migration: nếu DB cũ (chỉ lưu embedding), tự động nâng cấp
                migrated = {}
                for k, v in data.items():
                    if isinstance(v, np.ndarray):
                        migrated[k] = {"emb": v, "role": "Chưa phân loại"}
                    else:
                        migrated[k] = v
                return migrated
            except Exception:
                pass
        return {}

    def _save_db(self):
        with open(DB_PATH, "wb") as f:
            pickle.dump(self.db, f)

    # ══════════════════════════════════════════════════════════════════════
    # UI SETUP
    # ══════════════════════════════════════════════════════════════════════

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # ── HEADER ───────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=64)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        logo_f = ctk.CTkFrame(header, fg_color="transparent")
        logo_f.grid(row=0, column=0, padx=20, pady=8, sticky="w")
        ctk.CTkLabel(logo_f, text="⬡", font=("Arial", 28),
                     text_color=C_ACCENT).pack(side="left", padx=(0, 8))
        t_col = ctk.CTkFrame(logo_f, fg_color="transparent")
        t_col.pack(side="left")
        ctk.CTkLabel(t_col, text="HỆ THỐNG CHẤM CÔNG AI",
                     font=("Arial", 16, "bold"), text_color="white").pack(anchor="w")
        ctk.CTkLabel(t_col, text="Face Recognition Attendance System",
                     font=("Arial", 10), text_color=C_DIM).pack(anchor="w")

        self._indicator = ctk.CTkLabel(header, text="● ĐÃ TẮT",
                                       font=("Arial", 12, "bold"), text_color=C_DIM)
        self._indicator.grid(row=0, column=1)

        clk_f = ctk.CTkFrame(header, fg_color="transparent")
        clk_f.grid(row=0, column=2, padx=20, sticky="e")
        self.lbl_clock = ctk.CTkLabel(clk_f, text="00:00:00",
                                      font=("Arial", 22, "bold"), text_color=C_ACCENT)
        self.lbl_clock.pack()
        self.lbl_date = ctk.CTkLabel(clk_f, text="",
                                     font=("Arial", 10), text_color=C_DIM)
        self.lbl_date.pack()

        # ── BODY ─────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=12)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=0)
        body.grid_rowconfigure(0, weight=1)

        # ── CAMERA ───────────────────────────────────────────────────────
        cam_wrap = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=16)
        cam_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cam_wrap.grid_rowconfigure(1, weight=1)
        cam_wrap.grid_columnconfigure(0, weight=1)

        cam_top = ctk.CTkFrame(cam_wrap, fg_color=C_CARD, corner_radius=0, height=38)
        cam_top.grid(row=0, column=0, sticky="ew")
        cam_top.grid_propagate(False)
        ctk.CTkLabel(cam_top, text="  📷  CAMERA NHẬN DIỆN",
                     font=("Arial", 12, "bold"), text_color=C_DIM).pack(
                         side="left", padx=12, pady=8)

        self.video_label = ctk.CTkLabel(
            cam_wrap,
            text="📷\n\nHệ thống đang tắt\nBấm  ▶ BẬT CAMERA  để bắt đầu",
            font=("Arial", 16), text_color=C_DIM)
        self.video_label.grid(row=1, column=0, padx=12, pady=12, sticky="nsew")

        self.lbl_live_hint = ctk.CTkLabel(
            cam_wrap, text="", font=("Arial", 13), text_color=C_ORANGE)
        self.lbl_live_hint.grid(row=2, column=0, pady=(0, 10))

        # ── PANEL PHẢI ───────────────────────────────────────────────────
        right = ctk.CTkFrame(body, fg_color="transparent", width=305)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        # Card kết quả
        res_card = ctk.CTkFrame(right, fg_color=C_CARD, corner_radius=14)
        res_card.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(res_card, text="KẾT QUẢ NHẬN DIỆN",
                     font=("Arial", 10, "bold"), text_color=C_DIM).pack(pady=(12, 2))
        self.lbl_result = ctk.CTkLabel(
            res_card, text="---",
            font=("Arial", 20, "bold"), text_color="white",
            wraplength=280, justify="center")
        self.lbl_result.pack(pady=(2, 2))
        self.lbl_status = ctk.CTkLabel(
            res_card, text="Đang tải...",
            font=("Arial", 11), text_color=C_DIM, wraplength=280)
        self.lbl_status.pack(pady=(2, 12))

        # Card thống kê
        stat_card = ctk.CTkFrame(right, fg_color=C_CARD, corner_radius=14)
        stat_card.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        stat_card.grid_columnconfigure((0, 1), weight=1)

        def make_stat(parent, label, col):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.grid(row=0, column=col, padx=6, pady=10, sticky="ew")
            lbl = ctk.CTkLabel(f, text="0",
                               font=("Arial", 24, "bold"), text_color=C_ACCENT)
            lbl.pack()
            ctk.CTkLabel(f, text=label, font=("Arial", 10),
                         text_color=C_DIM).pack()
            return lbl

        self.lbl_emp_count   = make_stat(stat_card, "Nhân viên", 0)
        self.lbl_today_count = make_stat(stat_card, "Lượt hôm nay", 1)
        self.lbl_emp_count.configure(text=str(len(self.db)))

        # Card điều khiển
        ctrl_card = ctk.CTkFrame(right, fg_color=C_CARD, corner_radius=14)
        ctrl_card.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(ctrl_card, text="ĐIỀU KHIỂN",
                     font=("Arial", 10, "bold"), text_color=C_DIM).pack(pady=(10, 4))

        self.btn_power = ctk.CTkButton(
            ctrl_card, text="▶  BẬT CAMERA", height=44,
            command=self._toggle_camera,
            font=("Arial", 13, "bold"),
            fg_color=C_GREEN, hover_color="#059669", corner_radius=10)
        self.btn_power.pack(fill="x", padx=12, pady=3)

        self.btn_register = ctk.CTkButton(
            ctrl_card, text="➕  ĐĂNG KÝ NHÂN VIÊN", height=38,
            command=self._open_register,
            font=("Arial", 12), fg_color=C_ACCENT,
            hover_color="#2563eb", corner_radius=10)
        self.btn_register.pack(fill="x", padx=12, pady=3)

        ctk.CTkButton(
            ctrl_card, text="👥  DANH SÁCH NHÂN VIÊN", height=34,
            command=self._open_employee_list,
            font=("Arial", 11), fg_color=C_PANEL,
            hover_color=C_CARD, corner_radius=10,
            border_width=1, border_color=C_BORDER
        ).pack(fill="x", padx=12, pady=3)

        ctk.CTkButton(
            ctrl_card, text="📋  XEM LOG CHẤM CÔNG", height=34,
            command=self._open_log,
            font=("Arial", 11), fg_color=C_PANEL,
            hover_color=C_CARD, corner_radius=10,
            border_width=1, border_color=C_BORDER
        ).pack(fill="x", padx=12, pady=(3, 12))

        # Panel log hôm nay
        log_panel = ctk.CTkFrame(right, fg_color=C_CARD, corner_radius=14)
        log_panel.grid(row=3, column=0, sticky="nsew")
        log_panel.grid_rowconfigure(1, weight=1)
        log_panel.grid_columnconfigure(0, weight=1)

        log_top = ctk.CTkFrame(log_panel, fg_color="transparent")
        log_top.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(log_top, text="HOẠT ĐỘNG HÔM NAY",
                     font=("Arial", 10, "bold"), text_color=C_DIM).pack(side="left")
        ctk.CTkButton(
            log_top, text="↺", width=28, height=24,
            font=("Arial", 12), fg_color=C_PANEL,
            command=self._refresh_today_log
        ).pack(side="right")

        self.log_scroll = ctk.CTkScrollableFrame(
            log_panel, fg_color="transparent", corner_radius=0)
        self.log_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))


if __name__ == "__main__":
    app = AttendanceApp()
    app.mainloop()
