from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple
import json

STATE_FILE = Path('state/final_signal_model_v177.json')


ENTER_TH = 62.0
EXIT_TH = 46.0
ACTION_TH = 74.0
ACTION_EXIT_TH = 60.0
ENTER_BARS = 2
EXIT_BARS = 2


ACTIVE_GRID_STATES = {'RUN', 'REDUCE'}
PAUSE_WORDS = ('PAUSE', 'WAIT', 'NO ENTRY', 'NO_ENTRY', 'ЖДАТЬ', 'ПАУЗА')
WATCH_WORDS = ('WATCH', 'ARM', 'RECLAIM', 'RETES', 'ГОТОВ')
ACTION_WORDS = ('ENTER', 'ENTRY', 'ADD', 'PARTIAL', 'EXIT', 'HOLD', 'ВХОД', 'ДОБОР', 'ЧАСТИЧ', 'ВЫХОД', 'ДЕРЖАТЬ')


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _s(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def _normalize_direction(snapshot: Dict[str, Any]) -> str:
    decision = snapshot.get('decision') if isinstance(snapshot.get('decision'), dict) else {}
    direction = _s(decision.get('direction') or snapshot.get('final_decision') or snapshot.get('bias') or 'NEUTRAL').upper()
    if 'LONG' in direction or 'ЛОНГ' in direction:
        return 'LONG'
    if 'SHORT' in direction or 'ШОРТ' in direction:
        return 'SHORT'
    return 'NEUTRAL'


def _master_action(snapshot: Dict[str, Any]) -> str:
    decision = snapshot.get('decision') if isinstance(snapshot.get('decision'), dict) else {}
    return _s(decision.get('action') or snapshot.get('action_now') or snapshot.get('manager_action') or 'WAIT').upper()


def _action_class(action: str) -> str:
    if any(token in action for token in ACTION_WORDS):
        return 'ACTION'
    if any(token in action for token in WATCH_WORDS):
        return 'WATCH'
    if any(token in action for token in PAUSE_WORDS):
        return 'PAUSE'
    return 'PAUSE'


def _range_bucket(snapshot: Dict[str, Any]) -> str:
    explicit = _s(snapshot.get('range_position') or snapshot.get('range_position_zone') or snapshot.get('location_state')).upper()
    if explicit in {'MID', 'MID_RANGE', 'CENTER', 'MIDDLE'}:
        return 'MID'
    if explicit in {'UPPER', 'UPPER_RANGE', 'HIGH', 'HIGH_EDGE'}:
        return 'HIGH'
    if explicit in {'LOWER', 'LOWER_RANGE', 'LOW', 'LOW_EDGE'}:
        return 'LOW'
    price = _f(snapshot.get('price') or snapshot.get('current_price') or snapshot.get('last_price') or snapshot.get('close'))
    low = _f(snapshot.get('range_low'))
    high = _f(snapshot.get('range_high'))
    if price > 0 and high > low:
        pct = (price - low) / (high - low)
        if pct < 0.3:
            return 'LOW'
        if pct > 0.7:
            return 'HIGH'
        return 'MID'
    return 'UNKNOWN'


def _local_hint(snapshot: Dict[str, Any]) -> Tuple[str, float, Dict[str, Any]]:
    pattern = snapshot.get('pattern_memory_v2') if isinstance(snapshot.get('pattern_memory_v2'), dict) else snapshot.get('pattern_memory') if isinstance(snapshot.get('pattern_memory'), dict) else {}
    reversal = snapshot.get('reversal_engine_v15') if isinstance(snapshot.get('reversal_engine_v15'), dict) else snapshot.get('reversal_engine') if isinstance(snapshot.get('reversal_engine'), dict) else {}
    fake = snapshot.get('fake_move_detector') if isinstance(snapshot.get('fake_move_detector'), dict) else {}
    soft = snapshot.get('soft_signal') if isinstance(snapshot.get('soft_signal'), dict) else {}
    direction = 'NEUTRAL'
    strength = 0.0
    reasons = []

    patt_dir = _s(pattern.get('direction_bias') or pattern.get('pattern_bias') or pattern.get('bias')).upper()
    patt_pct = _f(pattern.get('probability_pct') or pattern.get('confidence_pct') or pattern.get('score') or pattern.get('match_pct'))
    if 'LONG' in patt_dir:
        direction = 'LONG'
        strength += min(22.0, max(0.0, patt_pct / 4.0))
        reasons.append('pattern')
    elif 'SHORT' in patt_dir:
        direction = 'SHORT'
        strength += min(22.0, max(0.0, patt_pct / 4.0))
        reasons.append('pattern')

    rev_dir = _s(reversal.get('direction') or reversal.get('bias') or reversal.get('signal_direction')).upper()
    rev_conf = _f(reversal.get('confidence_pct') or reversal.get('confidence') or reversal.get('score'))
    if ('LONG' in rev_dir or 'BULL' in rev_dir) and direction in {'NEUTRAL', 'LONG'}:
        direction = 'LONG'
        strength += min(24.0, max(0.0, rev_conf / 3.5 or 10.0))
        reasons.append('reversal')
    elif ('SHORT' in rev_dir or 'BEAR' in rev_dir) and direction in {'NEUTRAL', 'SHORT'}:
        direction = 'SHORT'
        strength += min(24.0, max(0.0, rev_conf / 3.5 or 10.0))
        reasons.append('reversal')

    fake_dir = _s(fake.get('side_hint') or fake.get('direction')).upper()
    if fake.get('confirmed') or fake.get('is_fake_move'):
        if 'LONG' in fake_dir:
            direction = 'LONG' if direction in {'NEUTRAL', 'LONG'} else direction
        elif 'SHORT' in fake_dir:
            direction = 'SHORT' if direction in {'NEUTRAL', 'SHORT'} else direction
        strength += 18.0
        reasons.append('fake_move')

    if bool(soft.get('active')):
        soft_dir = _s(soft.get('direction') or soft.get('bias')).upper()
        if 'LONG' in soft_dir and direction in {'NEUTRAL', 'LONG'}:
            direction = 'LONG'
        elif 'SHORT' in soft_dir and direction in {'NEUTRAL', 'SHORT'}:
            direction = 'SHORT'
        strength += 10.0
        reasons.append('soft_signal')

    if len(set(reasons)) >= 2:
        strength += 8.0
    return direction, min(100.0, strength), {'reasons': reasons, 'pattern_dir': patt_dir, 'reversal_dir': rev_dir, 'fake_dir': fake_dir}


def evaluate_signal_model(snapshot: Dict[str, Any], previous_state: Dict[str, Any] | None = None, persist: bool = False) -> Dict[str, Any]:
    prev = previous_state or load_state()
    direction = _normalize_direction(snapshot)
    action = _master_action(snapshot)
    action_class = _action_class(action)
    range_bucket = _range_bucket(snapshot)
    decision = snapshot.get('decision') if isinstance(snapshot.get('decision'), dict) else {}
    conf = _f(decision.get('confidence_pct') or decision.get('confidence') or snapshot.get('forecast_confidence') or snapshot.get('scenario_confidence'))
    if conf <= 1.0:
        conf *= 100.0
    local_dir, local_strength, local_meta = _local_hint(snapshot)
    aligned = local_dir == 'NEUTRAL' or direction == 'NEUTRAL' or local_dir == direction
    local_present = local_strength >= 12.0
    long_grid = _s(snapshot.get('long_grid') or snapshot.get('long_grid_state')).upper()
    short_grid = _s(snapshot.get('short_grid') or snapshot.get('short_grid_state')).upper()
    manage_mode = long_grid in ACTIVE_GRID_STATES or short_grid in ACTIVE_GRID_STATES

    structure_bonus = 8.0 if range_bucket in {'LOW', 'HIGH'} else -8.0 if range_bucket == 'MID' else 0.0
    if action_class == 'ACTION':
        structure_bonus += 10.0
    elif action_class == 'WATCH':
        structure_bonus += 3.0
    else:
        structure_bonus -= 5.0
    if not aligned:
        structure_bonus -= 18.0

    strength = max(0.0, min(100.0, conf * 0.55 + local_strength * 0.45 + structure_bonus))
    prev_edge = _s(prev.get('edge_state') or 'PAUSE')
    enter_th = ENTER_TH if prev_edge == 'PAUSE' else EXIT_TH
    action_th = ACTION_TH if prev_edge != 'ACTION READY' else ACTION_EXIT_TH

    if manage_mode:
        raw_state = 'MANAGE'
        edge_state = 'MANAGE ONLY'
    elif action_class == 'PAUSE' and not local_present:
        raw_state = 'QUIET'
        edge_state = 'PAUSE'
    elif action_class == 'PAUSE' and local_present:
        raw_state = 'WATCH'
        edge_state = 'WATCH EDGE'
    elif action_class == 'WATCH':
        raw_state = 'WATCH' if strength < enter_th else 'ARMED'
        edge_state = 'WATCH EDGE' if strength < enter_th else 'ARM EDGE'
    else:
        if strength >= action_th and aligned and range_bucket != 'MID':
            raw_state = 'ACTIONABLE'
            edge_state = 'ACTION READY'
        elif strength >= enter_th and aligned:
            raw_state = 'ARMED'
            edge_state = 'ARM EDGE'
        else:
            raw_state = 'WATCH' if local_present else 'QUIET'
            edge_state = 'WATCH EDGE' if local_present else 'PAUSE'

    stable_state = _s(prev.get('signal_state') or 'QUIET')
    stable_edge = _s(prev.get('edge_state') or 'PAUSE')
    candidate_state = _s(prev.get('candidate_state') or stable_state)
    candidate_edge = _s(prev.get('candidate_edge') or stable_edge)
    enter_count = int(prev.get('enter_count') or 0)
    exit_count = int(prev.get('exit_count') or 0)

    if raw_state != stable_state:
        if raw_state in {'ARMED', 'ACTIONABLE', 'MANAGE'}:
            if candidate_state == raw_state:
                enter_count += 1
            else:
                candidate_state = raw_state
                candidate_edge = edge_state
                enter_count = 1
            debounce_status = 'PENDING_CONFIRMATION' if enter_count < ENTER_BARS else 'CONFIRMED_SIGNAL'
            if enter_count >= ENTER_BARS:
                stable_state = raw_state
                stable_edge = edge_state
                exit_count = 0
        else:
            if candidate_state == raw_state:
                exit_count += 1
            else:
                candidate_state = raw_state
                candidate_edge = edge_state
                exit_count = 1
            debounce_status = 'WEAKENED_BUT_ACTIVE' if exit_count < EXIT_BARS else 'CANCELLED'
            if exit_count >= EXIT_BARS:
                stable_state = raw_state
                stable_edge = edge_state
                enter_count = 0
    else:
        candidate_state = raw_state
        candidate_edge = edge_state
        enter_count = 0
        exit_count = 0
        if local_present and stable_state in {'WATCH', 'ARMED'}:
            debounce_status = 'REARM_CONTINUATION'
        elif local_present:
            debounce_status = 'CONFIRMED_SIGNAL'
        else:
            debounce_status = 'SUPPRESSED_NOISE'

    if not local_present and action_class == 'PAUSE':
        debounce_status = 'SUPPRESSED_NOISE'

    if not aligned and local_present:
        alignment_status = 'BLOCKED_BY_MASTER'
    elif not aligned:
        alignment_status = 'INVALID_DIRECTION'
    elif local_strength >= 25:
        alignment_status = 'ALIGNED_CONFIRM'
    elif local_present:
        alignment_status = 'ALIGNED_WEAK_CONFIRM'
    else:
        alignment_status = 'NON_BLOCKING_CONFLICT' if direction == 'NEUTRAL' else 'ALIGNED_WEAK_CONFIRM'

    blocked_reason = ''
    if range_bucket == 'MID':
        blocked_reason = 'середина диапазона'
    elif not aligned and local_present:
        blocked_reason = 'локальный сигнал не совпадает с master decision'
    elif action_class == 'PAUSE' and local_present:
        blocked_reason = 'master decision не разрешает действие'
    elif strength < enter_th and local_present:
        blocked_reason = 'микросигнал слабый и отфильтрован'

    out = {
        'signal_state': stable_state,
        'edge_state': stable_edge,
        'raw_state': raw_state,
        'raw_edge_state': edge_state,
        'debounce_status': debounce_status,
        'alignment_status': alignment_status,
        'master_direction': direction,
        'master_action': action,
        'master_action_class': action_class,
        'local_direction': local_dir,
        'local_signal_strength': round(local_strength, 1),
        'strength_score': round(strength, 1),
        'range_bucket': range_bucket,
        'blocked_reason': blocked_reason,
        'manage_mode': manage_mode,
        'local_meta': local_meta,
        'candidate_state': candidate_state,
        'candidate_edge': candidate_edge,
        'enter_count': enter_count,
        'exit_count': exit_count,
        'updated_at': datetime.utcnow().isoformat(),
    }
    if persist:
        save_state(out)
    return out
