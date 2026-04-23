from __future__ import annotations

from typing import Any, Dict, List


def _score(card: Dict[str, Any]) -> float:
    try:
        return float(card.get('ranking_score') or card.get('score') or 0.0)
    except Exception:
        return 0.0


def _fmt_zone(z):
    try:
        if isinstance(z, (list, tuple)) and len(z) == 2:
            return f"{float(z[0]):.2f}–{float(z[1]):.2f}"
    except Exception:
        pass
    return 'нет данных'


def analyze_bot_market_mode(payload: Dict[str, Any]) -> str:
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    mode = str(decision.get('mode') or payload.get('market_mode') or 'MIXED').upper()
    if 'RANGE' in mode:
        return 'RANGE_FRIENDLY'
    if mode == 'TREND' or 'TREND' in mode:
        return 'TREND_BIASED'
    if mode in {'PANIC', 'VOLATILE_EXPANSION'}:
        return mode
    return 'MIXED'


def score_bot_layers(symbol: str, analysis_snapshot: Dict[str, Any], bot_cards: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for card in bot_cards or []:
        label = str(card.get('bot_label') or card.get('title') or card.get('bot_key') or '').strip() or 'UNKNOWN'
        out[label] = {'score': round(_score(card), 3), 'status': str(card.get('status') or card.get('activation_state') or 'OFF'), 'action': str(card.get('management_action') or 'WAIT'), 'note': str(card.get('entry_instruction') or card.get('exit_instruction') or card.get('note') or '').strip()}
    return out


def summarize_bot_control(symbol: str, analysis_snapshot: Dict[str, Any], bot_cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    mode = analyze_bot_market_mode(analysis_snapshot)
    scored = score_bot_layers(symbol, analysis_snapshot, bot_cards)
    ranked = sorted(scored.items(), key=lambda kv: kv[1]['score'], reverse=True)
    primary = ranked[0] if ranked else None
    secondary = ranked[1] if len(ranked) > 1 else None
    decision = analysis_snapshot.get('decision') if isinstance(analysis_snapshot.get('decision'), dict) else (analysis_snapshot if isinstance(analysis_snapshot, dict) else {})
    move_type_context = decision.get('move_type_context') if isinstance(decision.get('move_type_context'), dict) else {}
    range_bot_permission = decision.get('range_bot_permission') if isinstance(decision.get('range_bot_permission'), dict) else {}

    if not primary and isinstance(range_bot_permission, dict):
        perm_status = str(range_bot_permission.get('status') or '').upper()
        if perm_status:
            primary = ('RANGE CORE', {'action': 'ARM' if perm_status in {'ARMING','WATCH_ONLY'} else 'WAIT', 'score': 0.32 if perm_status in {'ARMING','WATCH_ONLY'} else 0.0})
    fake_move = decision.get('fake_move_detector') if isinstance(decision.get('fake_move_detector'), dict) else {}
    bot_mode_action = str(decision.get('bot_mode_action') or 'OFF').upper()
    directional_action = str(decision.get('directional_action') or decision.get('action') or 'WAIT').upper()
    move_type = str(move_type_context.get('type') or 'NO_CLEAR_MOVE').upper()
    market_mode = str(move_type_context.get('regime') or decision.get('market_mode') or decision.get('mode') or decision.get('regime') or mode).upper()
    borders = range_bot_permission.get('working_borders') if isinstance(range_bot_permission.get('working_borders'), dict) else {}
    long_zone = range_bot_permission.get('long_zone') if isinstance(range_bot_permission.get('long_zone'), list) else []
    short_zone = range_bot_permission.get('short_zone') if isinstance(range_bot_permission.get('short_zone'), list) else []
    invalidations = range_bot_permission.get('invalidation_conditions') if isinstance(range_bot_permission.get('invalidation_conditions'), list) else []
    range_volume_mode = 'OFF'
    if bot_mode_action == 'RANGE_VOLUME_REDUCED': range_volume_mode = 'READY_REDUCED'
    elif bot_mode_action == 'RANGE_VOLUME_SMALL': range_volume_mode = 'READY_SMALL'
    elif bot_mode_action == 'RANGE_VOLUME_NORMAL': range_volume_mode = 'READY_NORMAL'
    elif bot_mode_action == 'BLOCK_ALL': range_volume_mode = 'BLOCKED'
    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else {}
    trade_authorized = bool(decision.get('trade_authorized')) or bool(verdict.get('soft_allowed')) or bool(decision.get('bot_authorized'))
    edge_score = max(float(analysis_snapshot.get('edge_score') or decision.get('edge_score') or 0.0), float(verdict.get('trade_edge_score') or 0.0), float(verdict.get('bot_edge_score') or 0.0))
    setup_valid = bool(decision.get('setup_valid', True))
    action_bias = str(decision.get('action_bias') or '').upper()
    if (not trade_authorized) or edge_score <= 0.0 or (not setup_valid) or action_bias == 'NO TRADE':
        range_volume_mode = 'WATCH_ONLY'
    return {
        'market_mode_for_bots': mode,
        'primary_layer': primary[0] if primary else 'нет данных',
        'primary_action': primary[1]['action'] if primary else 'WAIT',
        'secondary_layer': secondary[0] if secondary else 'нет данных',
        'secondary_action': secondary[1]['action'] if secondary else 'WAIT',
        'layers': scored,
        'market_mode': market_mode,
        'move_type': move_type,
        'directional_action': directional_action,
        'bot_mode_action': bot_mode_action,
        'range_volume_mode': range_volume_mode,
        'range_bot_permission': range_bot_permission,
        'working_borders': borders,
        'long_zone': long_zone,
        'short_zone': short_zone,
        'invalidation_conditions': invalidations,
        'fake_move_status': str(fake_move.get('type') or 'NONE').upper(),
        'fake_move_confirmed': bool(fake_move.get('confirmed')),
        'summary_lines': [f'рыночный режим: {market_mode}', f'тип движения: {move_type}', f'directional trade: {directional_action}', f'range volume mode: {range_volume_mode}'] + ([f"рабочие границы: {borders.get('low'):.2f}–{borders.get('high'):.2f}"] if borders.get('low') and borders.get('high') else []) + ([f'long-zone: {_fmt_zone(long_zone)}'] if long_zone else []) + ([f'short-zone: {_fmt_zone(short_zone)}'] if short_zone else []),
    }
