from __future__ import annotations
"""
attendance.py — Logic chấm công: CHECK_IN/CHECK_OUT, tính giờ, tăng ca, âm thanh.

Fix lag hình ảnh:
  Âm thanh chạy trong subprocess riêng biệt — hoàn toàn tách khỏi process Python chính.
  Không dùng pygame.mixer, không dùng asyncio.run() trong thread, không tranh GIL.
"""

import csv, os, threading, time, tempfile, subprocess, sys
from datetime import datetime
from pathlib import Path
from config import LOG_PATH, SCAN_COOLDOWN, CHECK_OUT_HOUR

SOUNDS_DIR   = Path("sounds")
MP3_CHECKIN  = SOUNDS_DIR / "checkin.mp3"
MP3_CHECKOUT = SOUNDS_DIR / "checkout.mp3"
EDGE_VOICE   = "vi-VN-HoaiMyNeural"
MSG_CHECKIN  = "Xin chào {name}. Chúc bạn làm việc vui vẻ."
MSG_CHECKOUT = "Tạm biệt {name}. Đã làm {hours} giờ {mins} phút."
OVERTIME_HOURS = 8.0

# ── Phát hiện engine âm thanh ────────────────────────────────────────────────

def _detect_engine() -> str:
    """Trả về tên engine khả dụng tốt nhất, không khởi tạo gì."""
    try:
        import edge_tts  # noqa
        print("🔊 Âm thanh: edge-tts (HoaiMyNeural) ✅")
        return "edge"
    except ImportError:
        pass
    try:
        from gtts import gTTS  # noqa
        print("🔊 Âm thanh: gTTS (Google) ✅")
        return "gtts"
    except ImportError:
        pass
    if MP3_CHECKIN.exists() and MP3_CHECKOUT.exists():
        print("🔊 Âm thanh: MP3 offline ✅")
        return "mp3"
    print("⚠️  Không có âm thanh. Cài: pip install edge-tts  hoặc  pip install gtts")
    return "none"

_ENGINE = _detect_engine()

# Semaphore: chỉ cho 1 subprocess âm thanh chạy cùng lúc
# Nếu đang đọc câu trước → câu mới bị bỏ qua (không queue lại gây delay)
_audio_sem = threading.Semaphore(1)


# ── Script âm thanh chạy trong subprocess ────────────────────────────────────
#
# Tại sao subprocess thay vì thread?
#   - Thread chia sẻ GIL với Tkinter → pygame.mixer.get_busy() polling làm lag UI
#   - asyncio.run() trong thread xung đột event loop với Tkinter
#   - subprocess = process riêng biệt, Python interpreter riêng, GIL riêng → không ảnh hưởng UI
#   - Subprocess bị kill tự động khi main process chết (daemon=True không có trong subprocess
#     nhưng ta dùng Popen + không join → fire-and-forget)

_EDGE_SCRIPT = """\
import sys, asyncio, edge_tts, tempfile, os
async def run():
    text = sys.argv[1]
    voice = sys.argv[2]
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
        tmp = f.name
    await communicate.save(tmp)
    # Dùng playsound hoặc pygame trong subprocess này — không ảnh hưởng UI
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            import time; time.sleep(0.05)
        pygame.mixer.quit()
    except Exception:
        # Fallback: dùng lệnh hệ thống nếu không có pygame
        import platform
        if platform.system() == 'Windows':
            import winsound
            winsound.PlaySound(tmp, winsound.SND_FILENAME)
        else:
            os.system(f'aplay {tmp} 2>/dev/null || afplay {tmp} 2>/dev/null')
    os.unlink(tmp)
asyncio.run(run())
"""

_GTTS_SCRIPT = """\
import sys, tempfile, os
from gtts import gTTS
text = sys.argv[1]
tts = gTTS(text=text, lang='vi', slow=False)
with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
    tmp = f.name
tts.save(tmp)
try:
    import pygame
    pygame.mixer.init()
    pygame.mixer.music.load(tmp)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        import time; time.sleep(0.05)
    pygame.mixer.quit()
except Exception:
    import platform
    if platform.system() == 'Windows':
        import winsound
        winsound.PlaySound(tmp, winsound.SND_FILENAME)
    else:
        os.system(f'aplay {tmp} 2>/dev/null || afplay {tmp} 2>/dev/null')
os.unlink(tmp)
"""

_MP3_SCRIPT = """\
import sys, os
path = sys.argv[1]
try:
    import pygame
    pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        import time; time.sleep(0.05)
    pygame.mixer.quit()
except Exception:
    import platform
    if platform.system() == 'Windows':
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    else:
        os.system(f'aplay {path} 2>/dev/null || afplay {path} 2>/dev/null')
"""


def _run_audio_subprocess(script: str, args: list):
    """
    Chạy script âm thanh trong subprocess riêng.
    Non-blocking: trả về ngay, subprocess tự hoàn thành.
    """
    if not _audio_sem.acquire(blocking=False):
        # Đang phát câu khác → bỏ qua, không block
        return
    def _worker():
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", script] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                # Tách hoàn toàn khỏi parent process
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            proc.wait()   # chờ subprocess xong trong thread riêng
        except Exception as e:
            print(f"⚠️  Audio subprocess lỗi: {e}")
        finally:
            _audio_sem.release()   # nhả semaphore để câu tiếp theo có thể chạy

    threading.Thread(target=_worker, daemon=True).start()


