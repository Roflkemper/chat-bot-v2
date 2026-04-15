from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from core import pipeline
from market_data.ohlcv import get_klines
from services.timeframe_aggregator import aggregate_to_4h, aggregate_to_1d
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


@contextmanager
def _patched_pipeline(candles: List[Dict[str, Any]], state_box: Dict[str, Any]):
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

    def _get_klines(symbol: str = 'BTCUSDT', interval: str = '1h', limit: int = 200):
        if interval == '1h':
            return candles[-limit:]
        if interval == '4h':
            return aggregate_to_4h(candles)[-limit:]
        if interval == '1d':
            return aggregate_to_1d(candles)[-limit:]
        return candles[-limit:]

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


def _pattern_b_decision(signal: Dict[str, Any] | None) -> tuple[bool, str | None]:
    payload = signal if isinstance(signal, dict) else {}
    diagnostic_context = payload.get('diagnostic_context') if isinstance(payload.get('diagnostic_context'), dict) else {}

    action_type = _norm_label(
        payload.get('action_type')
        or payload.get('entry_source')
        or payload.get('historical_source')
        or diagnostic_context.get('entry_source')
        or payload.get('action')
        or ''
    )
    veto_reason = _norm_label(payload.get('veto_reason') or payload.get('gate_reason') or '')
    context_score = _safe_int(
        diagnostic_context.get('context_score', payload.get('context_score')),
        default=0,
    )
    bias_score = _safe_int(
        diagnostic_context.get('bias_score', payload.get('bias_score')),
        default=0,
    )
    trigger_type = _norm_label(
        diagnostic_context.get('trigger_type')
        or payload.get('trigger_type')
        or payload.get('trigger')
        or ''
    )

    if trigger_type == 'RECLAIM':
        return False, 'PATTERN_B_RECLAIM_FILTER'

    allowed = (
        action_type == 'PRESSURE_FLIP_ARM'
        and veto_reason == 'FLIP_EDGE_TOO_WEAK'
        and context_score >= 2
        and abs(bias_score) >= 3
    )
    return allowed, None



def should_allow_pattern_b(signal: Dict[str, Any] | None) -> bool:
    allowed, _ = _pattern_b_decision(signal)
    return allowed


def _is_pattern_b_source(source: Any) -> bool:
    return _norm_label(source) == 'PRESSURE_FLIP_ARM'


def context_filter(context_score: Any, bias_score: Any, session_strength: Any) -> bool:
    ctx = _safe_int(context_score, default=0)
    bias = _safe_int(bias_score, default=0)
    session = _norm_label(session_strength or 'NONE')

    if ctx >= 2:
        return True

    if abs(bias) >= 4 and session not in {'', 'NONE', 'LOW'}:
        return True

    return False


def _pattern_a_post_pass_filter(snapshot: Dict[str, Any], entry_source: str | None = None, quality_reason: str | None = None) -> tuple[bool, str | None]:
    source = _norm_label(entry_source)
    if quality_reason not in {None, '', 'PASS'}:
        return True, None
    if quality_reason == 'PATTERN_B':
        return True, None

    context_score = _safe_int(snapshot.get('context_score'), default=0)
    bias_score = _safe_int(snapshot.get('bias_score'), default=0)
    session_strength = _norm_label(snapshot.get('session_strength') or snapshot.get('trend_pressure_strength') or 'LOW')

    if context_filter(context_score, bias_score, session_strength):
        return True, None

    return False, 'PATTERN_A_WEAK_CONTEXT_FILTER'


