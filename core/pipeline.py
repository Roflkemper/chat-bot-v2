from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from market_data.price_feed import get_price
from market_data.ohlcv import get_klines
try:
    from services.timeframe_aggregator import aggregate_candles, aggregate_to_4h, aggregate_to_1d
except Exception:
    from services.timeframe_aggregator import aggregate_to_4h, aggregate_to_1d

    def aggregate_candles(candles, step: int):
        closed = list(candles or [])[:len(list(candles or [])) - (len(list(candles or [])) % step)]
        out = []
        for i in range(0, len(closed), step):
            group = closed[i:i + step]
            if len(group) < step:
                continue
            first = group[0]
            last = group[-1]
            out.append({
                'open_time': first.get('open_time'),
                'open': first.get('open'),
                'high': max(x.get('high', x.get('close')) for x in group),
                'low': min(x.get('low', x.get('close')) for x in group),
                'close': last.get('close'),
                'volume': sum(float(x.get('volume', 0.0) or 0.0) for x in group),
                'close_time': last.get('close_time'),
            })
        return out
from features.trigger_detection import detect_trigger
from features.forecast import short_term_forecast, session_forecast, medium_forecast, build_consensus
from features.liquidity_structure import detect_liquidity_structure
from features.structural_context import analyze_structural_context
from core.grid_adapter import snapshot_to_grid_input
from core.grid_action_engine import build_grid_action
from core.scenario_handoff import compute_block_pressure, compute_scenario_weights, update_flip_prep
from core.entry_quality_filter import build_entry_quality_context
from core.if_then_plan import build_if_then_plan as _compose_if_then_plan
from core.orchestrator.regime_classifier import RegimeStateStore, classify
from storage.market_state_store import load_market_state, save_market_state
try:
    from storage.position_state_store import load_position_state
except Exception:
    def load_position_state():
        return {}

NEAR_EDGE_THRESHOLD_PCT = 15.0
HEDGE_BUFFER_USD = 293.0
BLOCK_FLIP_CONFIRM_BARS = 3


def _regime_store_for_state_dir(state_dir: str) -> RegimeStateStore:
    # Backtests must not touch live state/; callers can inject an isolated dir.
    return RegimeStateStore(str(Path(state_dir) / "regime_state.json"))


def _timeframe_scale(timeframe: str) -> int:
    tf = str(timeframe or '1h').lower()
    return 4 if tf == '15m' else 1


def _scaled_window(size: int, timeframe: str) -> int:
    return max(1, int(size) * _timeframe_scale(timeframe))


def _base_limit_for_timeframe(timeframe: str) -> int:
    tf = str(timeframe or '1h').lower()
    return 800 if tf == '15m' else 200


def _aggregate_for_snapshot(candles: list[dict], timeframe: str, target: str) -> list[dict]:
    tf = str(timeframe or '1h').lower()
    target_tf = str(target or '1h').lower()
    if tf == target_tf:
        return list(candles or [])
    if tf == '15m':
        if target_tf == '1h':
            return aggregate_candles(candles, 4)
        if target_tf == '4h':
            return aggregate_candles(candles, 16)
        if target_tf == '1d':
            return aggregate_candles(candles, 96)
    if tf == '1h':
        if target_tf == '4h':
            return aggregate_to_4h(candles)
        if target_tf == '1d':
            return aggregate_to_1d(candles)
    return list(candles or [])


def _update_momentum_state(prev_state: dict, short_fc: dict, session_fc: dict) -> dict:
    state = dict(prev_state or {})
    short_side = str((short_fc or {}).get('direction') or 'NEUTRAL').upper()
    session_side = str((session_fc or {}).get('direction') or 'NEUTRAL').upper()

    short_streak = int(state.get('short_neutral_streak') or 0)
    session_streak = int(state.get('session_neutral_streak') or 0)
    double_streak = int(state.get('double_neutral_streak') or 0)

    short_streak = short_streak + 1 if short_side == 'NEUTRAL' else 0
    session_streak = session_streak + 1 if session_side == 'NEUTRAL' else 0
    if short_side == 'NEUTRAL' and session_side == 'NEUTRAL':
        double_streak += 1
    else:
        double_streak = 0

    state.update({
        'short_neutral_streak': short_streak,
        'session_neutral_streak': session_streak,
        'double_neutral_streak': double_streak,
        'momentum_exhausted': double_streak >= 2,
    })
    return state



def _true_range(bar: dict, prev_close: float | None = None) -> float:
    high = float(bar.get('high') or 0.0)
    low = float(bar.get('low') or 0.0)
    if prev_close is None:
        return max(0.0, high - low)
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _build_volatility_context(candles_1h: list[dict], timeframe: str = '1h') -> dict:
    recent_window = _scaled_window(32, timeframe)
    recent = candles_1h[-recent_window:] if len(candles_1h) >= recent_window else candles_1h
    if len(recent) < 10:
        return {'state': 'NORMAL', 'atr_ratio': 1.0}
    trs = []
    prev_close = None
    for bar in recent:
        trs.append(_true_range(bar, prev_close))
        prev_close = float(bar.get('close') or 0.0)
    fast_window = _scaled_window(8, timeframe)
    base_window = _scaled_window(24, timeframe)
    atr_fast = sum(trs[-fast_window:]) / max(1, len(trs[-fast_window:]))
    baseline = trs[-base_window:] if len(trs) >= base_window else trs
    atr_base = sum(baseline) / max(1, len(baseline))
    ratio = atr_fast / atr_base if atr_base > 0 else 1.0
    state = 'NORMAL'
    if ratio < 0.8:
        state = 'COMPRESSED'
    elif ratio > 1.4:
        state = 'EXPANDED'
    return {'state': state, 'atr_ratio': round(ratio, 2)}


