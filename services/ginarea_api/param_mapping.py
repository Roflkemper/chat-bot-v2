from __future__ import annotations

from copy import deepcopy
from typing import Any

UI_TO_API: dict[str, str] = {
    "grid_step": "gs",
    "grid_step_ratio": "gsr",
    "max_trigger_number": "maxOp",
    "order_size_min": "q.minQ",
    "order_size_max": "q.maxQ",
    "order_size_ratio": "q.qr",
    "in_stop": "gap.isg",
    "target_distance": "gap.tog",
    "min_stop_profit": "gap.minS",
    "max_stop_profit": "gap.maxS",
    "trading_direction": "side",
    "percentage_mode": "p",
    "border_bottom": "border.bottom",
    "border_top": "border.top",
    "disable_in": "dsblin",
    "disable_in_out_of_range": "dsblinbtr",
    "disable_in_by_avg_price": "dsblinbap",
    "out_by_avg_price": "obap",
    "remember_in_stop": "ris",
    "liquidation_stop_loss": "lsl",
    "total_stop_loss": "tsl",
    "take_profit": "ttp",
    "tp_autoupdate": "ttpinc",
    "stop_loss_trailing": "slt",
    "custom_fee": "cf",
    "hedge": "hedge",
    "leverage": "leverage",
}
API_TO_UI: dict[str, str] = {value: key for key, value in UI_TO_API.items()}


def get_param(params_dict: dict[str, Any], ui_key: str) -> object:
    path = UI_TO_API[ui_key]
    current: Any = params_dict
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def set_param(params_dict: dict[str, Any], ui_key: str, value: Any) -> dict[str, Any]:
    result = deepcopy(params_dict)
    path = UI_TO_API[ui_key].split(".")
    current: dict[str, Any] = result
    for part in path[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[path[-1]] = value
    return result
