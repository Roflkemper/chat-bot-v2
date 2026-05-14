"""Stale data monitor — sends Telegram alert if critical data sources go stale."""
from services.stale_monitor.monitor import stale_monitor_loop

__all__ = ["stale_monitor_loop"]
