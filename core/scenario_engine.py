from __future__ import annotations

from typing import Any, Dict


def build_wait_scenarios(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    active_block = str(snapshot.get("active_block") or "")
    range_high = snapshot.get("range_high")
    range_low = snapshot.get("range_low")
    pressure = str(snapshot.get("block_pressure") or "NONE")
    pressure_strength = str(snapshot.get("block_pressure_strength") or "LOW")
    range_pos = float(snapshot.get("range_position_pct") or 0.0)
    depth_label = str(snapshot.get("depth_label") or "")
    consensus_votes = str(snapshot.get("consensus_votes") or "0/3")

    if pressure == "NONE":
        return {"active": False}

    if active_block == "SHORT":
        flip_level = range_high
        base_condition = "отбой от верхнего края"
        base_outcome = "SHORT блок остаётся активным"
        alt_condition = f"пробой и закрепление выше {flip_level:.2f}"
        alt_outcome = "SHORT блок инвалидируется, сценарий смещается в LONG"
        trigger_text = f"2 закрытия выше {flip_level:.2f}"
    else:
        flip_level = range_low
        base_condition = "удержание нижнего края"
        base_outcome = "LONG блок остаётся активным"
        alt_condition = f"пробой и закрепление ниже {flip_level:.2f}"
        alt_outcome = "LONG блок инвалидируется, сценарий смещается в SHORT"
        trigger_text = f"2 закрытия ниже {flip_level:.2f}"

    if pressure_strength == "HIGH":
        base_prob, alt_prob = 55, 45
    elif pressure_strength == "MID":
        base_prob, alt_prob = 60, 40
    else:
        base_prob, alt_prob = 70, 30

    if depth_label in {"RISK", "DEEP"} and ((active_block == "SHORT" and range_pos >= 88) or (active_block == "LONG" and range_pos <= 12)):
        base_prob = max(50, base_prob - 5)
        alt_prob = min(50, alt_prob + 5)
    elif consensus_votes == "3/3":
        base_prob = max(50, base_prob - 5)
        alt_prob = min(50, alt_prob + 5)

    return {
        "active": True,
        "base": {
            "name": "BASE",
            "probability": base_prob,
            "condition": base_condition,
            "outcome": base_outcome,
        },
        "alternative": {
            "name": "ALTERNATIVE",
            "probability": alt_prob,
            "condition": alt_condition,
            "outcome": alt_outcome,
        },
        "flip_level": round(float(flip_level), 2) if flip_level is not None else None,
        "flip_confirm_bars": 2,
        "flip_condition_text": trigger_text,
    }
