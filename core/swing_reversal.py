from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

DEFAULT_CONFIRM_BARS = 3
DEFAULT_MIN_PRIOR_MOVE_PCT = 0.8
DEFAULT_TP_ATR_MULT = 1.2
DEFAULT_SL_ATR_MULT = 0.8
DEFAULT_HORIZON_BARS = 8
DEFAULT_COOLDOWN_BARS = 15
DEFAULT_MIN_ATR_PCT = 0.25


@dataclass
class SwingReversalTrade:
    entry_index: int
    exit_index: int
    side: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    exit_reason: str
    tp_price: float
    stop_price: float
    atr_pct: float


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _norm_side(value: Any) -> str:
    side = str(value or '').strip().upper()
    return side if side in {'LONG', 'SHORT'} else 'NONE'


def _true_range(bar: Dict[str, Any], prev_close: float | None = None) -> float:
    high = _safe_float(bar.get('high'), _safe_float(bar.get('close')))
    low = _safe_float(bar.get('low'), _safe_float(bar.get('close')))
    if prev_close is None:
        return max(0.0, high - low)
    return max(0.0, max(high - low, abs(high - prev_close), abs(low - prev_close)))


def atr_pct(candles: List[Dict[str, Any]], idx: int, period: int = 14) -> float:
    if idx <= 0:
        return 0.0
    start = max(0, idx - period)
    window = candles[start:idx + 1]
    if len(window) < 3:
        return 0.0
    prev_close = None
    trs: list[float] = []
    for bar in window:
        trs.append(_true_range(bar, prev_close))
        prev_close = _safe_float(bar.get('close'))
    close = _safe_float(window[-1].get('close'))
    if close <= 0:
        return 0.0
    return round((sum(trs[-period:]) / max(1, len(trs[-period:]))) / close * 100.0, 4)


def is_swing_low(candles: List[Dict[str, Any]], idx: int, confirm: int = DEFAULT_CONFIRM_BARS) -> bool:
    if idx - confirm < 0 or idx + confirm >= len(candles):
        return False
    low = _safe_float(candles[idx].get('low'))
    prev = candles[idx - confirm:idx]
    nxt = candles[idx + 1:idx + confirm + 1]
    return all(low <= _safe_float(bar.get('low'), low) for bar in prev) and all(low <= _safe_float(bar.get('low'), low) for bar in nxt)


def is_swing_high(candles: List[Dict[str, Any]], idx: int, confirm: int = DEFAULT_CONFIRM_BARS) -> bool:
    if idx - confirm < 0 or idx + confirm >= len(candles):
        return False
    high = _safe_float(candles[idx].get('high'))
    prev = candles[idx - confirm:idx]
    nxt = candles[idx + 1:idx + confirm + 1]
    return all(high >= _safe_float(bar.get('high'), high) for bar in prev) and all(high >= _safe_float(bar.get('high'), high) for bar in nxt)


def prior_move_pct(candles: List[Dict[str, Any]], idx: int, side: str, lookback: int = DEFAULT_CONFIRM_BARS) -> float:
    side = _norm_side(side)
    if side == 'NONE' or idx - lookback < 0:
        return 0.0
    base_close = _safe_float(candles[idx - lookback].get('close'))
    current_close = _safe_float(candles[idx].get('close'))
    if base_close <= 0:
        return 0.0
    raw = (current_close - base_close) / base_close * 100.0
    if side == 'LONG':
        return round(max(0.0, -raw), 4)
    return round(max(0.0, raw), 4)


def detect_swing_reversal(candles: List[Dict[str, Any]], idx: int, *, confirm_bars: int = DEFAULT_CONFIRM_BARS, min_prior_move_pct: float = DEFAULT_MIN_PRIOR_MOVE_PCT, min_atr_pct: float = DEFAULT_MIN_ATR_PCT) -> Dict[str, Any]:
    if idx < confirm_bars * 2:
        return {'candidate': False, 'side': 'NONE', 'reason': 'NOT_ENOUGH_BARS'}

    pivot_idx = idx - confirm_bars
    side = 'NONE'
    reason = 'NO_SWING'
    if is_swing_low(candles, pivot_idx, confirm=confirm_bars):
        side = 'LONG'
        reason = 'SWING_LOW_CONFIRMED'
    elif is_swing_high(candles, pivot_idx, confirm=confirm_bars):
        side = 'SHORT'
        reason = 'SWING_HIGH_CONFIRMED'

    if side == 'NONE':
        return {'candidate': False, 'side': 'NONE', 'reason': reason, 'pivot_index': pivot_idx}

    move_pct = prior_move_pct(candles, pivot_idx, side, lookback=confirm_bars)
    if move_pct < min_prior_move_pct:
        return {
            'candidate': False,
            'side': side,
            'reason': 'PRIOR_MOVE_TOO_SMALL',
            'pivot_index': pivot_idx,
            'prior_move_pct': move_pct,
        }

    current_atr_pct = atr_pct(candles, idx)
    if current_atr_pct < min_atr_pct:
        return {
            'candidate': False,
            'side': side,
            'reason': 'ATR_TOO_LOW',
            'pivot_index': pivot_idx,
            'prior_move_pct': move_pct,
            'atr_pct': current_atr_pct,
        }

    entry_price = _safe_float(candles[idx].get('close'))
    return {
        'candidate': True,
        'side': side,
        'reason': reason,
        'pivot_index': pivot_idx,
        'entry_index': idx,
        'entry_price': round(entry_price, 4),
        'prior_move_pct': move_pct,
        'atr_pct': current_atr_pct,
        'confirm_bars': confirm_bars,
        'mode': 'OBSERVE',
    }


