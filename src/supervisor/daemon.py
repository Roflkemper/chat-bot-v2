"""Supervisor daemon — manages bot7 child processes.

Launched by: python -m bot7 start  (as a detached background process)
Or directly: python -m src.supervisor.daemon

Responsibilities:
- Start all configured components
- Health-check every 30s (process alive + log not stale)
- Auto-restart on crash (max N times per window, then Telegram alarm)
- Log rotation at 00:00 UTC daily
- Write PID file for each managed process + own PID
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.supervisor.process_config import (
    ALL_COMPONENTS,
    COMPONENTS,
    LOGS_DIR,
    RUN_DIR,
    log_path,
    pid_path,
)
from src.utils.logging_config import CURRENT_DIR, rotate_logs, setup_logging

logger = setup_logging("supervisor")

HEALTH_CHECK_INTERVAL = 30   # seconds
DAEMON_PID_PATH = RUN_DIR / "supervisor.pid"


# ─────────────────────────────────────────────────────────────────────────────
# Telegram alarm (fire-and-forget, no dependency on running app_runner)
# ─────────────────────────────────────────────────────────────────────────────

def _send_telegram_alarm(text: str) -> None:
    try:
        import requests
        from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_IDS
        token = TELEGRAM_BOT_TOKEN
        chat_ids = AUTHORIZED_CHAT_IDS if isinstance(AUTHORIZED_CHAT_IDS, list) else [AUTHORIZED_CHAT_IDS]
        for cid in chat_ids:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": cid, "text": text},
                    timeout=10,
                )
            except Exception:
                pass
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Process state tracker
# ─────────────────────────────────────────────────────────────────────────────

class ManagedProcess:
    def __init__(self, name: str, cfg: dict) -> None:
        self.name = name
        self.cfg  = cfg
        self.proc: subprocess.Popen | None = None
        self.started_at: float | None = None
        self.alarm_sent = False
        # Timestamps of recent crashes (for rate limiting)
        self._crash_times: deque[float] = deque()

    # ── Start ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        # Clear stale internal PID files from the managed process itself
        for stale in self.cfg.get("stale_pid_files", []):
            try:
                p = Path(stale)
                if p.exists():
                    pid = int(p.read_text().strip())
                    if not _pid_alive(pid):
                        p.unlink()
                        logger.debug("%s: removed stale pid file %s", self.name, p)
            except Exception:
                pass

        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        log_file = CURRENT_DIR / self.cfg["log"]
        f = open(log_file, "ab")  # noqa: WPS515 — intentional long-lived file handle
        try:
            self.proc = subprocess.Popen(
                self.cfg["cmd"],
                cwd=str(self.cfg["cwd"]),
                stdout=f,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
        except Exception as exc:
            logger.error("%s: failed to start: %s", self.name, exc)
            self.proc = None
            return

        self.started_at = time.monotonic()
        self.alarm_sent = False
        pid_path(self.name).write_text(str(self.proc.pid))
        logger.info("%s: started (PID=%s)", self.name, self.proc.pid)

    # ── Stop ─────────────────────────────────────────────────────────────────

    def stop(self, timeout: int = 10) -> None:
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=timeout)
            logger.info("%s: stopped", self.name)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            logger.warning("%s: killed (did not stop in %ds)", self.name, timeout)
        except Exception as exc:
            logger.warning("%s: stop error: %s", self.name, exc)
        finally:
            self.proc = None
            p = pid_path(self.name)
            if p.exists():
                p.unlink(missing_ok=True)

    # ── Health ────────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def log_stale(self) -> bool:
        lp = log_path(self.name)
        if not lp.exists():
            return True
        age_min = (time.time() - lp.stat().st_mtime) / 60
        return age_min > self.cfg["health_stale_min"]

    def health(self) -> str:
        """Returns 'OK' | 'STALE' | 'DEAD'."""
        if not self.is_running():
            return "DEAD"
        if self.log_stale():
            return "STALE"
        return "OK"

    def uptime_str(self) -> str:
        if self.started_at is None or not self.is_running():
            return "-"
        secs = int(time.monotonic() - self.started_at)
        h, m = divmod(secs // 60, 60)
        d, h = divmod(h, 24)
        if d:
            return f"{d}d {h}h"
        if h:
            return f"{h}h {m}m"
        return f"{m}m"

    # ── Crash tracking + restart ──────────────────────────────────────────────

    def _prune_crash_times(self) -> None:
        window = self.cfg["restart_window_min"] * 60
        cutoff = time.time() - window
        while self._crash_times and self._crash_times[0] < cutoff:
            self._crash_times.popleft()

    def maybe_restart(self) -> None:
        if self.is_running():
            return

        now = time.time()
        self._prune_crash_times()
        self._crash_times.append(now)
        crashes = len(self._crash_times)
        max_crashes = self.cfg["restart_max"]

        if crashes > max_crashes:
            if not self.alarm_sent:
                msg = (
                    f"🚨 bot7 supervisor: {self.name} crashed {crashes}× "
                    f"in {self.cfg['restart_window_min']} min — auto-restart disabled.\n"
                    f"Run: python -m bot7 restart {self.name}"
                )
                logger.error(msg)
                _send_telegram_alarm(msg)
                self.alarm_sent = True
            return

        logger.warning("%s: dead, restarting (crash %d/%d)", self.name, crashes, max_crashes)
        self.start()


# ─────────────────────────────────────────────────────────────────────────────
# Log rotation thread
# ─────────────────────────────────────────────────────────────────────────────

def _rotation_thread(stop_event: threading.Event) -> None:
    last_day: int | None = None
    while not stop_event.is_set():
        now = datetime.now(tz=timezone.utc)
        today = now.day
        if last_day is not None and today != last_day:
            date_str = now.strftime("%Y-%m-%d")
            logger.info("Rotating logs → archive/%s", date_str)
            try:
                rotate_logs(date_str)
            except Exception as exc:
                logger.error("Log rotation failed: %s", exc)
        last_day = today
        stop_event.wait(60)


# ─────────────────────────────────────────────────────────────────────────────
# Main supervisor loop
# ─────────────────────────────────────────────────────────────────────────────

class Supervisor:
    def __init__(self, components: list[str] | None = None) -> None:
        names = components or ALL_COMPONENTS
        self.procs: dict[str, ManagedProcess] = {
            n: ManagedProcess(n, COMPONENTS[n]) for n in names if n in COMPONENTS
        }
        self._stop = threading.Event()

    def start_all(self) -> None:
        for mp in self.procs.values():
            mp.start()

    def stop_all(self) -> None:
        for mp in self.procs.values():
            mp.stop()

    def run(self) -> None:
        logger.info("Supervisor started (PID=%s)", os.getpid())
        DAEMON_PID_PATH.write_text(str(os.getpid()))

        self.start_all()

        rotation_thread = threading.Thread(
            target=_rotation_thread, args=(self._stop,), daemon=True, name="log-rotator"
        )
        rotation_thread.start()

        def _on_signal(signum, _frame) -> None:
            logger.info("Signal %s received — stopping", signum)
            self._stop.set()

        signal.signal(signal.SIGINT,  _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        while not self._stop.is_set():
            for mp in self.procs.values():
                mp.maybe_restart()
            self._stop.wait(HEALTH_CHECK_INTERVAL)

        logger.info("Supervisor stopping")
        self.stop_all()
        DAEMON_PID_PATH.unlink(missing_ok=True)
        logger.info("Supervisor exited")


# ─────────────────────────────────────────────────────────────────────────────
# Status helpers (used by CLI without running supervisor)
# ─────────────────────────────────────────────────────────────────────────────

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
    # Windows fallback via OpenProcess
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        import ctypes.wintypes
        code = ctypes.wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    # Unix fallback
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _log_last_ts(component: str) -> str:
    lp = log_path(component)
    if not lp.exists() or lp.stat().st_size == 0:
        return "-"
    age_s = int(time.time() - lp.stat().st_mtime)
    if age_s < 60:
        return f"{age_s}s ago"
    if age_s < 3600:
        return f"{age_s // 60}m ago"
    return f"{age_s // 3600}h ago"


def get_status_rows() -> list[dict]:
    """Return status rows for all components (usable without running supervisor)."""
    rows = []
    all_names = ["supervisor"] + ALL_COMPONENTS

    for name in all_names:
        if name == "supervisor":
            p = DAEMON_PID_PATH
            log = CURRENT_DIR / "supervisor.log"
        else:
            p = pid_path(name)
            log = log_path(name)

        pid = _read_pid(p)
        alive = _pid_alive(pid) if pid else False

        if not alive:
            health = "DEAD"
            uptime = "—"
        else:
            cfg = COMPONENTS.get(name, {})
            stale_min = cfg.get("health_stale_min", 5)
            log_age = (time.time() - log.stat().st_mtime) / 60 if log.exists() else 9999
            health = "STALE" if log_age > stale_min else "OK"
            uptime = "running"  # best-effort without start time

        rows.append({
            "component":   name,
            "pid":         pid or "-",
            "health":      health,
            "last_log":    _log_last_ts(name) if name != "supervisor" else "-",
        })

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main(components: list[str] | None = None) -> None:
    sv = Supervisor(components)
    sv.run()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("components", nargs="*", default=None)
    args = p.parse_args()
    main(args.components or None)
