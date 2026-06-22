from __future__ import annotations
"""
server.py — API Server trung tâm cho hệ thống chấm công.

KIẾN TRÚC: Server này KHÔNG có giao diện web, KHÔNG có HTML/CSS.
Mọi giao tiếp đều qua JSON (giống cách app điện thoại nói chuyện với server).

Server làm 3 việc:
  1. So sánh embedding khuôn mặt nhận từ client (cosine similarity)
  2. Quản lý logic CHECK_IN/CHECK_OUT + cooldown (dùng lại attendance.py cũ)
  3. Đọc/ghi database qua models.py + db_repository.py (y nguyên bản cũ)

CÁCH CHẠY:
    python server.py
Server chạy tại http://localhost:5000 (hoặc IP máy chủ trong mạng LAN)

CÁC ENDPOINT (API) — tất cả trả về JSON, không có trang web nào:
    GET    /api/health            — kiểm tra server còn sống
    POST   /api/register          — đăng ký nhân viên mới
    POST   /api/checkin           — gửi embedding để chấm công
    GET    /api/employees         — lấy danh sách nhân viên
    DELETE /api/employees/<name>  — xóa nhân viên
    GET    /api/logs/today        — lấy log chấm công hôm nay
"""

import numpy as np
from flask import Flask, request, jsonify
from datetime import datetime

from models import init_db
from db_repository import (
    add_employee, delete_employee, get_all_employees, get_employee_count,
    get_today_all_logs,
)
from config import SIMILARITY_THRESHOLD
from attendance import AttendanceLogger

app = Flask(__name__)

# ============================================================
# KHỞI TẠO — chạy 1 lần khi server bắt đầu
# ============================================================

init_db()
logger = AttendanceLogger()

print("=" * 60)
print("  SERVER CHẤM CÔNG ĐÃ SẴN SÀNG")
print(f"  Số nhân viên hiện có: {get_employee_count()}")
print("  Client tự trích xuất embedding bằng InsightFace,")
print("  server chỉ nhận vector và SO SÁNH (cosine similarity).")
print("=" * 60)


# ============================================================
# HÀM NHẬN DIỆN
# ============================================================

def recognize_embedding(emb: np.ndarray) -> dict:
    """So sánh 1 vector embedding với toàn bộ nhân viên trong DB."""
    db = get_all_employees()
    if not db:
        return {"status": "empty_db"}

    names   = list(db.keys())
    entries = list(db.values())
    vecs    = np.array([e["emb"] for e in entries], dtype=np.float32)

    sims = vecs @ emb
    idx  = int(np.argmax(sims))
    sim  = float(sims[idx])

    if sim >= SIMILARITY_THRESHOLD:
        entry = entries[idx]
        return {
            "status":     "recognized",
            "name":       names[idx],
            "role":       entry.get("role", ""),
            "dept":       entry.get("dept", ""),
            "confidence": round(sim * 100, 1),
        }
    return {"status": "unknown", "confidence": round(sim * 100, 1)}


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "employee_count": get_employee_count(),
        "server_time": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    })


@app.route("/api/register", methods=["POST"])
def register():
    """Body JSON: {"name": str, "role": str, "dept": str, "embedding": [512 số float]}"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Thieu du lieu JSON"}), 400

    name = (data.get("name") or "").strip()
    role = data.get("role", "")
    dept = data.get("dept", "")
    emb_list = data.get("embedding")

    if not name or not emb_list:
        return jsonify({"success": False, "error": "Thieu name hoac embedding"}), 400

    emb = np.array(emb_list, dtype=np.float32)
    ok = add_employee(name, role, dept, emb)

    if not ok:
        return jsonify({"success": False, "error": f"Ten '{name}' da ton tai"}), 409

    return jsonify({"success": True, "name": name, "role": role})


@app.route("/api/checkin", methods=["POST"])
def checkin():
    """
    Body JSON: {"embedding": [512 số float], "camera_id": str (tuỳ chọn)}

    Response format (khớp với client_main.py):
        {"recognized": bool, "name": str, "role": str, "confidence": float,
         "logged": bool, "event": str, "time": str}
    """
    data = request.get_json()
    if not data or "embedding" not in data:
        return jsonify({"recognized": False, "error": "Thieu embedding"}), 400

    emb  = np.array(data["embedding"], dtype=np.float32)
    norm = np.linalg.norm(emb)
    if norm == 0:
        return jsonify({"recognized": False, "error": "Embedding khong hop le"}), 400
    emb = emb / norm

    result = recognize_embedding(emb)

    if result["status"] == "empty_db":
        return jsonify({"recognized": False, "error": "Chua co nhan vien nao trong DB"}), 404

    if result["status"] == "unknown":
        return jsonify({"recognized": False, "confidence": result["confidence"]})

    # Đã nhận diện được người — thử ghi log (có cooldown bên trong)
    name = result["name"]
    log_entry = logger.try_log(name, result["confidence"], result.get("role", ""))

    camera_id = data.get("camera_id", "unknown")

    if log_entry is None:
        # Đang trong cooldown — vẫn coi là "recognized" nhưng "logged": False
        return jsonify({
            "recognized": True,
            "name":       name,
            "role":       result.get("role", ""),
            "confidence": result["confidence"],
            "logged":     False,
        })

    print(f"  📷 [{camera_id}] {log_entry['event']}: {name} ({result['confidence']}%)")

    return jsonify({
        "recognized": True,
        "name":       name,
        "role":       result.get("role", ""),
        "confidence": result["confidence"],
        "logged":     True,
        "event":      log_entry["event"],
        "time":       log_entry["time"],
    })


@app.route("/api/employees", methods=["GET"])
def list_employees():
    db = get_all_employees()
    result = [
        {"name": name, "role": data.get("role", ""), "dept": data.get("dept", "")}
        for name, data in db.items()
    ]
    return jsonify({"success": True, "count": len(result), "employees": result})


@app.route("/api/employees/<name>", methods=["DELETE"])
def remove_employee(name):
    ok = delete_employee(name)
    if not ok:
        return jsonify({"success": False, "error": f"Khong tim thay '{name}'"}), 404
    return jsonify({"success": True, "deleted": name})


@app.route("/api/logs/today", methods=["GET"])
def today_logs():
    logs = get_today_all_logs()
    return jsonify({"success": True, "count": len(logs), "logs": logs})


# ============================================================
# CHẠY SERVER
# ============================================================

if __name__ == "__main__":
    # host="0.0.0.0": cho phép máy khác trong mạng LAN kết nối (không chỉ localhost)
    app.run(host="0.0.0.0", port=5000, debug=False)
