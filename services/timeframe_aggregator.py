def aggregate_candles(candles_1h, step: int):
    closed = candles_1h[:len(candles_1h) - (len(candles_1h) % step)]
    out = []
    for i in range(0, len(closed), step):
        group = closed[i:i+step]
        if len(group) < step:
            continue
        out.append({
            "open_time": group[0]["open_time"],
            "open": group[0]["open"],
            "high": max(x["high"] for x in group),
            "low": min(x["low"] for x in group),
            "close": group[-1]["close"],
            "volume": sum(x["volume"] for x in group),
            "close_time": group[-1]["close_time"],
        })
    return out

def aggregate_to_4h(candles_1h):
    return aggregate_candles(candles_1h, 4)

def aggregate_to_1d(candles_1h):
    return aggregate_candles(candles_1h, 24)
