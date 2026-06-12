from __future__ import annotations
import time
import numpy as np
from config import MOTION_THRESHOLD, MOTION_TIMEOUT_SEC, MOTION_MIN_VARIANCE


class LivenessDetector:
    """
    Chống giả mạo bằng chuyển động đầu.
    Ảnh tĩnh = 0 motion. Video loop = motion đều, variance thấp.
    Người thật = micro-movement tự nhiên -> pass.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.prev_center    = None
        self.cum_motion     = 0.0
        self.start_time     = None
        self.passed         = False
        self.history        = []

    def update(self, face) -> tuple[bool, str]:
        if self.passed:
            return True, "THAT"

        if self.start_time is None:
            self.start_time = time.time()

        elapsed = time.time() - self.start_time
        if elapsed > MOTION_TIMEOUT_SEC:
            self.reset()
            return False, "Di chuyen dau de xac nhan"

        b  = face.bbox
        cx = (b[0] + b[2]) / 2
        cy = (b[1] + b[3]) / 2
        fw = abs(b[2] - b[0]) + 1e-6

        if self.prev_center:
            dx, dy = cx - self.prev_center[0], cy - self.prev_center[1]
            step   = (dx**2 + dy**2)**0.5 / fw * 100
            if step > 0.8:
                self.cum_motion += step
                self.history.append(step)

        self.prev_center = (cx, cy)

        if self.cum_motion >= MOTION_THRESHOLD:
            # Chống video loop: motion đều đặn bất thường
            if len(self.history) >= 8:
                var = float(np.var(self.history[-12:]))
                if var < MOTION_MIN_VARIANCE and self.cum_motion < MOTION_THRESHOLD * 1.3:
                    # Không reset prev_center (tránh kẹt vô hạn) — chỉ yêu cầu
                    # tích lũy thêm motion để tăng variance/vượt 1.3x ngưỡng
                    self.history = []
                    return False, "Di chuyen tu nhien hon"
            self.passed = True
            return True, "THAT"

        pct  = int(self.cum_motion / MOTION_THRESHOLD * 100)
        left = max(0, int(MOTION_TIMEOUT_SEC - elapsed))

        if pct < 25:   return False, f"Nhuc nhich dau nhe ({left}s)"
        elif pct < 60: return False, f"Tot lam! Tiep tuc... {pct}%"
        else:          return False, f"Gan xong! {pct}%"

    def update_no_face(self) -> tuple[bool, str]:
        self.prev_center = None
        if self.cum_motion > 0:
            return False, f"Dua mat vao... ({int(self.cum_motion/MOTION_THRESHOLD*100)}%)"
        return False, "Dua mat vao camera"