def build_swing_reversal_observe_context(candles: List[Dict[str, Any]], *, cooldown_bars: int = DEFAULT_COOLDOWN_BARS, last_entry_index: int | None = None) -> Dict[str, Any]:
    idx = len(candles) - 1
    ctx = detect_swing_reversal(candles, idx)
    if not ctx.get('candidate'):
        ctx['cooldown_ok'] = True
        return ctx
    if last_entry_index is not None and idx - int(last_entry_index) < cooldown_bars:
        ctx['candidate'] = False
        ctx['cooldown_ok'] = False
        ctx['reason'] = 'COOLDOWN_ACTIVE'
        ctx['cooldown_bars_left'] = max(0, cooldown_bars - (idx - int(last_entry_index)))
        return ctx
    ctx['cooldown_ok'] = True
    return ctx


def _build_levels(entry_price: float, side: str, atr_pct_value: float, tp_atr_mult: float, sl_atr_mult: float) -> tuple[float, float]:
    move_tp = entry_price * ((atr_pct_value * tp_atr_mult) / 100.0)
    move_sl = entry_price * ((atr_pct_value * sl_atr_mult) / 100.0)
    if side == 'LONG':
        return round(entry_price + move_tp, 4), round(entry_price - move_sl, 4)
    return round(entry_price - move_tp, 4), round(entry_price + move_sl, 4)


def scan_swing_reversal_trades(
    candles: List[Dict[str, Any]],
    *,
    confirm_bars: int = DEFAULT_CONFIRM_BARS,
    min_prior_move_pct: float = DEFAULT_MIN_PRIOR_MOVE_PCT,
    tp_atr_mult: float = DEFAULT_TP_ATR_MULT,
    sl_atr_mult: float = DEFAULT_SL_ATR_MULT,
    horizon_bars: int = DEFAULT_HORIZON_BARS,
    cooldown_bars: int = DEFAULT_COOLDOWN_BARS,
) -> Dict[str, Any]:
    candles = list(candles or [])
    trades: list[SwingReversalTrade] = []
    observed = 0
    candidate_count = 0
    last_entry_index: int | None = None
    next_allowed = 0
    i = confirm_bars * 2
    while i < len(candles) - 1:
        observed += 1
        ctx = detect_swing_reversal(
            candles,
            i,
            confirm_bars=confirm_bars,
            min_prior_move_pct=min_prior_move_pct,
        )
        if not ctx.get('candidate'):
            i += 1
            continue
        candidate_count += 1
        if i < next_allowed:
            i += 1
            continue
        side = _norm_side(ctx.get('side'))
        entry_price = _safe_float(ctx.get('entry_price'))
        atr_value = max(_safe_float(ctx.get('atr_pct')), DEFAULT_MIN_ATR_PCT)
        tp_price, stop_price = _build_levels(entry_price, side, atr_value, tp_atr_mult, sl_atr_mult)
        exit_reason = 'TIMEOUT'
        exit_price = _safe_float(candles[min(len(candles) - 1, i + horizon_bars)].get('close'), entry_price)
        exit_index = min(len(candles) - 1, i + horizon_bars)
        for j in range(i + 1, min(len(candles), i + horizon_bars + 1)):
            bar = candles[j]
            high = _safe_float(bar.get('high'), _safe_float(bar.get('close'), entry_price))
            low = _safe_float(bar.get('low'), _safe_float(bar.get('close'), entry_price))
            if side == 'LONG':
                if low <= stop_price:
                    exit_reason = 'STOP'
                    exit_price = stop_price
                    exit_index = j
                    break
                if high >= tp_price:
                    exit_reason = 'TP_HIT'
                    exit_price = tp_price
                    exit_index = j
                    break
            else:
                if high >= stop_price:
                    exit_reason = 'STOP'
                    exit_price = stop_price
                    exit_index = j
                    break
                if low <= tp_price:
                    exit_reason = 'TP_HIT'
                    exit_price = tp_price
                    exit_index = j
                    break
        raw = (exit_price - entry_price) / entry_price * 100.0 if entry_price > 0 else 0.0
        pnl_pct = raw if side == 'LONG' else -raw
        trades.append(
            SwingReversalTrade(
                entry_index=i,
                exit_index=exit_index,
                side=side,
                entry_price=round(entry_price, 4),
                exit_price=round(exit_price, 4),
                pnl_pct=round(pnl_pct, 4),
                exit_reason=exit_reason,
                tp_price=tp_price,
                stop_price=stop_price,
                atr_pct=round(atr_value, 4),
            )
        )
        last_entry_index = i
        next_allowed = i + cooldown_bars
        i = max(i + 1, next_allowed)
    wins = sum(1 for trade in trades if trade.pnl_pct > 0)
    total_pnl = round(sum(trade.pnl_pct for trade in trades), 4)
    return {
        'mode': 'OBSERVE',
        'observed_bars': observed,
        'candidate_count': candidate_count,
        'trades': len(trades),
        'winrate': round((wins / len(trades) * 100.0), 2) if trades else 0.0,
        'pnl_pct': total_pnl,
        'avg_pnl_pct': round(total_pnl / len(trades), 4) if trades else 0.0,
        'tp_hit_count': sum(1 for trade in trades if trade.exit_reason == 'TP_HIT'),
        'stop_count': sum(1 for trade in trades if trade.exit_reason == 'STOP'),
        'timeout_count': sum(1 for trade in trades if trade.exit_reason == 'TIMEOUT'),
        'cooldown_bars': cooldown_bars,
        'horizon_bars': horizon_bars,
        'tp_atr_mult': tp_atr_mult,
        'sl_atr_mult': sl_atr_mult,
        'min_prior_move_pct': min_prior_move_pct,
        'confirm_bars': confirm_bars,
        'trades_data': [asdict(trade) for trade in trades],
    }
