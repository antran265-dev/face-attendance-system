from __future__ import annotations
import csv, os
import cv2, numpy as np
import customtkinter as ctk
from PIL import Image
from datetime import datetime

from config import CAM_DISPLAY
from recognizer import FaceRecognizer
from attendance import AttendanceLogger
from ui_register import RegisterWindow
from models import init_db
from db_repository import (
    add_employee, delete_employee, get_all_employees,
    get_employee_count, get_today_all_logs, get_logs_by_date_range,
)

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

        init_db()                          # tạo file database.db nếu chưa có
        self.db   = get_all_employees()    # nạp cache từ DB vào RAM (giống cũ)
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

    # -- Khởi tạo --

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
            try:
                ok = add_employee(name, role, dept, emb)   # ghi vào DB ngay
                if not ok:
                    self._status(f"❌ Tên '{name}' đã tồn tại trong DB!", RED)
                    return
                self.db[name] = {"emb": emb, "role": role, "dept": dept}   # cập nhật cache RAM
                self.rec.set_db(self.db)
                self._status(f"✅ Đã thêm: {name} [{role}]", GREEN)
                self.lbl_emp.configure(text=str(len(self.db)))
            except Exception as e:
                import traceback
                print("❌ LỖI khi lưu nhân viên vào DB:")
                traceback.print_exc()
                self._status(f"❌ Lỗi lưu DB: {e}", RED)
            finally:
                if was:
                    self.rec.is_running = True
                    self._status("Camera đang hoạt động", GREEN)

        RegisterWindow(self, self.rec._app, list(self.db.keys()), done)

    # -- Danh sách nhân viên --

    def _open_list(self):
        win = ctk.CTkToplevel(self)
        win.title("DANH SÁCH NHÂN VIÊN")
        win.geometry("500x600")
        win.resizable(False, False)
        win.grab_set()
        win.configure(fg_color=PANEL)

        ctk.CTkLabel(win, text="👥  DANH SÁCH NHÂN VIÊN",
                     font=("Arial", 18, "bold")).pack(pady=(16, 2))
        ctk.CTkLabel(win, text=f"Tổng: {len(self.db)} nhân viên",
                     font=("Arial", 12), text_color=DIM).pack(pady=(0, 8))

        # Bộ lọc theo chức vụ
        filter_frame = ctk.CTkFrame(win, fg_color="transparent")
        filter_frame.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(filter_frame, text="Lọc:", font=("Arial", 12)).pack(side="left")

        from config import ROLE_OPTIONS
        filter_var = ctk.StringVar(value="Tất cả")
        scroll = ctk.CTkScrollableFrame(win, fg_color=CARD, height=380, corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        def refresh_list(choice="Tất cả"):
            for w in scroll.winfo_children(): w.destroy()
            items = [(n, v) for n, v in sorted(self.db.items())
                     if choice == "Tất cả" or
                     (isinstance(v, dict) and v.get("role","") == choice)]
            if not items:
                ctk.CTkLabel(scroll, text="Không có nhân viên nào.",
                             text_color=DIM, font=("Arial", 13)).pack(pady=20); return
            for i, (nm, v) in enumerate(items):
                role = v.get("role","") if isinstance(v, dict) else ""
                dept = v.get("dept","") if isinstance(v, dict) else ""
                tag  = f"  {i+1:02d}.  👤  {nm}"
                if role: tag += f"  —  {role}"
                b = ctk.CTkButton(scroll, text=tag, height=42, font=("Arial", 12),
                                  fg_color=PANEL, hover_color=BLUE, anchor="w",
                                  command=lambda n=nm: selected.update({"name": n})
                                      or lbl_sel.configure(text=f"Đã chọn: {n}", text_color="cyan")
                                      or [bx.configure(fg_color=BLUE if bx.cget("text").strip().endswith(n) or n in bx.cget("text") else PANEL) for bx in scroll.winfo_children() if isinstance(bx, ctk.CTkButton)])
                b.pack(fill="x", pady=2, padx=4)

        ctk.CTkOptionMenu(filter_frame, values=["Tất cả"] + ROLE_OPTIONS,
                          width=200, command=refresh_list).pack(side="left", padx=8)
        selected = {"name": None}
        lbl_sel = ctk.CTkLabel(win, text="Chưa chọn ai", font=("Arial", 12), text_color=DIM)
        lbl_sel.pack(pady=(0, 6))

        def do_delete():
            nm = selected["name"]
            if not nm: lbl_sel.configure(text="⚠ Chọn 1 nhân viên trước!", text_color=ORANGE); return
            dlg = ctk.CTkInputDialog(text=f"Nhập tên '{nm}' để xác nhận:", title="Xóa nhân viên")
            if dlg.get_input() and dlg.get_input().strip() == nm:
                delete_employee(nm)               # xóa khỏi DB
                del self.db[nm]                    # xóa khỏi cache RAM
                self.rec.set_db(self.db)
                self._status(f"Đã xóa: {nm}", ORANGE)
                self.lbl_emp.configure(text=str(len(self.db)))
                win.destroy()
            else:
                lbl_sel.configure(text="❌ Tên không khớp.", text_color=RED)

        ctk.CTkButton(win, text="🗑  XÓA NHÂN VIÊN ĐÃ CHỌN", height=44,
                      font=("Arial", 13, "bold"), fg_color="#7a2020", hover_color="#9a3030",
                      command=do_delete).pack(fill="x", padx=16, pady=(0, 16))
        refresh_list()

    # -- Log --

    def _open_log(self):
        """
        Xuất toàn bộ log từ Database ra file CSV (vì giờ dữ liệu nằm trong DB,
        không còn ghi trực tiếp vào CSV nữa), rồi mở file đó lên cho người dùng xem.
        """
        from datetime import datetime as _dt
        logs = get_logs_by_date_range(_dt(2000, 1, 1), _dt(2100, 1, 1))   # lấy toàn bộ

        if not logs:
            self._status("Chưa có log chấm công nào trong DB.", ORANGE)
            return

        export_path = os.path.join("database", "attendance_export.csv")
        try:
            with open(export_path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Ten", "Chuc vu", "Phong ban", "Su kien", "Thoi gian", "Do chinh xac (%)"])
                for l in logs:
                    w.writerow([
                        l["name"], l["role"], l["dept"], l["event"],
                        l["timestamp"].strftime("%d/%m/%Y %H:%M:%S"), l["confidence"]
                    ])
        except Exception as e:
            self._status(f"❌ Lỗi xuất log: {e}", RED)
            return

        self._status(f"Đã xuất {len(logs)} dòng log → {export_path}", GREEN)
        try:
            os.startfile(export_path)
        except AttributeError:
            os.system(f"xdg-open '{export_path}'")

    def _load_today_log(self):
        """Đọc log hôm nay từ Database thay vì file CSV."""
        self._log_today = get_today_all_logs()    # đã sắp xếp mới nhất trước, có sẵn name/role/event/time
        self._refresh_log()

    def _refresh_log(self):
        self._log_dirty = False
        for w in self.log_scroll.winfo_children(): w.destroy()
        count = len(self._log_today)
        self.lbl_today.configure(text=str(count))
        if not self._log_today:
            ctk.CTkLabel(self.log_scroll, text="Chưa có dữ liệu hôm nay",
                         font=("Arial", 11), text_color=DIM).pack(pady=16); return
        for e in self._log_today[:40]:
            is_in  = e.get("event") == "CHECK_IN"
            color  = GREEN if is_in else ORANGE
            icon   = "↗" if is_in else "↙"
            t_only = e["time"].split(" ")[1] if " " in e["time"] else e["time"]
            row = ctk.CTkFrame(self.log_scroll, fg_color=PANEL, corner_radius=6, height=36)
            row.pack(fill="x", pady=2, padx=4)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=icon, font=("Arial", 14, "bold"),
                         text_color=color, width=24).pack(side="left", padx=(8,4))
            ctk.CTkLabel(row, text=e["name"], font=("Arial", 11, "bold"),
                         text_color="white", anchor="w").pack(side="left", expand=True, fill="x")
            ctk.CTkLabel(row, text=t_only, font=("Arial", 11),
                         text_color=DIM, width=60).pack(side="right", padx=8)

    # -- Helpers --

    def _status(self, text, color): self.lbl_status.configure(text=text, text_color=color)

    # -- Build UI --

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=64)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkFrame(hdr, fg_color="transparent")
        logo.grid(row=0, column=0, padx=24, pady=8, sticky="w")
        ctk.CTkLabel(logo, text="⬡", font=("Arial", 28), text_color=BLUE).pack(side="left", padx=(0,8))
        col = ctk.CTkFrame(logo, fg_color="transparent")
        col.pack(side="left")
        ctk.CTkLabel(col, text="HỆ THỐNG CHẤM CÔNG AI",
                     font=("Arial", 16, "bold"), text_color="white").pack(anchor="w")
        ctk.CTkLabel(col, text="Face Recognition Attendance",
                     font=("Arial", 10), text_color=DIM).pack(anchor="w")

        self._indicator = ctk.CTkLabel(hdr, text="● ĐÃ TẮT",
                                       font=("Arial", 12, "bold"), text_color=DIM)
        self._indicator.grid(row=0, column=1)

        clk = ctk.CTkFrame(hdr, fg_color="transparent")
        clk.grid(row=0, column=2, padx=24, sticky="e")
        self.lbl_clock = ctk.CTkLabel(clk, text="00:00:00",
                                      font=("Arial", 22, "bold"), text_color=BLUE)
        self.lbl_clock.pack()
        self.lbl_date = ctk.CTkLabel(clk, text="", font=("Arial", 10), text_color=DIM)
        self.lbl_date.pack()

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=12)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=0)
        body.grid_rowconfigure(0, weight=1)

        # Camera
        cam_wrap = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=16)
        cam_wrap.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        cam_wrap.grid_rowconfigure(1, weight=1)
        cam_wrap.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(cam_wrap, fg_color=CARD, corner_radius=0, height=38)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_propagate(False)
        ctk.CTkLabel(top_bar, text="  📷  CAMERA NHẬN DIỆN",
                     font=("Arial", 12, "bold"), text_color=DIM).pack(side="left", padx=12, pady=8)

        self.lbl_cam = ctk.CTkLabel(cam_wrap,
            text="📷\n\nHệ thống đang tắt\nBấm  ▶ BẬT CAMERA  để bắt đầu",
            font=("Arial", 16), text_color=DIM)
        self.lbl_cam.grid(row=1, column=0, padx=12, pady=12, sticky="nsew")

        self.lbl_hint = ctk.CTkLabel(cam_wrap, text="", font=("Arial", 13), text_color=ORANGE)
        self.lbl_hint.grid(row=2, column=0, pady=(0, 10))

        # Panel phải
        right = ctk.CTkFrame(body, fg_color="transparent", width=300)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        # Card kết quả
        rc = ctk.CTkFrame(right, fg_color=CARD, corner_radius=14)
        rc.grid(row=0, column=0, sticky="ew", pady=(0,8))
        ctk.CTkLabel(rc, text="KẾT QUẢ NHẬN DIỆN",
                     font=("Arial", 10, "bold"), text_color=DIM).pack(pady=(14,2))
        self.lbl_result = ctk.CTkLabel(rc, text="---",
                                       font=("Arial", 21, "bold"), text_color="white",
                                       wraplength=270, justify="center")
        self.lbl_result.pack(pady=(4,2))
        self.lbl_status = ctk.CTkLabel(rc, text="Đang tải...",
                                       font=("Arial", 11), text_color=DIM, wraplength=270)
        self.lbl_status.pack(pady=(2,14))

        # Card thống kê
        sc = ctk.CTkFrame(right, fg_color=CARD, corner_radius=14)
        sc.grid(row=1, column=0, sticky="ew", pady=(0,8))
        sc.grid_columnconfigure((0,1), weight=1)

        def stat(parent, label, col):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.grid(row=0, column=col, padx=8, pady=12, sticky="ew")
            lbl = ctk.CTkLabel(f, text="0", font=("Arial", 26, "bold"), text_color=BLUE)
            lbl.pack()
            ctk.CTkLabel(f, text=label, font=("Arial", 10), text_color=DIM).pack()
            return lbl

        self.lbl_emp   = stat(sc, "Nhân viên", 0)
        self.lbl_today = stat(sc, "Lượt hôm nay", 1)
        self.lbl_emp.configure(text=str(len(self.db)))

        # Card nút
        bc = ctk.CTkFrame(right, fg_color=CARD, corner_radius=14)
        bc.grid(row=2, column=0, sticky="ew", pady=(0,8))
        ctk.CTkLabel(bc, text="ĐIỀU KHIỂN",
                     font=("Arial", 10, "bold"), text_color=DIM).pack(pady=(12,6))

        self.btn_cam = ctk.CTkButton(bc, text="▶  BẬT CAMERA", height=46,
                                     command=self._toggle_cam,
                                     font=("Arial", 13, "bold"), corner_radius=10)
        self.btn_cam.pack(fill="x", padx=12, pady=4)

        self.btn_reg = ctk.CTkButton(bc, text="➕  ĐĂNG KÝ NHÂN VIÊN", height=40,
                                     command=self._open_register,
                                     font=("Arial", 12), fg_color=BLUE, corner_radius=10)
        self.btn_reg.pack(fill="x", padx=12, pady=4)

        for text, cmd in [("👥  DANH SÁCH NHÂN VIÊN", self._open_list),
                           ("📋  XEM LOG CHẤM CÔNG",   self._open_log)]:
            ctk.CTkButton(bc, text=text, height=36, command=cmd,
                          font=("Arial", 11), fg_color=PANEL, corner_radius=10,
                          border_width=1, border_color="#1e3a5f"
                          ).pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(bc, text="").pack(pady=2)   # padding bên dưới

        # Panel log hôm nay
        lp = ctk.CTkFrame(right, fg_color=CARD, corner_radius=14)
        lp.grid(row=3, column=0, sticky="nsew")
        lp.grid_rowconfigure(1, weight=1)
        lp.grid_columnconfigure(0, weight=1)

        lh = ctk.CTkFrame(lp, fg_color="transparent")
        lh.grid(row=0, column=0, sticky="ew", padx=12, pady=(12,4))
        ctk.CTkLabel(lh, text="HOẠT ĐỘNG HÔM NAY",
                     font=("Arial", 10, "bold"), text_color=DIM).pack(side="left")
        ctk.CTkButton(lh, text="↺", width=28, height=24,
                      font=("Arial", 12), fg_color=PANEL,
                      command=self._load_today_log).pack(side="right")

        self.log_scroll = ctk.CTkScrollableFrame(lp, fg_color="transparent", corner_radius=0)
        self.log_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0,12))


if __name__ == "__main__":
    app = App()
    app.mainloop()