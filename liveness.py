from __future__ import annotations
"""
liveness.py — Chống giả mạo bằng Motion Liveness Detection.
"""

from __future__ import annotations

import time
import numpy as np
from config import MOTION_THRESHOLD, MOTION_TIMEOUT_SEC, MOTION_MIN_VARIANCE


class MotionLivenessDetector:

    def __init__(self):
        self.reset()

    def reset(self):
        self._prev_center    = None
        self._cum_motion     = 0.0
        self._start_time     = None
        self._passed         = False
        self._motion_history = []

    @property
    def passed(self) -> bool:
        return self._passed

    def _center(self, face) -> tuple:
        b = face.bbox
        return (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0

    def _face_w(self, face) -> float:
        b = face.bbox
        return float(abs(b[2] - b[0])) + 1e-6

    def update(self, face) -> tuple:
        """Trả về (passed: bool, message: str)."""
        if self._passed:
            return True, "THAT"

        if self._start_time is None:
            self._start_time = time.time()

        elapsed = time.time() - self._start_time
        if elapsed > MOTION_TIMEOUT_SEC:
            self.reset()
            return False, "Di chuyen dau de xac nhan"

        cx, cy = self._center(face)
        face_w = self._face_w(face)

        if self._prev_center is not None:
            dx = cx - self._prev_center[0]
            dy = cy - self._prev_center[1]
            dist = (dx**2 + dy**2) ** 0.5
            norm_dist = dist / face_w * 100.0
            if norm_dist > 0.8:
                self._cum_motion += norm_dist
                self._motion_history.append(norm_dist)

        self._prev_center = (cx, cy)

        # ── Kiểm tra pass ────────────────────────────────────────────────
        if self._cum_motion >= MOTION_THRESHOLD:
            # Chống video replay: chỉ kiểm tra variance khi có đủ mẫu VÀ
            # motion VƯỢT hẳn ngưỡng (>=1.5x) để tránh reject người thật
            # di chuyển chậm và đều
            if len(self._motion_history) >= 8:
                variance = float(np.var(self._motion_history[-12:]))
                # Chỉ reject nếu variance RẤT thấp VÀ motion vừa đúng ngưỡng
                # (dấu hiệu rõ của video loop lặp lại đều đặn)
                is_video_loop = (
                    variance < MOTION_MIN_VARIANCE
                    and self._cum_motion < MOTION_THRESHOLD * 1.3
                )
                if is_video_loop:
                    # Không reset hẳn, chỉ đặt lại prev_center để
                    # người thật có thể tiếp tục di chuyển thêm chút
                    self._prev_center = None
                    return False, "Di chuyen tu nhien hon"

            # Pass liveness
            self._passed = True
            return True, "THAT"

        # ── Hiển thị tiến trình ──────────────────────────────────────────
        # KHÔNG dùng min(..., 99) — để hiển thị đúng thực tế
        pct       = int(self._cum_motion / MOTION_THRESHOLD * 100)
        time_left = max(0, int(MOTION_TIMEOUT_SEC - elapsed))

        if pct < 25:
            return False, f"Nhuc nhich dau nhe ({time_left}s)"
        elif pct < 60:
            return False, f"Tot lam! Tiep tuc... {pct}%"
        else:
            return False, f"Gan xong! {pct}%"

    def update_no_face(self) -> tuple:
        self._prev_center = None
        if self._cum_motion > 0:
            pct = int(self._cum_motion / MOTION_THRESHOLD * 100)
            return False, f"Dua mat vao... ({pct}%)"
        return False, "Dua mat vao camera"