def _quality_gate(snapshot: Dict[str, Any], side: str, entry_source: str | None = None) -> tuple[bool, str | None]:
    side = _norm_label(side)
    source = _norm_label(entry_source)
    if side not in {'LONG', 'SHORT'}:
        return False, 'INVALID_SIDE'

    context_label = _norm_label(snapshot.get('context_label'))
    context_score = _safe_int(snapshot.get('context_score'), default=0)
    bias_score = _safe_int(snapshot.get('bias_score'), default=0)
    session_strength = _norm_label(snapshot.get('session_strength') or snapshot.get('trend_pressure_strength') or 'LOW')

    is_pattern_b_source = _is_pattern_b_source(source)
    is_flip_quality_source = source in {'PRESSURE_FLIP_ARM', 'MID_CROSS_FLIP', 'FLIP_CONFIRM'}
    if is_pattern_b_source:
        has_context = context_label in {'VALID', 'STRONG'} or context_score >= 2
        strong_flip_context = context_score >= 1
        if not has_context and not strong_flip_context:
            return False, 'WEAK_CONTEXT'
    else:
        has_context = context_label in {'VALID', 'STRONG'} or context_score >= 2
        if not has_context:
            return False, 'WEAK_CONTEXT'

    min_bias = 2
    if is_flip_quality_source:
        min_bias = 1
    if abs(bias_score) < min_bias:
        return False, 'LOW_BIAS'
    if side == 'LONG' and bias_score < min_bias:
        return False, 'BIAS_CONFLICT'
    if side == 'SHORT' and bias_score > -min_bias:
        return False, 'BIAS_CONFLICT'

    session_side = _norm_label(snapshot.get('session_side') or snapshot.get('trend_pressure_side') or 'NEUTRAL')
    if session_strength == 'HIGH':
        if side == 'LONG' and session_side == 'SHORT':
            return False, 'SESSION_CONFLICT'
        if side == 'SHORT' and session_side == 'LONG':
            return False, 'SESSION_CONFLICT'

    if is_flip_quality_source:
        edge_score = _edge_score(snapshot)
        block_pressure_strength = _norm_label(snapshot.get('block_pressure_strength') or snapshot.get('trend_pressure_strength') or 'LOW')
        confidence = _safe_float(snapshot.get('confidence'), default=0.0)
        has_score_support = confidence >= 47.0 or edge_score >= 36.0
        has_pressure_support = block_pressure_strength in {'MID', 'HIGH'}
        if not has_pressure_support and not has_score_support:
            pattern_b_signal = {
                'action_type': source,
                'veto_reason': 'FLIP_EDGE_TOO_WEAK',
                'context_score': context_score,
                'bias_score': bias_score,
                'entry_side': side,
                'trigger_type': snapshot.get('trigger_type'),
                'diagnostic_context': {
                    'context_score': context_score,
                    'context_label': context_label,
                    'bias_score': bias_score,
                    'entry_side': side,
                    'entry_source': source,
                    'trigger_type': snapshot.get('trigger_type'),
                    'confidence': confidence,
                    'edge_score': edge_score,
                },
            }
            pattern_b_allowed, pattern_b_reason = _pattern_b_decision(pattern_b_signal)
            if pattern_b_allowed:
                return True, 'PATTERN_B'
            if pattern_b_reason == 'PATTERN_B_RECLAIM_FILTER':
                return False, 'PATTERN_B_RECLAIM_FILTER'
            return False, 'FLIP_EDGE_TOO_WEAK'

    return True, None


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




def _trace_context_from_snapshot(snapshot: Dict[str, Any], *, entry_side: str | None = None, entry_source: str | None = None, quality_reason: str | None = None) -> Dict[str, Any]:
    return {
        'action': _norm_label(snapshot.get('action') or 'WAIT'),
        'entry_side': _norm_label(entry_side or snapshot.get('execution_side') or snapshot.get('active_block') or 'NONE'),
        'entry_source': _norm_label(entry_source or snapshot.get('historical_source') or snapshot.get('entry_source') or ''),
        'trigger_type': _norm_label(snapshot.get('trigger_type') or 'NONE'),
        'trigger_blocked': bool(snapshot.get('trigger_blocked')),
        'context_label': _norm_label(snapshot.get('context_label') or ''),
        'context_score': _safe_int(snapshot.get('context_score'), default=0),
        'bias_score': _safe_int(snapshot.get('bias_score'), default=0),
        'confidence': _safe_float(snapshot.get('confidence'), default=0.0),
        'edge_score': _edge_score(snapshot),
        'block_pressure': _norm_label(snapshot.get('block_pressure') or 'NONE'),
        'block_pressure_strength': _norm_label(snapshot.get('block_pressure_strength') or snapshot.get('trend_pressure_strength') or 'LOW'),
        'session_side': _norm_label(snapshot.get('session_side') or snapshot.get('trend_pressure_side') or 'NEUTRAL'),
        'session_strength': _norm_label(snapshot.get('session_strength') or snapshot.get('trend_pressure_strength') or 'LOW'),
        'range_position': snapshot.get('range_position'),
        'range_exp': _safe_float(snapshot.get('range_expansion') or snapshot.get('range_exp'), default=0.0),
        'vol_ratio': _safe_float(snapshot.get('vol_ratio'), default=0.0),
        'tp1_distance_pct': _safe_float(snapshot.get('tp1_distance_pct'), default=0.0),
        'stop_distance_pct': _safe_float(snapshot.get('stop_distance_pct'), default=0.0),
        'has_blocking_level_to_tp1': bool(snapshot.get('has_blocking_level_to_tp1')),
        'liquidity_before_tp1': bool(snapshot.get('liquidity_before_tp1')),
        'distance_to_liquidity_zone_pct': _safe_float(snapshot.get('distance_to_liquidity_zone_pct') or snapshot.get('liq_dist_pct') or snapshot.get('liq_dist'), default=0.0),
        'projection_to_tp1_ratio': _safe_float(snapshot.get('projection_to_tp1_ratio'), default=0.0),
        'move_projection_pct': _safe_float(snapshot.get('move_projection_pct'), default=0.0),
        'impulse_state': _norm_label(snapshot.get('impulse_state') or 'NONE'),
        'impulse_strength': _safe_float(snapshot.get('impulse_strength'), default=0.0),
        'impulse_decay': _safe_float(snapshot.get('impulse_decay'), default=0.0),
        'followthrough_score': _safe_float(snapshot.get('followthrough_score'), default=0.0),
        'quality_reason': quality_reason,
        'veto_reason': quality_reason if quality_reason and quality_reason != 'PATTERN_B' else None,
    }


