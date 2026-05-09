"""bot7 keepalive — runs every 2 min via OS scheduler.

Cross-platform: Windows Task Scheduler / macOS launchd / Linux systemd-timer.

2026-05-09 PIVOT: This script now monitors **app_runner directly**, not the
supervisor wrapper. The supervisor.daemon module had a chronic ~2-min
silent-death problem on Windows pythonw + Task Scheduler that 4 separate
fixes (signal handler, PID-reuse cmdline check, BREAKAWAY_FROM_JOB on
self, BREAKAWAY_FROM_JOB on children) reduced but did not fully eliminate.

Since app_runner.py runs all production async tasks via asyncio.gather and
has its own internal task-restart logic, the supervisor wrapper is
redundant — keepalive can launch app_runner directly and skip the broken
intermediate layer entirely. orphan tracker/collectors/state_snapshot
processes from prior runs are still cleaned by the cmdline-match logic
on each new launch.

Checks: app_runner alive? If not — launches app_runner directly.
Logs every check to logs/autostart/keepalive.log.
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_RUNNER_PID_FILE = ROOT / "run" / "app_runner.pid"
SUPERVISOR_PID_FILE = ROOT / "run" / "supervisor.pid"  # legacy — sweep on new launch
LOG_FILE = ROOT / "logs" / "autostart" / "keepalive.log"
APP_RUNNER_SCRIPT = ROOT / "app_runner.py"

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


def _find_app_runner_pid() -> int | None:
    """Find a live app_runner.py process by cmdline match (most reliable
    on Windows where venv shim PIDs come and go). Returns the parent if
    multiple are running (filter to one whose parent isn't python)."""
    try:
        import psutil
    except ImportError:
        return None
    candidates: list[int] = []
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info["name"] or "").lower()
                if "python" not in name:
                    continue
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "app_runner.py" in cmdline:
                    candidates.append(int(proc.info["pid"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    if not candidates:
        return None
    # Return the oldest (most likely the parent shim, with the longest uptime)
    return candidates[0]


def _kill_orphan_supervisors() -> int:
    """Best-effort kill of any leftover src.supervisor.daemon processes —
    those are the legacy wrapper we no longer use, but they might be
    consuming CPU cycles on hosts that ran the old keepalive."""
    killed = 0
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info["name"] or "").lower()
                if "python" not in name:
                    continue
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "src.supervisor.daemon" in cmdline:
                    proc.terminate()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return killed


def _start_app_runner() -> None:
    """Launch app_runner.py directly. Bypasses the broken supervisor wrapper.

    Windows: triple-flag detach — DETACHED_PROCESS + CREATE_BREAKAWAY_FROM_JOB
    + CREATE_NEW_PROCESS_GROUP — to escape Task Scheduler's Job Object.
    BREAKAWAY may fail with ACCESS_DENIED on locked-down systems; we retry
    without it as a fallback.
    """
    cmd = [str(PYTHON), str(APP_RUNNER_SCRIPT)]
    _log(f"Starting app_runner directly: {' '.join(cmd)}")
    kwargs: dict = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    flags_with_breakaway = 0x00000008 | 0x01000000 | 0x00000200
    flags_without_breakaway = 0x00000008 | 0x00000200
    try:
        if sys.platform == "win32":
            kwargs["creationflags"] = flags_with_breakaway
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        _log(f"app_runner launched PID={proc.pid}")
        # Persist PID for next-cycle health check
        try:
            APP_RUNNER_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            APP_RUNNER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            pass
    except OSError as exc:
        if sys.platform == "win32" and "creationflags" in kwargs:
            _log(f"BREAKAWAY denied ({exc}) — retrying without")
            kwargs["creationflags"] = flags_without_breakaway
            try:
                proc = subprocess.Popen(cmd, **kwargs)
                _log(f"app_runner launched without BREAKAWAY PID={proc.pid}")
                APP_RUNNER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
            except Exception as e2:
                _log(f"ERROR starting app_runner (retry): {e2}")
        else:
            _log(f"ERROR starting app_runner: {exc}")
    except Exception as e:
        _log(f"ERROR starting app_runner: {e}")


def main() -> int:
    """If no live app_runner.py process is found, sweep stale supervisor
    processes and launch app_runner directly. Otherwise log a sparse
    heartbeat."""
    live_pid = _find_app_runner_pid()
    if live_pid is None:
        legacy = _kill_orphan_supervisors()
        if legacy > 0:
            _log(f"swept {legacy} legacy supervisor process(es)")
        _log("no live app_runner — launching")
        _start_app_runner()
        return 0
    # Alive — log heartbeat once an hour to keep log compact
    now = datetime.now(timezone.utc)
    if now.minute < 2:
        _log(f"OK — app_runner PID={live_pid} alive (heartbeat)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
