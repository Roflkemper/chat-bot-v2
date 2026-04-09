from datetime import datetime
from market_data.price_feed import get_price
from market_data.ohlcv import get_klines
from services.timeframe_aggregator import aggregate_to_4h, aggregate_to_1d
from features.trigger_detection import detect_trigger
from features.forecast import short_term_forecast, session_forecast, medium_forecast, build_consensus

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

def build_full_snapshot(symbol="BTCUSDT"):
    price = get_price(symbol)
    candles_1h = get_klines(symbol=symbol, interval="1h", limit=200)
    candles_4h = aggregate_to_4h(candles_1h)
    candles_1d = aggregate_to_1d(candles_1h)

    range_low, range_high, range_mid = _build_range(candles_1h)
    range_size = max(range_high - range_low, 1e-9)

    if price >= range_mid:
        side = "SHORT"
        active_block = "SHORT"
        block_low = range_mid
        block_high = range_high
        active_edge = range_high
        distance_to_active_edge = active_edge - price
    else:
        side = "LONG"
        active_block = "LONG"
        block_low = range_low
        block_high = range_mid
        active_edge = range_low
        distance_to_active_edge = price - active_edge

    block_size = max(block_high - block_low, 1e-9)
    block_depth_pct = ((price - block_low) / block_size) * 100.0
    range_position_pct = ((price - range_low) / range_size) * 100.0
    distance_to_upper_edge = range_high - price
    distance_to_lower_edge = price - range_low

    if active_block == "SHORT":
        active_edge_distance_pct = max(0.0, ((block_high - price) / block_size) * 100.0)
    else:
        active_edge_distance_pct = max(0.0, ((price - block_low) / block_size) * 100.0)

    depth_label = _depth_label(block_depth_pct)

    trigger, trigger_type, trigger_note = detect_trigger(candles_1h, active_block, range_low, range_high)

    if price > range_high or price < range_low or block_depth_pct >= 100:
        state = "OVERRUN"
    elif trigger:
        state = "CONFIRMED"
    elif active_edge_distance_pct <= NEAR_EDGE_THRESHOLD_PCT:
        state = "PRE_ACTIVATION"
    elif depth_label in ("WORK", "RISK"):
        state = "SEARCH_TRIGGER"
    else:
        state = "MID_RANGE"

    action_map = {
        "MID_RANGE": "WAIT",
        "SEARCH_TRIGGER": "PREPARE",
        "PRE_ACTIVATION": "READY",
        "CONFIRMED": "ENTER",
        "OVERRUN": "PROTECT",
    }
    entry_map = {
        "MID_RANGE": None,
        "SEARCH_TRIGGER": "PROBE",
        "PRE_ACTIVATION": "PROBE",
        "CONFIRMED": "ENTER",
        "OVERRUN": None,
    }
    action = action_map[state]
    entry_type = entry_map[state]

    hedge_state = "OFF"
    if state in ("SEARCH_TRIGGER", "PRE_ACTIVATION"):
        hedge_state = "ARM"
    elif state == "OVERRUN":
        hedge_state = "TRIGGER"

    short_fc = short_term_forecast(candles_1h)
    session_fc = session_forecast(candles_4h)
    medium_fc = medium_forecast(candles_1d)
    consensus_direction, consensus_confidence, consensus_votes = build_consensus(short_fc, session_fc, medium_fc)

    # execution must still respect active side even if consensus conflicts
    if consensus_direction == "CONFLICT":
        execution_side = side
        execution_confidence = "LOW"
    else:
        execution_side = side
        execution_confidence = consensus_confidence if consensus_direction == side else "LOW"

    ginarea = {
        "mode": "PRIORITY_GRID",
        "long_grid": "REDUCE" if execution_side == "SHORT" else "WORK",
        "short_grid": "WORK" if execution_side == "SHORT" else "REDUCE",
        "aggression": "LOW" if state != "CONFIRMED" else "MID",
        "lifecycle": "REDUCE_GRID" if depth_label == "RISK" else "ARM_GRID" if state in ("SEARCH_TRIGGER", "PRE_ACTIVATION") else "WAIT_GRID",
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
        "block_low": round(block_low, 2),
        "block_high": round(block_high, 2),
        "block_depth_pct": round(block_depth_pct, 2),
        "depth_label": depth_label,

        "distance_to_active_edge": round(distance_to_active_edge, 2),
        "distance_to_upper_edge": round(distance_to_upper_edge, 2),
        "distance_to_lower_edge": round(distance_to_lower_edge, 2),
        "active_edge_distance_pct": round(active_edge_distance_pct, 2),

        "state": state,
        "trigger": trigger,
        "trigger_type": trigger_type,
        "trigger_note": trigger_note,

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

        "execution_side": execution_side,
        "execution_confidence": execution_confidence,

        "ginarea": ginarea,
    }
    return snapshot
