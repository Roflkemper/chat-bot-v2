from datetime import datetime
from market_data.price_feed import get_price
from market_data.ohlcv import get_klines
from services.timeframe_aggregator import aggregate_to_4h, aggregate_to_1d
from features.trigger_detection import detect_trigger
from features.forecast import short_term_forecast, session_forecast, medium_forecast, build_consensus
from core.scenario_engine import build_wait_scenarios

NEAR_EDGE_THRESHOLD_PCT = 15.0
HEDGE_BUFFER_USD = 293.0


def _depth_label(depth_pct: float) -> str:
    if depth_pct < 15:
        return "EARLY"
    if depth_pct < 50:
        return "WORK"
    if depth_pct < 85:
        return "RISK"
    return "DEEP"


def _build_range(candles_1h):
    window = candles_1h[-48:] if len(candles_1h) >= 48 else candles_1h
    range_low = min(x["low"] for x in window)
    range_high = max(x["high"] for x in window)
    range_mid = (range_low + range_high) / 2.0
    return range_low, range_high, range_mid


def _consensus_alignment(votes_text: str) -> int:
    try:
        return int(str(votes_text).split('/')[0])
    except Exception:
        return 0


def _context_score(state: str, depth_label: str, scalp_direction: str, active_side: str, candles_1h) -> tuple[int, str, list[str]]:
    score = 0
    details = []
    if depth_label in ("EARLY", "WORK"):
        score += 1
        details.append("глубина подходит для работы")
    last3 = candles_1h[-3:] if len(candles_1h) >= 3 else candles_1h
    if scalp_direction == active_side:
        score += 1
        details.append("скальп смотрит в сторону блока")
    closes_in_side = 0
    for bar in last3:
        if active_side == "LONG" and bar["close"] >= bar["open"]:
            closes_in_side += 1
        if active_side == "SHORT" and bar["close"] <= bar["open"]:
            closes_in_side += 1
    if closes_in_side >= 2:
        score += 1
        details.append("2 из 3 баров закрылись в сторону блока")
    label = "NO CONTEXT"
    if score == 3:
        label = "STRONG"
    elif score == 2:
        label = "VALID"
    elif score == 1:
        label = "WEAK"
    return score, label, details


def _block_pressure(active_side: str, consensus_direction: str, consensus_alignment: int, session_fc: dict, medium_fc: dict):
    if consensus_direction not in ("LONG", "SHORT") or consensus_direction == active_side:
        return "NONE", "LOW", False, ""

    session_high = session_fc.get("direction") == consensus_direction and session_fc.get("strength") == "HIGH"
    medium_against = medium_fc.get("direction") == consensus_direction and medium_fc.get("phase") in ("MARKUP", "MARKDOWN")

    if consensus_alignment == 3 and (session_high or medium_against):
        return "AGAINST", "HIGH", True, "все ТФ против активного блока — возможна смена активной зоны"
    if consensus_alignment == 3:
        return "AGAINST", "MID", True, "все ТФ против активного блока — давление на смену зоны"
    if consensus_alignment == 2 and medium_against:
        return "AGAINST", "LOW", True, "большинство ТФ против блока — давление на смену зоны"
    return "NONE", "LOW", False, ""


