from datetime import datetime

from market_data.price_feed import get_price
from market_data.ohlcv import get_klines
from services.timeframe_aggregator import aggregate_to_4h, aggregate_to_1d
from features.basic_metrics import atr
from features.trigger_detection import detect_trigger
from features.forecast import short_term_forecast, session_forecast, medium_forecast, build_consensus

NEAR_EDGE_THRESHOLD_PCT = 15.0
HEDGE_BUFFER_USD = 293.0
MIN_SL_BUFFER_USD = 50.0
SCALE_IN_DEPTH_LIMIT_PCT = 70.0
PARTIAL_ENTRY_RANGE = "30-50%"


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


def _two_of_last_three_in_side(candles_1h, side: str) -> bool:
    last_three = candles_1h[-3:]
    if len(last_three) < 3 or side not in {"LONG", "SHORT"}:
        return False
    aligned = 0
    for bar in last_three:
        if side == "LONG" and bar["close"] > bar["open"]:
            aligned += 1
        elif side == "SHORT" and bar["close"] < bar["open"]:
            aligned += 1
    return aligned >= 2


def _forecast_alignment(consensus_direction: str, active_side: str) -> str:
    if consensus_direction == active_side:
        return "ALIGNED"
    if consensus_direction in {"LONG", "SHORT"} and consensus_direction != active_side:
        return "AGAINST"
    return "NEUTRAL"


def _context_grade(depth_label: str, scalp_direction: str, active_side: str, candles_1h) -> dict:
    hits = []
    if depth_label in ("EARLY", "WORK"):
        hits.append("depth_label")
    if scalp_direction == active_side:
        hits.append("scalp_direction")
    if _two_of_last_three_in_side(candles_1h, active_side):
        hits.append("bar_alignment")
    score = len(hits)
    label = {
        3: "STRONG CONTEXT",
        2: "VALID CONTEXT",
        1: "WEAK CONTEXT",
        0: "NO CONTEXT",
    }[score]
    return {
        "score": score,
        "label": label,
        "details": hits,
        "valid": score >= 1,
    }


def _pick_primary_secondary_context(conflict_flag: bool, scalp_direction: str, active_side: str,
                                    trigger_type: str | None, range_position_pct: float,
                                    block_depth_pct: float, context_score: int) -> tuple[str | None, list[str], list[str]]:
    primary = None
    secondary = []
    context = []

    if conflict_flag:
        primary = "forecast против активного блока"
    if scalp_direction != active_side:
        if scalp_direction == "NEUTRAL":
            secondary.append("скальп не подтверждает — краткосрочного импульса нет")
        else:
            secondary.append("скальп против активного блока")
    if trigger_type is None:
        secondary.append("без trigger подтверждения вход запрещён")
    if context_score == 1:
        secondary.append("только 1 из 3 условий valid trigger context выполнено")
    if range_position_pct > 80:
        context.append("край диапазона — повышенный риск резкого выноса")
    if block_depth_pct > 65:
        context.append("глубоко в зоне — риск прошивки")

    return primary, secondary, context


def _entry_quality(trigger_detected: bool, trigger_type: str | None, context_score: int,
                   depth_label: str, scalp_direction: str, active_side: str,
                   forecast_alignment: str, trigger_blocked: bool, action: str) -> tuple[str, str]:
    if trigger_blocked or action == "WAIT" and context_score == 0:
        return "NO_TRADE", "вход запрещён: нет рабочего контекста или trigger заблокирован"
    if not trigger_detected and trigger_type is None:
        return "NO_TRADE", "нет trigger сигнала"

    clean_trigger = trigger_detected or trigger_type in {"RECLAIM", "FAKE_BREAK"}
    micro_ok = scalp_direction == active_side
    good_depth = depth_label in {"EARLY", "WORK"}

    if clean_trigger and context_score == 3 and good_depth and micro_ok and forecast_alignment == "ALIGNED":
        return "A", "чистый trigger, сильный контекст, micro подтверждает"
    if clean_trigger and context_score >= 2 and good_depth:
        return "B", "рабочий trigger и валидный контекст"
    if clean_trigger and context_score >= 1:
        return "C", "вход допустим, но контекст слабый или пограничный"
    return "NO_TRADE", "сетап не оправдывает вход"