def _write_trace(output_dir: str | Path, lookback_days: int, trace_rows: List[Dict[str, Any]]) -> str:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / f'backtest_{lookback_days}d_trace.json'
    trace_path.write_text(json.dumps(trace_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(trace_path)


def _write_loss_focus(output_dir: str | Path, lookback_days: int, trace_rows: List[Dict[str, Any]]) -> str:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    loss_path = output_dir / f'backtest_{lookback_days}d_loss_focus.json'
    filtered = [
        row for row in trace_rows
        if row.get('event') == 'TRADE_CLOSED'
        and _norm_label(row.get('entry_source')) == 'PRESSURE_FLIP_ARM'
        and _norm_label(row.get('side')) == 'SHORT'
        and _safe_float(row.get('pnl_pct'), default=0.0) < 0.0
    ]
    loss_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(loss_path)

def _default_swing_reversal_observe() -> Dict[str, Any]:
    return {
        'observe_count': 0,
        'confirm_count': 0,
        'reject_count': 0,
        'combined_validation': {
            'passed': 0,
            'failed': 0,
        },
    }


def _write_report(
    output_dir: str | Path,
    summary: BacktestSummary,
    trades: List[BacktestTrade],
    swing_reversal_observe: Dict[str, Any] | None = None,
) -> str:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f'backtest_{summary.lookback_days}d_report.json'
    observe_payload = swing_reversal_observe or _default_swing_reversal_observe()
    payload = {
        'summary': asdict(summary),
        'trades': [asdict(x) for x in trades],
        'swing_reversal_observe': observe_payload,
        'combined_validation': dict(observe_payload.get('combined_validation', {})),
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
    if len(candles) < MIN_WINDOW_BARS + horizon_bars + 5:
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
        swing_reversal_observe = _default_swing_reversal_observe()
        report_path = _write_report(output_dir, summary, [], swing_reversal_observe=swing_reversal_observe)
        summary.report_path = report_path
        data = asdict(summary)
        data['summary_lines'] = format_backtest_summary(data)
        data['trades_data'] = []
        data['swing_reversal_observe'] = swing_reversal_observe
        data['combined_validation'] = dict(swing_reversal_observe.get('combined_validation', {}))
        data['trace_path'] = _write_trace(output_dir, lookback_days, [])
        data['loss_focus_path'] = _write_loss_focus(output_dir, lookback_days, [])
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
    trace_rows: List[Dict[str, Any]] = []

    last_index_for_entry = max(0, len(candles) - horizon_bars - 1)
    for i in range(MIN_WINDOW_BARS, len(candles)):
        window = candles[max(0, i - MAX_WINDOW_BARS + 1):i + 1]
        with _patched_pipeline(window, state_box):
            snapshot = pipeline.build_full_snapshot(symbol)

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
                    trace_rows.append({
                        'index': i,
                        'event': 'ENTRY_REJECTED',
                        'side': entry_side,
                        'entry_source': entry_source,
                        'veto_reason': quality_reason,
                        'trace_context': _trace_context_from_snapshot(snapshot, entry_side=entry_side, entry_source=entry_source, quality_reason=quality_reason),
                    })
                    continue
                post_pass_ok, post_pass_reason = _pattern_a_post_pass_filter(snapshot, entry_source=entry_source, quality_reason=quality_reason)
                if not post_pass_ok:
                    if_then_failed += 1
                    trace_rows.append({
                        'index': i,
                        'event': 'ENTRY_REJECTED',
                        'side': entry_side,
                        'entry_source': entry_source,
                        'veto_reason': post_pass_reason,
                        'trace_context': _trace_context_from_snapshot(snapshot, entry_side=entry_side, entry_source=entry_source, quality_reason=post_pass_reason),
                    })
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
                    trace_rows.append({
                        'index': i,
                        'event': 'ENTRY_REJECTED',
                        'side': entry_side,
                        'entry_source': entry_source,
                        'veto_reason': str(entry_filter_ctx.get('reason_code') or entry_filter_ctx.get('reason') or 'ENTRY_FILTER_BLOCKED'),
                        'trace_context': _trace_context_from_snapshot(snapshot, entry_side=entry_side, entry_source=entry_source, quality_reason=str(entry_filter_ctx.get('reason_code') or entry_filter_ctx.get('reason') or 'ENTRY_FILTER_BLOCKED')),
                    })
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
                trace_rows.append({
                    'index': i,
                    'event': 'ENTRY_EXECUTED',
                    'side': entry_side,
                    'entry_source': entry_source,
                    'pattern': position.get('pattern'),
                    'entry_price': round(current_price, 4),
                    'trace_context': _trace_context_from_snapshot(snapshot, entry_side=entry_side, entry_source=entry_source, quality_reason=quality_reason),
                })
            elif action == 'PREPARE' and trigger_ready:
                pass
            elif primary and (trigger_ready or historical_triggered) and action not in {'ENTER', 'PREPARE'}:
                if_then_failed += 1
                trace_rows.append({
                    'index': i,
                    'event': 'ENTRY_REJECTED',
                    'side': historical_side or side,
                    'entry_source': historical_source or action,
                    'veto_reason': 'ACTION_NOT_ARMED',
                    'trace_context': _trace_context_from_snapshot(snapshot, entry_side=historical_side or side, entry_source=historical_source or action, quality_reason='ACTION_NOT_ARMED'),
                })
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
        trace_rows.append({
            'index': i,
            'event': 'TRADE_CLOSED',
            'side': trade.side,
            'entry_source': trade.action,
            'pattern': trade.pattern,
            'entry_index': trade.entry_index,
            'exit_index': trade.exit_index,
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'pnl_pct': trade.pnl_pct,
            'rr': trade.rr,
            'exit_reason': trade.exit_reason,
            'partial_taken': trade.partial_taken,
            'tp1_hit_index': trade.tp1_hit_index,
            'be_armed': trade.be_armed,
            'trace_context': _trace_context_from_snapshot(snapshot, entry_side=trade.side, entry_source=trade.action, quality_reason=position.get('entry_quality_gate') if isinstance(position, dict) else None),
        })
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
    swing_reversal_observe = _default_swing_reversal_observe()
    report_path = _write_report(output_dir, summary, trades, swing_reversal_observe=swing_reversal_observe)
    summary.report_path = report_path
    data = asdict(summary)
    data['summary_lines'] = format_backtest_summary(data)
    data['trades_data'] = [asdict(x) for x in trades]
    data['swing_reversal_observe'] = swing_reversal_observe
    data['combined_validation'] = dict(swing_reversal_observe.get('combined_validation', {}))
    data['trace_path'] = _write_trace(output_dir, lookback_days, trace_rows)
    data['loss_focus_path'] = _write_loss_focus(output_dir, lookback_days, trace_rows)
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
    bars = bars_for_days(lookback_days, timeframe) + MIN_WINDOW_BARS + DEFAULT_HORIZON_BARS + 10
    candles = get_klines(symbol=symbol, interval=timeframe, limit=bars)
    return run_backtest_from_candles(
        candles=candles,
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=lookback_days,
        horizon_bars=DEFAULT_HORIZON_BARS,
        output_dir=output_dir,
    )
