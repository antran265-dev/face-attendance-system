from __future__ import annotations
"""
config.py — Toàn bộ cấu hình hệ thống chấm công.
Chỉ cần chỉnh file này, không cần đụng code nơi khác.
"""

# ── Nhận diện ────────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.45   # ngưỡng cosine similarity để nhận ra (0.0–1.0)
                               # Tăng lên 0.55 nếu bị nhận nhầm người
                               # Giảm xuống 0.40 nếu khó nhận (đeo khẩu trang)

AI_MODEL        = "buffalo_sc" # buffalo_sc = nhỏ gọn CPU-friendly (~100MB)
                               # buffalo_l  = chính xác hơn nhưng nặng hơn 3x
AI_DET_SIZE     = (320, 320)  # kích thước detect của InsightFace
AI_INPUT_SIZE   = (320, 240)  # frame thu nhỏ trước khi đưa vào AI (tiết kiệm CPU)
AI_INTERVAL     = 0.10        # giây giữa 2 lần AI xử lý — tăng nếu CPU yếu

# ── Chống giả mạo (Motion Liveness) ─────────────────────────────────────────
MOTION_THRESHOLD   = 15.0     # tổng chuyển động cần tích lũy để pass
                               # Giảm xuống 10.0 = dễ pass hơn
                               # Tăng lên 25.0  = chặt hơn
MOTION_TIMEOUT_SEC = 8.0      # giây tối đa để thực hiện cử chỉ
MOTION_MIN_VARIANCE= 1.5      # variance tối thiểu — chống video replay đều đặn

# ── Logic chấm công ──────────────────────────────────────────────────────────
SCAN_COOLDOWN    = 60         # giây tối thiểu giữa 2 lần quét của cùng 1 người
                               # Ngăn double-scan khi đứng lâu trước camera
CHECK_OUT_HOUR   = 11         # Trước giờ này → luôn CHECK_IN
                               # Sau giờ này   → CHECK_OUT nếu đã vào, CHECK_IN nếu chưa

# ── Đăng ký nhân viên ────────────────────────────────────────────────────────
REG_SAMPLES = 30              # số mẫu embedding thu khi đăng ký mới

# ── Âm thanh ─────────────────────────────────────────────────────────────────
TTS_RATE     = 160            # tốc độ đọc (words/phút) — giảm nếu muốn chậm hơn
SOUND_CHECKIN  = "Xin chào {name}. Chúc bạn làm việc vui vẻ."
SOUND_CHECKOUT = "Tạm biệt {name}. Hẹn gặp lại."

# ── Đường dẫn ────────────────────────────────────────────────────────────────
import os
DB_DIR   = "database"
DB_PATH  = os.path.join(DB_DIR, "faces.pkl")
LOG_PATH = os.path.join(DB_DIR, "attendance_log.csv")
os.makedirs(DB_DIR, exist_ok=True)

# ── Camera ───────────────────────────────────────────────────────────────────
CAM_WIDTH   = 1280
CAM_HEIGHT  = 720
CAM_DISPLAY = (700, 525)      # kích thước hiển thị trong UI
