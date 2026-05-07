"""bot7 keepalive — runs every 2 min via OS scheduler.

Cross-platform: Windows Task Scheduler / macOS launchd / Linux systemd-timer.

Checks: supervisor alive? If not — runs `python -m bot7 start`.
Logs every check to logs/autostart/keepalive.log.

This is the OS-level safety net. Independent from supervisor + watchdog —
both can fail; this script runs as a separate scheduled task and brings
everything back up.

CPU/memory usage: <0.1% averaged. Each invocation: 2-3 syscalls + log write.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / "run" / "supervisor.pid"
LOG_FILE = ROOT / "logs" / "autostart" / "keepalive.log"

# Cross-platform Python interpreter resolution
if sys.platform == "win32":
    PYTHON = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not PYTHON.exists():
        PYTHON = Path(sys.executable)
else:
    # macOS / Linux
    PYTHON = ROOT / ".venv" / "bin" / "python"
    if not PYTHON.exists():
        PYTHON = Path(sys.executable)


def _log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} | {msg}\n")
    except OSError:
        pass


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    """Check if PID is alive AND is the bot7 supervisor (not a PID-reuse stranger).

    Pure psutil check (cross-platform — Windows / macOS / Linux).
    Раньше использовал os.kill(pid, 0) который выдавал WinError 87 на Windows
    в некоторых конфигурациях.

    Verifies cmdline contains "src.supervisor.daemon" чтобы защититься от
    PID-reuse (Windows aggressive с переиспользованием PID).
    """
    if pid is None or pid <= 0:
        return False
    try:
        import psutil
    except ImportError:
        # psutil missing — fallback to assume alive (don't restart prematurely)
        return True
    try:
        if not psutil.pid_exists(pid):
            return False
        p = psutil.Process(pid)
        if not p.is_running():
            return False
        cmdline = " ".join(p.cmdline()).lower()
        return "src.supervisor.daemon" in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # Не наш процесс / нет доступа = считаем мёртвым → restart
        return False
    except Exception:
        # Любая другая ошибка — на стороне осторожности (не рестартим преждевременно)
        return True


def _start_bot7() -> None:
    """Run `python -m bot7 start` to bring everything up. Cross-platform."""
    cmd = [str(PYTHON), "-m", "bot7", "start"]
    _log(f"Starting bot7 via: {' '.join(cmd)}")
    try:
        kwargs: dict = {
            "cwd": str(ROOT),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform == "win32":
            # DETACHED_PROCESS — supervisor живёт после выхода watchdog'а
            kwargs["creationflags"] = 0x00000008
        else:
            # POSIX — start_new_session чтобы не зависело от watchdog'а
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)
        _log("bot7 start dispatched")
    except Exception as e:
        _log(f"ERROR starting bot7: {e}")


def main() -> int:
    pid = _read_pid()
    if pid is None:
        _log("supervisor PID file missing — starting bot7")
        _start_bot7()
        return 0
    if not _pid_alive(pid):
        _log(f"supervisor PID={pid} dead — restarting bot7")
        _start_bot7()
        return 0
    # Alive — heartbeat once an hour to keep log compact
    now = datetime.now(timezone.utc)
    if now.minute < 2:  # log every hour around minute 0-1
        _log(f"OK — supervisor PID={pid} alive (heartbeat)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
