from __future__ import annotations
"""
migrate.py — Chạy file này 1 LẦN DUY NHẤT để chuyển dữ liệu cũ
(database/faces.pkl + database/attendance_log.csv) sang database mới (database/attendance.db).

Cách chạy:
    python migrate.py

An toàn: KHÔNG xóa file cũ, chỉ đọc và copy dữ liệu sang DB mới.
Sau khi xác nhận DB hoạt động đúng, có thể tự xóa file .pkl/.csv cũ nếu muốn.
"""

from db_repository import migrate_from_old_files

if __name__ == "__main__":
    print("=" * 60)
    print("  MIGRATE DỮ LIỆU SANG DATABASE MỚI (SQLite + SQLAlchemy)")
    print("=" * 60)
    print()

    emp_count, log_count = migrate_from_old_files()

    print()
    print("=" * 60)
    print(f"  HOÀN TẤT: {emp_count} nhân viên, {log_count} log chấm công")
    print(f"  Database mới tại: database/attendance.db")
    print("=" * 60)
    print()
    print("Bước tiếp theo: chạy 'python main.py' để dùng hệ thống với DB mới.")
