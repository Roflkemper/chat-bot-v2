from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from utils.safe_io import atomic_write_json, safe_read_json

POSITION_STATE_FILE = "storage/position_state.json"


def _directional_default() -> Dict[str, Any]:
    return {
        "has_position": False,
        "state": "NONE",
        "side": None,
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "entry_price": None,
        "opened_at": None,
        "comment": None,
    }


def _grid_default() -> Dict[str, Any]:
    return {
        "active": False,
        "state": "GRID_IDLE",
        "symbol": "BTCUSDT",
        "mode": "PRIORITY_GRID",
        "comment": None,
    }


def _default_state() -> Dict[str, Any]:
    return {"directional": _directional_default(), "grid": _grid_default()}


def load_position_state() -> Dict[str, Any]:
    state = safe_read_json(POSITION_STATE_FILE, _default_state())
    state.setdefault("directional", _directional_default())
    state.setdefault("grid", _grid_default())
    # backward-compatible flat aliases for older readers
    flat = dict(state["directional"])
    flat.update({"directional": state["directional"], "grid": state["grid"]})
    return flat


def save_position_state(state: Dict[str, Any]) -> None:
    safe_state = _default_state()
    if isinstance(state, dict):
        for key in ("directional", "grid"):
            if isinstance(state.get(key), dict):
                safe_state[key].update(state[key])
    atomic_write_json(POSITION_STATE_FILE, safe_state)


def open_position(side: str, symbol: str = "BTCUSDT", timeframe: str = "1h", entry_price: Any = None, comment: Optional[str] = None) -> Dict[str, Any]:
    state = load_position_state()
    state["directional"].update({
        "has_position": True,
        "state": "ENTERED",
        "side": str(side).upper(),
        "symbol": symbol,
        "timeframe": timeframe,
        "entry_price": entry_price,
        "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "comment": comment,
    })
    save_position_state(state)
    return state


def close_position() -> Dict[str, Any]:
    state = load_position_state()
    state["directional"] = _directional_default()
    save_position_state(state)
    return state
