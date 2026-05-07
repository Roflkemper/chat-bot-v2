"""Process definitions for bot7 supervisor."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_DIR  = ROOT / "run"
LOGS_DIR = ROOT / "logs" / "current"

# component_name → config dict
#
# 2026-05-07: добавлен cmdline_must_contain для всех компонентов. Без него
# is_running() в daemon.py не может детектить живой процесс через psutil
# fallback когда Windows venv shim exits. Это вызывало бесконечный цикл
# false-DEAD restart'ов каждые 5 минут — все 3 процесса одновременно.
# fragment = unique substring в command line, по которому psutil находит
# процесс среди всех python.exe.
COMPONENTS: dict[str, dict] = {
    "app_runner": {
        "cmd":               [sys.executable, "app_runner.py"],
        "cwd":               ROOT,
        "log":               "app_runner.log",
        "cmdline_must_contain": "app_runner.py",
        "health_stale_min":  5,    # log must be updated within N min
        "restart_max":       3,    # max restarts before alarm
        "restart_window_min": 10,  # ...within this window
    },
    "tracker": {
        "cmd":               [sys.executable, "ginarea_tracker/tracker.py"],
        "cwd":               ROOT,
        "log":               "tracker.log",
        "cmdline_must_contain": "ginarea_tracker",
        "health_stale_min":  15,
        "restart_max":       3,
        "restart_window_min": 10,
        # Stale PID files to unlink before restart (tracker writes its own lock)
        "stale_pid_files":   [ROOT / "ginarea_tracker" / "run" / "tracker.pid"],
    },
    "collectors": {
        "cmd":               [sys.executable, "-m", "market_collector.collector"],
        "cwd":               ROOT,
        "log":               "collectors.log",
        "cmdline_must_contain": "market_collector.collector",
        "health_stale_min":  5,
        "restart_max":       3,
        "restart_window_min": 10,
        "stale_pid_files":   [ROOT / "market_collector" / "run" / "collector.pid"],
    },
    "state_snapshot": {
        # 2026-05-07: replaces bot7-state-snapshot scheduled task. Was disabled
        # for orphan-cleanup, never re-enabled — paper_journal stale 4900s.
        # Now managed by supervisor → always restarts on crash.
        "cmd":               [sys.executable, "scripts/state_snapshot_loop.py", "--interval-sec", "300"],
        "cwd":               ROOT,
        "log":               "state_snapshot.log",
        "cmdline_must_contain": "state_snapshot_loop.py",
        "health_stale_min":  10,
        "restart_max":       3,
        "restart_window_min": 10,
    },
}

ALL_COMPONENTS = list(COMPONENTS.keys())


def pid_path(component: str) -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    return RUN_DIR / f"{component}.pid"


def log_path(component: str) -> Path:
    return LOGS_DIR / COMPONENTS[component]["log"]
