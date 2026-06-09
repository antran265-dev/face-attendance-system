from __future__ import annotations
import csv, os, subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path
from config import LOG_PATH, SCAN_COOLDOWN, CHECK_OUT_HOUR, EDGE_VOICE, MSG_CHECKIN, MSG_CHECKOUT


# ---------------------------------------------------------------------------
# Âm thanh — subprocess riêng, không đụng GIL/Tkinter
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

ENGINE    = _detect_engine()
_sem      = threading.Semaphore(1)   # chỉ 1 câu chạy cùng lúc

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
        return   # đang phát câu khác, bỏ qua

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
# Xác định loại sự kiện
# ---------------------------------------------------------------------------

def get_event(name: str) -> str:
    today = datetime.now().date().isoformat()
    hour  = datetime.now().hour
    has_in = has_out = False

    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("Ten") != name: continue
                try:
                    d = datetime.strptime(row["Thoi gian"], "%d/%m/%Y %H:%M:%S").date().isoformat()
                except Exception: continue
                if d != today: continue
                if row.get("Su kien") == "CHECK_IN":  has_in  = True
                if row.get("Su kien") == "CHECK_OUT": has_out = True

    if hour < CHECK_OUT_HOUR: return "CHECK_IN"
    if not has_in:            return "CHECK_IN"
    if has_out:               return "CHECK_IN"
    return "CHECK_OUT"


# ---------------------------------------------------------------------------
# Ghi log
# ---------------------------------------------------------------------------

class AttendanceLogger:

    def __init__(self):
        self._last: dict[str, float] = {}

    def try_log(self, name: str, conf: float, role: str = "") -> dict | None:
        now = time.time()
        if now - self._last.get(name, 0) < SCAN_COOLDOWN:
            return None

        self._last[name] = now
        event = get_event(name)
        dt    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self._write(name, event, dt, conf, role)
        self._say(name, event)
        return {"name": name, "event": event, "time": dt}

    def _write(self, name, event, dt, conf, role):
        exists = os.path.isfile(LOG_PATH)
        with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["Ten", "Chuc vu", "Su kien", "Thoi gian", "Do chinh xac (%)"])
            w.writerow([name, role, event, dt, conf])
        print(f"  {'✅ VÀO' if event=='CHECK_IN' else '🚪 RA'}  {name} [{role}]  {dt}")

    def _say(self, name, event):
        msg = MSG_CHECKIN if event == "CHECK_IN" else MSG_CHECKOUT
        speak(msg.format(name=name), event)
