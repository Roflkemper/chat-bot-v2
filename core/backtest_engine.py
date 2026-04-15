from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from core import pipeline
from market_data.ohlcv import get_klines
from services.timeframe_aggregator import aggregate_candles, aggregate_to_4h, aggregate_to_1d
from core.entry_quality_filter import build_entry_quality_context


DEFAULT_TIMEFRAME = '1h'
DEFAULT_LOOKBACK_DAYS = 90
MIN_WINDOW_BARS = 120
MAX_WINDOW_BARS = 240
DEFAULT_HORIZON_BARS = 12
DEFAULT_BE_BUFFER_PCT = 0.35
DEFAULT_BE_TRIGGER_TO_TP1 = 1.0
DEFAULT_PARTIAL_SIZE = 0.30
DEFAULT_MAX_STOP_PCT = 1.8
DEFAULT_DEAD_TRADE_MIN_BARS = 8
DEFAULT_DEAD_TRADE_MAX_PROFIT_PCT = 0.35
DEFAULT_DEAD_TRADE_COMPRESSION_RATIO = 0.75
DEFAULT_TP3_TAIL_SIZE = 0.10
DEFAULT_MIN_STOP_PCT = 0.5
DEFAULT_TP1_ATR_MULT = 1.0
DEFAULT_TP2_ATR_MULT = 1.9
DEFAULT_STOP_ATR_MULT = 1.5


def _timeframe_scale(timeframe: str) -> int:
    tf = str(timeframe or DEFAULT_TIMEFRAME).lower()
    return 4 if tf == '15m' else 1


def _effective_min_window_bars(timeframe: str) -> int:
    return max(MIN_WINDOW_BARS, MIN_WINDOW_BARS * _timeframe_scale(timeframe))


def _effective_max_window_bars(timeframe: str) -> int:
    return max(MAX_WINDOW_BARS, MAX_WINDOW_BARS * _timeframe_scale(timeframe))



@dataclass
class BacktestTrade:
    entry_index: int
    exit_index: int
    side: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    rr: float
    exit_reason: str
    action: str
    partial_taken: bool = False
    tp1_hit_index: int | None = None
    be_armed: bool = False
    pattern: str | None = None


@dataclass
class BacktestSummary:
    symbol: str
    timeframe: str
    lookback_days: int
    bars: int
    trades: int
    winrate: float
    avg_rr: float
    pnl_pct: float
    max_drawdown_pct: float
    prepare_count: int
    enter_count: int
    exit_signal_count: int
    if_then_triggered: int
    if_then_armed: int
    if_then_executed: int
    if_then_closed: int
    if_then_failed: int
    momentum_exit_count: int
    timeout_count: int
    tp_hit_count: int
    stop_count: int
    report_path: str = ''
    swing_reversal_observe: bool = False
    combined_validation: Dict[str, Any] = field(default_factory=dict)


@contextmanager
def _patched_pipeline(candles: List[Dict[str, Any]], state_box: Dict[str, Any], timeframe: str = DEFAULT_TIMEFRAME):
    original = {
        'get_price': pipeline.get_price,
        'get_klines': pipeline.get_klines,
        'aggregate_to_4h': pipeline.aggregate_to_4h,
        'aggregate_to_1d': pipeline.aggregate_to_1d,
        'load_market_state': pipeline.load_market_state,
        'save_market_state': pipeline.save_market_state,
        'load_position_state': getattr(pipeline, 'load_position_state', None),
    }

    def _get_price(symbol: str = 'BTCUSDT') -> float:
        return float(candles[-1]['close']) if candles else 0.0

    tf = str(timeframe or DEFAULT_TIMEFRAME).lower()

    def _aggregate(interval: str):
        interval = str(interval or tf).lower()
        if interval == tf:
            return candles
        if tf == '15m':
            if interval == '1h':
                return aggregate_candles(candles, 4)
            if interval == '4h':
                return aggregate_candles(candles, 16)
            if interval == '1d':
                return aggregate_candles(candles, 96)
        if interval == '4h':
            return aggregate_to_4h(candles)
        if interval == '1d':
            return aggregate_to_1d(candles)
        return candles

    def _get_klines(symbol: str = 'BTCUSDT', interval: str = '1h', limit: int = 200):
        return _aggregate(interval)[-limit:]

    pipeline.get_price = _get_price
    pipeline.get_klines = _get_klines
    pipeline.aggregate_to_4h = aggregate_to_4h
    pipeline.aggregate_to_1d = aggregate_to_1d
    pipeline.load_market_state = lambda: dict(state_box.get('market_state') or {})
    pipeline.save_market_state = lambda state: state_box.__setitem__('market_state', dict(state or {}))
    if original['load_position_state'] is not None:
        pipeline.load_position_state = lambda: {'active': False}

    try:
        yield
    finally:
        pipeline.get_price = original['get_price']
        pipeline.get_klines = original['get_klines']
        pipeline.aggregate_to_4h = original['aggregate_to_4h']
        pipeline.aggregate_to_1d = original['aggregate_to_1d']
        pipeline.load_market_state = original['load_market_state']
        pipeline.save_market_state = original['save_market_state']
        if original['load_position_state'] is not None:
            pipeline.load_position_state = original['load_position_state']




def _build_snapshot_compat(symbol: str, timeframe: str) -> Dict[str, Any]:
    try:
        return pipeline.build_full_snapshot(symbol, timeframe=timeframe)
    except TypeError as exc:
        if 'timeframe' not in str(exc):
            raise
        return pipeline.build_full_snapshot(symbol)

def _side_multiplier(side: str) -> float:
    return 1.0 if str(side).upper() == 'LONG' else -1.0


def _pct_move(entry_price: float, exit_price: float, side: str) -> float:
    if entry_price <= 0:
        return 0.0
    raw = ((exit_price - entry_price) / entry_price) * 100.0
    return raw * _side_multiplier(side)


