from __future__ import annotations

from typing import Any, Dict, List, Tuple


DEFAULT_LOOKBACK = 8
CLIMAX_VOL_RATIO = 2.0
CLIMAX_MOVE_PCT = 1.2


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _norm_side(side: Any) -> str:
    return str(side or '').strip().upper()


def build_entry_quality_context(
    candles: List[Dict[str, Any]],
    entry_idx: int | None = None,
    side: str = 'LONG',
    lookback: int = DEFAULT_LOOKBACK,
) -> Dict[str, Any]:
    series = list(candles or [])
    if not series:
        return {
            'ok': True,
            'reason': 'NO_DATA',
            'reason_code': 'NO_DATA',
            'price_change_lookback_pct': 0.0,
            'vol_ratio': 1.0,
            'up_bars': 0,
            'down_bars': 0,
            'move_in_trade_dir_pct': 0.0,
            'lookback_bars': 0,
        }

    if entry_idx is None:
        entry_idx = len(series) - 1
    entry_idx = max(0, min(int(entry_idx), len(series) - 1))
    start = max(0, entry_idx - max(int(lookback), 1))
    window = series[start:entry_idx + 1]
    closes = [_safe_float(bar.get('close')) for bar in window]
    vols = [_safe_float(bar.get('volume')) for bar in window]

    if len(closes) < 2:
        return {
            'ok': True,
            'reason': 'INSUFFICIENT_WINDOW',
            'reason_code': 'INSUFFICIENT_WINDOW',
            'price_change_lookback_pct': 0.0,
            'vol_ratio': 1.0,
            'up_bars': 0,
            'down_bars': 0,
            'move_in_trade_dir_pct': 0.0,
            'lookback_bars': len(window),
        }

    base_close = closes[0] if closes[0] > 0 else 0.0
    price_change = ((closes[-1] - base_close) / base_close) * 100.0 if base_close > 0 else 0.0
    avg_vol = sum(vols[:-1]) / max(1, len(vols) - 1)
    vol_ratio = vols[-1] / avg_vol if avg_vol > 0 else 1.0

    moves = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    up_bars = sum(1 for move in moves if move > 0)
    down_bars = sum(1 for move in moves if move < 0)

    side_norm = _norm_side(side)
    move_in_trade_dir = -price_change if side_norm == 'SHORT' else price_change

    ok = True
    reason = 'OK'
    reason_code = 'OK'

    if vol_ratio > CLIMAX_VOL_RATIO and move_in_trade_dir > CLIMAX_MOVE_PCT:
        ok = False
        reason_code = 'CLIMAX_VOLUME'
        reason = f'CLIMAX_VOLUME (объём {vol_ratio:.2f}x при движении {move_in_trade_dir:.2f}% в сторону входа)'

    return {
        'ok': ok,
        'reason': reason,
        'reason_code': reason_code,
        'price_change_lookback_pct': round(price_change, 4),
        'vol_ratio': round(vol_ratio, 4),
        'up_bars': int(up_bars),
        'down_bars': int(down_bars),
        'move_in_trade_dir_pct': round(move_in_trade_dir, 4),
        'lookback_bars': len(window),
    }


def check_entry_filters(
    candles: List[Dict[str, Any]],
    entry_idx: int | None,
    side: str,
    lookback: int = DEFAULT_LOOKBACK,
) -> Tuple[bool, str]:
    ctx = build_entry_quality_context(candles=candles, entry_idx=entry_idx, side=side, lookback=lookback)
    return bool(ctx.get('ok')), str(ctx.get('reason') or 'OK')