def speak(text: str, event_type: str = "CHECK_IN"):
    """
    Phát thông báo tiếng Việt.
    Hoàn toàn không block UI — subprocess chạy trong Python interpreter riêng.
    """
    if _ENGINE == "edge":
        _run_audio_subprocess(_EDGE_SCRIPT, [text, EDGE_VOICE])
    elif _ENGINE == "gtts":
        _run_audio_subprocess(_GTTS_SCRIPT, [text])
    elif _ENGINE == "mp3":
        path = str(MP3_CHECKIN if event_type == "CHECK_IN" else MP3_CHECKOUT)
        if os.path.exists(path):
            _run_audio_subprocess(_MP3_SCRIPT, [path])
    else:
        print(f"🔔 {text}")


# ── Logic CHECK_IN / CHECK_OUT ───────────────────────────────────────────────
def _read_today_events(name: str) -> list:
    """Đọc tất cả sự kiện hôm nay của người này từ CSV."""
    today = datetime.now().date().isoformat()
    events = []
    if not os.path.exists(LOG_PATH):
        return events
    try:
        with open(LOG_PATH, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("Ten") != name:
                    continue
                try:
                    dt = datetime.strptime(row["Thoi gian"], "%d/%m/%Y %H:%M:%S")
                    if dt.date().isoformat() == today:
                        events.append({
                            "event": row.get("Su kien", ""),
                            "time":  dt,
                        })
                except Exception:
                    pass
    except Exception:
        pass
    return sorted(events, key=lambda x: x["time"])

def get_event_type(name: str) -> str:
    hour   = datetime.now().hour
    events = _read_today_events(name)
    types  = [e["event"] for e in events]

    # Trước giờ checkout → luôn CHECK_IN
    if hour < CHECK_OUT_HOUR:
        return "CHECK_IN"
    # Chưa có CHECK_IN hôm nay → CHECK_IN (đến muộn)
    if "CHECK_IN" not in types:
        return "CHECK_IN"
    # Đã CHECK_IN nhưng chưa CHECK_OUT → CHECK_OUT
    if "CHECK_OUT" not in types:
        return "CHECK_OUT"
    # Đã có cả hai → CHECK_IN lại (tăng ca / vào ca mới)
    return "CHECK_IN"

def calc_hours_today(name: str) -> tuple:
    """
    Tính giờ làm thực tế hôm nay từ cặp CHECK_IN / CHECK_OUT.
    Trả về (total_hours: float, is_overtime: bool, pairs: list).
    Xử lý được nhiều ca, tăng ca.
    """
    events = _read_today_events(name)
    pairs  = []
    last_in = None

    for e in events:
        if e["event"] == "CHECK_IN":
            last_in = e["time"]
        elif e["event"] == "CHECK_OUT" and last_in:
            duration = (e["time"] - last_in).total_seconds() / 3600
            pairs.append({
                "in":       last_in.strftime("%H:%M"),
                "out":      e["time"].strftime("%H:%M"),
                "hours":    round(duration, 2),
                "overtime": duration > OVERTIME_HOURS,
            })
            last_in = None

    total     = sum(p["hours"] for p in pairs)
    overtime  = total > OVERTIME_HOURS
    return total, overtime, pairs

# ── Ghi log ──────────────────────────────────────────────────────────────────
class AttendanceLogger:

    def __init__(self):
        self._last_scan: dict = {}

    def try_log(self, name: str, confidence: float, camera_id: str = "cam1"):
        now  = time.time()
        key  = f"{name}_{camera_id}"
        if now - self._last_scan.get(key, 0) < SCAN_COOLDOWN:
            return None
        self._last_scan[key] = now

        event  = get_event_type(name)
        dt_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self._write_csv(name, event, dt_str, confidence, camera_id)
        self._announce(name, event)
        return {"name": name, "event": event, "time": dt_str, "camera": camera_id}

    def _write_csv(self, name, event, dt, conf, camera):
        exists = os.path.isfile(LOG_PATH)
        try:
            with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if not exists:
                    w.writerow(["Ten", "Su kien", "Thoi gian", "Do chinh xac (%)", "Camera"])
                w.writerow([name, event, dt, conf, camera])
            print(f"  {'✅ VÀO' if event=='CHECK_IN' else '🚪 RA'}  {name}  {dt}  [{camera}]")
        except Exception as e:
            print(f"❌ Lỗi log: {e}")

    def _announce(self, name, event):
        if event == "CHECK_IN":
            speak(MSG_CHECKIN.format(name=name), "CHECK_IN")
        else:
            total, overtime, _ = calc_hours_today(name)
            h  = int(total)
            m  = int((total - h) * 60)
            msg = MSG_CHECKOUT.format(name=name, hours=h, mins=m)
            if overtime:
                msg += " Bạn có tăng ca hôm nay."
            speak(msg, "CHECK_OUT")