def _safe_float(*values: Any, default: float = 0.0) -> float:
    for value in values:
        try:
            if value is None:
                continue
            return float(value)
        except Exception:
            continue
    return default


def _safe_int(*values: Any, default: int = 0) -> int:
    for value in values:
        try:
            if value is None:
                continue
            return int(value)
        except Exception:
            continue
    return default


def _norm_label(value: Any) -> str:
    return str(value or '').strip().upper()


def _edge_score(snapshot: Dict[str, Any]) -> float:
    return max(
        _safe_float(snapshot.get('edge_score'), default=0.0),
        _safe_float(snapshot.get('trade_edge_score'), default=0.0),
        _safe_float(snapshot.get('bot_edge_score'), default=0.0),
    )




def _medium_phase(snapshot: Dict[str, Any]) -> str:
    forecast = snapshot.get('forecast') or {}
    medium = forecast.get('medium') or {}
    return _norm_label(medium.get('phase') or snapshot.get('medium_phase'))


def _tp3_enabled(snapshot: Dict[str, Any], side: str) -> bool:
    return _norm_label(side) == 'LONG' and _medium_phase(snapshot) == 'MARKUP'


def _true_range(current: Dict[str, Any], prev_close: float | None) -> float:
    high = _safe_float(current.get('high'), current.get('close'), default=0.0)
    low = _safe_float(current.get('low'), current.get('close'), default=0.0)
    if prev_close is None:
        return max(0.0, high - low)
    return max(0.0, max(high - low, abs(high - prev_close), abs(low - prev_close)))


def _atr_pct(window: List[Dict[str, Any]], period: int = 14) -> float:
    series = list(window or [])
    if len(series) < 2:
        return 0.6
    tail = series[-max(period + 1, 3):]
    trs: list[float] = []
    prev_close = None
    for bar in tail:
        close = _safe_float(bar.get('close'), default=0.0)
        trs.append(_true_range(bar, prev_close))
        prev_close = close
    close = _safe_float(tail[-1].get('close'), default=0.0)
    atr = sum(trs[-period:]) / max(1, len(trs[-period:]))
    if close <= 0:
        return 0.6
    return max(0.15, round((atr / close) * 100.0, 4))

def _stop_pct(snapshot: Dict[str, Any], entry_price: float, side: str, atr_pct: float | None = None) -> float:
    if entry_price <= 0:
        return DEFAULT_MIN_STOP_PCT
    side = _norm_label(side)
    atr_pct = max(_safe_float(atr_pct, default=0.0), 0.0)
    anchor_pct = 0.0
    if side == 'LONG':
        anchor = snapshot.get('range_low')
        if anchor is None:
            anchor = snapshot.get('break_level')
        if anchor is not None:
            anchor_pct = max(0.0, ((entry_price - float(anchor)) / entry_price) * 100.0)
    elif side == 'SHORT':
        anchor = snapshot.get('range_high')
        if anchor is None:
            anchor = snapshot.get('break_level')
        if anchor is not None:
            anchor_pct = max(0.0, ((float(anchor) - entry_price) / entry_price) * 100.0)

    atr_stop = atr_pct * DEFAULT_STOP_ATR_MULT if atr_pct > 0 else 0.0
    structural_stop = anchor_pct * 1.05 if anchor_pct > 0 else 0.0
    blended = max(structural_stop, atr_stop, DEFAULT_MIN_STOP_PCT)
    if structural_stop > 0 and atr_stop > 0:
        blended = max(min(DEFAULT_MAX_STOP_PCT, structural_stop), atr_stop)
    return round(min(DEFAULT_MAX_STOP_PCT, max(DEFAULT_MIN_STOP_PCT, blended or DEFAULT_MIN_STOP_PCT)), 4)


def _quality_gate(snapshot: Dict[str, Any], side: str, entry_source: str | None = None) -> tuple[bool, str | None]:
    side = _norm_label(side)
    source = _norm_label(entry_source)
    if side not in {'LONG', 'SHORT'}:
        return False, 'INVALID_SIDE'

    context_label = _norm_label(snapshot.get('context_label'))
    context_score = _safe_int(snapshot.get('context_score'), default=0)
    has_context = context_label in {'VALID', 'STRONG'} or context_score >= 2
    strong_flip_context = source in {'PRESSURE_FLIP_ARM', 'MID_CROSS_FLIP', 'FLIP_CONFIRM'} and context_score >= 1
    if not has_context and not strong_flip_context:
        return False, 'WEAK_CONTEXT'

    bias_score = _safe_int(snapshot.get('bias_score'), default=0)
    min_bias = 2
    if source in {'PRESSURE_FLIP_ARM', 'MID_CROSS_FLIP', 'FLIP_CONFIRM'}:
        min_bias = 1
    if abs(bias_score) < min_bias:
        return False, 'LOW_BIAS'
    if side == 'LONG' and bias_score < min_bias:
        return False, 'BIAS_CONFLICT'
    if side == 'SHORT' and bias_score > -min_bias:
        return False, 'BIAS_CONFLICT'

    session_side = _norm_label(snapshot.get('session_side') or snapshot.get('trend_pressure_side') or 'NEUTRAL')
    session_strength = _norm_label(snapshot.get('session_strength') or snapshot.get('trend_pressure_strength') or 'LOW')
    if session_strength == 'HIGH':
        if side == 'LONG' and session_side == 'SHORT':
            return False, 'SESSION_CONFLICT'
        if side == 'SHORT' and session_side == 'LONG':
            return False, 'SESSION_CONFLICT'

    if source in {'PRESSURE_FLIP_ARM', 'MID_CROSS_FLIP', 'FLIP_CONFIRM'}:
        edge_score = _edge_score(snapshot)
        block_pressure_strength = _norm_label(snapshot.get('block_pressure_strength') or snapshot.get('trend_pressure_strength') or 'LOW')
        confidence = _safe_float(snapshot.get('confidence'), default=0.0)
        has_score_support = confidence >= 47.0 or edge_score >= 36.0
        has_pressure_support = block_pressure_strength in {'MID', 'HIGH'}
        if not has_pressure_support and not has_score_support:
            # Pattern B: PRESSURE_FLIP_ARM + ctx>=2 + |bias|>=3 + trigger!=RECLAIM
            trigger_type = _norm_label(snapshot.get('trigger_type') or '')
            if (
                source == 'PRESSURE_FLIP_ARM'
                and context_score >= 2
                and abs(bias_score) >= 3
                and trigger_type != 'RECLAIM'
            ):
                return True, 'PATTERN_B'
            return False, 'FLIP_EDGE_TOO_WEAK'

    return True, None


