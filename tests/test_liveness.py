"""
test_liveness.py — Unit test cho MotionLivenessDetector.

Chạy: python -m pytest tests/test_liveness.py -v
Hoặc: python tests/test_liveness.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from liveness import LivenessDetector


class FakeFace:
    """Giả lập object face từ InsightFace — chỉ cần thuộc tính bbox."""
    def __init__(self, x1, y1, x2, y2):
        self.bbox = [x1, y1, x2, y2]


def test_no_motion_does_not_pass():
    """Mặt đứng yên hoàn toàn (ảnh tĩnh) -> không bao giờ pass."""
    det = LivenessDetector()
    face = FakeFace(100, 100, 200, 200)

    for _ in range(50):
        passed, msg = det.update(face)

    assert passed is False
    print("✅ test_no_motion_does_not_pass: PASS")


def test_natural_motion_passes():
    """Mặt di chuyển tự nhiên (random, biên độ rõ rệt như người thật) -> phải pass."""
    det = LivenessDetector()
    import random
    random.seed(7)

    passed = False
    x = 100.0
    for i in range(300):
        x += random.uniform(-4, 4)   # bước đi ngẫu nhiên rõ rệt
        face = FakeFace(x, 100, x + 100, 200)
        passed, msg = det.update(face)
        if passed:
            break

    assert passed is True
    print("✅ test_natural_motion_passes: PASS")


def test_reset_clears_state():
    """reset() phải đưa detector về trạng thái ban đầu."""
    det = LivenessDetector()
    face = FakeFace(100, 100, 200, 200)
    det.update(face)
    det.cum_motion = 99  # giả lập đã tích lũy motion

    det.reset()

    assert det.cum_motion == 0.0
    assert det.passed is False
    assert det.prev_center is None
    print("✅ test_reset_clears_state: PASS")


def test_no_face_returns_hint():
    """Khi không có mặt, update_no_face() phải trả về thông báo hợp lệ."""
    det = LivenessDetector()
    passed, msg = det.update_no_face()

    assert passed is False
    assert isinstance(msg, str) and len(msg) > 0
    print("✅ test_no_face_returns_hint: PASS")


if __name__ == "__main__":
    test_no_motion_does_not_pass()
    test_natural_motion_passes()
    test_reset_clears_state()
    test_no_face_returns_hint()
    print("\n🎉 Tất cả test PASS!")
