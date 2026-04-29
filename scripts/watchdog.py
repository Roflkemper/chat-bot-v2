"""bot7 supervisor watchdog.

Runs independently of supervisor. Checks every POLL_INTERVAL seconds whether
supervisor is alive. If dead for GRACE_SECONDS, sends Telegram alarm and
attempts to restart via `python -m bot7 start`.

Usage (from Shell:Startup .bat or manually):
    python scripts/watchdog.py

Log: logs/autostart/watchdog.log
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs" / "autostart"
LOG_DIR.mkdir(parents=True, exist_ok=True)

WATCHDOG_PID_PATH = ROOT / "run" / "watchdog.pid"
# Hardcoded — do NOT import from src.supervisor.daemon here.
# That import executes setup_logging("supervisor") which reconfigures the root
# logger, making logging.basicConfig() a no-op and routing all watchdog output
# to supervisor.log instead of watchdog.log (confirmed in incident 2026-04-28).
DAEMON_PID_PATH = ROOT / "run" / "supervisor.pid"

_fmt = logging.Formatter(
    fmt="%(asctime)sZ | %(levelname)-7s | watchdog | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_file_handler = logging.FileHandler(LOG_DIR / "watchdog.log", encoding="utf-8")
_file_handler.setFormatter(_fmt)
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_fmt)

log = logging.getLogger("watchdog")
log.setLevel(logging.INFO)
log.addHandler(_file_handler)
log.addHandler(_stream_handler)
log.propagate = False  # prevent leaking to root logger (which may be supervisor's)

POLL_INTERVAL = 60       # seconds between checks
GRACE_SECONDS = 120      # supervisor must be dead this long before action
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = sys.executable


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if sys.platform == "win32":
        import ctypes
        import ctypes.wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        code = ctypes.wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _send_telegram(text: str) -> None:
    try:
        import requests
        sys.path.insert(0, str(ROOT))
        from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_IDS
        chat_ids = AUTHORIZED_CHAT_IDS if isinstance(AUTHORIZED_CHAT_IDS, list) else [AUTHORIZED_CHAT_IDS]
        for cid in chat_ids:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": text},
                    timeout=10,
                )
            except Exception:
                pass
    except Exception:
        pass


def _restart_supervisor() -> None:
    log.info("Attempting bot7 start...")
    try:
        subprocess.Popen(
            [PYTHON, "-m", "bot7", "start"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        log.error("Failed to restart supervisor: %s", exc)


_HEARTBEAT_INTERVAL = 300  # 5 min — keeps wd_log_age > 5 satisfied with 1 min buffer


def main() -> None:
    # Self-dedup: exit if another watchdog instance is already running.
    WATCHDOG_PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing_pid = _read_pid(WATCHDOG_PID_PATH)
    if existing_pid and existing_pid != os.getpid() and _pid_alive(existing_pid):
        log.warning("Another watchdog already running (PID=%s) — exiting duplicate", existing_pid)
        return

    WATCHDOG_PID_PATH.write_text(str(os.getpid()))

    log.info("Watchdog started (PID=%s, poll=%ds, grace=%ds)", os.getpid(), POLL_INTERVAL, GRACE_SECONDS)
    dead_since: float | None = None
    last_heartbeat = time.monotonic()

    while True:
        now_mono = time.monotonic()
        pid = _read_pid(DAEMON_PID_PATH)
        alive = _pid_alive(pid) if pid else False

        if alive:
            if dead_since is not None:
                log.info("Supervisor recovered (PID=%s)", pid)
            dead_since = None
        else:
            if dead_since is None:
                dead_since = now_mono
                log.warning("Supervisor not detected (PID=%s)", pid)
            elif now_mono - dead_since >= GRACE_SECONDS:
                msg = (
                    f"🚨 bot7 watchdog: supervisor DEAD for {int(now_mono - dead_since)}s!\n"
                    f"PID file: {pid or 'missing'}\n"
                    f"Auto-restarting via bot7 start..."
                )
                log.error(msg)
                _send_telegram(msg)
                _restart_supervisor()
                dead_since = None  # reset after restart attempt

        # Periodic heartbeat so supervisor health check sees fresh log mtime.
        if now_mono - last_heartbeat >= _HEARTBEAT_INTERVAL:
            log.info("[heartbeat] supervisor_alive=%s pid=%s", alive, pid or "-")
            last_heartbeat = now_mono

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
