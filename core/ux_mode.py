from __future__ import annotations

from typing import Any, Dict


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default




def _clean_prefixed_text(value: Any, prefix: str) -> str:
    text = str(value or '').strip()
    if not text:
        return 'нет данных'
    pfx = str(prefix or '').strip().lower().rstrip(':')
    cur = text
    while cur.lower().startswith(pfx):
        cur = cur[len(pfx):].strip(' :')
    return cur or 'нет данных'

def _decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get('decision')
    if isinstance(decision, dict):
        return decision
    if any(k in payload for k in ('action', 'action_text', 'direction', 'direction_text', 'edge_score', 'edge_label', 'execution_verdict', 'trade_authorized', 'bot_authorized')):
        return payload
    return {}


def is_no_trade_context(payload: Dict[str, Any]) -> bool:
    decision = _decision(payload)
    if _soft_probe_allowed(payload):
        return False
    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else {}
    edge = max(
        _num(payload.get('edge_score', decision.get('edge_score')), 0.0),
        _num(verdict.get('trade_edge_score'), 0.0),
        _num(verdict.get('bot_edge_score'), 0.0),
    )
    action = str(decision.get('action_text') or decision.get('action') or payload.get('final_decision') or '').upper()
    direction = str(decision.get('direction_text') or decision.get('direction') or payload.get('final_decision') or '').upper()
    range_position = str(payload.get('range_position') or payload.get('range_state') or '').upper()
    trap = str((payload.get('setup_quality') or {}).get('trap_risk') or payload.get('trap_risk') or '').upper()
    late = str((payload.get('setup_quality') or {}).get('late_entry_risk') or payload.get('late_entry_risk') or '').upper()
    setup_status = str((payload.get('setup_quality') or {}).get('setup_status_text') or payload.get('setup_status_text') or '').upper()
    grade = str((payload.get('setup_quality') or {}).get('grade') or payload.get('grade') or '').upper()
    if edge <= 0.05 and (
        'WAIT' in action or 'ЖДАТЬ' in action or direction in {'НЕЙТРАЛЬНО', 'NEUTRAL', 'NONE', ''}
    ):
        return True
    if 'NO TRADE' in grade or 'ПРОПУСТИТЬ' in setup_status:
        return True
    if 'MID' in range_position and trap == 'HIGH' and late in {'MEDIUM', 'HIGH'}:
        return True
    return False


def _bias_line(payload: Dict[str, Any]) -> str:
    decision = _decision(payload)
    side = str(
        decision.get('direction_text')
        or decision.get('direction')
        or payload.get('forecast_direction')
        or payload.get('final_decision')
        or 'НЕЙТРАЛЬНО'
    ).strip()
    conf = _num(
        decision.get('confidence_pct')
        or decision.get('confidence')
        or payload.get('forecast_confidence')
        or decision.get('forecast_confidence'),
        0.0,
    )
    if conf and conf <= 1.0:
        conf *= 100.0
    if side.upper() in {'НЕЙТРАЛЬНО', 'NEUTRAL', ''}:
        return 'перевес: НЕЙТРАЛЬНО'
    if conf > 0:
        return f'перевес: {side} ({conf:.1f}%)'
    return f'перевес: {side}'


def _execution_line(payload: Dict[str, Any]) -> str:
    state = str(_execution_state(payload) or 'WAIT').upper()
    mapping = {
        'WAIT': 'execution: WAIT / NO ENTRY',
        'WATCH': 'execution: WAIT_CONFIRM',
        'PROBE': 'execution: PROBE_ALLOWED',
        'READY': 'execution: ENTRY_ALLOWED',
    }
    return mapping.get(state, f'execution: {state}')


def _range_volume_status(payload: Dict[str, Any]) -> str:
    vr = payload.get('range_volume_bot') if isinstance(payload.get('range_volume_bot'), dict) else {}
    return str(vr.get('status') or '').upper()


