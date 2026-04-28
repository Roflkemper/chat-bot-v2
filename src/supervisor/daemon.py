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

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

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
LOCK_PATH = RUN_DIR / "supervisor.lock"
MEMORY_WARN_MB    = 300     # WARNING threshold
MEMORY_ALARM_MB   = 500     # ALARM threshold (Telegram)
MEMORY_RESTART_MB = 800     # auto-restart threshold (app_runner only)


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
# Orphan-kill helpers (TZ-045)
# ─────────────────────────────────────────────────────────────────────────────

def _kill_process_tree(root_pid: int, name: str, timeout: int = 10) -> None:
    """SIGTERM → wait → SIGKILL for root_pid and all its descendants."""
    if psutil is not None:
        try:
            parent = psutil.Process(root_pid)
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            return
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
        gone, alive = psutil.wait_procs([parent] + children, timeout=timeout)
        for proc in alive:
            try:
                proc.kill()
                logger.warning("%s: force-killed PID=%d (SIGKILL)", name, proc.pid)
            except psutil.NoSuchProcess:
                pass
        logger.info("%s: process tree stopped (root PID=%d)", name, root_pid)
    else:
        # psutil unavailable — fall back to plain terminate()
        try:
            os.kill(root_pid, signal.SIGTERM)
            for _ in range(timeout * 10):
                try:
                    os.kill(root_pid, 0)
                except OSError:
                    break
                time.sleep(0.1)
            else:
                os.kill(root_pid, signal.SIGKILL)
        except OSError:
            pass
        logger.info("%s: stopped (no psutil fallback, root PID=%d)", name, root_pid)


def _kill_cmdline_matching(fragment: str, name: str) -> None:
    """Kill ALL Python processes whose cmdline contains fragment (any PID).

    Used before start() and after stop() to sweep orphans that escaped
    the process tree (e.g. Windows venv shim grandchildren).
    """
    if psutil is None:
        return
    killed = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pname = (proc.name() or "").lower()
            if "python" not in pname:
                continue
            cmdline = " ".join(proc.cmdline() or [])
            if fragment not in cmdline:
                continue
            if proc.pid == os.getpid():
                continue  # never kill the supervisor itself
            proc.terminate()
            killed.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception:
            pass
    if killed:
        # Brief wait, then SIGKILL survivors
        time.sleep(1.0)
        for pid in killed:
            try:
                p = psutil.Process(pid)
                if p.is_running():
                    p.kill()
                    logger.warning("%s: force-killed orphan PID=%d (SIGKILL)", name, pid)
            except Exception:
                pass
        logger.info("%s: killed %d cmdline-matching orphan(s): %s", name, len(killed), killed)


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
        # Kill ALL running processes whose cmdline matches this component — not just
        # the one recorded in the PID file. This is the primary defence against orphan
        # accumulation: every deploy/restart cycle calls start(), which now sweeps
        # pre-existing instances before launching a fresh one.
        fragment = self.cfg.get("cmdline_must_contain")
        if fragment:
            _kill_cmdline_matching(fragment, self.name)

        # Clear internal lock files written by the managed process itself.
        for stale in self.cfg.get("stale_pid_files", []):
            try:
                p = Path(stale)
                if not p.exists():
                    continue
                pid = int(p.read_text().strip())
                if _pid_alive(pid):
                    logger.warning(
                        "%s: orphan process PID=%d holds lock %s — sending SIGTERM",
                        self.name, pid, p.name,
                    )
                    os.kill(pid, signal.SIGTERM)
                    for _ in range(10):
                        if not _pid_alive(pid):
                            break
                        time.sleep(0.1)
                p.unlink(missing_ok=True)
                logger.debug("%s: removed lock file %s", self.name, p)
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
            _kill_process_tree(self.proc.pid, self.name, timeout=timeout)
        except Exception as exc:
            logger.warning("%s: stop error: %s", self.name, exc)
        finally:
            self.proc = None
            p = pid_path(self.name)
            if p.exists():
                p.unlink(missing_ok=True)
        # Second pass: kill any stragglers matching the configured cmdline fragment.
        # Catches grandchildren that escaped the process tree (Windows venv shim).
        fragment = self.cfg.get("cmdline_must_contain")
        if fragment:
            _kill_cmdline_matching(fragment, self.name)

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
# Memory snapshot thread (TZ-045)
# ─────────────────────────────────────────────────────────────────────────────

