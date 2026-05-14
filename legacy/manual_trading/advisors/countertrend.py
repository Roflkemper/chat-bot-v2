from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_entry_anchor(snapshot: dict[str, Any]) -> float:
    price = _safe_float(snapshot.get("price"), 0.0)

    execution_plan = snapshot.get("execution_plan") or {}
    if not isinstance(execution_plan, dict):
        return price

    entry_zone = execution_plan.get("entry_zone")

    if entry_zone is None:
        return price

    if isinstance(entry_zone, (list, tuple)):
        if not entry_zone:
            return price
        return _safe_float(entry_zone[0], price)

    return _safe_float(entry_zone, price)


def analyze_countertrend(snapshot: dict[str, Any]) -> dict[str, Any]:
    price = _safe_float(snapshot.get("price"), 0.0)
    atr_pct = _safe_float(snapshot.get("atr_pct"), 0.0)
    ret10_pct = _safe_float(snapshot.get("ret10_pct"), 0.0)
    ret20_pct = _safe_float(snapshot.get("ret20_pct"), 0.0)
    regime = str(snapshot.get("regime") or "unknown").lower()
    range_position = str(snapshot.get("range_position") or "UNKNOWN").upper()
    breakout_risk = str(snapshot.get("breakout_risk") or "LOW").upper()
    false_break_signal = str(snapshot.get("false_break_signal") or "NONE").upper()

    entry_anchor = _extract_entry_anchor(snapshot)
    dist = abs(price - entry_anchor)

    ct_mode = "none"
    ct_advice = "no countertrend edge"
    ct_invalidation = price
    ct_stretch_atr = 0.0
    ct_trade_profile = "wait"
    ct_hold_horizon = "none"
    scalp_only = False
    next_trigger = "ждать более чистую реакцию"

    if atr_pct > 0:
        ct_stretch_atr = dist / atr_pct

    sharp_dump = ret10_pct <= -1.0 or ret20_pct <= -1.8
    sharp_pump = ret10_pct >= 1.0 or ret20_pct >= 1.8

    if false_break_signal == "UP_TRAP":
        ct_mode = "false_break"
        ct_trade_profile = "reversal_short"
        ct_hold_horizon = "intraday" if range_position in {"HIGH_EDGE", "UPPER_PART"} else "scalp"
        ct_advice = "ложный вынос вверх: ждать возврат под high и продавца на retest"
        next_trigger = "закрепление обратно под high / слабый retest вверх"
    elif false_break_signal == "DOWN_TRAP":
        ct_mode = "false_break"
        ct_trade_profile = "reversal_long"
        ct_hold_horizon = "intraday" if range_position in {"LOW_EDGE", "LOWER_PART"} else "scalp"
        ct_advice = "ложный вынос вниз: ждать возврат над low и покупателя на retest"
        next_trigger = "закрепление обратно над low / выкуп после retest"
    elif regime in {"panic", "compression"} and (sharp_dump or sharp_pump):
        ct_mode = "reversal_watch"
        ct_trade_profile = "watch_reclaim"
        ct_hold_horizon = "scalp"
        ct_advice = "рынок импульсный/ломаный: смотреть reclaim / rejection перед контртрендом"
        next_trigger = "сильная встречная свеча + удержание уровня"
    elif ct_stretch_atr >= 1.2:
        ct_mode = "stretch"
        ct_trade_profile = "fade_extreme"
        ct_hold_horizon = "scalp"
        scalp_only = True
        ct_advice = "движение растянуто: контртренд только после подтверждения и без догонки"
        next_trigger = "rejection-свеча или возврат под/над экстремум"
    elif ct_stretch_atr >= 0.6:
        ct_mode = "false_break"
        ct_trade_profile = "watch_trap"
        ct_hold_horizon = "scalp"
        scalp_only = True
        ct_advice = "есть риск ложного пробоя: ждать false break + reclaim"
        next_trigger = "возврат в диапазон после выноса"

    if breakout_risk == "HIGH":
        scalp_only = True
        if ct_trade_profile == "wait":
            ct_trade_profile = "watch_trap"
        ct_hold_horizon = "scalp" if ct_hold_horizon == "none" else ct_hold_horizon

    if sharp_dump:
        ct_invalidation = price * 0.995 if price > 0 else price
    elif sharp_pump:
        ct_invalidation = price * 1.005 if price > 0 else price
    else:
        ct_invalidation = entry_anchor if entry_anchor > 0 else price

    if ct_trade_profile.startswith("reversal_") and not scalp_only and breakout_risk != "HIGH":
        ct_hold_horizon = "intraday"
    elif ct_hold_horizon == "none":
        ct_hold_horizon = "wait"

    return {
        "ct_mode": ct_mode,
        "ct_stretch_atr": round(ct_stretch_atr, 4),
        "ct_advice": ct_advice,
        "ct_invalidation": round(ct_invalidation, 4),
        "ct_trade_profile": ct_trade_profile,
        "ct_hold_horizon": ct_hold_horizon,
        "scalp_only": scalp_only,
        "next_trigger": next_trigger,
    }