def _best_soft_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    if bool(payload.get('execution_truth_lock')):
        return {}
    cards = payload.get('bot_cards') if isinstance(payload.get('bot_cards'), list) else []
    best: Dict[str, Any] = {}
    best_score = -1.0
    for card in cards:
        if not isinstance(card, dict):
            continue
        action_hint = str(card.get('management_action') or '').upper()
        plan_state = str(card.get('plan_state') or '').upper()
        status_hint = str(card.get('status') or card.get('activation_state') or '').upper()
        score_hint = _num(card.get('ranking_score') or card.get('score'), 0.0)
        if score_hint > 1.0:
            score_hint /= 100.0
        soft = (
            action_hint in {'ENABLE SMALL SIZE', 'ENABLE SMALL SIZE REDUCED'}
            or plan_state in {'SMALL ENTRY', 'READY_SMALL', 'READY_SMALL_REDUCED'}
            or (status_hint in {'WATCH', 'SOFT_READY'} and score_hint >= 0.45)
        )
        if soft and score_hint > best_score:
            best_score = score_hint
            best = card
    return best


def _soft_probe_allowed(payload: Dict[str, Any]) -> bool:
    if bool(payload.get('execution_truth_lock')):
        return False
    decision = _decision(payload)
    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else {}
    if bool(verdict.get('soft_allowed')) or bool(verdict.get('bot_authorized')):
        return True
    confirm_ready = _num(payload.get('execution_confirm_ready'), 0.0)
    if confirm_ready <= 0.0:
        return False
    vr = payload.get('range_volume_bot') if isinstance(payload.get('range_volume_bot'), dict) else {}
    vr_status = _range_volume_status(payload)
    direction = str(decision.get('direction_text') or decision.get('direction') or payload.get('final_decision') or '').upper()
    breakout_risk = str(vr.get('breakout_risk') or '').upper()
    edge = _num(payload.get('edge_score', decision.get('edge_score')), 0.0)
    best_soft_card = _best_soft_card(payload)
    if best_soft_card:
        return True
    if vr_status in {'READY_SMALL', 'READY_SMALL_REDUCED'} and direction not in {'', 'NEUTRAL', 'НЕЙТРАЛЬНО', 'NONE'}:
        if breakout_risk in {'LOW', 'MEDIUM', ''}:
            return True
        if breakout_risk == 'HIGH' and edge > 0.0:
            return True
    bot_state = str(payload.get('bot_control_status') or payload.get('bot_mode') or '').upper()
    if bot_state in {'READY_SMALL', 'READY_SMALL_REDUCED', 'CARD_SMALL', 'SOFT_READY'}:
        return True
    entry_score = _num((payload.get('entry_score') or {}).get('score') if isinstance(payload.get('entry_score'), dict) else payload.get('entry_score'), 0.0)
    range_position = str(payload.get('range_position') or payload.get('range_state') or '').upper()
    activation_hint = str(payload.get('ginarea_status') or payload.get('activation_state') or payload.get('execution_bias') or '').upper()
    if entry_score >= 40.0 and direction not in {'', 'NEUTRAL', 'НЕЙТРАЛЬНО', 'NONE'}:
        if any(tag in range_position for tag in {'UPPER', 'LOWER', 'EDGE', 'ВЕРХ', 'НИЖ'}) or activation_hint in {'SOFT_READY', 'READY_SMALL', 'READY_SMALL_REDUCED'}:
            return True
    return False


def _execution_state(payload: Dict[str, Any]) -> str:
    decision = _decision(payload)
    if bool(decision.get('trade_authorized')):
        return 'READY'
    if _soft_probe_allowed(payload):
        return 'PROBE'
    if is_no_trade_context(payload):
        return 'WAIT'
    return 'WATCH'


