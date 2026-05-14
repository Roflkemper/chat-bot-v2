"""Paper trader v0.1 — opens/closes paper trades from setup_detector signals.

See trader.py for the public API.
"""
from services.paper_trader.trader import (
    PAPER_NOTIONAL_USD,
    CONFIDENCE_THRESHOLD,
    open_paper_trade,
    update_open_trades,
    daily_summary,
)

__all__ = [
    "PAPER_NOTIONAL_USD",
    "CONFIDENCE_THRESHOLD",
    "open_paper_trade",
    "update_open_trades",
    "daily_summary",
]