_MEMORY_SNAPSHOT_INTERVAL = 600  # 10 minutes


def _get_real_proc(shim: "psutil.Process") -> "psutil.Process":
    """On Windows each component = venv shim + real interpreter child.
    Return the child with the highest RSS (real interpreter), or shim itself.
    """
    try:
        children = shim.children(recursive=False)
        if children:
            # Pick the child with highest RSS (the real interpreter, not another shim)
            return max(children, key=lambda p: p.memory_info().rss)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return shim


def _memory_snapshot_thread(
    procs: dict[str, "ManagedProcess"],
    stop_event: threading.Event,
) -> None:
    """Log RSS of every managed process every 10 min.

    Tracks grandchild (real Python interpreter) not the venv shim, because on
    Windows each component has: shim (~4 MB) + real interpreter (60-900 MB).
    Thresholds: WARNING 300 MB, ALARM 500 MB, auto-restart 800 MB (app_runner).
    """
    if psutil is None:
        logger.warning("memory-monitor: psutil not available — disabled")
        return

    mem_log = CURRENT_DIR / "memory.log"
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)

    while not stop_event.is_set():
        stop_event.wait(_MEMORY_SNAPSHOT_INTERVAL)
        if stop_event.is_set():
            break

        lines = []
        for name, mp in procs.items():
            if mp.proc is None or mp.proc.poll() is not None:
                continue
            try:
                shim = psutil.Process(mp.proc.pid)
                real = _get_real_proc(shim)
                rss_mb = real.memory_info().rss / 1024 / 1024
                shim_note = f" (shim={mp.proc.pid}→real={real.pid})" if real.pid != mp.proc.pid else ""
                lines.append(f"{name} PID={real.pid} RSS={rss_mb:.1f}MB{shim_note}")

                if rss_mb >= MEMORY_RESTART_MB and name == "app_runner":
                    msg = (
                        f"MEMORY CRITICAL: {name} PID={real.pid} RSS={rss_mb:.0f}MB "
                        f">= {MEMORY_RESTART_MB}MB — auto-restarting"
                    )
                    logger.error(msg)
                    _send_telegram_alarm(f"bot7: {msg}")
                    # Restart by stopping and letting the supervisor loop restart it
                    try:
                        mp.stop()
                    except Exception as exc:
                        logger.error("auto-restart stop failed: %s", exc)
                elif rss_mb >= MEMORY_ALARM_MB:
                    msg = (
                        f"MEMORY ALARM: {name} PID={real.pid} RSS={rss_mb:.0f}MB "
                        f">= {MEMORY_ALARM_MB}MB"
                    )
                    logger.error(msg)
                    _send_telegram_alarm(f"bot7: {msg}")
                elif rss_mb >= MEMORY_WARN_MB:
                    logger.warning("[memory] %s", lines[-1])
                else:
                    logger.debug("[memory] %s", lines[-1])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if lines:
            ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                with mem_log.open("a", encoding="utf-8") as f:
                    f.write(f"{ts}  " + "  |  ".join(lines) + "\n")
            except Exception:
                pass


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

        memory_thread = threading.Thread(
            target=_memory_snapshot_thread, args=(self.procs, self._stop),
            daemon=True, name="memory-monitor",
        )
        memory_thread.start()

        def _on_signal(signum, _frame) -> None:
            logger.info("Signal %s received — stopping", signum)
            self._stop.set()

        signal.signal(signal.SIGINT,  _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        _ticks = 0
        while not self._stop.is_set():
            for mp in self.procs.values():
                mp.maybe_restart()
            _ticks += 1
            if _ticks % 10 == 0:  # every 10 × 30s = 5 min
                logger.info("[heartbeat] alive, managed=%d", len(self.procs))
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
    if psutil is not None:
        return psutil.pid_exists(pid)
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


def _pid_alive_for(pid: int, cmdline_must_contain: str | None = None) -> bool:
    """Check if PID is alive AND (optionally) its cmdline contains the expected fragment.

    Prevents false-alive when a PID is recycled to a different process.
    Falls back to plain _pid_alive if cmdline check is unavailable.
    """
    if not _pid_alive(pid):
        return False
    if not cmdline_must_contain:
        return True
    # Try WMI on Windows (no psutil required)
    if sys.platform == "win32":
        try:
            import subprocess as _sp
            result = _sp.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/value"],
                capture_output=True, text=True, timeout=3,
            )
            return cmdline_must_contain in result.stdout
        except Exception:
            pass
    # Unix: read /proc/PID/cmdline
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
        return cmdline_must_contain in cmdline
    except Exception:
        pass
    # Fallback: can't validate cmdline, assume alive if PID exists
    return True


