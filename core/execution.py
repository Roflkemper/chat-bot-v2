
def build_execution_snapshot(price: float):
    range_low = 69000
    range_high = 72857
    mid = (range_low + range_high) / 2

    if price > mid:
        side = "SHORT"
        block_low = mid
        block_high = range_high
    else:
        side = "LONG"
        block_low = range_low
        block_high = mid

    depth = (price - block_low) / (block_high - block_low) * 100
    distance_to_edge = block_high - price

    if depth < 15:
        state = "SEARCH_TRIGGER"
    elif depth < 85:
        state = "SEARCH_TRIGGER"
    else:
        state = "OVERRUN"

    confidence = "LOW" if depth > 50 else "MID"

    return {
        "price": price,
        "state": state,
        "side": side,
        "depth": round(depth, 2),
        "distance": round(distance_to_edge, 2),
        "confidence": confidence
    }
