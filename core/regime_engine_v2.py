from __future__ import annotations


def detect_regime_v2(df):
    last = df.iloc[-1]
    close = float(last['close'])
    ema20 = float(last.get('ema20', close))
    ema50 = float(last.get('ema50', close))
    ema100 = float(last.get('ema100', close))
    atr = float(last.get('atr14', 0.0))
    atr_pct = (atr / close * 100.0) if close else 0.0
    recent_move = 0.0
    if len(df) >= 5:
        prev = float(df['close'].iloc[-5])
        recent_move = ((close - prev) / close * 100.0) if close else 0.0
    stretch = abs(close - ema20) / atr if atr else 0.0
    bull = ema20 > ema50 > ema100
    bear = ema20 < ema50 < ema100
    base = 'RANGE'
    if atr_pct < 0.5:
        base = 'COMPRESSION'
    elif atr_pct > 2.0:
        base = 'EXPANSION'
    elif bull or bear:
        base = 'TREND'
    if bull or bear:
        if stretch < 1.5:
            sub = 'TREND_IMPULSE_FRESH'
        elif stretch < 3:
            sub = 'TREND_IMPULSE_LATE'
        else:
            sub = 'TREND_EXHAUSTION'
    else:
        sub = 'RANGE_CLEAN' if abs(recent_move) < 0.8 else 'RANGE_DIRTY'
    mean_rev = min(100.0, stretch * 30.0)
    return {'base_regime': base, 'regime_label': sub, 'confidence': float(min(100, abs(ema20-ema100)/(close or 1)*100*50)), 'mean_reversion_bias': float(mean_rev), 'continuation_bias': float(max(0,100-mean_rev)), 'grid_friendly': sub == 'RANGE_CLEAN', 'countertrend_friendly': sub in {'TREND_EXHAUSTION','RANGE_DIRTY'}, 'trend_friendly': sub == 'TREND_IMPULSE_FRESH', 'features': {'atr_pct': atr_pct, 'stretch': stretch}}