def _log_last_ts_path(lp: Path) -> str:
    if not lp.exists() or lp.stat().st_size == 0:
        return "-"
    age_s = int(time.time() - lp.stat().st_mtime)
    if age_s < 60:
        return f"{age_s}s ago"
    if age_s < 3600:
        return f"{age_s // 60}m ago"
    return f"{age_s // 3600}h ago"


def _log_last_ts(component: str) -> str:
    return _log_last_ts_path(log_path(component))


_WATCHDOG_PID_PATH = RUN_DIR / "watchdog.pid"
_WATCHDOG_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "autostart" / "watchdog.log"


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
        cfg = COMPONENTS.get(name, {})
        cmdline_check = cfg.get("cmdline_must_contain") if name != "supervisor" else None
        alive = _pid_alive_for(pid, cmdline_check) if pid else False

        if not alive:
            health = "DEAD"
        else:
            stale_min = cfg.get("health_stale_min", 5)
            log_age = (time.time() - log.stat().st_mtime) / 60 if log.exists() else 9999
            health = "STALE" if log_age > stale_min else "OK"

        rows.append({
            "component":   name,
            "pid":         pid or "-",
            "health":      health,
            "last_log":    _log_last_ts(name) if name != "supervisor" else "-",
        })

    # Watchdog: independent process (not managed by supervisor — by design).
    # Read-only status row based on its PID file written at watchdog startup.
    wd_pid = _read_pid(_WATCHDOG_PID_PATH)
    wd_alive = _pid_alive(wd_pid) if wd_pid else False
    if wd_alive:
        wd_log_age = (time.time() - _WATCHDOG_LOG_PATH.stat().st_mtime) / 60 if _WATCHDOG_LOG_PATH.exists() else 9999
        wd_health = "STALE" if wd_log_age > 10 else "OK"  # watchdog heartbeats every 5 min
    else:
        wd_health = "DEAD"
    wd_last_log = _log_last_ts_path(_WATCHDOG_LOG_PATH)
    rows.append({
        "component": "watchdog",
        "pid":       wd_pid or "-",
        "health":    wd_health,
        "last_log":  wd_last_log,
    })

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _acquire_lock() -> bool:
    """Return True if this process acquired the lock; False if another supervisor is running."""
    if LOCK_PATH.exists():
        pid = _read_pid(LOCK_PATH)
        if pid and _pid_alive(pid):
            logger.warning("Another supervisor already running (PID=%s) — exiting duplicate", pid)
            return False
        LOCK_PATH.unlink(missing_ok=True)
    LOCK_PATH.write_text(str(os.getpid()))
    return True


def main(components: list[str] | None = None) -> None:
    if not _acquire_lock():
        sys.exit(1)
    try:
        sv = Supervisor(components)
        sv.run()
    finally:
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("components", nargs="*", default=None)
    args = p.parse_args()
    main(args.components or None)
