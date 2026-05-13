"""Watchdog health-of-watchdog monitor.

Spotted incident 2026-05-11 22:02 -> 00:00 (2-hour gap in watchdog.log).
Diagnosis: psutil.process_iter likely hung; Task Scheduler MultipleInstances=IgnoreNew
meant all subsequent triggers were silently dropped.

This script:
  - Reads logs/watchdog.log mtime
  - If > MAX_AGE_MIN (default 8) → TG alert via done.py
  - Records last alert in state/watchdog_health.json so we don't spam every tick

Schedule via Windows Task Scheduler:
  Every 10 minutes, trigger: At system startup + repeat every 10m
  Action: pythonw.exe c:\\bot7\\scripts\\watchdog_health_check.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_LOG = ROOT / "logs" / "watchdog.log"
STATE_PATH = ROOT / "state" / "watchdog_health.json"
DONE_SCRIPT = ROOT / "scripts" / "done.py"

MAX_AGE_MIN = 8        # alert if log not touched in this many minutes
ALERT_REPEAT_MIN = 30  # repeat alert every 30 min while still down


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def _send_tg(msg: str) -> None:
    try:
        subprocess.Popen(
            [sys.executable, str(DONE_SCRIPT), msg],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def main() -> int:
    now = time.time()
    state = _load_state()

    if not WATCHDOG_LOG.exists():
        # nothing we can do — watchdog never wrote
        last_alert_ts = state.get("last_alert_ts", 0)
        if now - last_alert_ts > ALERT_REPEAT_MIN * 60:
            _send_tg("⚠ watchdog_health: logs/watchdog.log не существует. "
                     "Watchdog никогда не запускался?")
            state["last_alert_ts"] = now
            _save_state(state)
        return 1

    age_sec = now - WATCHDOG_LOG.stat().st_mtime
    age_min = age_sec / 60

    if age_min <= MAX_AGE_MIN:
        # healthy — clear alert state if needed
        if state.get("alerted"):
            _send_tg(f"✅ watchdog_health: watchdog восстановлен (log age {age_min:.1f}min)")
            state.pop("alerted", None)
            state["last_recovery_ts"] = now
            _save_state(state)
        return 0

    # stale — send alert if not too soon since last
    last_alert_ts = state.get("last_alert_ts", 0)
    if now - last_alert_ts > ALERT_REPEAT_MIN * 60:
        _send_tg(
            f"🚨 WATCHDOG MOLCHIT {age_min:.0f}min "
            f"(threshold {MAX_AGE_MIN}min). Это значит:\n"
            f"- упавшие сервисы НЕ будут подняты автоматически\n"
            f"- ручной check: tail -20 c:/bot7/logs/watchdog.log\n"
            f"- может зависший pythonw — killall (Task Manager или taskkill)"
        )
        state["last_alert_ts"] = now
        state["alerted"] = True
        _save_state(state)

    return 2


if __name__ == "__main__":
    sys.exit(main())
