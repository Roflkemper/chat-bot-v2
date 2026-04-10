from __future__ import annotations

from datetime import datetime

from market_data.price_feed import get_price
from market_data.ohlcv import get_klines
from services.timeframe_aggregator import aggregate_to_4h, aggregate_to_1d
from features.trigger_detection import detect_trigger
from features.forecast import short_term_forecast, session_forecast, medium_forecast, build_consensus
from features.liquidity_structure import detect_liquidity_structure
from core.grid_adapter import snapshot_to_grid_input
from core.grid_action_engine import build_grid_action
from core.scenario_handoff import compute_block_pressure, compute_scenario_weights, update_flip_prep
from storage.market_state_store import load_market_state, save_market_state

NEAR_EDGE_THRESHOLD_PCT = 15.0
HEDGE_BUFFER_USD = 293.0
BLOCK_FLIP_CONFIRM_BARS = 3


def _depth_label(depth_pct: float) -> str:
    if depth_pct < 15:
        return "EARLY"
    if depth_pct < 50:
        return "WORK"
    if depth_pct < 85:
        return "RISK"
    return "DEEP"


def _build_range(candles_1h):
    window = candles_1h[-48:] if len(candles_1h) >= 48 else candles_1h
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


def build_full_snapshot(symbol="BTCUSDT"):
    price = get_price(symbol)
    candles_1h = get_klines(symbol=symbol, interval="1h", limit=200)
    candles_4h = aggregate_to_4h(candles_1h)
    candles_1d = aggregate_to_1d(candles_1h)

    range_low, range_high, range_mid = _build_range(candles_1h)
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

    if active_block == 'SHORT' and consensus_direction == 'LONG' and consensus_alignment_count >= 2 and block_flip_warning:
        watch_side = 'LONG'
    elif active_block == 'LONG' and consensus_direction == 'SHORT' and consensus_alignment_count >= 2 and block_flip_warning:
        watch_side = 'SHORT'
    else:
        watch_side = 'NONE'

    base_snapshot = {
        'symbol': symbol,
        'timestamp': datetime.now().strftime('%H:%M'),
        'tf': '1h',
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
        **structure_flags,
    }

    prev_market_state = load_market_state()
    prep_state = update_flip_prep(prev_market_state, base_snapshot)
    base_snapshot.update(prep_state)

    base_prob, alt_prob, base_reasons, alt_reasons = compute_scenario_weights(base_snapshot)
    flip_level = range_high if active_block == 'SHORT' else range_low
    flip_condition_text = f"2 закрытия {'выше' if active_block == 'SHORT' else 'ниже'} {flip_level:.2f}"
    scenario_base_text = (
        f"отбой от {'верхнего' if active_block == 'SHORT' else 'нижнего'} края → {active_block} блок остаётся активным"
    )
    scenario_alt_text = (
        f"пробой и закрепление {'выше' if active_block == 'SHORT' else 'ниже'} {flip_level:.2f} → {active_block} блок инвалидируется, сценарий смещается в {watch_side if watch_side != 'NONE' else ('LONG' if active_block == 'SHORT' else 'SHORT')}"
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

    if state == "OVERRUN":
        action = "PROTECT"
        entry_type = None
    elif trigger and state == "CONFIRMED" and context_score >= 2 and not (block_pressure == 'AGAINST' and block_pressure_strength in {'MID', 'HIGH'}):
        action = "ENTER"
        entry_type = "ENTER"
    elif state in {"PRE_ACTIVATION", 'SEARCH_TRIGGER'} and context_score >= 1 and not conflict_flag and block_pressure != 'AGAINST':
        action = "PREPARE"
        entry_type = "PROBE"
    else:
        action = "WAIT"
        entry_type = None

    if block_depth_pct > 60:
        hedge_state = "PRE-TRIGGER"
    elif state in ("SEARCH_TRIGGER", "PRE_ACTIVATION"):
        hedge_state = "ARM"
    elif state == "OVERRUN":
        hedge_state = "TRIGGER"
    else:
        hedge_state = "OFF"

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

    if block_pressure == 'AGAINST' and block_pressure_strength in {'MID', 'HIGH'}:
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

    action_map = {
        'BOOST': 'WORK',
        'ENABLE': 'WORK',
        'HOLD': 'WORK',
        'REDUCE': 'REDUCE',
        'PAUSE': 'PAUSE',
    }
    ginarea = {
        'mode': 'PRIORITY_GRID',
        'long_grid': action_map.get(grid_action['long_action'], 'WORK'),
        'short_grid': action_map.get(grid_action['short_action'], 'WORK'),
        'aggression': 'LOW' if grid_action['grid_regime'] == 'DANGER' else 'MID' if grid_action['priority_side'] != 'NEUTRAL' else 'LOW',
        'lifecycle': 'REDUCE_GRID' if grid_action['grid_regime'] == 'DANGER' else 'ARM_GRID' if state in ('SEARCH_TRIGGER', 'PRE_ACTIVATION') else 'WAIT_GRID',
    }

    snapshot['ginarea'] = ginarea
    snapshot['grid_action'] = grid_action

    save_market_state(prep_state)
    return snapshot