def _depth_label(depth_pct: float) -> str:
    if depth_pct < 15:
        return "EARLY"
    if depth_pct < 50:
        return "WORK"
    if depth_pct < 85:
        return "RISK"
    return "DEEP"


def _build_range(candles_1h, timeframe: str = '1h'):
    range_window = _scaled_window(48, timeframe)
    window = candles_1h[-range_window:] if len(candles_1h) >= range_window else candles_1h
    range_low = min(x["low"] for x in window)
    range_high = max(x["high"] for x in window)
    range_mid = (range_low + range_high) / 2.0
    return range_low, range_high, range_mid


def _context_flags(state: str, depth_label: str, scalp_direction: str, active_side: str, candles_1h) -> tuple[int, list[str]]:
    checks = []
    details = []
    checks.append(depth_label in ("EARLY", "WORK"))
    if checks[-1]:
        details.append('глубина блока рабочая')
    last3 = candles_1h[-3:] if len(candles_1h) >= 3 else candles_1h
    closes_with_side = 0
    for bar in last3:
        if bar['close'] > bar['open'] and active_side == 'LONG':
            closes_with_side += 1
        elif bar['close'] < bar['open'] and active_side == 'SHORT':
            closes_with_side += 1
    checks.append(scalp_direction == active_side)
    if checks[-1]:
        details.append('скальп совпадает с активным блоком')
    checks.append(closes_with_side >= 2)
    if checks[-1]:
        details.append('2 из 3 баров закрылись в сторону блока')
    score = sum(1 for x in checks if x)
    return score, details


def _build_bias_score(active_side: str, consensus_direction: str, consensus_alignment_count: int, short_fc: dict, session_fc: dict, medium_fc: dict, structural_context: dict, block_pressure: str, edge_distance_pct: float) -> int:
    score = 0
    mapping = {'LOW': 1, 'MID': 2, 'HIGH': 3}
    if consensus_direction == 'LONG':
        score += mapping.get(str(short_fc.get('strength') or 'LOW').upper(), 1) if short_fc.get('direction') == 'LONG' else 0
        score += mapping.get(str(session_fc.get('strength') or 'LOW').upper(), 1) if session_fc.get('direction') == 'LONG' else 0
        score += max(1, mapping.get(str(medium_fc.get('strength') or 'LOW').upper(), 1) - 1) if medium_fc.get('direction') == 'LONG' else 0
    elif consensus_direction == 'SHORT':
        score -= mapping.get(str(short_fc.get('strength') or 'LOW').upper(), 1) if short_fc.get('direction') == 'SHORT' else 0
        score -= mapping.get(str(session_fc.get('strength') or 'LOW').upper(), 1) if session_fc.get('direction') == 'SHORT' else 0
        score -= max(1, mapping.get(str(medium_fc.get('strength') or 'LOW').upper(), 1) - 1) if medium_fc.get('direction') == 'SHORT' else 0
    else:
        for fc in (short_fc, session_fc, medium_fc):
            direction = str(fc.get('direction') or 'NEUTRAL').upper()
            strength = mapping.get(str(fc.get('strength') or 'LOW').upper(), 1)
            if direction == 'LONG':
                score += strength if fc is not medium_fc else max(1, strength - 1)
            elif direction == 'SHORT':
                score -= strength if fc is not medium_fc else max(1, strength - 1)

    structural_bias = str(structural_context.get('bias') or 'NEUTRAL').upper()
    if structural_bias == 'LONG':
        score += 2
    elif structural_bias == 'SHORT':
        score -= 2

    if active_side == 'LONG':
        score += 1
    elif active_side == 'SHORT':
        score -= 1

    if block_pressure == 'AGAINST':
        score += 1 if active_side == 'SHORT' else -1

    if edge_distance_pct <= NEAR_EDGE_THRESHOLD_PCT:
        score += 1 if active_side == 'LONG' else -1

    return max(-10, min(10, int(score)))


def _build_absorption(active_block: str, candles_1h: list[dict], block_low: float, block_high: float, timeframe: str = '1h') -> dict:
    absorption_window = _scaled_window(12, timeframe)
    recent = candles_1h[-absorption_window:] if len(candles_1h) >= absorption_window else candles_1h
    block_size = max(block_high - block_low, 1e-9)
    threshold = block_high - block_size * 0.25 if active_block == 'SHORT' else block_low + block_size * 0.25
    bars_at_edge = 0
    holding = True
    for bar in recent:
        close = float(bar['close'])
        if active_block == 'SHORT':
            if close >= threshold:
                bars_at_edge += 1
            if close < threshold:
                holding = False
        else:
            if close <= threshold:
                bars_at_edge += 1
            if close > threshold:
                holding = False
    is_active = bars_at_edge >= 4 and holding
    if active_block == 'SHORT':
        label = 'ABSORPTION у верхнего края' if is_active else 'нет подтверждённого absorption сверху'
    else:
        label = 'ABSORPTION у нижнего края' if is_active else 'нет подтверждённого absorption снизу'
    return {
        'bars_at_edge': bars_at_edge,
        'is_active': is_active,
        'label': label,
    }


def _build_if_then_plan(snapshot: dict) -> list[str]:
    return (_compose_if_then_plan(snapshot) or {}).get('lines') or []


