LOOKBACK_BARS = 3
RECLAIM_WITHIN = 2

def detect_trigger(candles_1h, active_block, range_low, range_high):
    if len(candles_1h) < LOOKBACK_BARS + 2:
        return False, None, "недостаточно баров"
    bars = candles_1h[-LOOKBACK_BARS:]
    recent = candles_1h[-RECLAIM_WITHIN:]

    if active_block == "SHORT":
        broke = any(bar["high"] > range_high for bar in bars)
        reclaimed = any(bar["close"] < range_high for bar in recent)
        if broke and reclaimed:
            return True, "FAKE_BREAK", "ложный вынос вверх и возврат внутрь диапазона"
        touch = any(bar["high"] >= range_high * 0.997 for bar in recent)
        if touch and reclaimed:
            return False, "RECLAIM", "касание верхнего края и удержание ниже"
        return False, None, "подтверждённого reject/reclaim ещё нет"

    if active_block == "LONG":
        broke = any(bar["low"] < range_low for bar in bars)
        reclaimed = any(bar["close"] > range_low for bar in recent)
        if broke and reclaimed:
            return True, "FAKE_BREAK", "ложный вынос вниз и возврат внутрь диапазона"
        touch = any(bar["low"] <= range_low * 1.003 for bar in recent)
        if touch and reclaimed:
            return False, "RECLAIM", "касание нижнего края и удержание выше"
        return False, None, "подтверждённого reject/reclaim ещё нет"

    return False, None, "нет активного блока"
