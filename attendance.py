from __future__ import annotations
"""
attendance.py — Logic chấm công, giờ dùng Database (SQLAlchemy) thay cho CSV.

THAY ĐỔI SO VỚI BẢN CŨ:
  - get_event() đọc lịch sử từ DB thay vì đọc file CSV dòng-by-dòng
  - try_log() ghi vào DB thay vì append CSV
  - API (tên hàm, tham số, kết quả trả về) giữ NGUYÊN — main.py không cần sửa gì

Âm thanh giữ nguyên cơ chế subprocess cũ.
"""

import subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path
from config import SCAN_COOLDOWN, CHECK_OUT_HOUR, EDGE_VOICE, MSG_CHECKIN, MSG_CHECKOUT
from db_repository import add_attendance_log, get_today_logs_for


# ---------------------------------------------------------------------------
# Âm thanh — subprocess riêng, không đụng GIL/Tkinter (giữ nguyên bản cũ)
# ---------------------------------------------------------------------------

def _detect_engine() -> str:
    try:
        import edge_tts; print("🔊 edge-tts (HoaiMyNeural)"); return "edge"
    except ImportError: pass
    try:
        from gtts import gTTS; print("🔊 gTTS (Google)"); return "gtts"
    except ImportError: pass
    mp3 = Path("sounds/checkin.mp3")
    if mp3.exists(): print("🔊 MP3 offline"); return "mp3"
    print("⚠️  Không có âm thanh — pip install edge-tts")
    return "none"

ENGINE = _detect_engine()
_sem   = threading.Semaphore(1)

_PLAY = """
import sys, os, tempfile
text, engine, voice = sys.argv[1], sys.argv[2], sys.argv[3]

def play(path):
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        import time
        while pygame.mixer.music.get_busy(): time.sleep(0.05)
        pygame.mixer.quit()
    except Exception:
        import platform, os
        if platform.system() == "Windows":
            import winsound; winsound.PlaySound(path, winsound.SND_FILENAME)
        else:
            os.system(f"aplay '{path}' 2>/dev/null")

if engine == "edge":
    import asyncio, edge_tts
    async def run():
        c = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f: tmp=f.name
        await c.save(tmp); play(tmp); os.unlink(tmp)
    asyncio.run(run())
elif engine == "gtts":
    from gtts import gTTS
    tts = gTTS(text=text, lang="vi")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f: tmp=f.name
    tts.save(tmp); play(tmp); os.unlink(tmp)
elif engine == "mp3":
    play(text)
"""

def speak(text: str, event: str = "CHECK_IN"):
    if ENGINE == "none":
        print(f"🔔 {text}"); return

    actual = text
    if ENGINE == "mp3":
        actual = "sounds/checkin.mp3" if event == "CHECK_IN" else "sounds/checkout.mp3"

    if not _sem.acquire(blocking=False):
        return

    def _run():
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc  = subprocess.Popen(
                [sys.executable, "-c", _PLAY, actual, ENGINE, EDGE_VOICE],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            proc.wait()
        except Exception as e:
            print(f"⚠️  Audio: {e}")
        finally:
            _sem.release()

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Xác định loại sự kiện — ĐỌC TỪ DATABASE thay vì CSV
# ---------------------------------------------------------------------------

def get_event(name: str) -> str:
    """
    Trả về CHECK_IN hoặc CHECK_OUT dựa trên giờ hiện tại và lịch sử hôm nay.
    Logic giữ nguyên 100% so với bản CSV cũ, chỉ đổi nguồn dữ liệu sang DB.
    """
    hour = datetime.now().hour

    today_logs = get_today_logs_for(name)   # <-- đây là điểm khác biệt duy nhất
    has_in  = any(l["event"] == "CHECK_IN"  for l in today_logs)
    has_out = any(l["event"] == "CHECK_OUT" for l in today_logs)

    if hour < CHECK_OUT_HOUR: return "CHECK_IN"
    if not has_in:            return "CHECK_IN"
    if has_out:                return "CHECK_IN"
    return "CHECK_OUT"


# ---------------------------------------------------------------------------
# Ghi log — GHI VÀO DATABASE thay vì CSV
# ---------------------------------------------------------------------------

class AttendanceLogger:
    """
    API giữ nguyên hoàn toàn so với bản cũ — main.py gọi try_log() như trước,
    không cần sửa gì ở phía UI.
    """

    def __init__(self):
        self._last: dict[str, float] = {}

    def try_log(self, name: str, conf: float, role: str = "") -> dict | None:
        now = time.time()
        if now - self._last.get(name, 0) < SCAN_COOLDOWN:
            return None

        self._last[name] = now
        event = get_event(name)

        result = add_attendance_log(name, event, conf)   # <-- ghi vào DB
        if result is None:
            print(f"⚠️  Không tìm thấy nhân viên '{name}' trong DB để ghi log.")
            return None

        icon = "✅ VÀO" if event == "CHECK_IN" else "🚪 RA"
        print(f"  {icon}  {name} [{role}]  {result['time']}")

        self._say(name, event)
        return result

    def _say(self, name, event):
        msg = MSG_CHECKIN if event == "CHECK_IN" else MSG_CHECKOUT
        speak(msg.format(name=name), event)
