from __future__ import annotations

from typing import Dict


def build_volatility_impulse_context(df) -> Dict:
    last = df.iloc[-1]
    close = float(last['close'])
    atr = float(last.get('atr14', 0.0))
    ema20 = float(last.get('ema20', close))

    atr_pct = (atr / close * 100.0) if close else 0.0
    stretch_atr = abs(close - ema20) / atr if atr else 0.0

    move_5 = 0.0
    if len(df) >= 6:
        prev = float(df['close'].iloc[-6])
        if prev:
            move_5 = ((close - prev) / prev) * 100.0

    impulse_strength = 'LOW'
    if abs(move_5) >= 1.2:
        impulse_strength = 'MEDIUM'
    if abs(move_5) >= 2.2:
        impulse_strength = 'HIGH'

    volatility_state = 'NORMAL'
    if atr_pct < 0.45:
        volatility_state = 'LOW'
    elif atr_pct > 1.25:
        volatility_state = 'HIGH'

    stretch_state = 'NORMAL'
    if stretch_atr >= 1.6:
        stretch_state = 'STRETCHED'
    if stretch_atr >= 2.6:
        stretch_state = 'EXTREME'

    trend_ct_risk = 'LOW'
    if impulse_strength == 'HIGH' and stretch_state in ('NORMAL', 'STRETCHED'):
        trend_ct_risk = 'HIGH'
    elif impulse_strength == 'MEDIUM':
        trend_ct_risk = 'MEDIUM'

    summary = f"vol={volatility_state}, impulse={impulse_strength}, stretch={stretch_state}, ct_risk={trend_ct_risk}"
    return {
        'atr_pct': round(atr_pct, 4),
        'move_5_pct': round(move_5, 4),
        'impulse_strength': impulse_strength,
        'volatility_state': volatility_state,
        'stretch_state': stretch_state,
        'countertrend_risk': trend_ct_risk,
        'summary': summary,
    }