def _precise_trigger(payload: Dict[str, Any]) -> str:
    decision = _decision(payload)
    direction = str(decision.get('direction_text') or decision.get('direction') or payload.get('final_decision') or '').upper()
    hi = payload.get('range_high') or ((payload.get('range') or {}).get('high') if isinstance(payload.get('range'), dict) else None)
    lo = payload.get('range_low') or ((payload.get('range') or {}).get('low') if isinstance(payload.get('range'), dict) else None)
    fake_move = payload.get('fake_move_detector') if isinstance(payload.get('fake_move_detector'), dict) else {}
    fake_type = str(fake_move.get('type') or '').upper()
    if direction in {'SHORT', 'ШОРТ'}:
        if hi is not None:
            if fake_type in {'FAKE_UP', 'FAKE_BREAK', 'FAKE_BREAK_UP', 'UP_TRAP'}:
                return f'ложный вынос выше {hi} → возврат под {hi} за 1–2 свечи рабочего ТФ → short только после rejection/подтверждения'
            return f'только если вынос выше {hi} быстро вернут под уровень за 1–2 свечи и следующая свеча не даст follow-through вверх'
        return 'short только после ложного выноса вверх / rejection / возврата под уровень и подтверждения следующей свечой'
    if direction in {'LONG', 'ЛОНГ'}:
        if lo is not None:
            if fake_type in {'FAKE_DOWN', 'FAKE_BREAK_DOWN', 'DOWN_TRAP'}:
                return f'ложный пролив ниже {lo} → возврат выше {lo} за 1–2 свечи рабочего ТФ → long только после reclaim/подтверждения'
            return f'только если пролив ниже {lo} быстро выкупят, цена вернётся выше уровня за 1–2 свечи и удержит reclaim'
        return 'long только после ложного пролива / reclaim / удержания уровня и подтверждения следующей свечой'
    if hi is not None and lo is not None:
        return f'вынос выше {hi} и быстрый возврат под уровень за 1–2 свечи = short; пролив ниже {lo} и возврат выше уровня за 1–2 свечи = long'
    return 'ждать retest / reclaim / подтверждение у края диапазона'


def compact_context_lines(payload: Dict[str, Any]) -> Dict[str, str]:
    decision = _decision(payload)
    trigger = str((decision.get('trigger_text') or decision.get('trigger') or payload.get('trigger') or '')).strip()
    trigger = _precise_trigger(payload) if not trigger or 'подход к' in trigger.lower() else trigger
    state = _execution_state(payload)
    summary = str(decision.get('summary') or payload.get('decision_summary') or 'Сейчас лучше ждать: явного directional edge нет.').strip()
    if state == 'PROBE':
        summary = 'Есть мягкий сценарий у края диапазона: допустим пробный малый вход, добавления только после подтверждения.'
    elif is_no_trade_context(payload):
        summary = 'Есть перевес, но вход не разрешён без подтверждения.'
    invalidation = str(decision.get('invalidation') or decision.get('scenario_invalidation') or 'до подтверждения активной стороны идеи нет').strip()
    no_chase = 'не входить из середины диапазона и не гнаться за движением'
    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else {}
    edge = max(_num(payload.get('edge_score', decision.get('edge_score')), 0.0), _num(verdict.get('trade_edge_score'), 0.0), _num(verdict.get('bot_edge_score'), 0.0))
    why = str((payload.get('setup_quality') or {}).get('summary') or payload.get('why_no_trade') or decision.get('no_trade_reason') or '').strip()
    if not why:
        if state == 'PROBE':
            why = 'разрешён только probe: допускается малый вход, но без доборов до подтверждения'
        elif state == 'WATCH':
            why = 'есть мягкий сценарий, но нужен локальный reclaim / rejection / follow-through запрет'
        elif edge <= 0.05:
            why = 'edge слишком слабый: вход не разрешён без подтверждения'
        else:
            why = 'нужен более чистый триггер'
    pattern_summary = str(payload.get('history_pattern_summary') or '').strip()
    return {
        'summary': summary,
        'next_trigger': trigger,
        'invalidation': invalidation,
        'risk': no_chase,
        'why': why,
        'bias': _bias_line(payload),
        'pattern': pattern_summary,
        'execution_state': state,
    }