def _execution_profile(entry_quality: str, context_score: int, forecast_alignment: str,
                       depth_label: str, action: str) -> tuple[str, str]:
    if action == "WAIT" or entry_quality == "NO_TRADE":
        return "NO_ENTRY", "вход не разрешён"
    if forecast_alignment == "ALIGNED" and entry_quality == "A" and context_score == 3 and depth_label not in {"RISK", "DEEP"}:
        return "AGGRESSIVE", "максимально сильный сетап без конфликта"
    if forecast_alignment == "NEUTRAL":
        return "STANDARD", "forecast нейтрален — aggressive не разрешён"
    if forecast_alignment == "AGAINST":
        return ("CONSERVATIVE", "forecast против блока — вход только аккуратно") if entry_quality in {"A", "B"} else ("PROBE_ONLY", "forecast против блока и слабое качество входа")
    if entry_quality in {"A", "B"}:
        return "STANDARD", "рабочий сетап без необходимости форсировать"
    return "PROBE_ONLY", "слабый сетап — только пробный вход"


def _risk_and_scaling(entry_quality: str, context_score: int, depth_label: str, block_depth_pct: float,
                      forecast_alignment: str, action: str) -> tuple[str, bool, bool]:
    if action == "WAIT" or entry_quality == "NO_TRADE":
        return "MINIMAL", False, False
    partial = entry_quality in {"B", "C"} or forecast_alignment == "AGAINST" or context_score < 3
    partial = bool(partial)
    scale_allowed = False
    if action in {"PREPARE", "ENTER"} and depth_label not in {"RISK", "DEEP"} and block_depth_pct <= SCALE_IN_DEPTH_LIMIT_PCT:
        scale_allowed = entry_quality in {"A", "B"} and context_score >= 2
    risk_mode = "FULL" if entry_quality == "A" and context_score == 3 and forecast_alignment == "ALIGNED" else "REDUCED" if entry_quality in {"A", "B", "C"} else "MINIMAL"
    return risk_mode, partial, scale_allowed


