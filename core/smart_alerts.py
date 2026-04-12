from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import json

from core.liquidity_lite import build_liquidity_lite_context
from core.priority_engine import build_priority_context
from core.market_phase_engine import classify_market_phase
from core.final_signal_model_v177 import evaluate_signal_model

STATE_FILE = Path('state/smart_alert_state.json')


def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def _s(x: Any, default: str = '') -> str:
    return str(x if x is not None else default)


def detect_alert_events(current_snapshot: Dict[str, Any], previous_snapshot: Dict[str, Any] | None = None) -> list[dict[str, Any]]:
    prev = previous_snapshot or _load_state()
    decision = current_snapshot.get('decision') if isinstance(current_snapshot.get('decision'), dict) else {}
    cur_dir = _s(decision.get('direction') or current_snapshot.get('final_decision') or 'NEUTRAL', 'NEUTRAL').upper()
    cur_action = _s(decision.get('action') or current_snapshot.get('action_now') or 'WAIT', 'WAIT').upper()
    cur_fast = _s(decision.get('fast_move_classification') or current_snapshot.get('fast_move_classification') or '').upper()
    cur_target = current_snapshot.get('target_zone') or current_snapshot.get('reaction_zone')
    liq = current_snapshot.get('liquidation_context') if isinstance(current_snapshot.get('liquidation_context'), dict) else {}
    soft = current_snapshot.get('soft_signal') if isinstance(current_snapshot.get('soft_signal'), dict) else {}
    lite = build_liquidity_lite_context(current_snapshot)
    coinglass = current_snapshot.get('coinglass_context') if isinstance(current_snapshot.get('coinglass_context'), dict) else {}
    fast_move = current_snapshot.get('fast_move') if isinstance(current_snapshot.get('fast_move'), dict) else {}
    bot_center = current_snapshot.get('bot_control_center') if isinstance(current_snapshot.get('bot_control_center'), dict) else {}
    events = []
    priority_ctx = build_priority_context(current_snapshot)
    phase_ctx = classify_market_phase(current_snapshot)
    signal_ctx = evaluate_signal_model(current_snapshot, previous_state=prev)

    cur_acceptance = _s(fast_move.get('acceptance_state') or current_snapshot.get('acceptance_state')).upper()
    cur_reclaim = _s(fast_move.get('reclaim_state') or current_snapshot.get('reclaim_state')).upper()
    top_permission = _s(bot_center.get('top_permission')).upper()

    if prev.get('direction') and prev.get('direction') != cur_dir:
        events.append({'type': 'scenario_flip', 'priority': 'HIGH', 'title': 'рынок сменил сторону'})
    if prev.get('main_priority') and prev.get('main_priority') != priority_ctx.get('main_priority'):
        events.append({'type': 'priority_shift', 'priority': 'HIGH', 'title': 'сменился главный приоритет сценария'})
    if prev.get('market_phase') and prev.get('market_phase') != phase_ctx.get('phase'):
        events.append({'type': 'market_phase_shift', 'priority': 'MEDIUM', 'title': 'изменилась фаза рынка'})

    if signal_ctx.get('debounce_status') == 'CONFIRMED_SIGNAL' and signal_ctx.get('signal_state') in {'ARMED', 'ACTIONABLE'} and prev.get('signal_state') != signal_ctx.get('signal_state'):
        title = 'setup стабилизировался и готов к работе' if signal_ctx.get('signal_state') == 'ARMED' else 'появилось подтверждённое действие по master decision'
        events.append({'type': 'signal_confirmed', 'priority': 'HIGH', 'title': title})
    if signal_ctx.get('debounce_status') == 'CANCELLED' and prev.get('signal_state') in {'ARMED', 'ACTIONABLE'}:
        events.append({'type': 'signal_cancelled', 'priority': 'HIGH', 'title': 'рабочий setup отменён без спама и переведён в паузу'})
    if signal_ctx.get('alignment_status') == 'BLOCKED_BY_MASTER' and prev.get('alignment_status') != 'BLOCKED_BY_MASTER':
        events.append({'type': 'signal_blocked', 'priority': 'MEDIUM', 'title': 'локальный сигнал заблокирован master decision'})
    if signal_ctx.get('edge_state') != prev.get('edge_state') and signal_ctx.get('debounce_status') not in {'PENDING_CONFIRMATION', 'WEAKENED_BUT_ACTIVE'}:
        edge_titles = {
            'PAUSE': 'режим переведён в паузу',
            'WATCH EDGE': 'рынок в наблюдении у рабочей зоны',
            'ARM EDGE': 'рабочий край armed без дёрганий',
            'ACTION READY': 'сценарий готов к действию',
            'MANAGE ONLY': 'режим сопровождения позиции / сетки',
        }
        title = edge_titles.get(signal_ctx.get('edge_state'), 'сменился режим работы сигнала')
        events.append({'type': 'edge_state_change', 'priority': 'MEDIUM', 'title': title})

    if prev.get('action') != cur_action and any(x in cur_action for x in ['ВХОД', 'ENTER', 'WATCH', 'RECLAIM']):
        if signal_ctx.get('debounce_status') != 'PENDING_CONFIRMATION':
            events.append({'type': 'fresh_entry', 'priority': 'HIGH', 'title': 'появился рабочий intraday-триггер'})
    if cur_fast in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN'} and signal_ctx.get('alignment_status') != 'BLOCKED_BY_MASTER':
        events.append({'type': 'fake_breakout_alert', 'priority': 'HIGH', 'title': 'ложный вынос выглядит вероятным'})
    if cur_fast in {'EARLY_FAKE_UP_RISK', 'EARLY_FAKE_DOWN_RISK'} and prev.get('fast_move') != cur_fast:
        events.append({'type': 'trap_risk_alert', 'priority': 'MEDIUM', 'title': 'растёт риск ловушки у локального экстремума'})
    if cur_fast in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} and prev.get('fast_move') != cur_fast and signal_ctx.get('alignment_status') != 'BLOCKED_BY_MASTER':
        events.append({'type': 'continuation_confirmed', 'priority': 'HIGH', 'title': 'движение принимают, continuation подтверждается'})
    if cur_fast == 'POST_LIQUIDATION_EXHAUSTION' and prev.get('fast_move') != cur_fast:
        events.append({'type': 'exhaustion_alert', 'priority': 'HIGH', 'title': 'после снятия ликвидности импульс выдыхается'})
    if ('FAILED' in cur_acceptance or cur_reclaim in {'FAILED', 'LOST'}) and prev.get('acceptance_state') != cur_acceptance:
        events.append({'type': 'reclaim_failed', 'priority': 'HIGH', 'title': 'reclaim/acceptance не удержан'})
    if cur_target and prev.get('target_zone') != cur_target:
        events.append({'type': 'target_zone', 'priority': 'MEDIUM', 'title': 'обновилась зона реакции / цель'})
    if _s(liq.get('cascade_risk')).upper() == 'HIGH' and prev.get('cascade_risk') != 'HIGH':
        events.append({'type': 'liq_risk', 'priority': 'HIGH', 'title': 'рядом высокая ликвидационная зона'})
    if bool(soft.get('active')) and not prev.get('soft_active') and signal_ctx.get('alignment_status') != 'BLOCKED_BY_MASTER':
        events.append({'type': 'soft_signal', 'priority': 'MEDIUM', 'title': 'включился soft intraday сигнал'})
    if _s(lite.get('wick_signal')).upper() in {'UP_SWEEP_REJECTED', 'DOWN_SWEEP_REJECTED'} and prev.get('wick_signal') != _s(lite.get('wick_signal')).upper() and signal_ctx.get('alignment_status') != 'BLOCKED_BY_MASTER':
        events.append({'type': 'liquidity_sweep', 'priority': 'HIGH', 'title': 'сформировался sweep / возможная ловушка'})
    if _s(lite.get('setup_bias')).upper() in {'SHORT_AFTER_FAKE_UP', 'LONG_AFTER_FAKE_DOWN'} and prev.get('setup_bias') != _s(lite.get('setup_bias')).upper() and signal_ctx.get('alignment_status') != 'BLOCKED_BY_MASTER':
        events.append({'type': 'trap_reclaim_ready', 'priority': 'HIGH', 'title': 'появилась reclaim-идея после выноса'})
    if top_permission in {'ALLOW', 'SMALL ONLY'} and prev.get('top_permission') != top_permission and signal_ctx.get('edge_state') != 'PAUSE':
        events.append({'type': 'bot_layer_activation', 'priority': 'MEDIUM', 'title': 'активировался рабочий слой для ботов'})
    if _s(coinglass.get('feed_health')).upper() == 'DEGRADED' and prev.get('feed_health') != 'DEGRADED':
        events.append({'type': 'feed_degraded', 'priority': 'MEDIUM', 'title': 'real-liq feed деградировал, логика перешла в fallback'})

    dedup = []
    seen = set()
    for event in events:
        key = (event.get('type'), event.get('title'))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(event)
    events = dedup

    new_state = {
        'direction': cur_dir,
        'action': cur_action,
        'fast_move': cur_fast,
        'acceptance_state': cur_acceptance,
        'reclaim_state': cur_reclaim,
        'target_zone': cur_target,
        'cascade_risk': _s(liq.get('cascade_risk') or 'LOW').upper(),
        'soft_active': bool(soft.get('active')),
        'wick_signal': _s(lite.get('wick_signal')).upper(),
        'setup_bias': _s(lite.get('setup_bias')).upper(),
        'top_permission': top_permission,
        'feed_health': _s(coinglass.get('feed_health')).upper(),
        'main_priority': _s(priority_ctx.get('main_priority')).upper(),
        'market_phase': _s(phase_ctx.get('phase')).upper(),
        'signal_state': signal_ctx.get('signal_state'),
        'edge_state': signal_ctx.get('edge_state'),
        'alignment_status': signal_ctx.get('alignment_status'),
        'candidate_state': signal_ctx.get('candidate_state'),
        'candidate_edge': signal_ctx.get('candidate_edge'),
        'enter_count': signal_ctx.get('enter_count'),
        'exit_count': signal_ctx.get('exit_count'),
        'updated_at': datetime.utcnow().isoformat(),
    }
    _save_state(new_state)
    return events


def build_alert_text(event: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    title = _s(event.get('title') or 'обновление сценария')
    decision = snapshot.get('decision') if isinstance(snapshot.get('decision'), dict) else {}
    direction = _s(decision.get('direction') or snapshot.get('final_decision') or 'НЕЙТРАЛЬНО')
    action = _s(snapshot.get('action_now') or decision.get('action') or 'ЖДАТЬ')
    zone = _s(snapshot.get('entry_zone') or snapshot.get('reaction_zone') or 'нет данных')
    inval = _s(decision.get('invalidation') or snapshot.get('invalidation') or 'нет данных')
    signal_ctx = evaluate_signal_model(snapshot)
    blocked = _s(signal_ctx.get('blocked_reason') or 'нет')
    return f"🔔 INTRADAY ALERT\n\n• событие: {title}\n• направление: {direction}\n• действие: {action}\n• сигнал: {signal_ctx.get('signal_state')} / {signal_ctx.get('edge_state')}\n• зона: {zone}\n• блок: {blocked}\n• инвалидация: {inval}"
