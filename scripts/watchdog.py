"""Unified bot7 watchdog — one file, simple logic, REALLY works.

Заменяет ВСЁ предыдущее:
  - src/supervisor/daemon.py — тихо умирал каждые 2 мин на Windows pythonw
  - scripts/keepalive_check.py — поднимал только app_runner, забывал
    collectors/tracker/state_snapshot/liquidations
  - bot7/__main__.py cmd_start — промежуточный слой добавлял проблем

Что делает:
  Каждый запуск (через Task Scheduler каждые ~2 мин):
    Для каждого компонента (app_runner, tracker, collectors, state_snapshot):
      1. Проверить cmdline psutil — есть ли живой процесс с нужной командой
      2. Проверить свежесть его output-файла (не stale ли)
      3. Если NOT RUNNING — запустить
      4. Если RUNNING + STALE — kill+restart
      5. Если RUNNING + FRESH — alive (ничего не делать)
    Лог в logs/watchdog.log

Запуск:
  Через Windows Task Scheduler:
    Trigger: At system startup + Every 2 minutes
    Action: pythonw.exe C:\\bot7\\scripts\\watchdog.py

Через флаги Windows процессов:
    DETACHED_PROCESS + CREATE_BREAKAWAY_FROM_JOB + CREATE_NEW_PROCESS_GROUP
    → процессы переживают завершение Task Scheduler task'а
    → процессы переживают перезагрузку Windows session
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = ROOT / "logs" / "watchdog.log"
ALERT_STATE = ROOT / "state" / "watchdog_alert_state.json"
# Alert if same component fails-to-start (or stays NOT RUNNING after restart)
# this many consecutive ticks. 3 ticks * 2min = 6 min of unrecoverable down.
ALERT_THRESHOLD = 3

if sys.platform == "win32":
    PYTHON = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not PYTHON.exists():
        PYTHON = Path(sys.executable)
else:
    PYTHON = ROOT / ".venv" / "bin" / "python"
    if not PYTHON.exists():
        PYTHON = Path(sys.executable)


COMPONENTS = {
    "app_runner": {
        "cmd": [str(PYTHON), "app_runner.py"],
        "cmdline_must_contain": "app_runner.py",
        "freshness_file": ROOT / "logs" / "app.log",
        # 2026-05-10 fix: было 5 мин — слишком агрессивно. На тихом рынке +
        # smart-pause приводило к 30 рестартам/час потому что setup_detector
        # не эмитил сетапы и log молчал >5min. Увеличиваем до 15 мин — этого
        # хватит чтобы deriv_live (5min interval) что-то записал между тиками.
        "freshness_max_min": 15,
    },
    "tracker": {
        "cmd": [str(PYTHON), "ginarea_tracker/tracker.py"],
        "cmdline_must_contain": "ginarea_tracker",
        "freshness_file": ROOT / "ginarea_live" / "snapshots.csv",
        "freshness_max_min": 10,
        "stale_pid_files": [ROOT / "ginarea_tracker" / "run" / "tracker.pid"],
    },
    "collectors": {
        "cmd": [str(PYTHON), "-m", "market_collector.collector"],
        "cmdline_must_contain": "market_collector.collector",
        "freshness_file": ROOT / "market_live" / "market_1m.csv",
        "freshness_max_min": 10,
        "stale_pid_files": [ROOT / "market_collector" / "run" / "collector.pid"],
    },
    "state_snapshot": {
        "cmd": [str(PYTHON), "scripts/state_snapshot_loop.py", "--interval-sec", "300"],
        "cmdline_must_contain": "state_snapshot_loop.py",
        "freshness_file": None,
        "freshness_max_min": None,
    },
}


def _log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} | {msg}"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, file=sys.stderr)
    except Exception:
        pass


def _find_running_pid(cmdline_fragment: str) -> Optional[int]:
    """Find first running process matching the cmdline fragment (excluding self)."""
    try:
        import psutil
    except ImportError:
        _log("psutil not installed — cannot check processes")
        return None
    self_pid = os.getpid()
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                pid = int(proc.info["pid"])
                if pid == self_pid:
                    continue
                name = (proc.info["name"] or "").lower()
                if "python" not in name:
                    continue
                cmdline = " ".join(proc.info["cmdline"] or [])
                if cmdline_fragment in cmdline:
                    return pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:
        _log(f"process_iter failed: {exc}")
    return None


def _is_stale(file_path: Optional[Path], max_age_min: Optional[float]) -> tuple[bool, str]:
    """Returns (is_stale, age_str)."""
    if file_path is None or max_age_min is None:
        return False, "n/a"
    if not file_path.exists():
        return True, "missing"
    age_sec = time.time() - file_path.stat().st_mtime
    age_min = age_sec / 60
    return age_min > max_age_min, f"{age_min:.1f}min"


def _kill_pid(pid: int, timeout: float = 5) -> bool:
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
            return True
        except psutil.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except psutil.TimeoutExpired:
                pass
            return True
    except Exception as exc:
        _log(f"kill {pid} failed: {exc}")
        return False


def _cleanup_stale_pid_files(stale_files: Optional[list]) -> None:
    for p in stale_files or []:
        try:
            if p.exists():
                p.unlink()
        except (OSError, AttributeError):
            pass


def _start_component(name: str, cfg: dict) -> Optional[int]:
    """Launch component as detached background process."""
    cmd = cfg["cmd"]
    _cleanup_stale_pid_files(cfg.get("stale_pid_files"))
    kwargs: dict = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB | CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = 0x00000008 | 0x01000000 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, **kwargs)
        try:
            (ROOT / "run").mkdir(exist_ok=True)
            (ROOT / "run" / f"{name}.pid").write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            pass
        return proc.pid
    except OSError as exc:
        # BREAKAWAY denied — retry without
        if sys.platform == "win32" and "creationflags" in kwargs:
            _log(f"{name}: BREAKAWAY denied ({exc}) — retry without")
            kwargs["creationflags"] = 0x00000008 | 0x00000200
            try:
                proc = subprocess.Popen(cmd, **kwargs)
                return proc.pid
            except Exception as exc2:
                _log(f"{name}: failed (retry): {exc2}")
                return None
        _log(f"{name}: failed to start: {exc}")
        return None
    except Exception as exc:
        _log(f"{name}: failed to start: {exc}")
        return None


def _check_and_revive(name: str, cfg: dict) -> str:
    running_pid = _find_running_pid(cfg["cmdline_must_contain"])
    is_stale, age = _is_stale(cfg.get("freshness_file"), cfg.get("freshness_max_min"))

    if running_pid is None:
        _log(f"{name}: NOT RUNNING — starting")
        new_pid = _start_component(name, cfg)
        if new_pid:
            return f"STARTED pid={new_pid}"
        return "FAILED_TO_START"

    if is_stale:
        _log(f"{name}: STALE pid={running_pid} age={age} — kill+restart")
        _kill_pid(running_pid)
        time.sleep(1)
        new_pid = _start_component(name, cfg)
        if new_pid:
            return f"REVIVED old={running_pid} new={new_pid}"
        return "REVIVE_FAILED"

    return f"alive pid={running_pid} age={age}"


def _load_alert_state() -> dict:
    try:
        if ALERT_STATE.exists():
            return json.loads(ALERT_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_alert_state(state: dict) -> None:
    try:
        ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_STATE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def _send_tg_alert(message: str) -> None:
    """Best-effort TG notification via done.py (already-handles env+chunking)."""
    try:
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "done.py"), message],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception as exc:
        _log(f"alert TG send failed: {exc}")


def _track_status_and_alert(name: str, status: str, alert_state: dict) -> dict:
    """If component is FAILED_TO_START or repeatedly NOT RUNNING, alert operator
    once after ALERT_THRESHOLD consecutive bad ticks. Reset counter on recovery."""
    is_bad = status.startswith("FAILED_TO_START") or status.startswith("REVIVE_FAILED")
    key = f"{name}_bad_ticks"
    sent_key = f"{name}_alert_sent"
    if is_bad:
        alert_state[key] = alert_state.get(key, 0) + 1
        if alert_state[key] >= ALERT_THRESHOLD and not alert_state.get(sent_key):
            _send_tg_alert(
                f"⚠ watchdog: {name} не поднимается {alert_state[key]} ticks подряд "
                f"(статус: {status}). Нужна ручная диагностика."
            )
            alert_state[sent_key] = True
    else:
        if alert_state.get(key, 0) > 0 or alert_state.get(sent_key):
            if alert_state.get(sent_key):
                _send_tg_alert(f"✅ watchdog: {name} восстановлен ({status})")
        alert_state[key] = 0
        alert_state[sent_key] = False
    return alert_state


def main() -> int:
    _log("=== watchdog tick ===")
    alert_state = _load_alert_state()
    for name, cfg in COMPONENTS.items():
        try:
            status = _check_and_revive(name, cfg)
            _log(f"  {name}: {status}")
            alert_state = _track_status_and_alert(name, status, alert_state)
        except Exception as exc:
            _log(f"  {name}: ERROR {exc}")
    _save_alert_state(alert_state)
    _log("=== watchdog done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