def _context_filter_ok(snapshot: Dict[str, Any]) -> bool:
    """Pattern A context filter: block weak entries without conviction."""
    ctx = _safe_int(snapshot.get('context_score'), default=0)
    bias = _safe_int(snapshot.get('bias_score'), default=0)
    session = _norm_label(
        snapshot.get('session_strength')
        or snapshot.get('trend_pressure_strength')
        or 'LOW'
    )
    # Strong context — always allow
    if ctx >= 2:
        return True
    # Weak/no context — allow only with strong bias AND non-LOW session
    if abs(bias) >= 4 and session not in {'', 'NONE', 'LOW'}:
        return True
    return False


def _tp_pct(snapshot: Dict[str, Any], stop_pct: float, side: str, atr_pct: float | None = None) -> float:
    stop_pct = max(_safe_float(stop_pct, default=DEFAULT_MIN_STOP_PCT), DEFAULT_MIN_STOP_PCT)
    atr_pct = max(_safe_float(atr_pct, default=0.0), 0.0)
    atr_target = atr_pct * DEFAULT_TP2_ATR_MULT if atr_pct > 0 else 0.0
    rr_floor = stop_pct * 1.9
    rr_cap = stop_pct * 2.2
    floor_value = max(rr_floor, atr_target, 1.0)
    return round(min(rr_cap, floor_value), 4)


def _tp1_pct(stop_pct: float, tp2_pct: float, atr_pct: float | None = None) -> float:
    stop_pct = max(_safe_float(stop_pct, default=DEFAULT_MIN_STOP_PCT), DEFAULT_MIN_STOP_PCT)
    atr_pct = max(_safe_float(atr_pct, default=0.0), 0.0)
    candidate = atr_pct * DEFAULT_TP1_ATR_MULT if atr_pct > 0 else 0.0
    floor_tp1 = max(stop_pct, 0.6)
    base_tp1 = max(candidate, floor_tp1)
    tp1_cap = max(floor_tp1, tp2_pct * 0.7)
    return round(min(tp1_cap, base_tp1, tp2_pct), 4)


def _price_levels(entry_price: float, side: str, stop_pct: float, tp1_pct: float, tp2_pct: float, be_buffer_pct: float) -> Dict[str, float]:
    side = _norm_label(side)
    if side == 'LONG':
        return {
            'stop': round(entry_price * (1.0 - stop_pct / 100.0), 4),
            'tp1': round(entry_price * (1.0 + tp1_pct / 100.0), 4),
            'tp2': round(entry_price * (1.0 + tp2_pct / 100.0), 4),
            'be_stop': round(entry_price * (1.0 + be_buffer_pct / 100.0), 4),
            'be_trigger': round(entry_price + ((entry_price * (tp1_pct / 100.0)) * DEFAULT_BE_TRIGGER_TO_TP1), 4),
        }
    return {
        'stop': round(entry_price * (1.0 + stop_pct / 100.0), 4),
        'tp1': round(entry_price * (1.0 - tp1_pct / 100.0), 4),
        'tp2': round(entry_price * (1.0 - tp2_pct / 100.0), 4),
        'be_stop': round(entry_price * (1.0 - be_buffer_pct / 100.0), 4),
        'be_trigger': round(entry_price - ((entry_price * (tp1_pct / 100.0)) * DEFAULT_BE_TRIGGER_TO_TP1), 4),
    }


def _bar_hits(bar: Dict[str, Any], levels: Dict[str, float], side: str, partial_taken: bool, be_armed: bool = False, tp2_taken: bool = False) -> tuple[bool, bool, bool, bool, float]:
    entry_price = 0.0
    high = _safe_float(bar.get('high'), bar.get('close'), default=entry_price)
    low = _safe_float(bar.get('low'), bar.get('close'), default=entry_price)
    open_price = _safe_float(bar.get('open'), bar.get('close'), default=entry_price)
    side = _norm_label(side)
    use_be_stop = partial_taken or be_armed
    if side == 'LONG':
        hit_tp1 = (not partial_taken) and high >= levels['tp1']
        hit_tp2 = (not tp2_taken) and high >= levels['tp2']
        hit_be_trigger = (not be_armed) and high >= levels['be_trigger']
        hit_stop = low <= (levels['be_stop'] if use_be_stop else levels['stop'])
        return hit_tp1, hit_tp2, hit_stop, hit_be_trigger, open_price
    hit_tp1 = (not partial_taken) and low <= levels['tp1']
    hit_tp2 = (not tp2_taken) and low <= levels['tp2']
    hit_be_trigger = (not be_armed) and low <= levels['be_trigger']
    hit_stop = high >= (levels['be_stop'] if use_be_stop else levels['stop'])
    return hit_tp1, hit_tp2, hit_stop, hit_be_trigger, open_price