def build_ultra_wait_block(title: str, payload: Dict[str, Any], *, include_price: bool = True) -> str:
    info = compact_context_lines(payload)
    price = payload.get('price')
    upper_title = title.upper()
    state = str(info.get('execution_state') or 'WAIT').upper()
    state_label = 'PROBE' if state == 'PROBE' else 'READY' if state == 'READY' else 'WATCH' if state == 'WATCH' else 'WAIT'
    decision = _decision(payload)
    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else {}
    edge_value = max(_num(payload.get('edge_score'), 0.0), _num(decision.get('edge_score'), 0.0), _num(verdict.get('trade_edge_score'), 0.0), _num(verdict.get('bot_edge_score'), 0.0))
    edge_label = 'NONE' if edge_value <= 0.0 else 'WEAK' if edge_value < 40.0 else 'TRADEABLE' if edge_value < 70.0 else 'STRONG'
    lines = [title, '', state_label]
    if include_price and price not in (None, 0, 0.0):
        lines.append(f'Цена: {price}')
    lines.append('')

    if 'FINAL DECISION' in upper_title or 'ФИНАЛЬНОЕ РЕШЕНИЕ' in upper_title:
        lines.extend([
            f'• {info["bias"]}',
            f'• {_execution_line(payload)}',
            f'• edge: {edge_label} ({edge_value:.1f}/100)',
            f'• решение: {"разрешён только малый probe после подтверждения" if state_label == "PROBE" else "СМОТРЕТЬ / ЖДАТЬ ПОДТВЕРЖДЕНИЕ" if state_label == "WATCH" else "ЖДАТЬ"}',
            f'• почему: {info["why"]}',
            f'• trigger: {info["next_trigger"]}',
            f'• запрет: {info.get("risk", "нет данных")}',
        ])
    elif 'ЧТО ДЕЛАТЬ' in upper_title:
        lines.extend([
            f'• что делать: {"SMALL PROBE" if state_label == "PROBE" else "СМОТРЕТЬ ПОДТВЕРЖДЕНИЕ" if state_label == "WATCH" else "ЖДАТЬ"}',
            f'• тактический режим: {"PROBE_ONLY" if state_label == "PROBE" else "WAIT_CONFIRM" if state_label == "WATCH" else "NO_CHASE"}',
            f'• edge: {edge_label} ({edge_value:.1f}/100)',
            f'• триггер: {info["next_trigger"]}',
            f'• отмена идеи: {info["invalidation"]}',
            f'• комментарий: {info["summary"]}',
        ])
    elif 'FORECAST' in upper_title or 'ПРОГНОЗ' in upper_title:
        lines.extend([
            f'• {info["bias"]}',
            f'• {_execution_line(payload)}',
            f'• edge: {edge_label} ({edge_value:.1f}/100)',
            f'• trigger: {info["next_trigger"]}',
        ])
    elif 'SUMMARY' in upper_title or 'СВОДКА' in upper_title:
        lines.extend([
            f'• {info["bias"]}',
            f'• {_execution_line(payload)}',
            f'• edge: {edge_label} ({edge_value:.1f}/100)',
            f'• {info["summary"]}',
        ])
    elif 'ЛУЧШАЯ СДЕЛКА' in upper_title or 'BEST TRADE' in upper_title:
        lines.extend([
            f'• лучший сценарий: {"probe" if state_label == "PROBE" else "watch" if state_label == "WATCH" else "wait"}',
            f'• сторона: {"setup" if state_label in {"PROBE", "WATCH"} else "FLAT"}',
            f'• edge: {edge_label} ({edge_value:.1f}/100)',
            f'• действие сейчас: {"ждать подтверждение и брать только small" if state_label == "PROBE" else "смотреть подтверждение и не входить из середины" if state_label == "WATCH" else "ЖДАТЬ"}',
            f'• когда смотреть снова: {info["next_trigger"]}',
            f'• запрет: {info["risk"]}',
        ])
    elif 'TRADE MANAGER' in upper_title or 'МЕНЕДЖЕР' in upper_title:
        lines.extend([
            f'• {info["bias"]}',
            f'• {_execution_line(payload)}',
            '• активного ведения позиции сейчас нет' if state_label not in {'PROBE','WATCH'} else '• допускается только пробный малый вход, без доборов до подтверждения' if state_label == 'PROBE' else '• активной позиции нет: пока только наблюдение и ожидание локального подтверждения',
            f'• почему: {info["why"]}',
            f'• trigger: {info["next_trigger"]}',
        ])
    else:
        lines.extend([
            f'• {info["bias"]}',
            f'• {_execution_line(payload)}',
            f'• edge: {edge_label} ({edge_value:.1f}/100)',
            f'• {info["summary"]}',
            f'• trigger: {info["next_trigger"]}',
            f'• invalidation: {info["invalidation"]}',
            f'• запрет: {info["risk"]}',
        ])
    base = '\n'.join(lines)
    return base
