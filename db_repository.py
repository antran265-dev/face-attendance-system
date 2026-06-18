from __future__ import annotations
"""
db_repository.py — Lớp trung gian giữa code cũ (main.py, recognizer.py, attendance.py)
và database mới (models.py).

Mục đích: các file khác chỉ cần gọi hàm Python bình thường,
không cần biết SQLAlchemy hay SQL là gì.

Đây là điểm thay thế cho:
    - pickle.load(faces.pkl)   -> get_all_employees()
    - pickle.dump(faces.pkl)   -> add_employee() / delete_employee()
    - csv ghi attendance_log   -> add_attendance_log()
    - csv đọc để tính CHECK_IN/OUT -> get_today_logs_for()
"""

import numpy as np
from datetime import datetime, date
from models import get_session, Employee, AttendanceLog, init_db


# ============================================================
# NHÂN VIÊN
# ============================================================

def add_employee(name: str, role: str, dept: str, embedding: np.ndarray) -> bool:
    """
    Thêm nhân viên mới vào DB.
    Trả False nếu tên đã tồn tại.
    """
    session = get_session()
    try:
        existing = session.query(Employee).filter_by(name=name).first()
        if existing:
            return False

        emp = Employee(name=name, role=role, dept=dept)
        emp.set_embedding(embedding)
        session.add(emp)
        session.commit()
        return True
    finally:
        session.close()


def delete_employee(name: str) -> bool:
    """Xóa nhân viên theo tên. Trả False nếu không tìm thấy."""
    session = get_session()
    try:
        emp = session.query(Employee).filter_by(name=name).first()
        if not emp:
            return False
        session.delete(emp)
        session.commit()
        return True
    finally:
        session.close()


def get_all_employees() -> dict:
    """
    Trả về dict giống cấu trúc cũ của faces.pkl để code cũ không cần đổi nhiều:
        {name: {"emb": np.ndarray, "role": str, "dept": str}}
    """
    session = get_session()
    try:
        employees = session.query(Employee).all()
        result = {}
        for emp in employees:
            result[emp.name] = {
                "emb":  emp.get_embedding(),
                "role": emp.role or "",
                "dept": emp.dept or "",
            }
        return result
    finally:
        session.close()


def get_employee_count() -> int:
    session = get_session()
    try:
        return session.query(Employee).count()
    finally:
        session.close()


# ============================================================
# CHẤM CÔNG
# ============================================================

def add_attendance_log(name: str, event_type: str, confidence: float) -> dict | None:
    """
    Ghi 1 lượt chấm công. Trả về dict thông tin nếu thành công, None nếu không tìm thấy nhân viên.
    """
    session = get_session()
    try:
        emp = session.query(Employee).filter_by(name=name).first()
        if not emp:
            return None

        log = AttendanceLog(
            employee_id=emp.id,
            event_type=event_type,
            confidence=confidence,
            timestamp=datetime.now()
        )
        session.add(log)
        session.commit()

        return {
            "name":  name,
            "event": event_type,
            "time":  log.timestamp.strftime("%d/%m/%Y %H:%M:%S"),
        }
    finally:
        session.close()


def get_today_logs_for(name: str) -> list[dict]:
    """
    Lấy toàn bộ log chấm công HÔM NAY của 1 người.
    Dùng để xác định CHECK_IN hay CHECK_OUT (thay thế đọc CSV cũ).
    """
    session = get_session()
    try:
        emp = session.query(Employee).filter_by(name=name).first()
        if not emp:
            return []

        today = date.today()
        logs = (session.query(AttendanceLog)
                .filter(AttendanceLog.employee_id == emp.id)
                .filter(AttendanceLog.timestamp >= datetime(today.year, today.month, today.day))
                .all())

        return [{"event": l.event_type, "time": l.timestamp} for l in logs]
    finally:
        session.close()


def get_today_all_logs() -> list[dict]:
    """
    Lấy toàn bộ log chấm công hôm nay của TẤT CẢ nhân viên.
    Dùng để hiển thị panel "Hoạt động hôm nay" trong main.py.
    """
    session = get_session()
    try:
        today = date.today()
        logs = (session.query(AttendanceLog, Employee)
                .join(Employee, AttendanceLog.employee_id == Employee.id)
                .filter(AttendanceLog.timestamp >= datetime(today.year, today.month, today.day))
                .order_by(AttendanceLog.timestamp.desc())
                .all())

        return [{
            "name":  emp.name,
            "role":  emp.role or "",
            "event": log.event_type,
            "time":  log.timestamp.strftime("%d/%m/%Y %H:%M:%S"),
        } for log, emp in logs]
    finally:
        session.close()