def _intrabar_priority(bar: Dict[str, Any], side: str, open_price: float, levels: Dict[str, float], partial_taken: bool, be_armed: bool = False) -> list[str]:
    side = _norm_label(side)
    close_price = _safe_float(bar.get('close'), open_price, default=open_price)
    stop_key = 'be_stop' if partial_taken else 'stop'
    favorable_bar = (side == 'LONG' and close_price >= open_price) or (side == 'SHORT' and close_price <= open_price)
    if favorable_bar:
        ordered = ['BE', 'TP1', 'TP2', 'STOP']
    else:
        ordered = ['STOP', 'BE', 'TP1', 'TP2']
    if partial_taken:
        ordered = ['TP2', 'STOP'] if favorable_bar else ['STOP', 'TP2']
    elif be_armed:
        ordered = ['TP1', 'TP2', 'STOP'] if favorable_bar else ['STOP', 'TP1', 'TP2']
    return ordered


def _primary_side(snapshot: Dict[str, Any]) -> str:
    layer = snapshot.get('if_then_layer') or {}
    scenarios = layer.get('scenarios') or []
    if scenarios and _norm_label(scenarios[0].get('side')) in {'LONG', 'SHORT'}:
        return _norm_label(scenarios[0]['side'])
    side = _norm_label(snapshot.get('execution_side') or snapshot.get('active_block') or 'NONE')
    return side if side in {'LONG', 'SHORT'} else 'NONE'


