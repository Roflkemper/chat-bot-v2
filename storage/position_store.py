from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from utils.safe_io import atomic_write_json, safe_read_json

POSITION_STATE_FILE = "position_state.json"


def _default_state() -> Dict[str, Any]:
    return {"has_position": False, "side": None, "symbol": "BTCUSDT", "timeframe": "1h", "entry_price": None, "opened_at": None, "comment": None}


def load_position_state() -> Dict[str, Any]:
    return safe_read_json(POSITION_STATE_FILE, _default_state())


def save_position_state(state: Dict[str, Any]) -> None:
    safe_state = _default_state()
    if isinstance(state, dict):
        safe_state.update(state)
    atomic_write_json(POSITION_STATE_FILE, safe_state)


def open_position(side: str, symbol: str = "BTCUSDT", timeframe: str = "1h", entry_price: Any = None, comment: Optional[str] = None) -> Dict[str, Any]:
    state = {"has_position": True, "side": str(side).upper(), "symbol": symbol, "timeframe": timeframe, "entry_price": entry_price, "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "comment": comment}
    save_position_state(state)
    return state


def close_position() -> Dict[str, Any]:
    state = _default_state()
    save_position_state(state)
    return state
