from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class DerivativesSnapshot:
    funding_rate: float = 0.0
    funding_zscore: float = 0.0
    open_interest: float = 0.0
    oi_change_1h_pct: float = 0.0
    oi_change_4h_pct: float = 0.0
    long_liq_distance_pct: float = 999.0
    short_liq_distance_pct: float = 999.0


def build_derivatives_context(price_change_1h_pct: float, snapshot: Optional[DerivativesSnapshot] = None) -> Dict:
    snapshot = snapshot or DerivativesSnapshot()
    oi_1h = float(snapshot.oi_change_1h_pct or 0.0)
    oi_4h = float(snapshot.oi_change_4h_pct or 0.0)
    fr = float(snapshot.funding_rate or 0.0)

    if price_change_1h_pct > 0 and oi_1h > 0:
        price_oi_regime = 'BULLISH_BUILDUP'
    elif price_change_1h_pct < 0 and oi_1h > 0:
        price_oi_regime = 'BEARISH_BUILDUP'
    elif price_change_1h_pct > 0 and oi_1h < 0:
        price_oi_regime = 'SHORT_COVERING'
    elif price_change_1h_pct < 0 and oi_1h < 0:
        price_oi_regime = 'LONG_UNWIND'
    else:
        price_oi_regime = 'NEUTRAL'

    if fr >= 0.03:
        funding_state = 'EXTREME_LONG_CROWDED'
    elif fr >= 0.01:
        funding_state = 'LONG_CROWDED'
    elif fr <= -0.03:
        funding_state = 'EXTREME_SHORT_CROWDED'
    elif fr <= -0.01:
        funding_state = 'SHORT_CROWDED'
    elif fr > 0:
        funding_state = 'LIGHT_LONG_BIAS'
    elif fr < 0:
        funding_state = 'LIGHT_SHORT_BIAS'
    else:
        funding_state = 'NEUTRAL'

    if abs(oi_1h) >= 8.0 or abs(oi_4h) >= 12.0:
        oi_state = 'AGGRESSIVE_POSITIONING'
    elif abs(oi_1h) >= 4.0 or abs(oi_4h) >= 6.0:
        oi_state = 'EXPANDING_OI'
    elif abs(oi_1h) >= 1.5:
        oi_state = 'MODEST_OI_SHIFT'
    else:
        oi_state = 'FLAT_OI'

    liq_magnet_side = 'UP' if snapshot.short_liq_distance_pct < snapshot.long_liq_distance_pct else 'DOWN' if snapshot.long_liq_distance_pct < snapshot.short_liq_distance_pct else 'NEUTRAL'

    nearest = min(float(snapshot.short_liq_distance_pct or 999.0), float(snapshot.long_liq_distance_pct or 999.0))
    squeeze_risk = 'LOW'
    if nearest < 0.9 or abs(oi_1h) >= 3.5:
        squeeze_risk = 'MEDIUM'
    if nearest < 0.45 or abs(oi_1h) >= 6.0:
        squeeze_risk = 'HIGH'
    if nearest < 0.25 or abs(oi_1h) >= 9.0:
        squeeze_risk = 'EXTREME'

    crowding_risk = 'LOW'
    if 'CROWDED' in funding_state and abs(oi_1h) >= 3.0:
        crowding_risk = 'MEDIUM'
    if 'EXTREME' in funding_state or ('CROWDED' in funding_state and abs(oi_1h) >= 6.0):
        crowding_risk = 'HIGH'

    trap_bias = 'NEUTRAL'
    if price_oi_regime == 'BULLISH_BUILDUP' and 'LONG' in funding_state and liq_magnet_side == 'UP':
        trap_bias = 'UPSIDE_SQUEEZE_THEN_FADE_RISK'
    elif price_oi_regime == 'BEARISH_BUILDUP' and 'SHORT' in funding_state and liq_magnet_side == 'DOWN':
        trap_bias = 'DOWNSIDE_FLUSH_THEN_BOUNCE_RISK'
    elif price_oi_regime in {'SHORT_COVERING', 'LONG_UNWIND'}:
        trap_bias = 'MOVE_CAN_FADE_WITHOUT_FRESH_OI'

    derivative_edge = 'NEUTRAL'
    if price_oi_regime in {'BULLISH_BUILDUP', 'BEARISH_BUILDUP'} and crowding_risk in {'LOW', 'MEDIUM'}:
        derivative_edge = 'CONFIRMED_TREND_PRESSURE'
    elif price_oi_regime in {'SHORT_COVERING', 'LONG_UNWIND'}:
        derivative_edge = 'UNWIND_NOT_CLEAN_TREND'
    if crowding_risk == 'HIGH' and squeeze_risk in {'HIGH', 'EXTREME'}:
        derivative_edge = 'CROWDING_TRAP_RISK'

    summary = (
        f'{price_oi_regime}, funding={funding_state}, oi_state={oi_state}, '
        f'squeeze_risk={squeeze_risk}, crowding={crowding_risk}, liq_magnet={liq_magnet_side}'
    )
    return {
        'price_oi_regime': price_oi_regime,
        'funding_state': funding_state,
        'oi_state': oi_state,
        'squeeze_risk': squeeze_risk,
        'crowding_risk': crowding_risk,
        'liq_magnet_side': liq_magnet_side,
        'trap_bias': trap_bias,
        'derivative_edge': derivative_edge,
        'oi_change_1h_pct': oi_1h,
        'oi_change_4h_pct': oi_4h,
        'funding_rate': fr,
        'open_interest': float(snapshot.open_interest or 0.0),
        'summary': summary,
    }
