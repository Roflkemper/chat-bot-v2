from statistics import mean
from features.basic_metrics import candle_direction, body_ratio, atr

def _direction_from_score(score):
    if score > 0.15:
        return "LONG"
    if score < -0.15:
        return "SHORT"
    return "NEUTRAL"

def short_term_forecast(candles_1h):
    bars = candles_1h[-5:]
    if len(bars) < 5:
        return {"direction": "NEUTRAL", "strength": "LOW", "note": "мало данных"}
    dir_score = mean(candle_direction(x) for x in bars)
    body = mean(body_ratio(x) for x in bars)
    vol_now = bars[-1]["volume"]
    vol_avg = mean(x["volume"] for x in bars)
    pressure_proxy = ((vol_now / max(vol_avg, 1e-9)) - 1.0) * dir_score
    direction = _direction_from_score(dir_score + pressure_proxy * 0.5)
    strength = "HIGH" if abs(dir_score) > 0.6 else "MID" if abs(dir_score) > 0.25 else "LOW"
    return {
        "direction": direction,
        "strength": strength,
        "note": f"body={body:.2f}, pressure={pressure_proxy:.2f}"
    }

def session_forecast(candles_4h):
    bars = candles_4h[-5:]
    if len(bars) < 3:
        return {"direction": "NEUTRAL", "strength": "LOW", "note": "мало 4h данных"}
    move = (bars[-1]["close"] - bars[0]["open"]) / max(bars[0]["open"], 1e-9)
    compression = atr(candles_4h[-20:], 14) / max(atr(candles_4h[-40:], 14), 1e-9)
    direction = "LONG" if move > 0.003 else "SHORT" if move < -0.003 else "NEUTRAL"
    mode = "COMPRESSION" if compression < 0.8 else "EXPANSION" if compression > 1.2 else "NORMAL"
    strength = "HIGH" if abs(move) > 0.01 else "MID" if abs(move) > 0.004 else "LOW"
    return {
        "direction": direction,
        "strength": strength,
        "note": f"{mode}, move={move*100:.2f}%"
    }

def medium_forecast(candles_1d):
    bars = candles_1d[-10:]
    if len(bars) < 5:
        return {"direction": "NEUTRAL", "strength": "LOW", "phase": "UNKNOWN", "note": "мало 1d данных"}
    move = (bars[-1]["close"] - bars[0]["open"]) / max(bars[0]["open"], 1e-9)
    highs = [x["high"] for x in bars]
    lows = [x["low"] for x in bars]
    range_growth = (max(highs) - min(lows)) / max(bars[0]["open"], 1e-9)
    if move > 0.02:
        phase = "MARKUP"
        direction = "LONG"
    elif move < -0.02:
        phase = "MARKDOWN"
        direction = "SHORT"
    else:
        phase = "ACCUMULATION" if bars[-1]["close"] >= bars[0]["open"] else "DISTRIBUTION"
        direction = "LONG" if phase == "ACCUMULATION" else "SHORT"
    strength = "HIGH" if abs(move) > 0.05 else "MID" if abs(move) > 0.02 else "LOW"
    return {
        "direction": direction,
        "strength": strength,
        "phase": phase,
        "note": f"range={range_growth*100:.2f}%"
    }

def build_consensus(short_fc, session_fc, medium_fc):
    dirs = [short_fc["direction"], session_fc["direction"], medium_fc["direction"]]
    long_votes = sum(1 for d in dirs if d == "LONG")
    short_votes = sum(1 for d in dirs if d == "SHORT")
    neutral_votes = sum(1 for d in dirs if d == "NEUTRAL")
    alignment = max(long_votes, short_votes)

    if alignment == 0:
        return "CONFLICTED", "LOW", "0/3"
    if long_votes > short_votes:
        direction = "LONG"
        if long_votes == 3:
            confidence = "HIGH"
        elif long_votes == 2:
            confidence = "MID"
        else:
            confidence = "LOW"
        return direction, confidence, f"{long_votes}/3"
    if short_votes > long_votes:
        direction = "SHORT"
        if short_votes == 3:
            confidence = "HIGH"
        elif short_votes == 2:
            confidence = "MID"
        else:
            confidence = "LOW"
        return direction, confidence, f"{short_votes}/3"

    # equal non-zero votes -> conflicted
    return "CONFLICTED", "LOW", f"{alignment}/3"