def _build_top_signal(snapshot: dict) -> str:
    danger = snapshot.get('danger_to_active_side', False)
    distance = snapshot.get('distance_to_break_level', 0.0)
    break_level = snapshot.get('break_level', 0.0)
    active_block = snapshot['active_block']
    opposite = 'вверх' if active_block == 'SHORT' else 'вниз'
    threatened_side = active_block
    if danger:
        return f"⚠️ DANGER | {distance:.2f}$ до пробоя {opposite} — {threatened_side} под угрозой"
    if snapshot['action'] == 'WAIT' and snapshot.get('near_breakout'):
        return f"⚠️ WAIT | пробой близко — {distance:.2f}$ до {break_level:.2f}"
    if snapshot.get('trigger_blocked'):
        return f"⏸️ WAIT | {snapshot['execution_side']} заблокирован — следить за сменой блока"
    return f"⏸️ {snapshot['action']} | ждать подтверждение"




def _grid_line_from_action(side: str, action: str, trigger_level: float, snapshot: dict | None = None) -> str:
    action = str(action or 'HOLD').upper()
    snap = snapshot or {}
    absorption = snap.get('absorption') or {}
    bars_at_edge = int(absorption.get('bars_at_edge') or 0)
    absorption_active = bool(absorption.get('is_active'))
    waiting_trigger = str(snap.get('action') or '').upper() == 'WAIT' and not str(snap.get('trigger_type') or '').strip()
    active_block = str(snap.get('active_block') or '').upper()
    side = str(side or '').upper()
    pressure_against = str(snap.get('block_pressure') or '').upper() == 'AGAINST'
    risky_same_side = side == active_block and bars_at_edge >= 4 and not absorption_active and (waiting_trigger or pressure_against)

    if action == 'BOOST':
        if risky_same_side:
            return 'HOLD / усиливать только на SWEEP зоне лимитками'
        return 'можно усиливать'
    if action == 'ENABLE':
        if risky_same_side:
            return 'держать готовыми / без агрессивного добора'
        return 'держать готовыми'
    if action == 'REDUCE':
        return 'не усиливать / сокращать'
    if action == 'PAUSE':
        return f'пауза при пробое {trigger_level:.2f}'
    return 'держать'



def _build_exit_strategy(snapshot: dict) -> list[str]:
    forecast = snapshot.get('forecast') or {}
    short_fc = forecast.get('short') or {}
    session_fc = forecast.get('session') or {}
    active_block = str(snapshot.get('active_block') or 'LONG').upper()
    short_side = str(short_fc.get('direction') or 'NEUTRAL').upper()
    session_side = str(session_fc.get('direction') or 'NEUTRAL').upper()
    session_strength = str(session_fc.get('strength') or 'LOW').upper()
    hedge_down = float(snapshot.get('hedge_arm_down') or 0.0)
    hedge_up = float(snapshot.get('hedge_arm_up') or 0.0)
    break_level = float(snapshot.get('break_level') or 0.0)
    absorption = snapshot.get('absorption') or {}
    bars_at_edge = int(absorption.get('bars_at_edge') or 0)
    absorption_active = bool(absorption.get('is_active'))
    bias_score = int(snapshot.get('bias_score') or 0)
    vol_ctx = snapshot.get('volatility') or {}
    atr_ratio = float(vol_ctx.get('atr_ratio') or 1.0)
    double_neutral_streak = int(snapshot.get('double_neutral_streak') or 0)
    neutral_now = short_side == 'NEUTRAL' and session_side == 'NEUTRAL'
    soft_exhaustion = neutral_now and ((active_block == 'LONG' and bias_score >= 3 and atr_ratio <= 0.8) or (active_block == 'SHORT' and bias_score <= -3 and atr_ratio <= 0.8))
    momentum_exhausted = bool(snapshot.get('momentum_exhausted')) or double_neutral_streak >= 2 or soft_exhaustion
    exhaustion_count = max(double_neutral_streak, 2) if momentum_exhausted and neutral_now else double_neutral_streak

    if active_block == 'LONG' or (session_side == 'SHORT' and session_strength in {'MID', 'HIGH'}):
        tp1 = max(0.0, (break_level + hedge_down) / 2.0)
        tp2 = hedge_down
        lines = [
            '• если держишь SHORT — сопровождать, не переворачивать без reclaim',
            f'• TP1: {tp1:.2f} — частично фиксировать',
            f'• TP2: {tp2:.2f} — добирать остаток / hedge arm',
            f'• ВЫХОД: reclaim выше {break_level:.2f} (2 бара) → закрыть SHORT',
        ]
        if neutral_now and momentum_exhausted:
            lines.append(f'• CLIMAX: нет | движение остановилось, {bars_at_edge} баров у края')
            lines.append(f'• ⚠️ скальп и сессия NEUTRAL x{exhaustion_count} — momentum иссяк')
            lines.append('• ФИКСАЦИЯ: шорт частями, не ждать полного добоя')
        else:
            lines.append(f"• CLIMAX: {'есть absorption снизу' if absorption_active else 'нет climax, давление ещё рабочее'} | {bars_at_edge} баров у края")
        return lines

    tp1 = min(hedge_up, (break_level + hedge_up) / 2.0 if hedge_up else break_level)
    tp2 = hedge_up
    lines = [
        '• если держишь LONG — сопровождать, не переворачивать без reclaim',
        f'• TP1: {tp1:.2f} — частично фиксировать',
        f'• TP2: {tp2:.2f} — добирать остаток / hedge arm',
        f'• ВЫХОД: reclaim ниже {break_level:.2f} (2 бара) → закрыть LONG',
    ]
    if neutral_now and momentum_exhausted:
        lines.append(f'• CLIMAX: нет | движение остановилось, {bars_at_edge} баров у края')
        lines.append(f'• ⚠️ скальп и сессия NEUTRAL x{exhaustion_count} — momentum иссяк')
        lines.append('• ФИКСАЦИЯ: лонг частями, не ждать полного добоя')
    else:
        lines.append(f"• CLIMAX: {'есть absorption сверху' if absorption_active else 'нет climax, импульс ещё рабочий'} | {bars_at_edge} баров у края")
    return lines


