from statistics import mean

def sma(values, n):
    if not values:
        return 0.0
    window = values[-n:] if len(values) >= n else values
    return mean(window)

def atr(candles, n=14):
    if len(candles) < 2:
        return 0.0
    trs = []
    prev_close = candles[0]["close"]
    for c in candles[1:]:
        tr = max(
            c["high"] - c["low"],
            abs(c["high"] - prev_close),
            abs(c["low"] - prev_close),
        )
        trs.append(tr)
        prev_close = c["close"]
    if not trs:
        return 0.0
    window = trs[-n:] if len(trs) >= n else trs
    return mean(window)

def body_ratio(candle):
    spread = max(candle["high"] - candle["low"], 1e-9)
    return abs(candle["close"] - candle["open"]) / spread

def candle_direction(candle):
    if candle["close"] > candle["open"]:
        return 1
    if candle["close"] < candle["open"]:
        return -1
    return 0