def build_full_snapshot(symbol="BTCUSDT"):
    price = get_price(symbol)
    candles_1h = get_klines(symbol=symbol, interval="1h", limit=200)
    candles_4h = aggregate_to_4h(candles_1h)
    candles_1d = aggregate_to_1d(candles_1h)

    range_low, range_high, range_mid = _build_range(candles_1h)
    range_size = max(range_high - range_low, 1e-9)

    if price >= range_mid:
        active_side = "SHORT"
        active_block = "SHORT"
        block_low = range_mid
        block_high = range_high
        distance_to_upper_edge = range_high - price
        distance_to_lower_edge = price - range_low
        edge_distance_pct = max(0.0, ((block_high - price) / max(block_high - block_low, 1e-9)) * 100.0)
    else:
        active_side = "LONG"
        active_block = "LONG"
        block_low = range_low
        block_high = range_mid
        distance_to_upper_edge = range_high - price
        distance_to_lower_edge = price - range_low
        edge_distance_pct = max(0.0, ((price - block_low) / max(block_high - block_low, 1e-9)) * 100.0)

    block_size = max(block_high - block_low, 1e-9)
    block_depth_pct = ((price - block_low) / block_size) * 100.0
    range_position_pct = ((price - range_low) / range_size) * 100.0
    depth_label = _depth_label(block_depth_pct)

    trigger, trigger_type, trigger_note = detect_trigger(candles_1h, active_block, range_low, range_high)

    if price > range_high or price < range_low or block_depth_pct >= 100:
        state = "OVERRUN"
    elif trigger:
        state = "CONFIRMED"
    elif edge_distance_pct <= NEAR_EDGE_THRESHOLD_PCT:
        state = "PRE_ACTIVATION"
    elif depth_label in ("WORK", "RISK"):
        state = "SEARCH_TRIGGER"
    else:
        state = "MID_RANGE"

    short_fc = short_term_forecast(candles_1h)
    session_fc = session_forecast(candles_4h)
    medium_fc = medium_forecast(candles_1d)
    consensus_direction, consensus_confidence, consensus_votes = build_consensus(short_fc, session_fc, medium_fc)
    consensus_alignment = _consensus_alignment(consensus_votes)

    conflict_flag = consensus_direction in ("LONG", "SHORT") and consensus_direction != active_side
    scalp_direction = short_fc["direction"]
    context_score, context_label, context_details = _context_score(state, depth_label, scalp_direction, active_side, candles_1h)
    block_pressure, block_pressure_strength, block_flip_warning, block_pressure_reason = _block_pressure(
        active_side, consensus_direction, consensus_alignment, session_fc, medium_fc
    )

    pre_activation_valid = (
        state == "PRE_ACTIVATION"
        and (not trigger)
        and context_score >= 1
        and block_pressure != "AGAINST"
    )

    trigger_blocked = False
    trigger_block_reason = ""
    trigger_reason_display = trigger_note
    if state == "OVERRUN":
        action = "PROTECT"
        entry_type = None
    elif trigger and state == "CONFIRMED":
        if block_pressure == "AGAINST" or context_score == 0:
            action = "WAIT"
            entry_type = None
            trigger_blocked = True
            if block_pressure == "AGAINST":
                trigger_block_reason = "давление против блока"
            else:
                trigger_block_reason = "нет подтверждённого направления"
        else:
            action = "ENTER"
            entry_type = "ENTER"
    elif pre_activation_valid:
        action = "PREPARE"
        entry_type = "PROBE"
    else:
        action = "WAIT"
        entry_type = None

    hedge_state = "OFF"
    if block_depth_pct > 60:
        hedge_state = "PRE-TRIGGER"
    elif state in ("SEARCH_TRIGGER", "PRE_ACTIVATION"):
        hedge_state = "ARM"
    elif state == "OVERRUN":
        hedge_state = "TRIGGER"

    execution_side = active_side
    execution_confidence = consensus_confidence
    if conflict_flag and execution_confidence == "HIGH":
        execution_confidence = "MID"

    warnings = []
    if trigger_blocked:
        warnings.append(f"БЛОКИРОВКА: {trigger_block_reason}")
    elif conflict_flag:
        warnings.append("forecast против активного блока — не форсировать")
    if scalp_direction != active_side:
        if scalp_direction == "NEUTRAL":
            warnings.append("скальп не подтверждает — краткосрочного импульса нет")
        else:
            warnings.append("скальп против активного блока")
    if trigger_type is None:
        warnings.append("без trigger подтверждения вход запрещён")
    if range_position_pct > 80 or range_position_pct < 20:
        warnings.append("край диапазона — повышенный риск резкого выноса")
    if block_depth_pct > 65:
        warnings.append("глубоко в зоне — риск прошивки")
    if block_pressure == "AGAINST":
        warnings.append("среднесрок и большинство ТФ против блока")

    ginarea = {
        "mode": "PRIORITY_GRID",
        "long_grid": "REDUCE" if execution_side == "SHORT" else "WORK",
        "short_grid": "WORK" if execution_side == "SHORT" else "REDUCE",
        "aggression": "LOW" if action != "ENTER" else "MID",
        "lifecycle": "REDUCE_GRID" if depth_label in ("RISK", "DEEP") else "ARM_GRID" if state in ("SEARCH_TRIGGER", "PRE_ACTIVATION") else "WAIT_GRID",
    }

    snapshot = {
        "symbol": symbol,
        "timestamp": datetime.now().strftime("%H:%M"),
        "tf": "1h",
        "price": round(price, 2),
        "range_low": round(range_low, 2),
        "range_high": round(range_high, 2),
        "range_mid": round(range_mid, 2),
        "range_position_pct": round(range_position_pct, 2),
        "active_block": active_block,
        "active_side": active_side,
        "block_low": round(block_low, 2),
        "block_high": round(block_high, 2),
        "block_depth_pct": round(block_depth_pct, 2),
        "depth_label": depth_label,
        "distance_to_upper_edge": round(distance_to_upper_edge, 2),
        "distance_to_lower_edge": round(distance_to_lower_edge, 2),
        "edge_distance_pct": round(edge_distance_pct, 2),
        "state": state,
        "trigger": trigger,
        "trigger_type": trigger_type,
        "trigger_note": trigger_reason_display,
        "trigger_blocked": trigger_blocked,
        "trigger_block_reason": trigger_block_reason,
        "action": action,
        "entry_type": entry_type,
        "hedge_state": hedge_state,
        "hedge_arm_up": round(range_high + HEDGE_BUFFER_USD, 2),
        "hedge_arm_down": round(range_low - HEDGE_BUFFER_USD, 2),
        "forecast": {
            "short": short_fc,
            "session": session_fc,
            "medium": medium_fc,
        },
        "consensus_direction": consensus_direction,
        "consensus_confidence": consensus_confidence,
        "consensus_votes": consensus_votes,
        "consensus_alignment": consensus_alignment,
        "execution_side": execution_side,
        "execution_confidence": execution_confidence,
        "conflict_flag": conflict_flag,
        "context_score": context_score,
        "context_label": context_label,
        "context_details": context_details,
        "block_pressure": block_pressure,
        "block_pressure_strength": block_pressure_strength,
        "block_flip_warning": block_flip_warning,
        "block_pressure_reason": block_pressure_reason,
        "warnings": warnings,
        "ginarea": ginarea,
    }
    snapshot["scenario"] = build_wait_scenarios(snapshot)
    return snapshot