def get_logs_by_date_range(start: datetime, end: datetime) -> list[dict]:
    """
    Lấy log trong khoảng thời gian — dùng cho xuất báo cáo Excel theo tuần/tháng.
    """
    session = get_session()
    try:
        logs = (session.query(AttendanceLog, Employee)
                .join(Employee, AttendanceLog.employee_id == Employee.id)
                .filter(AttendanceLog.timestamp >= start)
                .filter(AttendanceLog.timestamp <= end)
                .order_by(AttendanceLog.timestamp.asc())
                .all())

        return [{
            "name":       emp.name,
            "role":       emp.role or "",
            "dept":       emp.dept or "",
            "event":      log.event_type,
            "timestamp":  log.timestamp,
            "confidence": log.confidence,
        } for log, emp in logs]
    finally:
        session.close()


# ============================================================
# MIGRATE DỮ LIỆU CŨ (chạy 1 lần để chuyển từ pickle/CSV sang DB)
# ============================================================

def migrate_from_old_files(pkl_path="database/faces.pkl", csv_path="database/attendance_log.csv"):
    """
    Đọc dữ liệu cũ từ faces.pkl và attendance_log.csv, đưa vào database mới.
    Chạy 1 lần duy nhất khi nâng cấp. An toàn — không xóa file cũ.
    """
    import pickle, os, csv as csv_module

    init_db()
    migrated_emp = 0
    migrated_log = 0

    # --- Migrate nhân viên ---
    if os.path.exists(pkl_path):
        with open(pkl_path, "rb") as f:
            old_db = pickle.load(f)

        for name, data in old_db.items():
            if isinstance(data, dict):
                emb  = data.get("emb") if data.get("emb") is not None else data.get("embedding")
                role = data.get("role", "")
                dept = data.get("dept", "")
            else:
                emb, role, dept = data, "", ""   # trường hợp cũ chỉ lưu thẳng vector

            if emb is not None:
                ok = add_employee(name, role, dept, np.array(emb, dtype=np.float32))
                if ok:
                    migrated_emp += 1

        print(f"✅ Đã chuyển {migrated_emp} nhân viên từ {pkl_path}")
    else:
        print(f"⚠️  Không tìm thấy {pkl_path}, bỏ qua bước này.")

    # --- Migrate log chấm công ---
    if os.path.exists(csv_path):
        session = get_session()
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv_module.DictReader(f)
                for row in reader:
                    name  = row.get("Ten") or row.get("Name")
                    event = row.get("Su kien") or row.get("Event") or "CHECK_IN"
                    ts_str = row.get("Thoi gian") or row.get("Time")
                    conf  = float(row.get("Do chinh xac (%)", 0) or 0)

                    emp = session.query(Employee).filter_by(name=name).first()
                    if not emp:
                        continue

                    try:
                        ts = datetime.strptime(ts_str, "%d/%m/%Y %H:%M:%S")
                    except Exception:
                        continue

                    log = AttendanceLog(employee_id=emp.id, event_type=event,
                                        timestamp=ts, confidence=conf)
                    session.add(log)
                    migrated_log += 1

            session.commit()
            print(f"✅ Đã chuyển {migrated_log} log chấm công từ {csv_path}")
        finally:
            session.close()
    else:
        print(f"⚠️  Không tìm thấy {csv_path}, bỏ qua bước này.")

    return migrated_emp, migrated_log


if __name__ == "__main__":
    print("🚀 Bắt đầu migrate dữ liệu cũ sang database mới...\n")
    emp_count, log_count = migrate_from_old_files()
    print(f"\n🎉 Hoàn tất! {emp_count} nhân viên, {log_count} log đã chuyển vào database.db")
    print("💡 File cũ (faces.pkl, attendance_log.csv) vẫn được giữ nguyên, có thể xóa sau khi xác nhận DB hoạt động đúng.")