def _trade_plan(snapshot: dict, candles_1h, execution_profile: str) -> dict | None:
    if snapshot["action"] not in {"PREPARE", "ENTER"} or snapshot["entry_quality"] == "NO_TRADE":
        return None

    mode = "GRID" if snapshot.get("ginarea", {}).get("mode") == "PRIORITY_GRID" else "DIRECTIONAL"
    price = snapshot["price"]
    block_low = snapshot["block_low"]
    block_high = snapshot["block_high"]
    range_low = snapshot["range_low"]
    range_high = snapshot["range_high"]
    side = snapshot["execution_side"]
    atr_1h = atr(candles_1h[-20:], 14)
    sl_buffer = max(MIN_SL_BUFFER_USD, atr_1h * 0.5)

    if mode == "GRID":
        if side == "SHORT":
            invalidation = round(block_high + sl_buffer, 2)
            reduce_trigger = round(block_low + (block_high - block_low) * 0.35, 2)
            close_trigger = round(range_low + (range_high - range_low) * 0.2, 2)
        else:
            invalidation = round(block_low - sl_buffer, 2)
            reduce_trigger = round(block_high - (block_high - block_low) * 0.35, 2)
            close_trigger = round(range_high - (range_high - range_low) * 0.2, 2)
        return {
            "mode": mode,
            "entry_zone_low": round(block_low, 2),
            "entry_zone_high": round(block_high, 2),
            "entry_type": "LIMIT" if execution_profile != "CONSERVATIVE" else "CONFIRMATION",
            "entry_comment": "работать от активного края сетки без directional TP/SL",
            "invalidation_level": invalidation,
            "profit_target_usd": round(max(150.0, atr_1h * 0.6), 2),
            "reduce_trigger": reduce_trigger,
            "grid_close_trigger": close_trigger,
            "lifecycle_mode": "REDUCE_GRID" if snapshot["depth_label"] in {"RISK", "DEEP"} else "ARM_GRID",
            "summary": "GRID PLAN: использовать invalidation / reduce / close trigger вместо классических TP/SL",
        }

    block_size = max(block_high - block_low, 1e-9)
    if execution_profile == "AGGRESSIVE":
        entry_type = "MARKET"
        zone_low = block_high - block_size * 0.15 if side == "SHORT" else block_low
        zone_high = block_high if side == "SHORT" else block_low + block_size * 0.15
    elif execution_profile == "STANDARD":
        entry_type = "LIMIT"
        zone_low = block_high - block_size * 0.35 if side == "SHORT" else block_low
        zone_high = block_high if side == "SHORT" else block_low + block_size * 0.35
    elif execution_profile == "CONSERVATIVE":
        entry_type = "CONFIRMATION"
        zone_low = block_high - block_size * 0.25 if side == "SHORT" else block_low
        zone_high = block_high if side == "SHORT" else block_low + block_size * 0.25
    else:
        entry_type = "LIMIT"
        zone_low = block_high - block_size * 0.10 if side == "SHORT" else block_low
        zone_high = block_high if side == "SHORT" else block_low + block_size * 0.10

    if side == "SHORT":
        sl_price = round(block_high + sl_buffer, 2)
        tp1 = round((range_low + range_high) / 2.0, 2)
        tp2 = round(range_low, 2)
        invalidation_type = "BLOCK_BREAK"
        entry_comment = "вход от верхнего блока после реакции" if entry_type != "CONFIRMATION" else "ждать реакцию и подтверждение перед входом"
    else:
        sl_price = round(block_low - sl_buffer, 2)
        tp1 = round((range_low + range_high) / 2.0, 2)
        tp2 = round(range_high, 2)
        invalidation_type = "BLOCK_BREAK"
        entry_comment = "вход от нижнего блока после реакции" if entry_type != "CONFIRMATION" else "ждать реакцию и подтверждение перед входом"

    be_trigger_r = {
        "AGGRESSIVE": 1.0,
        "STANDARD": 1.0,
        "CONSERVATIVE": 0.8,
        "PROBE_ONLY": None,
    }.get(execution_profile)
    management_mode = "FAST_SCALP" if execution_profile == "AGGRESSIVE" else "INTRADAY" if snapshot["trigger_context_score"] >= 2 else "DEFENSIVE"

    return {
        "mode": mode,
        "entry_zone_low": round(min(zone_low, zone_high), 2),
        "entry_zone_high": round(max(zone_low, zone_high), 2),
        "entry_type": entry_type,
        "entry_comment": entry_comment,
        "tp1_price": tp1,
        "tp2_price": tp2,
        "tp_strategy": "PARTIAL + HOLD",
        "sl_price": sl_price,
        "sl_buffer": round(sl_buffer, 2),
        "invalidation_type": invalidation_type,
        "be_trigger_r": be_trigger_r,
        "partial_tp_r": 1.0,
        "management_mode": management_mode,
        "trade_plan_summary": f"{side} от активного блока, работать от реакции, без догоняния",
    }


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

    trigger_detected, trigger_type, trigger_note = detect_trigger(candles_1h, active_block, range_low, range_high)

    if price > range_high or price < range_low or block_depth_pct >= 100:
        state = "OVERRUN"
    elif trigger_detected:
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

    conflict_flag = consensus_direction in ("LONG", "SHORT") and consensus_direction != active_side
    scalp_direction = short_fc["direction"]
    forecast_alignment = _forecast_alignment(consensus_direction, active_side)
    ctx = _context_grade(depth_label, scalp_direction, active_side, candles_1h)

    trigger_blocked = False
    trigger_block_reason_code = None
    trigger_block_reason_text = None

    if trigger_type and not trigger_detected and conflict_flag:
        trigger_blocked = True
        trigger_block_reason_code = "FORECAST_VS_BLOCK"
        trigger_block_reason_text = "forecast против активного блока"
    elif trigger_type and not trigger_detected and ctx["score"] == 0:
        trigger_blocked = True
        trigger_block_reason_code = "NO_VALID_TRIGGER_CONTEXT"
        trigger_block_reason_text = "нет valid trigger context"

    if state == "OVERRUN":
        action = "PROTECT"
        entry_type = None
    elif trigger_detected and state == "CONFIRMED" and not conflict_flag:
        action = "ENTER"
        entry_type = "ENTER"
    elif trigger_detected and state == "CONFIRMED" and conflict_flag:
        action = "PREPARE" if ctx["score"] >= 3 else "WAIT"
        entry_type = "PROBE" if action == "PREPARE" else None
        if action == "WAIT":
            trigger_blocked = True
            trigger_block_reason_code = "FORECAST_VS_BLOCK"
            trigger_block_reason_text = "forecast против активного блока"
    elif state == "PRE_ACTIVATION" and ctx["valid"] and not trigger_blocked:
        action = "PREPARE"
        entry_type = "PROBE"
    else:
        action = "WAIT"
        entry_type = None

    if action == "WAIT" and trigger_type and not trigger_blocked and ctx["score"] == 0:
        trigger_blocked = True
        trigger_block_reason_code = "NO_VALID_TRIGGER_CONTEXT"
        trigger_block_reason_text = "нет valid trigger context"

    if state == "OVERRUN":
        hedge_state = "TRIGGER"
    elif block_depth_pct > 60:
        hedge_state = "PRE-TRIGGER"
    elif state in ("SEARCH_TRIGGER", "PRE_ACTIVATION"):
        hedge_state = "ARM"
    else:
        hedge_state = "OFF"

    execution_side = active_side
    execution_confidence = "LOW" if conflict_flag else consensus_confidence

    primary_warning, secondary_warnings, context_warnings = _pick_primary_secondary_context(
        conflict_flag=conflict_flag,
        scalp_direction=scalp_direction,
        active_side=active_side,
        trigger_type=trigger_type,
        range_position_pct=range_position_pct,
        block_depth_pct=block_depth_pct,
        context_score=ctx["score"],
    )
    if trigger_blocked and trigger_block_reason_text:
        primary_warning = trigger_block_reason_text

    entry_quality, entry_quality_reason = _entry_quality(
        trigger_detected=trigger_detected,
        trigger_type=trigger_type,
        context_score=ctx["score"],
        depth_label=depth_label,
        scalp_direction=scalp_direction,
        active_side=active_side,
        forecast_alignment=forecast_alignment,
        trigger_blocked=trigger_blocked,
        action=action,
    )
    execution_profile, execution_profile_reason = _execution_profile(
        entry_quality=entry_quality,
        context_score=ctx["score"],
        forecast_alignment=forecast_alignment,
        depth_label=depth_label,
        action=action,
    )
    risk_mode, partial_entry_allowed, scale_in_allowed = _risk_and_scaling(
        entry_quality=entry_quality,
        context_score=ctx["score"],
        depth_label=depth_label,
        block_depth_pct=block_depth_pct,
        forecast_alignment=forecast_alignment,
        action=action,
    )

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
        "trigger": trigger_detected,
        "trigger_type": trigger_type,
        "trigger_note": trigger_note,
        "trigger_detected": trigger_detected,
        "trigger_blocked": trigger_blocked,
        "trigger_block_reason_code": trigger_block_reason_code,
        "trigger_block_reason_text": trigger_block_reason_text,
        "trigger_context_score": ctx["score"],
        "trigger_context_label": ctx["label"],
        "trigger_context_details": ctx["details"],
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
        "forecast_alignment": forecast_alignment,
        "execution_side": execution_side,
        "execution_confidence": execution_confidence,
        "conflict_flag": conflict_flag,
        "primary_warning": primary_warning,
        "secondary_warnings": secondary_warnings,
        "context_warnings": context_warnings,
        "warnings": ([primary_warning] if primary_warning else []) + secondary_warnings + context_warnings,
        "entry_quality": entry_quality,
        "entry_quality_reason": entry_quality_reason,
        "execution_profile": execution_profile,
        "execution_profile_reason": execution_profile_reason,
        "entry_risk_mode": risk_mode,
        "partial_entry_allowed": partial_entry_allowed,
        "partial_entry_size": PARTIAL_ENTRY_RANGE if partial_entry_allowed else None,
        "scale_in_allowed": scale_in_allowed,
        "ginarea": ginarea,
    }
    snapshot["trade_plan"] = _trade_plan(snapshot, candles_1h, execution_profile)
    return snapshot
