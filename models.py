from __future__ import annotations
"""
models.py — Định nghĩa cơ sở dữ liệu bằng SQLAlchemy ORM.

Không cần viết SQL. Mọi thao tác đều qua Python object.
Thay thế hoàn toàn faces.pkl + attendance_log.csv bằng 1 file database.db.

Cách dùng cơ bản:
    from models import init_db, get_session, Employee, AttendanceLog

    init_db()                          # gọi 1 lần khi khởi động app
    session = get_session()

    # Thêm nhân viên
    emp = Employee(name="Nguyen Van A", role="Cong nhan", embedding=vector_bytes)
    session.add(emp)
    session.commit()

    # Tìm nhân viên
    emp = session.query(Employee).filter_by(name="Nguyen Van A").first()

    # Lấy tất cả nhân viên
    all_emps = session.query(Employee).all()
"""

import numpy as np
import threading
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, LargeBinary, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

DB_PATH = "sqlite:///database/attendance.db"


# ============================================================
# BẢNG NHÂN VIÊN
# ============================================================

class Employee(Base):
    """
    Bảng lưu thông tin nhân viên + vector khuôn mặt.
    Thay thế cho faces.pkl.
    """
    __tablename__ = "employees"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    name      = Column(String(100), unique=True, nullable=False)
    role      = Column(String(50),  default="")
    dept      = Column(String(100), default="")
    embedding = Column(LargeBinary, nullable=False)   # vector 512-dim lưu dạng bytes
    created_at = Column(DateTime, default=datetime.now)

    # Quan hệ 1-nhiều: 1 nhân viên có nhiều log chấm công
    logs = relationship("AttendanceLog", back_populates="employee", cascade="all, delete-orphan")

    def set_embedding(self, vec: np.ndarray):
        """Lưu numpy array dạng bytes vào DB."""
        self.embedding = vec.astype(np.float32).tobytes()

    def get_embedding(self) -> np.ndarray:
        """Đọc lại numpy array từ bytes lưu trong DB."""
        return np.frombuffer(self.embedding, dtype=np.float32)

    def __repr__(self):
        return f"<Employee id={self.id} name={self.name} role={self.role}>"


# ============================================================
# BẢNG LOG CHẤM CÔNG
# ============================================================

class AttendanceLog(Base):
    """
    Bảng lưu mỗi lượt chấm công.
    Thay thế cho attendance_log.csv.
    """
    __tablename__ = "attendance_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    event_type  = Column(String(20), nullable=False)   # "CHECK_IN" hoặc "CHECK_OUT"
    timestamp   = Column(DateTime, default=datetime.now)
    confidence  = Column(Float, default=0.0)

    employee = relationship("Employee", back_populates="logs")

    def __repr__(self):
        return f"<Log {self.event_type} employee_id={self.employee_id} at={self.timestamp}>"


# ============================================================
# KHỞI TẠO & QUẢN LÝ KẾT NỐI
# ============================================================

_engine = None
_SessionLocal = None
_init_lock = threading.Lock()


def init_db():
    """
    Gọi 1 lần khi khởi động app.
    Tạo file database.db và toàn bộ bảng nếu chưa có.
    Thread-safe: nhiều thread gọi cùng lúc vẫn chỉ khởi tạo 1 lần.
    """
    global _engine, _SessionLocal
    with _init_lock:
        if _SessionLocal is not None:
            return   # đã khởi tạo rồi, bỏ qua

        import os
        os.makedirs("database", exist_ok=True)

        # check_same_thread=False: cho phép gọi từ nhiều thread (camera, AI worker, UI)
        # timeout=15: chờ tối đa 15s nếu DB đang bị lock, tránh đứng hình vô hạn
        _engine = create_engine(
            DB_PATH, echo=False,
            connect_args={"check_same_thread": False, "timeout": 15}
        )
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine)
        print("✅ Database sẵn sàng:", DB_PATH)


def get_session():
    """
    Trả về 1 session mới để thao tác với DB.
    Mỗi lần cần đọc/ghi DB, gọi hàm này lấy session rồi dùng.
    """
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()