def _build_position_control(position_state: dict, snapshot: dict) -> dict:
    pos = position_state if isinstance(position_state, dict) else {}
    if not pos.get('active'):
        return {'status': 'FLAT', 'source': pos.get('source', 'none'), 'entry_price': None, 'pnl_pct': 0.0, 'recommended_action': 'WAIT'}
    side = str(pos.get('side') or 'NONE').upper()
    entry_price = float(pos.get('entry_price') or 0.0) if pos.get('entry_price') is not None else None
    price = float(snapshot.get('price') or 0.0)
    pnl_pct = 0.0
    if entry_price:
        pnl_pct = ((price - entry_price) / entry_price) * 100.0 if side == 'LONG' else ((entry_price - price) / entry_price) * 100.0
    recommended = 'HOLD'
    if side and side != str(snapshot.get('consensus_direction') or '').upper() and str(snapshot.get('consensus_direction') or '').upper() in {'LONG','SHORT'}:
        recommended = 'REDUCE / PROTECT'
    elif str(snapshot.get('action') or '').upper() == 'PROTECT':
        recommended = 'PROTECT'
    return {'status': f'{side} {str(pos.get("stage") or "ACTIVE").upper()}'.strip(), 'source': pos.get('source', 'state'), 'entry_price': entry_price, 'pnl_pct': round(pnl_pct, 4), 'recommended_action': recommended}


def _build_risk_authority(snapshot: dict, position_control: dict) -> dict:
    mode = 'NORMAL'
    add = 'ALLOW'
    lines = []
    if position_control.get('recommended_action') == 'REDUCE / PROTECT' or str(snapshot.get('block_pressure') or '').upper() == 'AGAINST':
        mode = 'LOCKDOWN'
        add = 'NO_ADD'
    lines.append(f'• MODE: {mode}')
    lines.append(f'• ADD: {add}')
    if str(snapshot.get('trigger_block_reason') or '').strip():
        lines.append(f"• BLOCK: {snapshot.get('trigger_block_reason')}")
    return {'mode': mode, 'add': add, 'lines': lines}


def _build_manual_grid_blocks(snapshot: dict) -> tuple[list[str], list[str], list[str], list[str]]:
    grid_action = snapshot.get('grid_action') or {}
    manual_action_lines = list(snapshot.get('current_action_lines') or [])
    grid_action_lines = [
        f"• LONG: {grid_action.get('long_action', 'HOLD')}",
        f"• SHORT: {grid_action.get('short_action', 'HOLD')}",
    ]
    grid_shift_lines = [
        f"• PRIORITY: {grid_action.get('priority_side', 'NEUTRAL')}",
        f"• REGIME: {grid_action.get('grid_regime', 'SAFE')}",
    ]
    liquidity_void_lines = [
        f"• DOWN TARGET: {grid_action.get('down_target', snapshot.get('down_target'))}",
        f"• UP TARGET: {grid_action.get('up_target', snapshot.get('up_target'))}",
    ]
    return manual_action_lines, grid_action_lines, grid_shift_lines, liquidity_void_lines


