from __future__ import annotations

from typing import Any, Dict

from core.trade_flow import build_trade_flow_summary
from core.liquidation_character import analyze_fast_move
from core.final_signal_model_v177 import evaluate_signal_model


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def evaluate_entry_window(data: Dict[str, Any], analysis_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    flow = build_trade_flow_summary(data, analysis_snapshot)
    move = analyze_fast_move(data, analysis_snapshot)
    decision = data.get('decision') if isinstance(data.get('decision'), dict) else {}
    edge = _f(data.get('edge_score') or decision.get('best_trade_score') or 0.0)
    conf = _f(decision.get('confidence_pct') or data.get('forecast_confidence') or 0.0)
    soft = data.get('soft_signal') if isinstance(data.get('soft_signal'), dict) else {}
    fake = data.get('fake_move_detector') if isinstance(data.get('fake_move_detector'), dict) else {}
    liq = data.get('liquidation_context') if isinstance(data.get('liquidation_context'), dict) else {}
    deriv = data.get('derivatives_context') if isinstance(data.get('derivatives_context'), dict) else {}
    projection = data.get('move_projection') if isinstance(data.get('move_projection'), dict) else {}

    entry_type = 'БЕЗ ВХОДА'
    comment = 'пока нет свежего входа'
    size_mode = 'x0.00'
    action_now = 'ЖДАТЬ'

    if flow['side'] == 'NEUTRAL' or edge < 20:
        entry_type = 'БЕЗ ВХОДА'
        action_now = 'ЖДАТЬ КРАЙ / RETEST'
        comment = 'идеи недостаточно, лучше ждать край диапазона или подтверждение'
    elif fake.get('is_fake_move'):
        entry_type = 'ЛОВУШКА / RECLAIM ВХОД'
        action_now = 'ЖДАТЬ RECLAIM И БРАТЬ ТОЛЬКО ПО ПОДТВЕРЖДЕНИЮ'
        size_mode = 'x0.35'
        comment = str(fake.get('action') or 'после ложного выноса вход только через возврат под/над зону')
    elif soft.get('active') and conf < 55:
        entry_type = 'SOFT INTRADAY ВХОД'
        action_now = 'МОЖНО МАЛЫМ РАЗМЕРОМ ПОСЛЕ ПОДТВЕРЖДЕНИЯ'
        size_mode = 'x0.30'
        comment = 'ранний intraday режим включён: допускается только reduced size и без погони за свечой'
    elif flow['continuation_state'] == 'ALIVE' and move['move_type'] == 'NORMAL' and edge >= 45:
        entry_type = 'ПОДТВЕРЖДЁННЫЙ ВХОД'
        action_now = 'ВХОД ПО СЦЕНАРИЮ'
        size_mode = 'x1.00'
        comment = 'вход еще не поздний, запас хода есть'
    elif flow['continuation_state'] == 'ALIVE' and move['move_type'] == 'AGGRESSIVE_PUSH':
        entry_type = 'ВХОД ОТ ОТКАТА'
        action_now = 'ЖДАТЬ ОТКАТ'
        size_mode = 'x0.50'
        comment = 'идея жива, но лучше не по рынку — ждать откат'
    elif flow['continuation_state'] == 'ALIVE_BUT_LATE':
        entry_type = 'ПОЗДНИЙ ВХОД / CHASE'
        action_now = 'НЕ ГНАТЬСЯ, ТОЛЬКО RETEST'
        size_mode = 'x0.25'
        comment = 'идея еще жива, но новый вход уже поздний'
    elif flow['continuation_state'] in {'FADING', 'POSSIBLE_FALSE_BREAK'}:
        entry_type = 'ТОЛЬКО RE-ENTRY' if move['move_type'] != 'FALSE_BREAK' else 'АГРЕССИВНЫЙ ВХОД'
        action_now = 'ЖДАТЬ НОВЫЙ ТРИГГЕР'
        size_mode = 'x0.30'
        comment = 'основной вход уже неидеален; нужен новый триггер или подтверждение'

    if str(liq.get('cascade_risk') or '').upper() == 'HIGH' and entry_type not in {'БЕЗ ВХОДА', 'ЛОВУШКА / RECLAIM ВХОД'}:
        size_mode = 'x0.50' if size_mode == 'x1.00' else size_mode
        comment += '; рядом ликвидационная зона — размер лучше уменьшить'
    if str(deriv.get('squeeze_risk') or '').upper() == 'HIGH' and entry_type == 'БЕЗ ВХОДА':
        action_now = 'ЖДАТЬ ВЫНОС / SQUEEZE'
        comment = 'рядом squeeze-риск: не вставать против движения заранее'

    zone = data.get('entry_zone')
    if not zone:
        price = _f(data.get('price') or 0.0)
        low = _f(data.get('range_low') or 0.0)
        mid = _f(data.get('range_mid') or 0.0)
        high = _f(data.get('range_high') or 0.0)
        side = str(flow.get('side') or projection.get('side') or 'NEUTRAL').upper()
        invalidation_level = _f(flow.get('invalidation_level') or projection.get('invalidation') or 0.0)
        if side == 'LONG' and low and mid and mid > low:
            zone = f"{round(low, 2)}–{round(mid, 2)}"
        elif side == 'SHORT' and mid and high and high > mid:
            zone = f"{round(mid, 2)}–{round(high, 2)}"
        elif price and invalidation_level and abs(price - invalidation_level) / max(price, 1.0) < 0.12:
            zone = f"{round(min(invalidation_level, price), 2)}–{round(max(invalidation_level, price), 2)}"
        else:
            zone = 'нет валидной зоны'
    confirm = data.get('trigger') or soft.get('trigger') or 'удержание локального уровня + продолжение по стороне сценария'
    invalid = flow.get('invalidation_level') or projection.get('invalidation')
    rr = 'не оценен'
    nt = flow.get('nearest_target') or projection.get('target_price')
    price = _f(data.get('price') or 0.0)
    if price and invalid and nt:
        risk = abs(price - _f(invalid))
        reward = abs(_f(nt) - price)
        if risk > 0:
            rr = f"{reward / risk:.2f}"
    return {
        'entry_type': entry_type,
        'entry_zone': zone,
        'confirm_trigger': confirm,
        'invalidation': invalid,
        'chase_risk': 'HIGH' if entry_type == 'ПОЗДНИЙ ВХОД / CHASE' else 'MEDIUM' if move['move_type'] == 'AGGRESSIVE_PUSH' else 'LOW',
        'rr_estimate': rr,
        'comment': comment.strip('; '),
        'size_mode': size_mode,
        'action_now': action_now,
    }



def _clean_text(value: Any, default: str = '') -> str:
    text = str(value or default).strip()
    return text


def build_v17_execution_plan(payload: Dict[str, Any], view: Dict[str, Any] | None = None) -> Dict[str, Any]:
    view = view if isinstance(view, dict) else {}
    ctx = view.get('ctx') if isinstance(view.get('ctx'), dict) else {}
    range_state = str(ctx.get('range_state') or '').upper()
    at_mid = bool(ctx.get('at_mid')) or range_state == 'MID RANGE'
    long_grid = str(view.get('long_grid') or payload.get('long_grid') or 'PAUSE').upper()
    short_grid = str(view.get('short_grid') or payload.get('short_grid') or 'PAUSE').upper()
    conf = float(view.get('scenario_confidence') or payload.get('scenario_confidence') or 0)
    scenario_text = _clean_text(view.get('scenario_text') or payload.get('scenario_text'))
    impulse_text = _clean_text(view.get('impulse_text') or payload.get('impulse_text'))
    invalidation_text = _clean_text(view.get('invalidation_text') or payload.get('invalidation_text'), 'смотреть слом текущего сценария')
    range_low = _f(payload.get('range_low'))
    range_mid = _f(payload.get('range_mid'))
    range_high = _f(payload.get('range_high'))
    regime_title = _clean_text(view.get('authority_title_ru') or view.get('action_now') or payload.get('action_now') or 'ПАУЗА')
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    price = _f(view.get('price') or payload.get('price') or payload.get('current_price'))
    signal_ctx = evaluate_signal_model({**payload, 'long_grid': long_grid, 'short_grid': short_grid, 'scenario_confidence': conf})

    side = 'NEUTRAL'
    side_grid = 'PAUSE'
    if long_grid == 'RUN' and short_grid != 'RUN':
        side = 'LONG'
        side_grid = long_grid
    elif short_grid == 'RUN' and long_grid != 'RUN':
        side = 'SHORT'
        side_grid = short_grid
    elif long_grid == 'REDUCE' and short_grid == 'PAUSE':
        side = 'LONG'
        side_grid = long_grid
    elif short_grid == 'REDUCE' and long_grid == 'PAUSE':
        side = 'SHORT'
        side_grid = short_grid
    else:
        side = str(signal_ctx.get('master_direction') or 'NEUTRAL').upper()

    blocked_by_master = signal_ctx.get('alignment_status') == 'BLOCKED_BY_MASTER'
    blocked_reason = _clean_text(signal_ctx.get('blocked_reason'))
    no_entry_text = 'НЕ ВХОДИТЬ: середина диапазона'
    no_add_text = 'НЕ ДОБИРАТЬ: нет подтверждения'
    hold_residual_text = 'нет активного остатка'
    do_not_hold_text = 'не применяется'
    master_trigger_text = 'ждать удержание рабочей зоны + подтверждение по стороне сценария'

    if at_mid or (long_grid == 'PAUSE' and short_grid == 'PAUSE') or blocked_by_master or side == 'NEUTRAL':
        if blocked_by_master and blocked_reason:
            no_entry_text = f'НЕ ВХОДИТЬ: {blocked_reason}'
        elif at_mid:
            no_entry_text = 'НЕ ВХОДИТЬ ИЗ СЕРЕДИНЫ ДИАПАЗОНА'
        else:
            no_entry_text = 'НЕ ВХОДИТЬ БЕЗ MASTER DECISION'
        return {
            'side': 'NEUTRAL',
            'entry_mode': 'NO_ENTRY',
            'entry_zone_text': no_entry_text.lower().replace('не ', 'вход запрещён: ').capitalize(),
            'entry_trigger_text': 'ждать подход к краю диапазона и подтверждение реакции по master decision',
            'add_allowed': False,
            'add_zone_text': 'добор запрещён',
            'add_trigger_text': 'нет активной стороны',
            'partial_exit_allowed': False,
            'partial_exit_text': 'нет активной позиции',
            'full_exit_text': 'не применяется',
            'hold_text': 'ничего не делать; ждать выход цены к краю диапазона',
            'execution_summary': no_entry_text,
            'execution_reason': regime_title,
            'no_entry_text': no_entry_text,
            'no_add_text': 'НЕ ДОБИРАТЬ: нет активной позиции',
            'hold_residual_text': hold_residual_text,
            'do_not_hold_text': 'НЕ ДЕРЖАТЬ: пока нечего сопровождать',
            'decision_trigger_text': 'что изменит решение: рабочий край + подтверждение без конфликта с master decision',
            'signal_state': signal_ctx.get('signal_state'),
            'edge_state': signal_ctx.get('edge_state'),
            'alignment_status': signal_ctx.get('alignment_status'),
        }

    entry_mode = 'NORMAL'
    if conf < 60 or 'СЛАБ' in scenario_text.upper() or signal_ctx.get('signal_state') == 'WATCH':
        entry_mode = 'PROBE'
    elif conf >= 70 and side_grid == 'RUN' and 'ПАУЗА' not in scenario_text.upper() and signal_ctx.get('signal_state') in {'ARMED', 'ACTIONABLE', 'MANAGE'}:
        entry_mode = 'CONFIRMED'

    chase_risk = 'HIGH' if price and ((side == 'LONG' and range_mid and price > range_mid) or (side == 'SHORT' and range_mid and price < range_mid)) else 'LOW'
    fading = 'ЗАТУХ' in impulse_text.upper() or 'СЛАБ' in impulse_text.upper()

    if side == 'LONG':
        entry_zone = f'нижний блок {range_low:,.2f}–{range_mid:,.2f}'.replace(',', ' ') if range_low and range_mid else 'нижний блок диапазона'
        entry_trigger = 'касание нижнего блока + ложный вынос вниз + быстрый возврат обратно в диапазон'
        add_zone = entry_zone
        add_trigger = 'повторный тест нижнего блока без продолжения вниз; добирать только после нового подтверждения'
        partial_text = f'частично крыть у середины диапазона {range_mid:,.2f}'.replace(',', ' ') if range_mid else 'частично крыть у середины диапазона'
        full_exit = invalidation_text
        hold_text = 'держать остаток, пока лонг-сетка рабочая и сценарий не сломан'
        hold_residual_text = 'ДЕРЖАТЬ ОСТАТОК: структура жива и master decision всё ещё за лонг'
        do_not_hold_text = 'НЕ ДЕРЖАТЬ: если возврат вниз ломает сценарий или рынок вернулся в шум'
        summary = 'лонг-режим: работать только от нижнего края диапазона'
        no_entry_text = 'НЕ ВХОДИТЬ В ДОГОНКУ ВЫШЕ СЕРЕДИНЫ ДИАПАЗОНА' if chase_risk == 'HIGH' else 'НЕ ВХОДИТЬ БЕЗ RECLAIM ОТ НИЖНЕГО КРАЯ'
        no_add_text = 'НЕ ДОБИРАТЬ ПОСЛЕ УХОДА ИЗ НИЖНЕЙ ЗОНЫ'
        master_trigger_text = 'что изменит решение: возврат от нижнего блока и удержание сценария вверх'
    else:
        entry_zone = f'верхний блок {range_mid:,.2f}–{range_high:,.2f}'.replace(',', ' ') if range_mid and range_high else 'верхний блок диапазона'
        entry_trigger = 'касание верхнего блока + ложный вынос вверх + быстрый возврат обратно в диапазон'
        add_zone = entry_zone
        add_trigger = 'повторный тест верхнего блока без продолжения вверх; добирать только после нового подтверждения'
        partial_text = f'частично крыть у середины диапазона {range_mid:,.2f}'.replace(',', ' ') if range_mid else 'частично крыть у середины диапазона'
        full_exit = invalidation_text
        hold_text = 'держать остаток, пока шорт-сетка рабочая и сценарий не сломан'
        hold_residual_text = 'ДЕРЖАТЬ ОСТАТОК: структура жива и master decision всё ещё за шорт'
        do_not_hold_text = 'НЕ ДЕРЖАТЬ: если возврат вверх ломает сценарий или рынок вернулся в шум'
        summary = 'шорт-режим: работать только от верхнего края диапазона'
        no_entry_text = 'НЕ ВХОДИТЬ В ДОГОНКУ НИЖЕ СЕРЕДИНЫ ДИАПАЗОНА' if chase_risk == 'HIGH' else 'НЕ ВХОДИТЬ БЕЗ REJECT/RECLAIM ОТ ВЕРХНЕГО КРАЯ'
        no_add_text = 'НЕ ДОБИРАТЬ ПОСЛЕ УХОДА ИЗ ВЕРХНЕЙ ЗОНЫ'
        master_trigger_text = 'что изменит решение: реакция от верхнего блока и удержание сценария вниз'

    add_allowed = entry_mode != 'NO_ENTRY' and conf >= 58 and 'ПАУЗА' not in impulse_text.upper() and signal_ctx.get('edge_state') in {'ARM EDGE', 'ACTION READY', 'MANAGE ONLY'}
    if fading or chase_risk == 'HIGH' or signal_ctx.get('alignment_status') == 'BLOCKED_BY_MASTER':
        add_allowed = False
    if long_grid == 'REDUCE' or short_grid == 'REDUCE':
        add_allowed = False
        no_add_text = 'НЕ ДОБИРАТЬ: режим уже в сокращении риска'
    elif fading:
        no_add_text = 'НЕ ДОБИРАТЬ В ЗАТУХАЮЩИЙ ИМПУЛЬС'
    elif chase_risk == 'HIGH':
        no_add_text = 'НЕ ДОБИРАТЬ В УХУДШЕНИЕ СРЕДНЕЙ'

    return {
        'side': side,
        'entry_mode': entry_mode,
        'entry_zone_text': entry_zone,
        'entry_trigger_text': entry_trigger,
        'add_allowed': bool(add_allowed),
        'add_zone_text': add_zone if add_allowed else 'добор запрещён до подтверждения удержания зоны',
        'add_trigger_text': add_trigger if add_allowed else no_add_text,
        'partial_exit_allowed': side != 'NEUTRAL',
        'partial_exit_text': partial_text,
        'full_exit_text': full_exit,
        'hold_text': hold_text,
        'execution_summary': summary,
        'execution_reason': regime_title,
        'no_entry_text': no_entry_text,
        'no_add_text': no_add_text,
        'hold_residual_text': hold_residual_text,
        'do_not_hold_text': do_not_hold_text,
        'decision_trigger_text': master_trigger_text,
        'signal_state': signal_ctx.get('signal_state'),
        'edge_state': signal_ctx.get('edge_state'),
        'alignment_status': signal_ctx.get('alignment_status'),
    }
