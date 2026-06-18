from __future__ import annotations
import os

# === NHẬN DIỆN ===
SIMILARITY_THRESHOLD = 0.45   # tăng lên 0.55 nếu nhận nhầm, giảm 0.40 nếu đeo khẩu trang
AI_MODEL      = "buffalo_sc"
AI_DET_SIZE   = (320, 320)
AI_INPUT_SIZE = (320, 240)
AI_INTERVAL   = 0.10          # giây giữa 2 lần AI chạy — tăng nếu CPU yếu

# === CHỐNG GIẢ MẠO ===
MOTION_THRESHOLD    = 15.0    # giảm = dễ pass hơn, tăng = chặt hơn
MOTION_TIMEOUT_SEC  = 8.0
MOTION_MIN_VARIANCE = 1.5

# === CHẤM CÔNG ===
SCAN_COOLDOWN   = 60          # giây chờ giữa 2 lần quét của cùng 1 người
CHECK_OUT_HOUR  = 11          # trước giờ này luôn là CHECK_IN

# === ĐĂNG KÝ ===
REG_SAMPLES = 30

# === ÂM THANH ===
EDGE_VOICE     = "vi-VN-HoaiMyNeural"
MSG_CHECKIN    = "Xin chào {name}. Chúc bạn làm việc vui vẻ."
MSG_CHECKOUT   = "Tạm biệt {name}. Hẹn gặp lại."

# === ĐƯỜNG DẪN ===
DB_DIR   = "database"
LOG_PATH = os.path.join(DB_DIR, "attendance_log.csv")   # chỉ dùng khi export CSV thủ công
os.makedirs(DB_DIR, exist_ok=True)

# === CAMERA ===
CAM_WIDTH   = 1280
CAM_HEIGHT  = 720
CAM_DISPLAY = (700, 525)

# === CHỨC VỤ ===
ROLE_OPTIONS = [
    "Công nhân", "Nhân viên văn phòng", "Kỹ sư / Kỹ thuật viên",
    "Tổ trưởng / Trưởng ca", "Trưởng phòng", "Quản lý", "Bảo vệ", "Lái xe", "Khác",
]