def build_full_snapshot(
    symbol="BTCUSDT",
    timeframe='1h',
    reference_time: datetime | None = None,
    state_dir: str = "state",
):
    tf = str(timeframe or '1h').lower()
    base_limit = _base_limit_for_timeframe(tf)
    candles_1h = get_klines(symbol=symbol, interval=tf, limit=base_limit)
    candles_1h = [{**row, 'volume': float(row.get('volume', 0.0) or 0.0)} for row in candles_1h]
    try:
        price = get_price(symbol)
    except Exception:
        price = float(candles_1h[-1]['close']) if candles_1h else 0.0
    candles_4h = _aggregate_for_snapshot(candles_1h, tf, '4h')
    candles_1d = _aggregate_for_snapshot(candles_1h, tf, '1d')

    range_low, range_high, range_mid = _build_range(candles_1h, tf)
    range_size = max(range_high - range_low, 1e-9)

    if price >= range_mid:
        active_side = active_block = "SHORT"
        block_low, block_high = range_mid, range_high
        distance_to_upper_edge = range_high - price
        distance_to_lower_edge = price - range_low
        edge_distance_pct = max(0.0, ((block_high - price) / max(block_high - block_low, 1e-9)) * 100.0)
    else:
        active_side = active_block = "LONG"
        block_low, block_high = range_low, range_mid
        distance_to_upper_edge = range_high - price
        distance_to_lower_edge = price - range_low
        edge_distance_pct = max(0.0, ((price - block_low) / max(block_high - block_low, 1e-9)) * 100.0)

    block_size = max(block_high - block_low, 1e-9)
    block_depth_pct = ((price - block_low) / block_size) * 100.0
    range_position_pct = ((price - range_low) / range_size) * 100.0
    depth_label = _depth_label(block_depth_pct)

    trigger, trigger_type, trigger_note = detect_trigger(candles_1h, active_block, range_low, range_high)

    short_fc = short_term_forecast(candles_1h)
    session_fc = session_forecast(candles_4h)
    medium_fc = medium_forecast(candles_1d)
    consensus_direction, consensus_confidence, consensus_votes, consensus_alignment_count = build_consensus(short_fc, session_fc, medium_fc)

    block_pressure, block_pressure_strength, block_flip_warning, block_pressure_reason = compute_block_pressure(
        active_block, consensus_direction, consensus_alignment_count, session_fc, medium_fc
    )

    structure_flags = detect_liquidity_structure(candles_1h)
    structural_context = analyze_structural_context(candles_1h)
    absorption = _build_absorption(active_block, candles_1h, block_low, block_high, tf)

    scalp_direction = short_fc["direction"]
    context_score, context_details = _context_flags('SEARCH_TRIGGER', depth_label, scalp_direction, active_side, candles_1h)
    context_label = 'STRONG' if context_score == 3 else 'VALID' if context_score == 2 else 'WEAK' if context_score == 1 else 'NO CONTEXT'

    if price > range_high or price < range_low or block_depth_pct >= 100:
        state = "OVERRUN"
    elif trigger:
        state = "CONFIRMED"
    elif edge_distance_pct <= NEAR_EDGE_THRESHOLD_PCT:
        state = "PRE_ACTIVATION"
    elif depth_label in ("WORK", "RISK", 'DEEP'):
        state = "SEARCH_TRIGGER"
    else:
        state = "MID_RANGE"

    conflict_flag = consensus_direction in ("LONG", "SHORT") and consensus_direction != active_side
    structural_bias = str(structural_context.get('bias') or 'NEUTRAL').upper()
    structural_conflict = structural_bias in {'LONG', 'SHORT'} and structural_bias != active_side

    if active_block == 'SHORT' and consensus_direction == 'LONG' and consensus_alignment_count >= 2 and block_flip_warning:
        watch_side = 'LONG'
    elif active_block == 'LONG' and consensus_direction == 'SHORT' and consensus_alignment_count >= 2 and block_flip_warning:
        watch_side = 'SHORT'
    else:
        watch_side = 'NONE'

    volatility = _build_volatility_context(candles_1h, tf)
    entry_filter = build_entry_quality_context(candles=candles_1h, entry_idx=len(candles_1h) - 1, side=active_side)

    _now_utc = datetime.now(timezone.utc)
    base_snapshot = {
        'symbol': symbol,
        'timestamp': _now_utc.strftime('%H:%M'),
        'ts_utc': _now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'tf': tf,
        'price': round(price, 2),
        'range_low': round(range_low, 2),
        'range_high': round(range_high, 2),
        'range_mid': round(range_mid, 2),
        'range_position_pct': round(range_position_pct, 2),
        'range_width_pct': round((range_size / max(price, 1e-9)) * 100.0, 2),
        'active_block': active_block,
        'active_side': active_side,
        'block_low': round(block_low, 2),
        'block_high': round(block_high, 2),
        'block_depth_pct': round(block_depth_pct, 2),
        'depth_label': depth_label,
        'distance_to_upper_edge': round(distance_to_upper_edge, 2),
        'distance_to_lower_edge': round(distance_to_lower_edge, 2),
        'edge_distance_pct': round(edge_distance_pct, 2),
        'state': state,
        'trigger': trigger,
        'trigger_type': trigger_type,
        'trigger_note': trigger_note,
        'forecast': {'short': short_fc, 'session': session_fc, 'medium': medium_fc},
        'consensus_direction': consensus_direction,
        'consensus_confidence': consensus_confidence,
        'consensus_votes': consensus_votes,
        'consensus_alignment_count': consensus_alignment_count,
        'execution_side': active_side,
        'block_pressure': block_pressure,
        'block_pressure_strength': block_pressure_strength,
        'block_flip_warning': block_flip_warning,
        'block_pressure_reason': block_pressure_reason,
        'watch_side': watch_side,
        'market_regime': 'RANGE' if 20 <= range_position_pct <= 80 else 'CHOP',
        'range_quality': 'GOOD' if range_size / max(price, 1e-9) >= 0.05 else 'OK',
        'trend_pressure_side': consensus_direction if consensus_direction in {'LONG', 'SHORT'} else 'NEUTRAL',
        'trend_pressure_strength': block_pressure_strength if block_pressure_strength in {'LOW', 'MID', 'HIGH'} else 'LOW',
        'forecast_conflict': conflict_flag,
        'structural_context': structural_context,
        'absorption': absorption,
        'volatility': volatility,
        'entry_filter': entry_filter,
        'entry_filter_ok': bool(entry_filter.get('ok')),
        'entry_filter_reason': str(entry_filter.get('reason') or 'OK'),
        'entry_filter_reason_code': str(entry_filter.get('reason_code') or 'OK'),
        **structure_flags,
    }

    # Compute delta_1h_pct and consec_1h_up/down from live candles for advisor cascade.
    # src/features/pipeline.py writes these to parquet (batch), but live snapshot
    # must compute them directly so cascade.evaluate() gets real-time values.
    if len(candles_1h) >= 2:
        c_now = float(candles_1h[-1].get('close') or 0)
        c_prev = float(candles_1h[-2].get('close') or 0)
        base_snapshot['delta_1h_pct'] = round((c_now - c_prev) / c_prev * 100.0, 4) if c_prev else None
    else:
        base_snapshot['delta_1h_pct'] = None

    _consec_up = 0
    _consec_dn = 0
    for _bar in reversed(candles_1h[-20:]):
        _o, _c = float(_bar.get('open') or 0), float(_bar.get('close') or 0)
        if _c > _o:
            if _consec_dn > 0:
                break
            _consec_up += 1
        elif _c < _o:
            if _consec_up > 0:
                break
            _consec_dn += 1
        else:
            break
    base_snapshot['consec_1h_up'] = _consec_up
    base_snapshot['consec_1h_down'] = _consec_dn

    prev_market_state = load_market_state()
    prep_state = update_flip_prep(prev_market_state, base_snapshot)
    prep_state = _update_momentum_state(prep_state, short_fc, session_fc)
    base_snapshot.update(prep_state)

    hedge_state = "PRE-TRIGGER" if block_depth_pct > 60 else "ARM" if state in ("SEARCH_TRIGGER", "PRE_ACTIVATION") else "TRIGGER" if state == "OVERRUN" else "OFF"
    base_snapshot['hedge_state'] = hedge_state

    base_prob, alt_prob, base_reasons, alt_reasons = compute_scenario_weights(base_snapshot)

    if structural_conflict and str(structural_context.get('strength') or 'LOW').upper() in {'MID', 'HIGH'}:
        if active_block == 'LONG':
            alt_prob = min(85, alt_prob + 10)
        else:
            alt_prob = min(85, alt_prob + 5)
        base_prob = 100 - alt_prob
        alt_reasons = list(alt_reasons) + ['локальная 1h-структура против активного блока']

    if absorption['is_active']:
        if active_block == 'SHORT':
            alt_prob = min(85, alt_prob + 10)
        else:
            base_prob = min(85, base_prob + 10)
        if active_block == 'SHORT':
            base_prob = 100 - alt_prob
        else:
            alt_prob = 100 - base_prob

    short_side = str(short_fc.get('direction') or 'NEUTRAL').upper()
    session_side = str(session_fc.get('direction') or 'NEUTRAL').upper()
    atr_ratio = float((volatility or {}).get('atr_ratio') or 1.0)
    bars_at_edge = int((absorption or {}).get('bars_at_edge') or 0)
    if short_side == 'NEUTRAL' and session_side == 'NEUTRAL' and atr_ratio <= 0.8:
        alt_prob = max(20, alt_prob - 10)
        base_prob = 100 - alt_prob
    if active_block == 'LONG' and bars_at_edge >= 4 and not absorption['is_active'] and short_side == 'NEUTRAL' and session_side == 'NEUTRAL':
        fatigue_penalty = min(bars_at_edge * 2, 15)
        alt_prob = max(20, alt_prob - fatigue_penalty)
        base_prob = 100 - alt_prob

    flip_level = range_high if active_block == 'SHORT' else range_low
    flip_condition_text = f"{prep_state.get('flip_prep_confirm_bars_needed', 2)} закрытия {'выше' if active_block == 'SHORT' else 'ниже'} {flip_level:.2f}"
    scenario_base_text = (
        f"отбой от {'верхнего' if active_block == 'SHORT' else 'нижнего'} края → {active_block} блок остаётся активным"
    )
    scenario_alt_side = watch_side if watch_side != 'NONE' else ('LONG' if active_block == 'SHORT' else 'SHORT')
    scenario_alt_text = (
        f"пробой и закрепление {'выше' if active_block == 'SHORT' else 'ниже'} {flip_level:.2f} → {active_block} блок инвалидируется, сценарий смещается в {scenario_alt_side}"
    )
    base_snapshot.update({
        'scenario_base_probability': base_prob,
        'scenario_alt_probability': alt_prob,
        'scenario_weight_reason_base': base_reasons,
        'scenario_weight_reason_alt': alt_reasons,
        'scenario_base_text': scenario_base_text,
        'scenario_alt_text': scenario_alt_text,
        'scenario_flip_trigger': flip_condition_text,
    })

    session_side = str(session_fc.get('direction') or 'NEUTRAL').upper()
    session_strength = str(session_fc.get('strength') or 'LOW').upper()
    session_veto = (
        (active_block == 'LONG' and session_side == 'SHORT' and session_strength == 'HIGH')
        or (active_block == 'SHORT' and session_side == 'LONG' and session_strength == 'HIGH')
    )

    entry_filter_ok = bool(entry_filter.get('ok'))
    entry_filter_reason = str(entry_filter.get('reason') or 'OK')

    if state == "OVERRUN":
        action = "PROTECT"
        entry_type = None
    elif not trigger:
        action = "WAIT"
        entry_type = None
    elif session_veto:
        action = "WAIT"
        entry_type = None
    elif not entry_filter_ok:
        action = "WAIT"
        entry_type = None
    elif trigger and state == "CONFIRMED" and context_score >= 2 and not (block_pressure == 'AGAINST' and block_pressure_strength in {'MID', 'HIGH'}):
        action = "ENTER"
        entry_type = "ENTER"
    elif trigger and context_score >= 1 and not conflict_flag and block_pressure != 'AGAINST' and not structural_conflict:
        action = "PREPARE"
        entry_type = "PROBE"
    else:
        action = "WAIT"
        entry_type = None

    entry_quality = 'NO_TRADE'
    execution_profile = 'NO_ENTRY'
    risk_mode = 'MINIMAL'
    partial_entry_allowed = False
    scale_in_allowed = False
    if action in {'PREPARE', 'ENTER'}:
        entry_quality = 'A' if context_score == 3 else 'B' if context_score == 2 else 'C'
        if action == 'ENTER' and entry_quality == 'A' and consensus_direction == active_side:
            execution_profile = 'AGGRESSIVE'
        elif entry_quality in {'A', 'B'}:
            execution_profile = 'STANDARD' if consensus_direction == 'NONE' or consensus_direction == active_side else 'CONSERVATIVE'
        else:
            execution_profile = 'PROBE_ONLY'
        risk_mode = 'FULL' if entry_quality == 'A' else 'REDUCED' if entry_quality == 'B' else 'MINIMAL'
        partial_entry_allowed = entry_quality in {'B', 'C'}
        scale_in_allowed = entry_quality in {'A', 'B'} and depth_label not in {'RISK', 'DEEP'} and block_depth_pct <= 70

    warnings = []
    primary_blocker = None
    secondary_warnings = []
    context_warnings = []
    trigger_blocked = False
    trigger_block_reason = ''

    if structural_conflict and str(structural_context.get('strength') or 'LOW').upper() in {'MID', 'HIGH'}:
        primary_blocker = 'структура 1h против активного блока'
        secondary_warnings.append('локальная структура смотрит в противоположную сторону')
        trigger_blocked = True
        trigger_block_reason = 'структура 1h против активного блока'
    elif block_pressure == 'AGAINST' and block_pressure_strength in {'MID', 'HIGH'}:
        primary_blocker = 'давление против блока'
        secondary_warnings.append('forecast против активного блока')
        if block_pressure_reason:
            secondary_warnings.append(block_pressure_reason)
        trigger_blocked = True
        trigger_block_reason = 'давление против блока'
    elif context_score == 0:
        primary_blocker = 'нет рабочего контекста'
        trigger_blocked = True
        trigger_block_reason = 'нет рабочего контекста'
    elif conflict_flag:
        primary_blocker = 'forecast против активного блока'
        trigger_blocked = True
        trigger_block_reason = 'forecast против активного блока'
    elif not trigger:
        primary_blocker = 'нет подтверждённого trigger'
        trigger_blocked = True
        trigger_block_reason = 'нет подтверждённого trigger'
    elif not entry_filter_ok:
        primary_blocker = entry_filter_reason
        trigger_blocked = True
        trigger_block_reason = entry_filter_reason

    if session_veto:
        secondary_warnings.append('сильная старшая сессия блокирует вход против блока')
    if not entry_filter_ok:
        secondary_warnings.append(f'entry filter veto: {entry_filter_reason}')
    if scalp_direction != active_side:
        if scalp_direction == 'NEUTRAL':
            secondary_warnings.append('скальп не подтверждает — краткосрочного импульса нет')
        else:
            secondary_warnings.append('скальп против активного блока')
    if range_position_pct > 80 or range_position_pct < 20:
        context_warnings.append('край диапазона — повышенный риск резкого выноса')
    if block_depth_pct > 65:
        context_warnings.append('глубоко в зоне — риск прошивки')
    if block_pressure == 'AGAINST' and block_pressure_reason and block_pressure_reason not in secondary_warnings:
        context_warnings.append(block_pressure_reason)
    if context_score == 1:
        secondary_warnings.append('только 1 из 3 условий контекста выполнено')

    if primary_blocker:
        warnings.append(f'БЛОКИРОВКА: {primary_blocker}')
        warnings.extend([f'   • {x}' for x in (secondary_warnings + context_warnings)])
    else:
        warnings.extend([f'• {x}' for x in (secondary_warnings + context_warnings)])

    hedge_arm_up = round(range_high + HEDGE_BUFFER_USD, 2)
    hedge_arm_down = round(range_low - HEDGE_BUFFER_USD, 2)
    down_target = hedge_arm_down
    up_target = hedge_arm_up
    down_impulse_pct = max(0.0, ((price - down_target) / max(price, 1e-9)) * 100.0)
    up_impulse_pct = max(0.0, ((up_target - price) / max(price, 1e-9)) * 100.0)

    def _layers_from_impulse(impulse_pct: float) -> int:
        if impulse_pct >= 2.9:
            return 3
        if impulse_pct >= 2.2:
            return 2
        if impulse_pct >= 1.3:
            return 1
        return 0

    down_layers = _layers_from_impulse(down_impulse_pct)
    up_layers = _layers_from_impulse(up_impulse_pct)


    snapshot = {
        **base_snapshot,
        'action': action,
        'entry_type': entry_type,
        'hedge_state': hedge_state,
        'hedge_arm_up': hedge_arm_up,
        'hedge_arm_down': hedge_arm_down,
        'execution_side': active_side,
        'execution_confidence': consensus_confidence,
        'conflict_flag': conflict_flag,
        'context_score': context_score,
        'context_label': context_label,
        'context_details': context_details,
        'warnings': warnings,
        'trigger_blocked': trigger_blocked,
        'trigger_block_reason': trigger_block_reason,
        'entry_quality': entry_quality,
        'execution_profile': execution_profile,
        'risk_mode': risk_mode,
        'partial_entry_allowed': partial_entry_allowed,
        'scale_in_allowed': scale_in_allowed,
        'trade_plan_mode': 'GRID MONITORING' if action == 'WAIT' else 'GRID',
        'trade_plan_active': action != 'WAIT',
        'down_target': round(down_target, 2),
        'up_target': round(up_target, 2),
        'down_impulse_pct': round(down_impulse_pct, 2),
        'up_impulse_pct': round(up_impulse_pct, 2),
        'down_layers': down_layers,
        'up_layers': up_layers,
    }

    grid_input = snapshot_to_grid_input(snapshot)
    grid_action = build_grid_action(grid_input)

    # Regression shield: execution side must stay anchored to the active block,
    # even if downstream layers derive or mutate directional helpers.
    execution_side = str(snapshot.get('active_block') or active_side).upper()
    if execution_side not in {'LONG', 'SHORT'}:
        execution_side = str(active_side or 'LONG').upper()
    snapshot['execution_side'] = execution_side

    action_map = {
        'BOOST': 'WORK',
        'ENABLE': 'WORK',
        'HOLD': 'WORK',
        'REDUCE': 'REDUCE',
        'PAUSE': 'PAUSE',
    }
    ginarea = {
        'mode': 'PRIORITY_GRID',
        'long_grid': 'REDUCE' if execution_side == 'SHORT' else 'WORK',
        'short_grid': 'WORK' if execution_side == 'SHORT' else 'REDUCE',
        'aggression': 'LOW' if grid_action['grid_regime'] == 'DANGER' else 'MID' if grid_action['priority_side'] != 'NEUTRAL' else 'LOW',
        'lifecycle': 'REDUCE_GRID' if grid_action['grid_regime'] == 'DANGER' else 'ARM_GRID' if state in ('SEARCH_TRIGGER', 'PRE_ACTIVATION') else 'WAIT_GRID',
        'priority_side': grid_action['priority_side'],
    }

    bias_score = _build_bias_score(active_side, consensus_direction, consensus_alignment_count, short_fc, session_fc, medium_fc, structural_context, block_pressure, edge_distance_pct)
    bias_label = 'бычье давление' if bias_score >= 2 else 'медвежье давление' if bias_score <= -2 else 'конфликтный рынок'

    snapshot['bias_score'] = bias_score
    snapshot['bias_label'] = bias_label
    break_level = range_high if active_block == 'SHORT' else range_low
    distance_to_break_level = distance_to_upper_edge if active_block == 'SHORT' else distance_to_lower_edge
    near_breakout = edge_distance_pct <= NEAR_EDGE_THRESHOLD_PCT
    danger_to_active_side = near_breakout and structural_conflict and str(short_fc.get('direction') or 'NEUTRAL').upper() == structural_bias and str(session_fc.get('direction') or 'NEUTRAL').upper() == structural_bias

    snapshot.update({
        'ginarea': ginarea,
        'grid_action': grid_action,
        'break_level': round(break_level, 2),
        'distance_to_break_level': round(distance_to_break_level, 2),
        'near_breakout': near_breakout,
        'danger_to_active_side': danger_to_active_side,
        'top_signal': '',
        'if_then_plan': [],
        'if_then_layer': {},
        'current_action_lines': [],
        'exit_strategy_lines': [],
    })

    snapshot['current_action_lines'] = [
        f"• руками: {'не входить — ждать подтверждение' if action == 'WAIT' else 'допустима работа по сигналу'}",
        f"• LONG сетки: {_grid_line_from_action('LONG', grid_action.get('long_action'), hedge_arm_down, snapshot)}",
        f"• SHORT сетки: {_grid_line_from_action('SHORT', grid_action.get('short_action'), hedge_arm_up, snapshot)}",
    ]
    if active_block == 'SHORT' and near_breakout and grid_action.get('long_action') in {'ENABLE', 'BOOST'}:
        snapshot['current_action_lines'][1] = f"• LONG сетки: готовить к активации при пробое {round(range_high, 2)}"
    if active_block == 'LONG' and near_breakout and grid_action.get('short_action') in {'ENABLE', 'BOOST'}:
        snapshot['current_action_lines'][2] = f"• SHORT сетки: готовить к активации при пробое {round(range_low, 2)}"

    snapshot['if_then_layer'] = _compose_if_then_plan(snapshot)
    snapshot['if_then_plan'] = (snapshot['if_then_layer'] or {}).get('lines') or []
    snapshot['exit_strategy_lines'] = _build_exit_strategy(snapshot)
    snapshot['top_signal'] = _build_top_signal(snapshot)

    position_state = load_position_state()
    snapshot['position_control'] = _build_position_control(position_state, snapshot)
    snapshot['risk_authority'] = _build_risk_authority(snapshot, snapshot['position_control'])
    manual_action_lines, grid_action_lines, grid_shift_lines, liquidity_void_lines = _build_manual_grid_blocks(snapshot)
    snapshot['manual_action_lines'] = manual_action_lines
    snapshot['grid_action_lines'] = grid_action_lines
    snapshot['grid_shift_lines'] = grid_shift_lines
    snapshot['liquidity_void_lines'] = liquidity_void_lines
    if not snapshot.get('trade_plan_active'):
        snapshot['trade_plan_activation_note'] = 'условный — активируется при подтверждении сценария'
    candles_1m = [{**row, 'volume': float(row.get('volume', 0.0) or 0.0)} for row in get_klines(symbol=symbol, interval='1m', limit=120)]
    candles_15m = [{**row, 'volume': float(row.get('volume', 0.0) or 0.0)} for row in get_klines(symbol=symbol, interval='15m', limit=100)]
    candles_1h_regime = [{**row, 'volume': float(row.get('volume', 0.0) or 0.0)} for row in get_klines(symbol=symbol, interval='1h', limit=300)]
    candles_4h_regime = [{**row, 'volume': float(row.get('volume', 0.0) or 0.0)} for row in get_klines(symbol=symbol, interval='4h', limit=100)]
    regime_ts = reference_time or datetime.now(timezone.utc)
    regime_store = _regime_store_for_state_dir(state_dir)
    regime = classify(
        symbol=symbol,
        ts=regime_ts,
        candles_1m=candles_1m,
        candles_15m=candles_15m,
        candles_1h=candles_1h_regime,
        candles_4h=candles_4h_regime,
        funding_rate=None,
        manual_blackout_until=regime_store.get_blackout(),
        state_store=regime_store,
    )
    snapshot["regime"] = {
        "primary": regime.primary_regime,
        "modifiers": regime.modifiers,
        "age_bars": regime.regime_age_bars,
        "bias_score": regime.bias_score,
        "session": regime.session,
        "metrics": asdict(regime.metrics),
    }
    save_market_state(prep_state)
    return snapshot
