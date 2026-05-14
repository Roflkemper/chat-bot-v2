from __future__ import annotations

from typing import Any, Dict, List

from core.final_signal_model_v177 import evaluate_signal_model


def _u(v: Any, default: str = "") -> str:
    try:
        if v is None:
            return default
        return str(v).strip().upper()
    except Exception:
        return default


def _fmt_price(v: Any) -> str:
    try:
        x = float(v)
        return f"{x:.2f}" if x > 0 else 'нет данных'
    except Exception:
        return 'нет данных'


def _fmt_zone(a: Any, b: Any) -> str:
    try:
        x = float(a); y = float(b)
        lo, hi = min(x, y), max(x, y)
        return f"{lo:.2f}–{hi:.2f}"
    except Exception:
        return 'нет данных'


def _market_mode(payload: Dict[str, Any], decision: Dict[str, Any], move_type_context: Dict[str, Any]) -> str:
    regime = _u(move_type_context.get('regime') or decision.get('market_mode') or decision.get('mode') or decision.get('regime') or payload.get('market_mode') or payload.get('regime') or 'UNKNOWN')
    if 'RANGE' in regime:
        return 'RANGE'
    if 'TREND' in regime:
        return 'TREND'
    if 'MIXED' in regime:
        return 'MIXED'
    return 'UNKNOWN'


def build_action_output(payload: Dict[str, Any], decision: Dict[str, Any], move_type_context: Dict[str, Any], bot_mode_context: Dict[str, Any]) -> Dict[str, Any]:
    market_mode = _market_mode(payload, decision, move_type_context)
    action = _u(decision.get('action') or 'WAIT')
    location = _u(move_type_context.get('location_state') or payload.get('location_state') or '')
    fake = payload.get('fake_move_detector') if isinstance(payload.get('fake_move_detector'), dict) else {}
    impulse = payload.get('impulse_character') if isinstance(payload.get('impulse_character'), dict) else {}
    liq = payload.get('liquidity_decision') if isinstance(payload.get('liquidity_decision'), dict) else {}
    signal_ctx = evaluate_signal_model(payload)

    high = payload.get('range_high') or decision.get('range_high')
    low = payload.get('range_low') or decision.get('range_low')
    mid = payload.get('range_mid') or decision.get('range_mid')

    summary_lines: List[str] = []
    launch_lines: List[str] = []
    invalidation_lines: List[str] = []

    if location == 'MID' or signal_ctx.get('edge_state') == 'PAUSE':
        now_line = 'PAUSE'
    elif signal_ctx.get('edge_state') == 'WATCH EDGE':
        now_line = 'WATCH'
    elif signal_ctx.get('edge_state') == 'ARM EDGE':
        now_line = 'ARM'
    elif signal_ctx.get('edge_state') == 'ACTION READY':
        now_line = action or 'ENTER'
    else:
        now_line = action or 'HOLD'

    why = []
    forbidden = []
    if location == 'MID':
        why.append('цена в середине диапазона')
        forbidden.append('НЕ ВХОДИТЬ ИЗ СЕРЕДИНЫ')
    if fake.get('confirmed'):
        why.append(str(fake.get('summary') or 'ложный вынос подтверждён'))
    elif str(fake.get('state') or '').upper() in {'RECLAIM_PENDING_SHORT', 'RECLAIM_PENDING_LONG'}:
        why.append('есть sweep, но нужен reclaim')
    if str(impulse.get('state') or '').upper() in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} and location != 'MID':
        why.append(str(impulse.get('comment') or 'чистое продолжение движения'))
    elif str(impulse.get('state') or '').upper() in {'EXHAUSTION_UP', 'EXHAUSTION_DOWN'}:
        why.append(str(impulse.get('comment') or 'движение затухает'))
        forbidden.append('НЕ ДОБИРАТЬ В ЗАТУХАЮЩИЙ ИМПУЛЬС')
    if liq.get('summary'):
        why.append(str(liq.get('summary')))
    if signal_ctx.get('alignment_status') == 'BLOCKED_BY_MASTER':
        forbidden.append('ЛОКАЛЬНЫЙ СИГНАЛ ЗАБЛОКИРОВАН MASTER DECISION')

    summary_lines.append(f'главное действие: {now_line}')
    summary_lines.append(f'режим: {market_mode}')
    summary_lines.append(f"сигнал: {signal_ctx.get('signal_state')} / {signal_ctx.get('edge_state')}")
    summary_lines.append(f"импульс: {impulse.get('state') or 'NO_CLEAR_IMPULSE'}")
    summary_lines.append(f"fake move: {fake.get('state') or 'NO_SWEEP'}")
    summary_lines.append(f"ликвидность: {liq.get('liq_side_pressure') or 'NEUTRAL'} / squeeze {liq.get('squeeze_risk') or 'LOW'}")

    if high and mid:
        launch_lines.extend([
            f"SHORT PLAN: зона { _fmt_zone(mid, high) }",
            f"триггер: {fake.get('action') if str(fake.get('side_hint')).upper() == 'SHORT' else 'ждать вынос выше зоны и возврат под уровень'}",
            f"запрет: не входить в догонку ниже середины и не добирать без нового rejection",
        ])
    if low and mid:
        launch_lines.extend([
            f"LONG PLAN: зона { _fmt_zone(low, mid) }",
            f"триггер: {fake.get('action') if str(fake.get('side_hint')).upper() == 'LONG' else 'ждать пролив ниже зоны и reclaim вверх'}",
            f"запрет: не входить в догонку выше середины и не добирать без нового reclaim",
        ])

    if why:
        summary_lines.append('почему: ' + ' | '.join(why[:3]))
    if forbidden:
        summary_lines.append('запрет: ' + ' | '.join(forbidden[:2]))
    if decision.get('invalidation_reason'):
        invalidation_lines.append(str(decision.get('invalidation_reason')))
    elif high and low:
        invalidation_lines.append(f"выход из диапазона {_fmt_price(low)}–{_fmt_price(high)} с удержанием за границей")

    return {
        'title': '⚡ ЧТО ДЕЛАТЬ',
        'market_mode': market_mode,
        'directional_action': action or 'WAIT',
        'bot_mode_action': _u(bot_mode_context.get('bot_mode_action') or 'OFF'),
        'summary_lines': summary_lines[:7],
        'launch_lines': launch_lines[:6],
        'invalidation_lines': invalidation_lines[:3],
    }


__all__ = ['build_action_output']