def _confirmed_flip_break(window: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> tuple[bool, str]:
    active_block = _norm_label(snapshot.get('active_block') or 'NONE')
    watch_side = _norm_label(snapshot.get('watch_side') or 'NONE')
    break_level = snapshot.get('break_level')
    confirm_bars = max(1, _safe_int(snapshot.get('flip_prep_confirm_bars_needed'), default=2))
    if break_level is None or watch_side not in {'LONG', 'SHORT'} or len(window) < confirm_bars:
        return False, watch_side
    recent = window[-confirm_bars:]
    try:
        level = float(break_level)
        closes = [float(x.get('close') or 0.0) for x in recent]
    except Exception:
        return False, watch_side
    if active_block == 'SHORT' and watch_side == 'LONG':
        return all(c > level for c in closes), 'LONG'
    if active_block == 'LONG' and watch_side == 'SHORT':
        return all(c < level for c in closes), 'SHORT'
    if watch_side == 'LONG':
        return all(c > level for c in closes), 'LONG'
    if watch_side == 'SHORT':
        return all(c < level for c in closes), 'SHORT'
    return False, watch_side


def _historical_entry_candidate(window: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> tuple[str | None, str | None]:
    action = _norm_label(snapshot.get('action') or 'WAIT')
    side = _primary_side(snapshot)
    trigger_type = _norm_label(snapshot.get('trigger_type') or 'NONE')
    trigger_blocked = bool(snapshot.get('trigger_blocked'))
    if action == 'ENTER' and side in {'LONG', 'SHORT'}:
        return side, 'NATIVE_ENTER'
    if action == 'PREPARE' and side in {'LONG', 'SHORT'} and trigger_type not in {'', 'NONE'} and not trigger_blocked:
        return side, 'PRIMARY_PREPARE_TRIGGER'
    confirmed_flip, flip_side = _confirmed_flip_break(window, snapshot)
    if confirmed_flip and flip_side in {'LONG', 'SHORT'}:
        return flip_side, 'FLIP_CONFIRM'

    active_block = _norm_label(snapshot.get('active_block') or 'NONE')
    watch_side = _norm_label(snapshot.get('watch_side') or 'NONE')
    consensus_direction = _norm_label(snapshot.get('consensus_direction') or 'NONE')
    block_pressure = _norm_label(snapshot.get('block_pressure') or 'NONE')
    range_mid = snapshot.get('range_mid')
    if (
        range_mid is not None and len(window) >= 2 and watch_side in {'LONG', 'SHORT'}
        and consensus_direction == watch_side and block_pressure == 'AGAINST'
    ):
        prev_close = _safe_float(window[-2].get('close'), default=0.0)
        current_close = _safe_float(window[-1].get('close'), default=0.0)
        mid = float(range_mid)
        if active_block == 'SHORT' and watch_side == 'LONG' and prev_close <= mid < current_close:
            return 'LONG', 'MID_CROSS_FLIP'
        if active_block == 'LONG' and watch_side == 'SHORT' and prev_close >= mid > current_close:
            return 'SHORT', 'MID_CROSS_FLIP'

    if watch_side in {'LONG', 'SHORT'} and consensus_direction == watch_side and block_pressure == 'AGAINST':
        if active_block in {'LONG', 'SHORT'} and active_block != watch_side:
            return watch_side, 'PRESSURE_FLIP_ARM'
    return None, None




def _progress_to_target(entry_price: float, current_price: float, side: str, tp2_price: float) -> float:
    entry_price = float(entry_price or 0.0)
    current_price = float(current_price or 0.0)
    tp2_price = float(tp2_price or 0.0)
    if entry_price <= 0 or tp2_price <= 0 or current_price <= 0:
        return 0.0
    side = _norm_label(side)
    if side == 'LONG':
        denom = max(tp2_price - entry_price, 1e-9)
        return max(0.0, min(1.5, (current_price - entry_price) / denom))
    denom = max(entry_price - tp2_price, 1e-9)
    return max(0.0, min(1.5, (entry_price - current_price) / denom))


def _update_timeout_state(position: Dict[str, Any], current_price: float, held_bars: int) -> Dict[str, Any]:
    levels = _price_levels(
        entry_price=float(position['entry_price']),
        side=str(position['side']),
        stop_pct=float(position['stop_pct']),
        tp1_pct=float(position['tp1_pct']),
        tp2_pct=float(position['tp2_pct']),
        be_buffer_pct=float(position.get('be_buffer_pct') or DEFAULT_BE_BUFFER_PCT),
    )
    progress = _progress_to_target(float(position['entry_price']), current_price, str(position['side']), levels['tp2'])
    pnl_pct = _pct_move(float(position['entry_price']), float(current_price), str(position['side']))
    peak_progress = max(float(position.get('peak_progress') or 0.0), progress)
    peak_pnl_pct = max(float(position.get('peak_pnl_pct') or 0.0), pnl_pct)
    last_progress_held_bars = int(position.get('last_progress_held_bars') or 0)
    progress_step = float(position.get('progress_step') or 0.08)
    pnl_step = float(position.get('pnl_step') or 0.12)
    if progress >= peak_progress - progress_step or pnl_pct >= peak_pnl_pct - pnl_step:
        last_progress_held_bars = max(last_progress_held_bars, held_bars)
    position['current_progress'] = round(progress, 4)
    position['current_pnl_pct'] = round(pnl_pct, 4)
    position['peak_progress'] = round(peak_progress, 4)
    position['peak_pnl_pct'] = round(peak_pnl_pct, 4)
    position['last_progress_held_bars'] = last_progress_held_bars
    return position


def _dynamic_timeout_bars(position: Dict[str, Any], current_price: float, atr_pct: float) -> int:
    base = int(position.get('base_timeout_bars') or DEFAULT_HORIZON_BARS)
    levels = _price_levels(
        entry_price=float(position['entry_price']),
        side=str(position['side']),
        stop_pct=float(position['stop_pct']),
        tp1_pct=float(position['tp1_pct']),
        tp2_pct=float(position['tp2_pct']),
        be_buffer_pct=float(position.get('be_buffer_pct') or DEFAULT_BE_BUFFER_PCT),
    )
    current_progress = _progress_to_target(float(position['entry_price']), current_price, str(position['side']), levels['tp2'])
    peak_progress = max(current_progress, float(position.get('peak_progress') or 0.0))
    current_pnl = _pct_move(float(position['entry_price']), float(current_price), str(position['side']))
    peak_pnl = max(current_pnl, float(position.get('peak_pnl_pct') or 0.0))

    timeout = base
    if peak_progress >= 0.85:
        timeout = int(round(base * 3.0))
    elif peak_progress >= 0.6:
        timeout = int(round(base * 2.4))
    elif peak_progress >= 0.35:
        timeout = int(round(base * 1.8))
    elif atr_pct <= 0.45:
        timeout = int(round(base * 1.4))

    if bool(position.get('partial_taken')):
        timeout = max(timeout, int(round(base * 3.0)))
    elif peak_pnl >= 0.8:
        timeout = max(timeout, int(round(base * 2.5)))
    elif peak_pnl >= 0.35:
        timeout = max(timeout, int(round(base * 1.9)))

    if peak_progress < 0.15 and peak_pnl < 0.15 and not bool(position.get('partial_taken')):
        timeout = min(timeout, base)

    return max(base, timeout)


def _timeout_exit_allowed(position: Dict[str, Any], current_price: float, held_bars: int, atr_pct: float) -> bool:
    dynamic_timeout = _dynamic_timeout_bars(position, current_price, atr_pct)
    if held_bars < dynamic_timeout:
        return False

    levels = _price_levels(
        entry_price=float(position['entry_price']),
        side=str(position['side']),
        stop_pct=float(position['stop_pct']),
        tp1_pct=float(position['tp1_pct']),
        tp2_pct=float(position['tp2_pct']),
        be_buffer_pct=float(position.get('be_buffer_pct') or DEFAULT_BE_BUFFER_PCT),
    )
    current_progress = _progress_to_target(float(position['entry_price']), current_price, str(position['side']), levels['tp2'])
    current_pnl = _pct_move(float(position['entry_price']), float(current_price), str(position['side']))
    peak_progress = max(current_progress, float(position.get('peak_progress') or 0.0))
    peak_pnl = max(current_pnl, float(position.get('peak_pnl_pct') or 0.0))
    last_progress_held_bars = int(position.get('last_progress_held_bars') or 0)
    bars_since_progress = max(0, held_bars - last_progress_held_bars)

    productive_runner = bool(position.get('partial_taken')) or peak_progress >= 0.45 or peak_pnl >= 0.6
    structural_progress = peak_progress >= 0.22 or peak_pnl >= 0.25
    dead_trade = peak_progress < 0.15 and peak_pnl < 0.15 and not bool(position.get('partial_taken'))

    if dead_trade:
        return True

    if productive_runner:
        if bars_since_progress <= 5 and current_pnl >= -0.1:
            return False
        hard_limit = max(dynamic_timeout + 8, int(round(dynamic_timeout * 1.7)))
        return held_bars >= hard_limit

    if structural_progress:
        if bars_since_progress <= 3 and current_pnl >= -0.15:
            return False
        hard_limit = max(dynamic_timeout + 6, int(round(dynamic_timeout * 1.5)))
        return held_bars >= hard_limit

    return True



def _dead_trade_exit_allowed(position: Dict[str, Any], current_price: float, held_bars: int, atr_pct: float) -> bool:
    if bool(position.get('partial_taken')) or bool(position.get('tp2_taken')):
        return False
    min_bars = int(position.get('dead_trade_min_bars') or DEFAULT_DEAD_TRADE_MIN_BARS)
    if held_bars < min_bars:
        return False
    current_pnl = _pct_move(float(position['entry_price']), float(current_price), str(position['side']))
    if current_pnl < 0 or current_pnl > float(position.get('dead_trade_max_profit_pct') or DEFAULT_DEAD_TRADE_MAX_PROFIT_PCT):
        return False
    entry_atr_pct = max(_safe_float(position.get('entry_atr_pct'), default=0.0), 0.0)
    if entry_atr_pct <= 0 or atr_pct <= 0:
        return False
    compression_ratio = float(position.get('dead_trade_compression_ratio') or DEFAULT_DEAD_TRADE_COMPRESSION_RATIO)
    compressed = atr_pct <= max(0.15, entry_atr_pct * compression_ratio)
    if not compressed:
        return False
    peak_pnl = max(float(position.get('peak_pnl_pct') or 0.0), current_pnl)
    peak_progress = float(position.get('peak_progress') or 0.0)
    return peak_pnl <= float(position.get('dead_trade_max_profit_pct') or DEFAULT_DEAD_TRADE_MAX_PROFIT_PCT) and peak_progress < 0.45


def _equity_drawdown(equity_curve: Iterable[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        dd = peak - value
        max_dd = max(max_dd, dd)
    return round(max_dd, 4)


def _write_report(output_dir: str | Path, summary: BacktestSummary, trades: List[BacktestTrade]) -> str:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    days = getattr(summary, 'lookback_days', 90) or 90
    report_path = output_dir / f'backtest_{days}d_report.json'
    payload = {
        'summary': asdict(summary),
        'trades': [asdict(x) for x in trades],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(report_path)


def format_backtest_summary(summary: Dict[str, Any]) -> List[str]:
    return [
        f"BACKTEST {summary.get('lookback_days', 90)}D",
        f"Trades: {summary.get('trades', 0)}",
        f"Winrate: {summary.get('winrate', 0.0)}%",
        f"Avg RR: {summary.get('avg_rr', 0.0)}",
        f"PnL: {summary.get('pnl_pct', 0.0)}%",
        f"Max DD: -{summary.get('max_drawdown_pct', 0.0)}%",
        'IF-THEN:',
        f"- triggered: {summary.get('if_then_triggered', 0)}",
        f"- armed: {summary.get('if_then_armed', summary.get('if_then_executed', 0))}",
        f"- entered: {summary.get('if_then_executed', 0)}",
        f"- closed: {summary.get('if_then_closed', summary.get('trades', 0))}",
        f"- failed: {summary.get('if_then_failed', 0)}",
        'EXITS:',
        f"- tp_hit: {summary.get('tp_hit_count', 0)}",
        f"- stop: {summary.get('stop_count', 0)}",
        f"- timeout: {summary.get('timeout_count', 0)}",
    ]


def _apply_intrabar_management(position: Dict[str, Any], bar: Dict[str, Any], current_index: int) -> tuple[str | None, float | None, Dict[str, Any]]:
    levels = _price_levels(
        entry_price=float(position['entry_price']),
        side=str(position['side']),
        stop_pct=float(position['stop_pct']),
        tp1_pct=float(position['tp1_pct']),
        tp2_pct=float(position['tp2_pct']),
        be_buffer_pct=float(position.get('be_buffer_pct') or DEFAULT_BE_BUFFER_PCT),
    )
    hit_tp1, hit_tp2, hit_stop, hit_be_trigger, open_price = _bar_hits(bar, levels, str(position['side']), bool(position.get('partial_taken')), bool(position.get('be_armed')), bool(position.get('tp2_taken')))
    if not (hit_tp1 or hit_tp2 or hit_stop or hit_be_trigger):
        return None, None, position

    ordered = _intrabar_priority(bar, str(position['side']), open_price, levels, bool(position.get('partial_taken')), bool(position.get('be_armed')))
    for event in ordered:
        if event == 'BE' and hit_be_trigger and not position.get('be_armed'):
            position['be_armed'] = True
            hit_be_trigger = False
            hit_tp1, hit_tp2, hit_stop, _be_trigger, _open = _bar_hits(bar, levels, str(position['side']), bool(position.get('partial_taken')), True, bool(position.get('tp2_taken')))
            continue
        if event == 'TP1' and hit_tp1 and not position.get('partial_taken'):
            position['partial_taken'] = True
            position['be_armed'] = True
            position['tp1_hit_index'] = current_index
            partial_size = float(position.get('partial_size') or DEFAULT_PARTIAL_SIZE)
            partial_gain = _pct_move(float(position['entry_price']), levels['tp1'], str(position['side']))
            position['realized_pnl_pct'] = round(float(position.get('realized_pnl_pct') or 0.0) + partial_gain * partial_size, 4)
            position['remaining_size'] = round(max(0.0, float(position.get('remaining_size') or 1.0) - partial_size), 4)
            hit_tp1 = False
            position['be_armed'] = True
            # continue processing same bar for remainder after BE arm
            hit_tp1, hit_tp2, hit_stop, hit_be_trigger, _open = _bar_hits(bar, levels, str(position['side']), True, True, bool(position.get('tp2_taken')))
            continue
        if event == 'TP2' and hit_tp2:
            if bool(position.get('tp3_enabled')) and not bool(position.get('tp2_taken')):
                tail_size = min(float(position.get('tp3_tail_size') or DEFAULT_TP3_TAIL_SIZE), float(position.get('remaining_size') or 0.0))
                close_size = max(0.0, float(position.get('remaining_size') or 0.0) - tail_size)
                if close_size > 0:
                    tp2_gain = _pct_move(float(position['entry_price']), levels['tp2'], str(position['side']))
                    position['realized_pnl_pct'] = round(float(position.get('realized_pnl_pct') or 0.0) + tp2_gain * close_size, 4)
                position['remaining_size'] = round(max(0.0, tail_size), 4)
                position['tp2_taken'] = True
                position['tp2_hit_index'] = current_index
                position['be_armed'] = True
                return None, None, position
            return 'TP_HIT', levels['tp2'], position
        if event == 'STOP' and hit_stop:
            return 'STOP', levels['be_stop'] if (position.get('partial_taken') or position.get('be_armed')) else levels['stop'], position
    return None, None, position


def run_backtest_from_candles(
    candles: List[Dict[str, Any]],
    symbol: str = 'BTCUSDT',
    timeframe: str = DEFAULT_TIMEFRAME,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    horizon_bars: int = DEFAULT_HORIZON_BARS,
    output_dir: str | Path = 'backtests',
) -> Dict[str, Any]:
    candles = list(candles or [])
    effective_min_window = _effective_min_window_bars(timeframe)
    effective_max_window = _effective_max_window_bars(timeframe)

    if len(candles) < effective_min_window + horizon_bars + 5:
        summary = BacktestSummary(
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            bars=len(candles),
            trades=0,
            winrate=0.0,
            avg_rr=0.0,
            pnl_pct=0.0,
            max_drawdown_pct=0.0,
            prepare_count=0,
            enter_count=0,
            exit_signal_count=0,
            if_then_triggered=0,
            if_then_armed=0,
            if_then_executed=0,
            if_then_closed=0,
            if_then_failed=0,
            momentum_exit_count=0,
            timeout_count=0,
            tp_hit_count=0,
            stop_count=0,
        )
        report_path = _write_report(output_dir, summary, [])
        summary.report_path = report_path
        data = asdict(summary)
        data['summary_lines'] = format_backtest_summary(data)
        data['trades_data'] = []
        return data

    state_box: Dict[str, Any] = {'market_state': {}}
    position: Dict[str, Any] | None = None
    trades: List[BacktestTrade] = []
    equity_curve: List[float] = []
    cumulative_pnl = 0.0
    prepare_count = 0
    enter_count = 0
    exit_signal_count = 0
    if_then_triggered = 0
    if_then_armed = 0
    if_then_executed = 0
    if_then_failed = 0
    momentum_exit_count = 0
    timeout_count = 0
    tp_hit_count = 0
    stop_count = 0
    entry_filter_lock_until = -1

    last_index_for_entry = max(0, len(candles) - horizon_bars - 1)
    for i in range(effective_min_window, len(candles)):
        window = candles[max(0, i - effective_max_window + 1):i + 1]
        with _patched_pipeline(window, state_box, timeframe=timeframe):
            snapshot = _build_snapshot_compat(symbol, timeframe)

        action = _norm_label(snapshot.get('action') or 'WAIT')
        side = _primary_side(snapshot)
        current_price = _safe_float(window[-1].get('close'), default=0.0)
        if_then_layer = snapshot.get('if_then_layer') or {}
        scenarios = if_then_layer.get('scenarios') or []
        primary = scenarios[0] if scenarios else {}
        trigger_type = _norm_label(snapshot.get('trigger_type') or 'NONE')
        trigger_blocked = bool(snapshot.get('trigger_blocked'))
        trigger_ready = trigger_type not in {'', 'NONE'} and not trigger_blocked
        historical_side, historical_source = _historical_entry_candidate(window, snapshot)
        historical_triggered = historical_side in {'LONG', 'SHORT'}

        if action == 'PREPARE':
            prepare_count += 1
        if action == 'EXIT':
            exit_signal_count += 1
        if trigger_ready or historical_triggered:
            if_then_triggered += 1

        if position is None:
            if i <= entry_filter_lock_until:
                continue
            if historical_triggered and i <= last_index_for_entry:
                entry_side = historical_side or side
                entry_source = historical_source or action
                quality_ok, quality_reason = _quality_gate(snapshot, entry_side, entry_source)
                if not quality_ok:
                    if_then_failed += 1
                    continue
                # Pattern A context filter (skip for Pattern B which has its own gate)
                if quality_reason != 'PATTERN_B':
                    if not _context_filter_ok(snapshot):
                        if_then_failed += 1
                        continue
                if 'entry_filter_ok' in snapshot or 'entry_filter_reason' in snapshot or 'entry_filter_reason_code' in snapshot:
                    entry_filter_ctx = {
                        'ok': bool(snapshot.get('entry_filter_ok')),
                        'reason': str(snapshot.get('entry_filter_reason') or 'OK'),
                        'reason_code': str(snapshot.get('entry_filter_reason_code') or ('OK' if snapshot.get('entry_filter_ok', True) else 'FILTERED')),
                    }
                else:
                    entry_filter_ctx = {'ok': True, 'reason': 'OK', 'reason_code': 'OK'}
                if not bool(entry_filter_ctx.get('ok')):
                    if_then_failed += 1
                    entry_filter_lock_until = max(entry_filter_lock_until, i + horizon_bars)
                    continue
                if_then_armed += 1
                enter_count += 1
                if_then_executed += 1
                atr_pct = _atr_pct(window)
                stop_pct = _stop_pct(snapshot, current_price, entry_side, atr_pct=atr_pct)
                tp2_pct = _tp_pct(snapshot, stop_pct, entry_side, atr_pct=atr_pct)
                tp1_pct = _tp1_pct(stop_pct, tp2_pct, atr_pct=atr_pct)
                position = {
                    'side': entry_side,
                    'entry_price': current_price,
                    'entry_index': i,
                    'stop_pct': stop_pct,
                    'tp1_pct': tp1_pct,
                    'tp2_pct': tp2_pct,
                    'entry_action': entry_source,
                    'entry_quality_gate': quality_reason or 'PASS',
                    'pattern': 'B2' if quality_reason == 'PATTERN_B' else None,
                    'entry_filter_reason': str(entry_filter_ctx.get('reason') or 'OK'),
                    'entry_filter_reason_code': str(entry_filter_ctx.get('reason_code') or 'OK'),
                    'partial_taken': False,
                    'tp1_hit_index': None,
                    'be_armed': False,
                    'be_buffer_pct': DEFAULT_BE_BUFFER_PCT,
                    'partial_size': DEFAULT_PARTIAL_SIZE,
                    'remaining_size': 1.0,
                    'realized_pnl_pct': 0.0,
                    'entry_atr_pct': atr_pct,
                    'base_timeout_bars': horizon_bars,
                    'tp3_enabled': _tp3_enabled(snapshot, entry_side),
                    'tp3_tail_size': DEFAULT_TP3_TAIL_SIZE,
                    'tp2_taken': False,
                    'tp2_hit_index': None,
                    'dead_trade_min_bars': DEFAULT_DEAD_TRADE_MIN_BARS,
                    'dead_trade_max_profit_pct': DEFAULT_DEAD_TRADE_MAX_PROFIT_PCT,
                    'dead_trade_compression_ratio': DEFAULT_DEAD_TRADE_COMPRESSION_RATIO,
                    'be_trigger_ratio': DEFAULT_BE_TRIGGER_TO_TP1,
                    'peak_progress': 0.0,
                    'peak_pnl_pct': 0.0,
                    'current_progress': 0.0,
                    'current_pnl_pct': 0.0,
                    'last_progress_held_bars': 0,
                    'progress_step': 0.08,
                    'pnl_step': 0.12,
                }
            elif action == 'PREPARE' and trigger_ready:
                pass
            elif primary and (trigger_ready or historical_triggered) and action not in {'ENTER', 'PREPARE'}:
                if_then_failed += 1
            continue

        held_bars = i - int(position['entry_index'])
        exit_reason = None
        exit_price = None
        current_atr_pct = _atr_pct(window)
        position = _update_timeout_state(position, current_price, held_bars)
        dynamic_timeout = _dynamic_timeout_bars(position, current_price, current_atr_pct)

        exit_reason, exit_price, position = _apply_intrabar_management(position, window[-1], i)
        if exit_reason is None and action == 'EXIT':
            exit_reason = 'EXIT_SIGNAL'
            exit_price = current_price
        elif exit_reason is None and _norm_label(side) in {'LONG', 'SHORT'} and _norm_label(side) != _norm_label(position['side']) and action == 'ENTER':
            exit_reason = 'SIDE_FLIP'
            exit_price = current_price
        elif exit_reason is None and bool(snapshot.get('momentum_exhausted')):
            exit_reason = 'MOMENTUM_EXHAUSTED'
            exit_price = current_price
            momentum_exit_count += 1
        elif exit_reason is None and _dead_trade_exit_allowed(position, current_price, held_bars, current_atr_pct):
            exit_reason = 'TIMEOUT'
            exit_price = current_price
        elif exit_reason is None and _timeout_exit_allowed(position, current_price, held_bars, current_atr_pct):
            exit_reason = 'TIMEOUT'
            exit_price = current_price

        if exit_reason is None:
            continue

        remaining_size = float(position.get('remaining_size') or 0.0)
        realized_pnl = float(position.get('realized_pnl_pct') or 0.0)
        remaining_pnl = _pct_move(float(position['entry_price']), float(exit_price or current_price), str(position['side'])) * max(remaining_size, 0.0)
        pnl_pct = round(realized_pnl + remaining_pnl, 4)
        stop_pct = float(position['stop_pct']) or 0.5
        rr = round(pnl_pct / stop_pct, 4) if stop_pct else 0.0
        trade = BacktestTrade(
            entry_index=int(position['entry_index']),
            exit_index=i,
            side=_norm_label(position['side']),
            entry_price=round(float(position['entry_price']), 4),
            exit_price=round(float(exit_price or current_price), 4),
            pnl_pct=pnl_pct,
            rr=rr,
            exit_reason=exit_reason,
            action=_norm_label(position.get('entry_action') or 'ENTER'),
            partial_taken=bool(position.get('partial_taken')),
            tp1_hit_index=position.get('tp1_hit_index'),
            be_armed=bool(position.get('be_armed')),
            pattern=position.get('pattern'),
        )
        trades.append(trade)
        cumulative_pnl += trade.pnl_pct
        equity_curve.append(round(cumulative_pnl, 4))
        if exit_reason == 'TIMEOUT':
            timeout_count += 1
        elif exit_reason == 'TP_HIT':
            tp_hit_count += 1
        elif exit_reason == 'STOP':
            stop_count += 1
        position = None

    wins = sum(1 for t in trades if t.pnl_pct > 0)
    summary = BacktestSummary(
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=lookback_days,
        bars=len(candles),
        trades=len(trades),
        winrate=round((wins / len(trades) * 100.0), 2) if trades else 0.0,
        avg_rr=round(sum(t.rr for t in trades) / len(trades), 4) if trades else 0.0,
        pnl_pct=round(float(sum(t.pnl_pct for t in trades)), 4),
        max_drawdown_pct=_equity_drawdown(equity_curve),
        prepare_count=prepare_count,
        enter_count=enter_count,
        exit_signal_count=exit_signal_count,
        if_then_triggered=if_then_triggered,
        if_then_armed=if_then_armed,
        if_then_executed=if_then_executed,
        if_then_closed=len(trades),
        if_then_failed=if_then_failed,
        momentum_exit_count=momentum_exit_count,
        timeout_count=timeout_count,
        tp_hit_count=tp_hit_count,
        stop_count=stop_count,
    )
    report_path = _write_report(output_dir, summary, trades)
    summary.report_path = report_path
    data = asdict(summary)
    data['summary_lines'] = format_backtest_summary(data)
    data['trades_data'] = [asdict(x) for x in trades]
    return data


def bars_for_days(days: int = DEFAULT_LOOKBACK_DAYS, timeframe: str = DEFAULT_TIMEFRAME) -> int:
    tf = str(timeframe).lower()
    mapping = {
        '1h': 24,
        '4h': 6,
        '1d': 1,
        '15m': 96,
        '5m': 288,
    }
    return int(days * mapping.get(tf, 24))


def run_backtest(
    symbol: str = 'BTCUSDT',
    timeframe: str = DEFAULT_TIMEFRAME,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    output_dir: str | Path = 'backtests',
) -> Dict[str, Any]:
    bars = bars_for_days(lookback_days, timeframe) + _effective_min_window_bars(timeframe) + DEFAULT_HORIZON_BARS + 10
    candles = get_klines(symbol=symbol, interval=timeframe, limit=bars)
    return run_backtest_from_candles(
        candles=candles,
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=lookback_days,
        horizon_bars=DEFAULT_HORIZON_BARS,
        output_dir=output_dir,
    )
