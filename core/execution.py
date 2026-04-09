from datetime import datetime

def build_execution_snapshot(price: float):
    range_low = 69000.0
    range_high = 72857.0
    range_mid = (range_low + range_high) / 2.0

    if price > range_mid:
        side = "SHORT"
        active_block = "SHORT"
        block_low = range_mid
        block_high = range_high
    else:
        side = "LONG"
        active_block = "LONG"
        block_low = range_low
        block_high = range_mid

    block_size = max(block_high - block_low, 1e-9)
    range_size = max(range_high - range_low, 1e-9)

    block_depth_pct = ((price - block_low) / block_size) * 100.0
    range_position_pct = ((price - range_low) / range_size) * 100.0

    distance_to_active_edge = (block_high - price) if active_block == "SHORT" else (price - block_low)
    distance_to_upper_edge = range_high - price
    distance_to_lower_edge = price - range_low

    if block_depth_pct < 15:
        depth_label = "EARLY"
    elif block_depth_pct < 50:
        depth_label = "WORK"
    elif block_depth_pct < 85:
        depth_label = "RISK"
    else:
        depth_label = "DEEP"

    if block_depth_pct < 85:
        state = "SEARCH_TRIGGER"
    else:
        state = "OVERRUN"

    confidence = "LOW" if block_depth_pct > 50 else "MID"

    consensus_direction = side
    consensus_confidence = confidence
    consensus_votes = "2/3"

    hedge_buffer = 293.0
    hedge_arm_up = range_high + hedge_buffer
    hedge_arm_down = range_low - hedge_buffer

    return {
        "timestamp": datetime.now().strftime("%H:%M"),
        "tf": "1h",
        "price": round(price, 2),
        "state": state,
        "side": side,
        "active_block": active_block,
        "block_depth_pct": round(block_depth_pct, 2),
        "depth_label": depth_label,
        "range_position_pct": round(range_position_pct, 2),
        "distance_to_active_edge": round(distance_to_active_edge, 2),
        "distance_to_upper_edge": round(distance_to_upper_edge, 2),
        "distance_to_lower_edge": round(distance_to_lower_edge, 2),
        "consensus_direction": consensus_direction,
        "consensus_confidence": consensus_confidence,
        "consensus_votes": consensus_votes,
        "hedge_arm_up": round(hedge_arm_up, 2),
        "hedge_arm_down": round(hedge_arm_down, 2),
    }
