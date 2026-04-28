"""Process definitions for bot7 supervisor."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_DIR  = ROOT / "run"
LOGS_DIR = ROOT / "logs" / "current"

# component_name → config dict
COMPONENTS: dict[str, dict] = {
    "app_runner": {
        "cmd":               [sys.executable, "app_runner.py"],
        "cwd":               ROOT,
        "log":               "app_runner.log",
        "health_stale_min":  5,    # log must be updated within N min
        "restart_max":       3,    # max restarts before alarm
        "restart_window_min": 10,  # ...within this window
    },
    "tracker": {
        "cmd":               [sys.executable, "ginarea_tracker/tracker.py"],
        "cwd":               ROOT,
        "log":               "tracker.log",
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
        "health_stale_min":  5,
        "restart_max":       3,
        "restart_window_min": 10,
        "stale_pid_files":   [ROOT / "market_collector" / "run" / "collector.pid"],
    },
}

ALL_COMPONENTS = list(COMPONENTS.keys())


def pid_path(component: str) -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    return RUN_DIR / f"{component}.pid"


def log_path(component: str) -> Path:
    return LOGS_DIR / COMPONENTS[component]["log"]
