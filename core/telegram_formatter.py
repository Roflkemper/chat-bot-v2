from __future__ import annotations
from typing import Dict, Any, List

from core.grid_regime_manager_v1689 import derive_v1689_context
from core.execution_advisor import build_v17_execution_plan
from core.context_consensus_filter import evaluate_context_consensus
from core.external_market_bias_flow import evaluate_external_market_bias, evaluate_flow_pressure


def _fmt_price(value: float | int | None) -> str:
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except Exception:
        return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _direction_ru(value: str) -> str:
    return {"LONG": "ЛОНГ", "SHORT": "ШОРТ", "NEUTRAL": "НЕЙТРАЛЬНО"}.get(str(value).upper(), str(value))


def _runtime_icon(state: str) -> str:
    return {
        'RUN': '🟢',
        'REDUCE': '🟡',
        'PAUSE': '⏸',
        'EXIT': '🔴',
        'ARM': '🔵',
    }.get(str(state or '').upper(), '•')


def _runtime_ru(state: str) -> str:
    return {
        'RUN': 'держать рабочим',
        'REDUCE': 'сокращать / не добавлять',
        'PAUSE': 'пауза / не включать',
        'EXIT': 'выход / закрыть',
        'ARM': 'готовить только у края',
    }.get(str(state or '').upper(), str(state or ''))


def _runtime_state_ru(state: str) -> str:
    return {
        'RUN': 'РАБОТАТЬ',
        'REDUCE': 'СОКРАТИТЬ',
        'PAUSE': 'ПАУЗА',
        'EXIT': 'ВЫХОД',
        'ARM': 'ГОТОВИТЬ',
    }.get(str(state or '').upper(), str(state or ''))




def _entry_mode_ru(value: str) -> str:
    return {
        'NO_ENTRY': 'ВХОД ЗАПРЕЩЁН',
        'PROBE': 'ПРОБНЫЙ ВХОД',
        'NORMAL': 'ОБЫЧНЫЙ ВХОД',
        'CONFIRMED': 'ПОДТВЕРЖДЁННЫЙ ВХОД',
    }.get(str(value or '').upper(), str(value or ''))


def _consensus_bias_ru(value: str) -> str:
    return {
        'STRONG_BULL': 'СИЛЬНО БЫЧИЙ',
        'BULL': 'БЫЧИЙ',
        'NEUTRAL': 'НЕЙТРАЛЬНЫЙ',
        'BEAR': 'МЕДВЕЖИЙ',
        'STRONG_BEAR': 'СИЛЬНО МЕДВЕЖИЙ',
    }.get(str(value or '').upper(), str(value or ''))


def _consensus_state_ru(value: str) -> str:
    return {
        'CONSENSUS_SUPPORTS_LONG': 'поддержка лонга',
        'CONSENSUS_SUPPORTS_SHORT': 'поддержка шорта',
        'CONSENSUS_NEUTRAL': 'нейтрально',
        'CONSENSUS_BLOCKS_LONG': 'блок лонга',
        'CONSENSUS_BLOCKS_SHORT': 'блок шорта',
        'CONSENSUS_RISK_OFF': 'risk-off для сетки',
        'CONSENSUS_CONFLICTED': 'конфликтный контекст',
    }.get(str(value or '').upper(), str(value or ''))


def _consensus_line_ru(consensus: Dict[str, Any]) -> list[str]:
    c = consensus if isinstance(consensus, dict) else {}
    htf = str(c.get('htf_state') or '')
    htf_ru = 'выше EMA200 / RSI > 50' if htf == 'BULLISH_HTF' else 'ниже EMA200 / RSI < 50' if htf == 'BEARISH_HTF' else 'смешанный HTF'
    trend = str(c.get('trend_pressure') or '')
    trend_ru = 'трендовый риск для сетки' if trend == 'RISK_OFF_GRID' else 'направленное давление' if trend.startswith('TRENDING') else 'grid-friendly / без сильного тренда'
    leader = str(c.get('leader_pressure') or '')
    leader_ru = {
        'BTC_DOWN_HARD': 'BTC резко давит вниз',
        'BTC_DOWN': 'BTC давит вниз',
        'BTC_UP_HARD': 'BTC резко тащит вверх',
        'BTC_UP': 'BTC поддерживает рост',
        'BTC_NEUTRAL': 'BTC нейтрален',
    }.get(leader, leader or 'BTC нейтрален')
    sentiment = str(c.get('sentiment_label') or '')
    sentiment_ru = {
        'LONG_CRODED': 'лонги перегреты',
        'SHORT_CROWDED': 'шорты перегреты',
        'TOP_TRADERS_LEAN_SHORT': 'топ-трейдеры склоняются к шорту',
        'TOP_TRADERS_LEAN_LONG': 'топ-трейдеры склоняются к лонгу',
        'NEUTRAL_SENTIMENT': 'сентимент нейтрален',
    }.get(sentiment, 'сентимент нейтрален')
    permission = str(c.get('permission_text') or 'обе стороны без блокировки')
    bias_score = c.get('bias_score')
    funding_regime = str(c.get('funding_regime') or 'NORMAL')
    funding_ru = {'HIGH_POSITIVE': 'фандинг высокий / лонги перегреты', 'NEGATIVE': 'фандинг отрицательный / риск шорт-сквиза', 'NORMAL': 'фандинг нормальный'}.get(funding_regime, 'фандинг нормальный')
    flow_hint = c.get('absorption_score')
    flow_text = 'без явного поглощения'
    try:
        fv = float(flow_hint)
        if fv >= 0.20:
            flow_text = 'покупки поглощаются сверху'
        elif fv <= -0.20:
            flow_text = 'продажи поглощаются снизу'
    except Exception:
        pass
    return [
        '',
        '🌐 КОНТЕКСТ РЫНКА',
        '',
        f"• bias: {_consensus_bias_ru(c.get('overall_bias'))}",
        f"• HTF: {htf_ru}",
        f"• trend pressure: {trend_ru}",
        f"• BTC поводырь: {leader_ru}",
        f"• sentiment: {sentiment_ru}",
        f"• bias score: {bias_score}",
        f"• funding: {funding_ru}",
        f"• flow: {flow_text}",
        f"• итог: {permission}",
    ]


def _execution_block_lines(payload: Dict[str, Any], view: Dict[str, Any]) -> List[str]:
    plan = build_v17_execution_plan(payload, view)
    consensus = evaluate_context_consensus(payload, view)
    lines = ['', '🎯 УПРАВЛЕНИЕ СДЕЛКОЙ', '']
    side_ru = {'LONG': 'ЛОНГ', 'SHORT': 'ШОРТ', 'NEUTRAL': 'НЕТ АКТИВНОЙ СТОРОНЫ'}.get(str(plan.get('side') or '').upper(), str(plan.get('side') or 'НЕТ'))
    lines.append(f"• сторона: {side_ru}")
    lines.append(f"• сигнал / режим: {plan.get('signal_state', 'нет данных')} / {plan.get('edge_state', 'нет данных')}")
    lines.append(f"• тип входа: {_entry_mode_ru(plan.get('entry_mode'))}")
    lines.append(f"• вход: {plan.get('entry_zone_text')}")
    lines.append(f"• триггер: {plan.get('entry_trigger_text')}")
    lines.append(f"• не входить: {plan.get('no_entry_text', 'нет данных')}")
    lines.append(f"• добор: {plan.get('add_zone_text')}")
    lines.append(f"• не добирать: {plan.get('no_add_text', 'нет данных')}")
    lines.append(f"• частично крыть: {plan.get('partial_exit_text')}")
    lines.append(f"• держать остаток: {plan.get('hold_residual_text', plan.get('hold_text'))}")
    lines.append(f"• не держать: {plan.get('do_not_hold_text', 'нет данных')}")
    lines.append(f"• полный выход: {plan.get('full_exit_text')}")
    lines.append(f"• что изменит решение: {plan.get('decision_trigger_text', 'нет данных')}")
    lines.append(f"• защита / hedge: {plan.get('hedge_action_text', 'нет данных')}")
    lines.append(f"• consensus: {_consensus_state_ru(plan.get('consensus_state'))} / {_consensus_bias_ru(plan.get('consensus_bias'))}")
    lines.append(f"• итог: {plan.get('execution_summary')}")
    return lines






def _external_bias_ru(value: str) -> str:
    return {
        'RISK_OFF': 'RISK-OFF',
        'RISK_ON': 'RISK-ON',
        'BEARISH_SUPPORT': 'внешний медвежий фон',
        'BULLISH_SUPPORT': 'внешний бычий фон',
        'NEUTRAL_EXTERN': 'нейтральный внешний фон',
        'CONFLICTED_EXTERN': 'внешний фон конфликтный',
    }.get(str(value or '').upper(), str(value or ''))


def _flow_pressure_ru(value: str) -> str:
    return {
        'BUY_PRESSURE': 'давление вверх',
        'SELL_PRESSURE': 'давление вниз',
        'ABSORBED_BUYING': 'покупки поглощаются сверху',
        'ABSORBED_SELLING': 'продажи поглощаются снизу',
        'BALANCED_FLOW': 'поток сбалансирован',
        'FAKE_EXPANSION': 'риск ловушки / fake expansion',
        'PRESSURE_BUILDING': 'скрытое давление копится',
        'FLOW_EXHAUSTION': 'давление выдыхается',
    }.get(str(value or '').upper(), str(value or ''))


def _pre_hedge_block_lines(payload: Dict[str, Any], view: Dict[str, Any]) -> List[str]:
    plan = build_v17_execution_plan(payload, view)
    return [
        '',
        '⚠️ PRE-HEDGE WARNING',
        '',
        f"• статус: {plan.get('pre_hedge_status', 'нет данных')}",
        f"• причина: {plan.get('pre_hedge_reason', 'нет данных')}",
        f"• действие: {plan.get('pre_hedge_action', 'нет данных')}",
        f"• hedge trigger: {_fmt_price(plan.get('hedge_trigger_price')) if plan.get('hedge_trigger_price') else 'нет данных'}",
    ]


def _extern_block_lines(payload: Dict[str, Any], view: Dict[str, Any]) -> List[str]:
    plan = build_v17_execution_plan(payload, view)
    return [
        '',
        '🌍 MARKET BIAS (EXTERN)',
        '',
        f"• внешний фон: {_external_bias_ru(plan.get('external_bias_state'))}",
        f"• главный драйвер: {plan.get('external_bias_driver', 'нет данных')}",
        f"• long: {plan.get('external_bias_long_text', 'нет данных')}",
        f"• short: {plan.get('external_bias_short_text', 'нет данных')}",
    ]


def _flow_block_lines(payload: Dict[str, Any], view: Dict[str, Any]) -> List[str]:
    plan = build_v17_execution_plan(payload, view)
    return [
        '',
        '🌊 FLOW / LIQUIDITY PRESSURE',
        '',
        f"• поток: {_flow_pressure_ru(plan.get('flow_pressure_state'))}",
        f"• смысл: {plan.get('flow_pressure_summary', 'нет данных')}",
        f"• влияние на добор: {plan.get('flow_add_risk_modifier', 'NORMAL')}",
    ]

def _lifecycle_phase_ru(value: str) -> str:
    return {
        'IDLE': 'НЕ ГОТОВА',
        'PREPARE': 'ПОДГОТОВКА',
        'ARM': 'БОЕВАЯ ГОТОВНОСТЬ',
        'ACTIVE': 'АКТИВНА',
        'HOLD_ACTIVE': 'УДЕРЖАНИЕ БЕЗ РАСШИРЕНИЯ',
        'DEFEND': 'ЗАЩИТА',
        'REDUCE': 'РАЗГРУЗКА',
        'EXIT': 'ВЫХОД',
        'REARM_WAIT': 'ПАУЗА ПЕРЕЗАПУСКА',
        'REARM_READY': 'ПОВТОРНЫЙ ЗАПУСК РАЗРЕШЁН',
    }.get(str(value or '').upper(), str(value or ''))


def _lifecycle_block_lines(payload: Dict[str, Any], view: Dict[str, Any]) -> List[str]:
    plan = build_v17_execution_plan(payload, view)
    return [
        '',
        '🔄 ЖИЗНЕННЫЙ ЦИКЛ СЕТКИ',
        '',
        f"• фаза: {_lifecycle_phase_ru(plan.get('lifecycle_phase'))}",
        f"• authority: {plan.get('lifecycle_authority', 'нет данных')}",
        f"• смысл: {plan.get('lifecycle_meaning_text', 'нет данных')}",
        f"• что делать сейчас: {plan.get('lifecycle_action_text', 'нет данных')}",
        f"• что запрещено: {plan.get('lifecycle_forbidden_text', 'нет данных')}",
        f"• что переведёт дальше: {plan.get('lifecycle_next_text', 'нет данных')}",
        f"• что сломает фазу: {plan.get('lifecycle_break_text', 'нет данных')}",
    ]

def _hedge_mode_ru(value: str) -> str:
    return {
        'OFF': 'ВЫКЛ',
        'WATCH': 'НАБЛЮДЕНИЕ',
        'ARM': 'ГОТОВИТЬ',
        'READY': 'ГОТОВ',
        'ACTIVE_ADVISORY': 'АКТИВНАЯ ЗАЩИТА',
        'REDUCE': 'СНИЖАТЬ',
        'EXIT': 'СНИМАТЬ',
    }.get(str(value or '').upper(), str(value or ''))


def _hedge_type_ru(value: str) -> str:
    return {
        'NONE': 'нет',
        'LOCK': 'lock hedge',
        'PARTIAL_DEFENSE': 'частичная защита',
        'TRAILING_DEFENSE': 'trailing defense',
        'CROSS_HEDGE_ADVISORY': 'cross-hedge advisory',
    }.get(str(value or '').upper(), str(value or ''))


def _hedge_block_lines(payload: Dict[str, Any], view: Dict[str, Any]) -> List[str]:
    plan = build_v17_execution_plan(payload, view)
    return [
        '',
        '🛡 ХЕДЖ / ЗАЩИТА',
        '',
        f"• режим защиты: {_hedge_mode_ru(plan.get('hedge_mode'))}",
        f"• состояние: {plan.get('hedge_state', 'нет данных')}",
        f"• тип защиты: {_hedge_type_ru(plan.get('hedge_type'))}",
        f"• effective delta: {plan.get('effective_delta', 'нет данных')}",
        f"• нагрузка сетки: {plan.get('grid_stress', 'нет данных')}",
        f"• причина: {plan.get('hedge_reason', 'нет данных')}",
        f"• что делать сейчас: {plan.get('hedge_action_text', 'нет данных')}",
        f"• что запрещено: {plan.get('hedge_forbidden_text', 'нет данных')}",
        f"• что усилит защиту: {plan.get('hedge_escalation_text', 'нет данных')}",
        f"• что снимет защиту: {plan.get('hedge_release_text', 'нет данных')}",
    ]

def _authority_ru(value: str) -> str:
    mapping = {
        'ARM ONLY AT EDGE': 'готовить только у края',
        'PAUSE MID RANGE': 'середина диапазона — пауза по обеим сеткам',
        'PAUSE / WAIT RECLAIM': 'снизить активность и ждать возврат в диапазон',
        'ARM SHORT EDGE': 'верхний край — short-grid главнее',
        'ARM LONG EDGE': 'нижний край — long-grid главнее',
        'EXIT / PAUSE BREAK UP': 'пробой вверх — short-grid выключать',
        'EXIT / PAUSE BREAK DOWN': 'пробой вниз — long-grid выключать',
    }
    key = str(value or '').upper()
    return mapping.get(key, str(value or ''))


def _authority_title_ru(value: str) -> str:
    mapping = {
        'ARM ONLY AT EDGE': 'ГОТОВИТЬ ТОЛЬКО У КРАЯ',
        'PAUSE MID RANGE': 'ПАУЗА В СЕРЕДИНЕ ДИАПАЗОНА',
        'PAUSE / WAIT RECLAIM': 'ПАУЗА И ЖДАТЬ ВОЗВРАТ В ДИАПАЗОН',
        'ARM SHORT EDGE': 'ГОТОВИТЬ ШОРТ У ВЕРХНЕГО КРАЯ',
        'ARM LONG EDGE': 'ГОТОВИТЬ ЛОНГ У НИЖНЕГО КРАЯ',
        'EXIT / PAUSE BREAK UP': 'ПРОБОЙ ВВЕРХ — СЛАБУЮ СТОРОНУ ОТКЛЮЧИТЬ',
        'EXIT / PAUSE BREAK DOWN': 'ПРОБОЙ ВНИЗ — СЛАБУЮ СТОРОНУ ОТКЛЮЧИТЬ',
    }
    return mapping.get(str(value or '').upper(), str(value or ''))


def _manager_action_ru(value: str) -> str:
    mapping = {
        'ARM_EDGE': 'ГОТОВИТЬ У КРАЯ',
        'PAUSE_MID': 'ПАУЗА В СЕРЕДИНЕ',
        'WAIT_RECLAIM': 'ЖДАТЬ ВОЗВРАТ В ДИАПАЗОН',
        'ARM_SHORT_EDGE': 'ГОТОВИТЬ ШОРТ У КРАЯ',
        'ARM_LONG_EDGE': 'ГОТОВИТЬ ЛОНГ У КРАЯ',
        'BREAK_UP': 'ПРОБОЙ ВВЕРХ',
        'BREAK_DOWN': 'ПРОБОЙ ВНИЗ',
    }
    return mapping.get(str(value or '').upper(), str(value or ''))





def _range_quality_ru(label: str) -> str:
    key = str(label or '').upper()
    mapping = {
        'RANGE HEALTHY': 'ЖИВОЙ ДИАПАЗОН',
        'RANGE NOISY': 'ШУМНЫЙ ДИАПАЗОН',
        'RANGE BREAK RISK': 'РИСК СЛОМА ДИАПАЗОНА',
    }
    return mapping.get(key, str(label or ''))


def _divergence_ru(state: str, strength: str) -> str:
    state_key = str(state or '').upper()
    strength_key = str(strength or '').upper()
    state_ru = {
        'BEARISH': 'медвежья дивергенция',
        'BULLISH': 'бычья дивергенция',
        'BEARISH_HINT': 'медвежий намёк',
        'BULLISH_HINT': 'бычий намёк',
        'NONE': 'нет дивергенции',
    }.get(state_key, str(state or ''))
    strength_ru = {
        'LOW': 'слабая',
        'MEDIUM': 'умеренная',
        'SOFT': 'мягкий сигнал',
        'HIGH': 'сильная',
    }.get(strength_key, str(strength or ''))
    if state_key == 'NONE':
        return state_ru
    return f'{state_ru} | {strength_ru}'


def _scenario_confidence(action_now: str, range_quality: str, scenario_text: str, impulse_text: str, long_grid: str, short_grid: str) -> tuple[int, str]:
    score = 50
    scenario_u = str(scenario_text or '').upper()
    rq = str(range_quality or '').upper()
    impulse_u = str(impulse_text or '').upper()
    action_u = str(action_now or '').upper()
    lg = str(long_grid or '').upper()
    sg = str(short_grid or '').upper()

    if 'INVALID' in scenario_u:
        score = 8
    elif 'FAILING' in scenario_u:
        score = 22
    elif 'WAIT' in scenario_u:
        score = 28
    elif 'WEAK' in scenario_u:
        score = 43
    elif 'ACTIVE' in scenario_u:
        score = 62

    if rq == 'RANGE HEALTHY':
        score += 8
    elif rq == 'RANGE NOISY':
        score -= 4
    elif rq == 'RANGE BREAK RISK':
        score -= 14

    if 'ПОДТВЕРЖДАЕТСЯ' in impulse_u or 'ИМПУЛЬС ЖИВ' in impulse_u:
        score += 10
    if 'ЗАТУХАЕТ' in impulse_u or 'РИСК ОТКАТА' in impulse_u or 'ФЕЙК' in impulse_u:
        score -= 6

    if action_u.startswith('ARM ') or action_u == 'ARM ONLY AT EDGE':
        score += 4
    if action_u.startswith('EXIT') or action_u.startswith('PAUSE / WAIT'):
        score -= 8

    if (lg == 'RUN') ^ (sg == 'RUN'):
        score += 4

    score = max(5, min(95, int(round(score))))
    if score >= 70:
        label = 'высокая'
    elif score >= 55:
        label = 'рабочая'
    elif score >= 40:
        label = 'умеренная'
    else:
        label = 'низкая'
    return score, label


def _auto_risk_mode(confidence: int, scenario_text: str, action_now: str) -> str:
    scenario_u = str(scenario_text or '').upper()
    action_u = str(action_now or '').upper()
    if 'INVALID' in scenario_u or action_u.startswith('EXIT'):
        return '🔴 СТОП — риск высокий, активную сетку выключать'
    if 'FAILING' in scenario_u or action_u == 'PAUSE / WAIT RECLAIM':
        return '⏸ ЗАЩИТА — только защита, без добора'
    if 'WAIT' in scenario_u or action_u == 'PAUSE MID RANGE':
        return '⏸ ПАУЗА — середина диапазона, без активации'
    if confidence >= 70:
        return '🟢 НОРМАЛЬНЫЙ+ — сценарий крепкий, можно держать базовый риск'
    if confidence >= 55:
        return '🟢 НОРМАЛЬНЫЙ — рабочий риск без форсирования'
    if confidence >= 40:
        return '🟡 ЛЁГКИЙ — уменьшенный риск, аккуратное ведение'
    return '🟠 МИКРО — только минимальный риск и точечная работа'


def _market_target_text(action_now: str, range_state: str, range_low: Any, range_mid: Any, range_high: Any, long_grid: str = '', short_grid: str = '') -> str:
    authority = str(action_now or '').upper()
    rs = str(range_state or '').upper()
    lg = str(long_grid or '').upper()
    sg = str(short_grid or '').upper()
    if authority == 'PAUSE MID RANGE':
        return '🎯 цель: ждать выход цены к краю диапазона; из середины не активировать'
    if authority == 'PAUSE / WAIT RECLAIM':
        return '🎯 цель: дождаться возврата в диапазон и только потом возвращать активность'
    if authority == 'EXIT / PAUSE BREAK UP':
        return f"🎯 цель: удержание выше {_fmt_price(range_high)}; шорт-сетка выключена до нового возврата в диапазон"
    if authority == 'EXIT / PAUSE BREAK DOWN':
        return f"🎯 цель: удержание ниже {_fmt_price(range_low)}; лонг-сетка выключена до нового возврата в диапазон"
    if sg == 'RUN' and lg == 'REDUCE':
        return f"🎯 цель: возврат к середине диапазона {_fmt_price(range_mid)}; при усилении — тест нижней половины"
    if lg == 'RUN' and sg == 'REDUCE':
        return f"🎯 цель: возврат к середине диапазона {_fmt_price(range_mid)}; при усилении — тест верхней половины"
    if rs == 'UPPER RANGE':
        return f"🎯 цель: ротация вниз к середине диапазона {_fmt_price(range_mid)}"
    if rs == 'LOWER RANGE':
        return f"🎯 цель: ротация вверх к середине диапазона {_fmt_price(range_mid)}"
    return '🎯 цель: диапазонная ротация от края к краю без погони за серединой'


def _impulse_state_text(payload: Dict[str, Any], range_state: str, long_grid: str, short_grid: str) -> str:
    payload = _safe_dict(payload)
    decision = _safe_dict(payload.get('decision'))
    reaction = _safe_dict(payload.get('liquidation_reaction') or payload.get('reaction_to_blocks'))
    fake = _safe_dict(payload.get('fake_move_v14') or payload.get('fake_move') or payload.get('fake_context'))
    acceptance = str(reaction.get('acceptance') or fake.get('acceptance') or '').upper()
    fake_state = str(fake.get('state') or fake.get('fake_move_state') or '').upper()
    impulse_state = str(payload.get('impulse_state') or decision.get('impulse_state') or _safe_dict(payload.get('impulse')).get('state') or '').upper()

    if fake_state in {'FAKE_UP', 'TRAP_UP'}:
        return '⚠️ импульс вверх слабый / возможен фейк; приоритет — шорт-ротация'
    if fake_state in {'FAKE_DOWN', 'TRAP_DOWN'}:
        return '⚠️ импульс вниз слабый / возможен фейк; приоритет — лонг-ротация'
    if acceptance == 'ACCEPTED_ABOVE':
        return '🔥 движение вверх подтверждается; сценарий диапазона ломается'
    if acceptance == 'ACCEPTED_BELOW':
        return '🔥 движение вниз подтверждается; сценарий диапазона ломается'
    if impulse_state in {'IMPULSE_CONTINUES', 'BULLISH_ACTIVE', 'BEARISH_ACTIVE'}:
        side = 'вверх' if long_grid == 'RUN' and short_grid != 'RUN' else 'вниз' if short_grid == 'RUN' and long_grid != 'RUN' else 'по текущей стороне'
        return f'🔥 импульс жив; движение {side} ещё не погасло'
    if impulse_state in {'BULLISH_BUILDING', 'BEARISH_BUILDING', 'PENDING_CONFIRMATION', 'IMPULSE_UNCERTAIN', 'CONFLICTED'}:
        return '🟠 импульс есть, но подтверждение слабое; форсировать нельзя'
    if impulse_state in {'IMPULSE_EXHAUSTING', 'FADING'}:
        return '⚠️ импульс затухает; высок шанс возврата внутрь диапазона'
    if range_state == 'UPPER RANGE' and short_grid == 'RUN':
        return '⚠️ рост без уверенного подтверждения; риск отката вниз повышен'
    if range_state == 'LOWER RANGE' and long_grid == 'RUN':
        return '⚠️ пролив без уверенного подтверждения; риск отскока вверх повышен'
    return '↔️ импульс слабый; рынок остаётся в режиме диапазонной ротации'




def _scenario_state_text(payload: Dict[str, Any], action_now: str, range_state: str, long_grid: str, short_grid: str, range_quality: str) -> str:
    payload = _safe_dict(payload)
    reaction = _safe_dict(payload.get('liquidation_reaction') or payload.get('reaction_to_blocks'))
    fake = _safe_dict(payload.get('fake_move_v14') or payload.get('fake_move') or payload.get('fake_context'))
    acceptance = str(reaction.get('acceptance') or fake.get('acceptance') or '').upper()
    fake_state = str(fake.get('state') or fake.get('fake_move_state') or '').upper()
    authority = str(action_now or '').upper()
    rq = str(range_quality or '').upper()

    if acceptance in {'ACCEPTED_ABOVE', 'ACCEPTED_BELOW'}:
        return '🚫 СЛОМ — диапазонный сценарий уже ломается подтверждённым выходом'
    if authority in {'EXIT / PAUSE BREAK UP', 'EXIT / PAUSE BREAK DOWN'}:
        return '🚫 СЛОМ — слабая сторона выключается до нового возврата в диапазон'
    if authority == 'PAUSE / WAIT RECLAIM' or rq == 'RANGE BREAK RISK':
        return '⚠️ СЛАБЕЕТ — диапазон под риском, сначала возврат в диапазон и защита'
    if fake_state in {'FAKE_UP', 'TRAP_UP', 'FAKE_DOWN', 'TRAP_DOWN'}:
        return '🟠 АКТИВЕН — есть ловушка у края, но нужен аккуратный добор'
    if short_grid == 'RUN' and long_grid == 'REDUCE' and str(range_state).upper() == 'UPPER RANGE':
        return '🟠 СЛАБЫЙ — продавец есть, но без жёсткого импульсного подтверждения'
    if long_grid == 'RUN' and short_grid == 'REDUCE' and str(range_state).upper() == 'LOWER RANGE':
        return '🟠 СЛАБЫЙ — покупатель есть, но без жёсткого импульсного подтверждения'
    if authority == 'PAUSE MID RANGE':
        return '⏸ ПАУЗА — середина диапазона, активную сторону не форсировать'
    if short_grid == 'RUN' or long_grid == 'RUN':
        return '🟢 АКТИВЕН — рабочая сторона есть, диапазон пока удерживается'
    return '↔️ ПАУЗА — рынок остаётся внутри диапазона без явной ведущей стороны'


def _hard_invalidation_text(payload: Dict[str, Any], action_now: str, long_grid: str, short_grid: str) -> str:
    payload = _safe_dict(payload)
    reaction = _safe_dict(payload.get('liquidation_reaction') or payload.get('reaction_to_blocks'))
    fake = _safe_dict(payload.get('fake_move_v14') or payload.get('fake_move') or payload.get('fake_context'))
    acceptance = str(reaction.get('acceptance') or fake.get('acceptance') or '').upper()
    low = payload.get('range_low')
    mid = payload.get('range_mid')
    high = payload.get('range_high')
    authority = str(action_now or '').upper()

    if acceptance == 'ACCEPTED_ABOVE':
        return f'🚫 удержание выше {_fmt_price(high)} — шорт-сетку выключить / пауза до нового возврата в диапазон'
    if acceptance == 'ACCEPTED_BELOW':
        return f'🚫 удержание ниже {_fmt_price(low)} — лонг-сетку выключить / пауза до нового возврата в диапазон'
    if authority == 'EXIT / PAUSE BREAK UP':
        return f'🚫 закрепление выше {_fmt_price(high)} — шорт-сетку выключить, лонг-сетке не мешать'
    if authority == 'EXIT / PAUSE BREAK DOWN':
        return f'🚫 закрепление ниже {_fmt_price(low)} — лонг-сетку выключить, шорт-сетке не мешать'
    if short_grid == 'RUN' and long_grid == 'REDUCE':
        return f'🚫 закрепление выше {_fmt_price(high)} — шорт-сетку сократить / выйти и ждать возврата в диапазон'
    if long_grid == 'RUN' and short_grid == 'REDUCE':
        return f'🚫 закрепление ниже {_fmt_price(low)} — лонг-сетку сократить / выйти и ждать возврата в диапазон'
    return f'🚫 подтверждённый выход за {_fmt_price(low)}–{_fmt_price(high)} отключает диапазонный режим'

def _forecast_text(pattern_bias: str, action_now: str, range_state: str, range_quality: str, long_grid: str = '', short_grid: str = '') -> str:
    side = str(pattern_bias or 'NEUTRAL').upper()
    authority = str(action_now or '').upper()
    range_state_u = str(range_state or '').upper()
    rq = str(range_quality or '').upper()
    lg = str(long_grid or '').upper()
    sg = str(short_grid or '').upper()
    if authority == 'PAUSE MID RANGE':
        return '⏸ БАЗА: рынок внутри диапазона; форсировать сетки нельзя до подхода к краю'
    if authority == 'PAUSE / WAIT RECLAIM':
        return '⚠️ БАЗА: диапазон под риском; сначала возврат в диапазон, потом продолжение работы'
    if authority == 'EXIT / PAUSE BREAK UP':
        return '📈 БАЗА: пробой вверх; шорт-сетка слабее, рынок смещается выше'
    if authority == 'EXIT / PAUSE BREAK DOWN':
        return '📉 БАЗА: пробой вниз; лонг-сетка слабее, рынок смещается ниже'
    if sg == 'RUN' and lg == 'REDUCE':
        return '📉 БАЗА: рынок тяготеет вниз; шорт-сетка ведущая, лонг-сетку сдерживать'
    if lg == 'RUN' and sg == 'REDUCE':
        return '📈 БАЗА: рынок тяготеет вверх; лонг-сетка ведущая, шорт-сетку сдерживать'
    if side == 'SHORT' and range_state_u == 'UPPER RANGE':
        return '📉 БАЗА: рынок тянет к шорту от верхней части диапазона'
    if side == 'LONG' and range_state_u == 'LOWER RANGE':
        return '📈 БАЗА: рынок тянет к лонгу от нижней части диапазона'
    if rq == 'RANGE BREAK RISK':
        return '⚠️ БАЗА: диапазон ломкий; приоритет — защита, а не добор'
    return '↔️ БАЗА: рынок остаётся в диапазоне; работа только от края'


def _runtime_line(long_grid: str, short_grid: str) -> str:
    return f"{_runtime_icon(long_grid)} лонг {_runtime_state_ru(long_grid)} | {_runtime_icon(short_grid)} шорт {_runtime_state_ru(short_grid)}"


def _coerce_master_authority(payload: Dict[str, Any]) -> Dict[str, Any]:
    value = payload.get('master_runtime_authority')
    return value if isinstance(value, dict) else {}


def _derive_range_state(payload: Dict[str, Any], decision: Dict[str, Any]) -> tuple[str, bool]:
    explicit = str(
        decision.get('range_position')
        or decision.get('range_position_zone')
        or decision.get('range_position_label')
        or payload.get('range_position')
        or payload.get('range_position_zone')
        or payload.get('range_position_label')
        or ''
    ).upper()
    if explicit in {'MID', 'MID_RANGE', 'CENTER', 'MIDDLE'}:
        return 'MID RANGE', True
    if explicit in {'UPPER', 'UPPER_RANGE', 'UPPER_PART', 'HIGH_EDGE'}:
        return 'UPPER RANGE', False
    if explicit in {'LOWER', 'LOWER_RANGE', 'LOWER_PART', 'LOW_EDGE'}:
        return 'LOWER RANGE', False
    price = _safe_float(payload.get('price') or payload.get('last_price') or payload.get('current_price') or payload.get('close'))
    low = _safe_float(payload.get('range_low'))
    high = _safe_float(payload.get('range_high'))
    if price > 0 and low > 0 and high > low:
        pos_pct = ((price - low) / (high - low)) * 100.0
        if 30.0 <= pos_pct <= 70.0:
            return 'MID RANGE', True
        return ('UPPER RANGE', False) if pos_pct > 70.0 else ('LOWER RANGE', False)
    return 'MID RANGE', True


def _pattern_confirmation_label(pattern_pct: float) -> str:
    if pattern_pct >= 75:
        return 'сильное'
    if pattern_pct >= 60:
        return 'умеренное'
    return 'слабое'

def _should_suppress_pattern_bias(ctx: Dict[str, Any], authority: Dict[str, Any] | None = None) -> bool:
    authority = authority or {}
    action_now = str(authority.get('action_now') or '').upper()
    return bool(ctx.get('at_mid')) and str(ctx.get('structure') or '').upper() == 'CHOP' and str(ctx.get('breakout') or 'UNCONFIRMED').upper() in {'UNCONFIRMED', 'WEAK', 'FAILED', ''} and ('PAUSE' in action_now or 'WAIT' in action_now or 'NO ENTRY' in action_now)



def _derive_clean_bot_context(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    price = payload.get('price') or payload.get('last_price') or payload.get('current_price') or payload.get('close')
    range_state, at_mid = _derive_range_state(payload, decision)
    structure = str((_safe_dict(payload.get('impulse_character')).get('state')) or payload.get('structure') or 'CHOP').upper()
    volume_ctx = _safe_dict(payload.get('volume_context'))
    breakout = str(volume_ctx.get('breakout_state') or volume_ctx.get('breakout') or 'UNCONFIRMED').upper()
    volume_quality = str(volume_ctx.get('quality') or volume_ctx.get('state') or 'MIXED').upper()
    pattern = _safe_dict(payload.get('pattern_memory_v2') or payload.get('pattern_memory'))
    pattern_bias = str(pattern.get('direction_bias') or pattern.get('pattern_bias') or pattern.get('bias') or decision.get('direction') or 'NEUTRAL').upper()
    if pattern_bias not in {'LONG', 'SHORT'}:
        pattern_bias = str(decision.get('direction') or 'NEUTRAL').upper()
    grid_mode = 'PREFER_GRID' if at_mid or structure == 'CHOP' or breakout == 'UNCONFIRMED' else 'DIRECTIONAL'
    return {
        'price': price,
        'structure': structure,
        'range_state': range_state,
        'at_mid': at_mid,
        'grid_mode': grid_mode,
        'pattern_bias': pattern_bias,
        'volume_quality': volume_quality,
        'breakout': breakout,
    }




def _derive_grid_action_authority(payload: Dict[str, Any], ctx: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    reaction = _safe_dict(payload.get('liquidation_reaction') or payload.get('reaction_to_blocks'))
    fake = _safe_dict(payload.get('fake_move_v14') or payload.get('fake_move') or payload.get('fake_context'))
    acceptance = str(reaction.get('acceptance') or fake.get('acceptance') or '').upper()
    fake_state = str(fake.get('state') or fake.get('fake_move_state') or '').upper()

    at_mid = bool(ctx.get('at_mid'))
    range_state = str(ctx.get('range_state') or 'MID RANGE').upper()
    range_quality = str(extra.get('range_quality', {}).get('label') or 'RANGE HEALTHY').upper()
    reclaim = extra.get('reclaim') if isinstance(extra.get('reclaim'), dict) else {}
    divergence = extra.get('divergence') if isinstance(extra.get('divergence'), dict) else {}

    long_grid = 'PAUSE'
    short_grid = 'PAUSE'
    action_now = 'ARM ONLY AT EDGE'
    manager_action = 'ARM_EDGE'
    manager_reason = 'сетки включать только у рабочего края диапазона'
    runtime_note = 'обе сетки в режиме работы от края'
    edge_label = 'EDGE'

    if at_mid:
        action_now = 'PAUSE MID RANGE'
        manager_action = 'PAUSE_MID'
        manager_reason = 'середина диапазона — обе сетки на паузе'
        runtime_note = 'mid range: long-grid PAUSE | short-grid PAUSE'
        edge_label = 'MID RANGE'
    elif range_state == 'UPPER RANGE':
        long_grid = 'REDUCE'
        short_grid = 'RUN'
        manager_reason = 'верхний край — шорт-сетка рабочая, лонг-сетку сокращать'
        runtime_note = 'верхний край: лонг-сетку сокращать | шорт-сетку держать рабочей'
        edge_label = 'UPPER RANGE'
    elif range_state == 'LOWER RANGE':
        long_grid = 'RUN'
        short_grid = 'REDUCE'
        manager_reason = 'нижний край — лонг-сетка рабочая, шорт-сетку сокращать'
        runtime_note = 'нижний край: лонг-сетку держать рабочей | шорт-сетку сокращать'
        edge_label = 'LOWER RANGE'

    if range_quality == 'RANGE BREAK RISK':
        action_now = 'PAUSE / WAIT RECLAIM'
        manager_action = 'WAIT_RECLAIM'
        if at_mid:
            long_grid = 'PAUSE'
            short_grid = 'PAUSE'
        else:
            long_grid = 'REDUCE' if long_grid != 'EXIT' else 'EXIT'
            short_grid = 'REDUCE' if short_grid != 'EXIT' else 'EXIT'
        manager_reason = 'риск слома диапазона — сетки не форсировать, ждать возврата в диапазон'
        runtime_note = f'{edge_label.lower()}: long-grid {long_grid} | short-grid {short_grid} | ждать reclaim'

    if acceptance == 'ACCEPTED_ABOVE':
        action_now = 'EXIT / PAUSE BREAK UP'
        manager_action = 'BREAK_UP'
        long_grid = 'RUN' if range_quality != 'RANGE BREAK RISK' else 'REDUCE'
        short_grid = 'EXIT'
        manager_reason = 'цена принята выше верхнего блока — шорт-сетке выход, лонг-сетку не форсировать без нового возврата в диапазон'
        runtime_note = 'пробой вверх: шорт-сетке выход | лонг-сетка только по подтверждению'
    elif acceptance == 'ACCEPTED_BELOW':
        action_now = 'EXIT / PAUSE BREAK DOWN'
        manager_action = 'BREAK_DOWN'
        long_grid = 'EXIT'
        short_grid = 'RUN' if range_quality != 'RANGE BREAK RISK' else 'REDUCE'
        manager_reason = 'цена принята ниже нижнего блока — лонг-сетке выход, шорт-сетку не форсировать без нового возврата в диапазон'
        runtime_note = 'пробой вниз: лонг-сетке выход | шорт-сетка только по подтверждению'
    elif reclaim.get('state') == 'RECLAIM CONFIRMED' and reclaim.get('side') == 'SHORT':
        action_now = 'ARM SHORT EDGE'
        manager_action = 'ARM_SHORT_EDGE'
        long_grid = 'REDUCE'
        short_grid = 'RUN'
        manager_reason = 'подтверждённый возврат сверху — шорт-сетка главная'
        runtime_note = 'возврат сверху: лонг-сетку сокращать | шорт-сетку держать рабочей'
    elif reclaim.get('state') == 'RECLAIM CONFIRMED' and reclaim.get('side') == 'LONG':
        action_now = 'ARM LONG EDGE'
        manager_action = 'ARM_LONG_EDGE'
        long_grid = 'RUN'
        short_grid = 'REDUCE'
        manager_reason = 'подтверждённый возврат снизу — лонг-сетка главная'
        runtime_note = 'возврат снизу: лонг-сетку держать рабочей | шорт-сетку сокращать'

    div_state = str(divergence.get('state') or '').upper()
    if div_state in {'BEARISH', 'BEARISH_HINT'} and range_state == 'UPPER RANGE' and short_grid != 'EXIT':
        short_grid = 'RUN'
        if long_grid != 'EXIT':
            long_grid = 'REDUCE'
    elif div_state in {'BULLISH', 'BULLISH_HINT'} and range_state == 'LOWER RANGE' and long_grid != 'EXIT':
        long_grid = 'RUN'
        if short_grid != 'EXIT':
            short_grid = 'REDUCE'

    if fake_state in {'FAKE_UP', 'TRAP_UP'} and short_grid != 'EXIT':
        action_now = 'ARM SHORT EDGE'
        manager_action = 'ARM_SHORT_EDGE'
        short_grid = 'RUN'
        if long_grid != 'EXIT':
            long_grid = 'REDUCE'
        manager_reason = 'ложный вынос вверх — short-grid активнее'
    elif fake_state in {'FAKE_DOWN', 'TRAP_DOWN'} and long_grid != 'EXIT':
        action_now = 'ARM LONG EDGE'
        manager_action = 'ARM_LONG_EDGE'
        long_grid = 'RUN'
        if short_grid != 'EXIT':
            short_grid = 'REDUCE'
        manager_reason = 'ложный пролив вниз — long-grid активнее'

    return {
        'action_now': action_now,
        'manager_action': manager_action,
        'manager_reason': manager_reason,
        'long_grid': long_grid,
        'short_grid': short_grid,
        'runtime_note': runtime_note,
        'edge_label': edge_label,
        'acceptance': acceptance,
        'fake_state': fake_state,
    }

def _derive_v16_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    decision = _safe_dict(payload.get('decision'))
    ctx = _derive_clean_bot_context(payload, decision)
    extra = derive_v1689_context(payload)
    pattern = _safe_dict(payload.get('pattern_memory_v2') or payload.get('pattern_memory'))
    low, mid, high = payload.get('range_low'), payload.get('range_mid'), payload.get('range_high')
    upper_low = mid or low or high
    upper_high = high or mid or low
    lower_low = low or mid or high
    lower_high = mid or high or low
    if ctx['pattern_bias'] == 'SHORT':
        pattern_pct = pattern.get('short_prob')
    elif ctx['pattern_bias'] == 'LONG':
        pattern_pct = pattern.get('long_prob')
    else:
        pattern_pct = None
    if pattern_pct is None:
        pattern_pct = pattern.get('confidence') or 0
    try:
        pattern_pct = float(pattern_pct)
    except Exception:
        pattern_pct = 0.0
    pattern_expectation = str(pattern.get('expectation') or pattern.get('dominant_move') or pattern.get('expected_path') or 'range rotation')
    regime = 'RANGE / GRID' if ctx['grid_mode'] == 'PREFER_GRID' else 'DIRECTIONAL'
    volume_line = f"{ctx['volume_quality']} | breakout не подтверждён" if ctx['breakout'] == 'UNCONFIRMED' else f"{ctx['volume_quality']} | breakout подтверждён"

    rq = extra['range_quality']
    reclaim = extra['reclaim']
    div = extra['divergence']

    local_authority = _derive_grid_action_authority(payload, ctx, extra)
    master_authority = _coerce_master_authority(payload)
    authority = dict(local_authority)
    master_tf = str(master_authority.get('timeframe') or '').strip()
    master_locked = False
    if master_authority:
        for key in ('action_now', 'manager_action', 'manager_reason', 'long_grid', 'short_grid', 'runtime_note'):
            if master_authority.get(key):
                authority[key] = master_authority.get(key)
        master_locked = True

    pattern_side_raw = str(ctx['pattern_bias'] or decision.get('direction') or 'NEUTRAL').upper()
    if _should_suppress_pattern_bias(ctx, authority):
        pattern_side_raw = 'NEUTRAL'
    forecast_text = _forecast_text(pattern_side_raw, authority['action_now'], ctx['range_state'], rq['label'], authority['long_grid'], authority['short_grid'])

    target_text = _market_target_text(authority['action_now'], ctx['range_state'], payload.get('range_low'), payload.get('range_mid'), payload.get('range_high'), authority['long_grid'], authority['short_grid'])
    impulse_text = _impulse_state_text(payload, ctx['range_state'], authority['long_grid'], authority['short_grid'])
    scenario_text = _scenario_state_text(payload, authority['action_now'], ctx['range_state'], authority['long_grid'], authority['short_grid'], rq['label'])
    invalidation_text = _hard_invalidation_text(payload, authority['action_now'], authority['long_grid'], authority['short_grid'])
    scenario_confidence, scenario_confidence_ru = _scenario_confidence(authority['action_now'], rq['label'], scenario_text, impulse_text, authority['long_grid'], authority['short_grid'])
    auto_risk_mode = _auto_risk_mode(scenario_confidence, scenario_text, authority['action_now'])
    consensus = evaluate_context_consensus(payload, {'ctx': ctx, 'long_grid': authority['long_grid'], 'short_grid': authority['short_grid'], 'scenario_confidence': scenario_confidence})

    return {
        'ctx': ctx,
        'decision': decision,
        'price': ctx['price'],
        'regime': regime,
        'action_now': authority['action_now'],
        'manager_action': authority['manager_action'],
        'manager_reason': authority['manager_reason'],
        'long_grid': authority['long_grid'],
        'short_grid': authority['short_grid'],
        'runtime_note': authority['runtime_note'],
        'upper_low': upper_low,
        'upper_high': upper_high,
        'lower_low': lower_low,
        'lower_high': lower_high,
        'pattern_side': _direction_ru(pattern_side_raw),
        'pattern_pct': int(round(pattern_pct)) if pattern_side_raw in {'LONG', 'SHORT'} and pattern_pct else 0,
        'pattern_expectation': 'context only / blocked by mid range' if pattern_side_raw == 'NEUTRAL' and _should_suppress_pattern_bias(ctx, authority) else pattern_expectation,
        'pattern_confirmation': 'context only' if pattern_side_raw == 'NEUTRAL' and _should_suppress_pattern_bias(ctx, authority) else _pattern_confirmation_label(pattern_pct),
        'volume_line': volume_line,
        'integration_1': f"{ctx['structure']} + {ctx['volume_quality']}",
        'integration_2': 'направленный вход не подтверждён' if ctx['grid_mode'] == 'PREFER_GRID' else 'направленный сценарий активен',
        'integration_3': 'ТОЛЬКО ОТ КРАЯ / ПРИОРИТЕТ СЕТОК' if ctx['grid_mode'] == 'PREFER_GRID' else 'НАПРАВЛЕННЫЙ РЕЖИМ',
        'trigger': 'касание края + слабый пробой / быстрый возврат',
        'range_quality': rq,
        'reclaim': reclaim,
        'divergence': div,
        'authority': authority,
        'master_locked': master_locked,
        'master_tf': master_tf,
        'forecast_text': forecast_text,
        'target_text': target_text,
        'impulse_text': impulse_text,
        'scenario_text': scenario_text,
        'invalidation_text': invalidation_text,
        'scenario_confidence': scenario_confidence,
        'scenario_confidence_ru': scenario_confidence_ru,
        'auto_risk_mode': auto_risk_mode,
        'range_quality_text': _range_quality_ru(rq['label']),
        'divergence_text': _divergence_ru(div.get('state'), div.get('strength')),
        'authority_ru': _authority_ru(authority['action_now']),
        'authority_title_ru': _authority_title_ru(authority['action_now']),
        'manager_action_ru': _manager_action_ru(authority['manager_action']),
        'runtime_line': _runtime_line(authority['long_grid'], authority['short_grid']),
        'long_grid_ru': _runtime_ru(authority['long_grid']),
        'short_grid_ru': _runtime_ru(authority['short_grid']),
        'consensus': consensus,
    }


def format_v14_action_text(payload: Dict[str, Any], title: str = '⚡ ЧТО ДЕЛАТЬ') -> str:
    v = _derive_v16_view(payload)
    lines = [title, '']
    if v['price'] is not None:
        lines += [v['authority_title_ru'], f"Цена: {_fmt_price(v['price'])}", '']
    lines += [
        f"• структура: {v['ctx']['structure']}",
        f"• позиция: {v['ctx']['range_state']}",
        f"• runtime: {v['runtime_line']}",
        f"• режим действий: {v['authority_title_ru']} — {v['authority_ru']}",
        f"• режим: {v['integration_3']}",
        f"• прогноз рынка: {v['forecast_text']}",
        f"• цель движения: {v['target_text']}",
        f"• импульс: {v['impulse_text']}",
        f"• сценарий: {v['scenario_text']}",
        f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}",
        f"• авто-риск: {v['auto_risk_mode']}",
        f"• слом сценария: {v['invalidation_text']}",
        *_consensus_line_ru(v.get('consensus')),
        *_extern_block_lines(payload, v),
        *_flow_block_lines(payload, v),
        *_pre_hedge_block_lines(payload, v),
        '',
        'ПЛАН:',
        f"• short: только у верхнего блока {_fmt_price(v['upper_low'])}–{_fmt_price(v['upper_high'])}",
        f"• long: только у нижнего блока {_fmt_price(v['lower_low'])}–{_fmt_price(v['lower_high'])}",
        f"• триггер: {v['trigger']}",
    ]
    return '\n'.join(lines)


def format_v14_summary_text(payload: Dict[str, Any], title: str = '📘 BTC SUMMARY') -> str:
    v = _derive_v16_view(payload)
    lines = [title, '']
    if v['price'] is not None:
        lines += [v['authority_title_ru'], f"Цена: {_fmt_price(v['price'])}", '']
    lines += [
        f"• перевес: {v['pattern_side']}",
        f"• режим: {v['regime']}",
        f"• runtime: {v['runtime_line']}",
        f"• режим действий: {v['authority_title_ru']} — {v['authority_ru']}",
        f"• качество диапазона: {v['range_quality_text']}",
        f"• прогноз рынка: {v['forecast_text']}",
        f"• цель движения: {v['target_text']}",
        f"• импульс: {v['impulse_text']}",
        f"• сценарий: {v['scenario_text']}",
        f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}",
        f"• авто-риск: {v['auto_risk_mode']}",
        f"• слом сценария: {v['invalidation_text']}",
        *_consensus_line_ru(v.get('consensus')),
        *_extern_block_lines(payload, v),
        *_flow_block_lines(payload, v),
        *_pre_hedge_block_lines(payload, v),
        *( [f"• синхронизация: мастер-режим из {v['master_tf']}"] if v['master_locked'] and v['master_tf'] else [] ),
    ]
    return '\n'.join(lines)


def format_v14_forecast_text(payload: Dict[str, Any], title: str = '🔮 BTC FORECAST') -> str:
    v = _derive_v16_view(payload)
    lines = [title, '']
    if v['price'] is not None:
        lines += [v['authority_title_ru'], f"Цена: {_fmt_price(v['price'])}", '']
    lines += [
        f"• базовый сценарий: {v['pattern_side']}",
        f"• runtime: {v['runtime_line']}",
        f"• режим действий: {v['authority_title_ru']} — {v['authority_ru']}",
        f"• качество диапазона: {v['range_quality_text']}",
        f"• прогноз рынка: {v['forecast_text']}",
        f"• цель движения: {v['target_text']}",
        f"• импульс: {v['impulse_text']}",
        f"• сценарий: {v['scenario_text']}",
        f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}",
        f"• авто-риск: {v['auto_risk_mode']}",
        f"• слом сценария: {v['invalidation_text']}",
        *_consensus_line_ru(v.get('consensus')),
        *_extern_block_lines(payload, v),
        *_flow_block_lines(payload, v),
        *_pre_hedge_block_lines(payload, v),
        *( [f"• синхронизация: мастер-режим из {v['master_tf']}"] if v['master_locked'] and v['master_tf'] else [] ),
        *([f"• reclaim: {v['reclaim']['state']}"] if v['reclaim']['visible'] else []),
        *([f"• дивергенция: {v['divergence_text']}"] if v['divergence']['visible'] else []),
    ]
    return '\n'.join(lines)


def format_v14_decision_text(payload: Dict[str, Any], title: str = '🧠 FINAL DECISION') -> str:
    v = _derive_v16_view(payload)
    lines = [title, '']
    if v['price'] is not None:
        lines += [v['authority_title_ru'], f"Цена: {_fmt_price(v['price'])}", '']
    lines += [
        f"• перевес: {v['pattern_side']}",
        f"• решение: {v['authority_title_ru']} — {v['authority_ru']}",
        f"• runtime: {v['runtime_line']}",
        f"• режим: {v['regime']}",
        f"• причина: {v['integration_2']}",
        f"• качество диапазона: {v['range_quality_text']}",
        f"• прогноз рынка: {v['forecast_text']}",
        f"• цель движения: {v['target_text']}",
        f"• импульс: {v['impulse_text']}",
        f"• сценарий: {v['scenario_text']}",
        f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}",
        f"• авто-риск: {v['auto_risk_mode']}",
        f"• слом сценария: {v['invalidation_text']}",
        *_consensus_line_ru(v.get('consensus')),
        *_extern_block_lines(payload, v),
        *_flow_block_lines(payload, v),
        *_pre_hedge_block_lines(payload, v),
        *( [f"• синхронизация: мастер-режим из {v['master_tf']}"] if v['master_locked'] and v['master_tf'] else [] ),
    ]
    return '\n'.join(lines)


def format_v14_ginarea_text(payload: Dict[str, Any], title: str = '🧩 BTC GINAREA') -> str:
    v = _derive_v16_view(payload)
    lines = [title, '', f"Режим: {v['regime']}", f"Сейчас: {v['authority_title_ru']}", '', 'КРАТКО ПО БОТАМ:']
    lines += [
        f"• режим: {'ПРИОРИТЕТ СЕТОК' if v['ctx']['grid_mode'] == 'PREFER_GRID' else 'НАПРАВЛЕННЫЙ'}",
        f"• лонг-сетка: {_runtime_icon(v['long_grid'])} {_runtime_state_ru(v['long_grid'])} — {v['long_grid_ru']}",
        f"• шорт-сетка: {_runtime_icon(v['short_grid'])} {_runtime_state_ru(v['short_grid'])} — {v['short_grid_ru']}",
        '• активация: только у края',
        f"• середина: {'запрещено' if v['ctx']['at_mid'] else 'не активировать до касания края'}",
        f"• качество диапазона: {v['range_quality_text']}",
        f"• прогноз рынка: {v['forecast_text']}",
        f"• цель движения: {v['target_text']}",
        f"• импульс: {v['impulse_text']}",
        f"• сценарий: {v['scenario_text']}",
        f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}",
        f"• авто-риск: {v['auto_risk_mode']}",
        f"• слом сценария: {v['invalidation_text']}",
        *_consensus_line_ru(v.get('consensus')),
        *_extern_block_lines(payload, v),
        *_flow_block_lines(payload, v),
        *_pre_hedge_block_lines(payload, v),
        '• агрессия: низкая',
    ]
    if payload.get('range_low') or payload.get('range_mid') or payload.get('range_high'):
        lines.append(f"• зоны: низ {_fmt_price(payload.get('range_low'))}  | середина {_fmt_price(payload.get('range_mid'))}  | верх {_fmt_price(payload.get('range_high'))}")
    lines += _execution_block_lines(payload, v)
    lines += _lifecycle_block_lines(payload, v)
    lines += _hedge_block_lines(payload, v)
    return '\n'.join(lines)


def format_v14_best_trade_text(payload: Dict[str, Any], title: str = '🏆 ЛУЧШАЯ СДЕЛКА') -> str:
    v = _derive_v16_view(payload)
    return '\n'.join([
        title,
        '',
        f"• сценарий: {v['regime']}",
        f"• сторона: {v['pattern_side']}",
        f"• действие: {v['authority_title_ru']}",
        f"• runtime: {v['runtime_line']}",
        f"• сетап: {'СЕРЕДИНА ДИАПАЗОНА' if v['ctx']['at_mid'] else 'КРАЙ ДИАПАЗОНА' if v['ctx']['grid_mode'] == 'PREFER_GRID' else 'НАПРАВЛЕННЫЙ'}",
        f"• качество диапазона: {v['range_quality_text']}",
        f"• прогноз рынка: {v['forecast_text']}",
        f"• цель движения: {v['target_text']}",
        f"• импульс: {v['impulse_text']}",
        f"• сценарий: {v['scenario_text']}",
        f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}",
        f"• авто-риск: {v['auto_risk_mode']}",
        f"• слом сценария: {v['invalidation_text']}",
        *_consensus_line_ru(v.get('consensus')),
        *_extern_block_lines(payload, v),
        *_flow_block_lines(payload, v),
        *_pre_hedge_block_lines(payload, v),
    ])


def format_v14_trade_manager_text(payload: Dict[str, Any], title: str = '🛠 BTC TRADE MANAGER') -> str:
    v = _derive_v16_view(payload)
    lines = [title, '', f"• режим менеджера: {v['manager_action_ru']}", f"• причина: {v['manager_reason']}", f"• лонг-сетка: {_runtime_icon(v['long_grid'])} {_runtime_state_ru(v['long_grid'])} — {v['long_grid_ru']}", f"• шорт-сетка: {_runtime_icon(v['short_grid'])} {_runtime_state_ru(v['short_grid'])} — {v['short_grid_ru']}", f"• режим: {v['integration_3']}", f"• качество диапазона: {v['range_quality_text']}", f"• прогноз рынка: {v['forecast_text']}", f"• цель движения: {v['target_text']}", f"• импульс: {v['impulse_text']}", f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}", f"• авто-риск: {v['auto_risk_mode']}", f"• слом сценария: {v['invalidation_text']}", *_consensus_line_ru(v.get('consensus')), *_extern_block_lines(payload, v), *_flow_block_lines(payload, v), *_pre_hedge_block_lines(payload, v)]
    if payload.get('range_low') or payload.get('range_mid') or payload.get('range_high'):
        lines.append(f"• зоны: низ {_fmt_price(payload.get('range_low'))}  | середина {_fmt_price(payload.get('range_mid'))}  | верх {_fmt_price(payload.get('range_high'))}")
    lines += _execution_block_lines(payload, v)
    lines += _lifecycle_block_lines(payload, v)
    lines += _hedge_block_lines(payload, v)
    return '\n'.join(lines)


def format_v16_bots_status_text(payload: Dict[str, Any], title: str = '🤖 СТАТУС БОТОВ') -> str:
    v = _derive_v16_view(payload)
    lines = [title, '']
    lines += [
        f"• ЛОНГ-СЕТКА: {_runtime_state_ru(v['long_grid'])}",
        f"  - {('держать рабочей у нижнего края' if v['long_grid'] == 'RUN' else 'сокращать и не добавлять' if v['long_grid'] == 'REDUCE' else 'выключить до возврата в диапазон' if v['long_grid'] == 'EXIT' else 'на паузе до подхода к краю')}",
        f"• ШОРТ-СЕТКА: {_runtime_state_ru(v['short_grid'])}",
        f"  - {('держать рабочей у верхнего края' if v['short_grid'] == 'RUN' else 'сокращать и не добавлять' if v['short_grid'] == 'REDUCE' else 'выключить до возврата в диапазон' if v['short_grid'] == 'EXIT' else 'на паузе до подхода к краю')}",
        '',
        'КОМАНДЫ ДЛЯ РУЧНОГО ВЕДЕНИЯ:',
        '• BOT RANGE LONG ACTIVE / SMALL / AGGRESSIVE / ADD / PARTIAL / EXIT / CANCEL / RESET',
        '• BOT RANGE SHORT ACTIVE / SMALL / AGGRESSIVE / ADD / PARTIAL / EXIT / CANCEL / RESET',
        '',
        'ЦЕНТР УПРАВЛЕНИЯ СЕТКАМИ:',
        f"• режим: {'ПРИОРИТЕТ СЕТОК' if v['ctx']['grid_mode'] == 'PREFER_GRID' else 'НАПРАВЛЕННЫЙ'}",
        f"• режим действий: {v['authority_title_ru']} — {v['authority_ru']}",
        f"• runtime: {v['runtime_line']}",
        f"• качество диапазона: {v['range_quality_text']}",
        f"• прогноз рынка: {v['forecast_text']}",
        f"• цель движения: {v['target_text']}",
        f"• импульс: {v['impulse_text']}",
        f"• сценарий: {v['scenario_text']}",
        f"• уверенность сценария: {v['scenario_confidence']}% — {v['scenario_confidence_ru']}",
        f"• авто-риск: {v['auto_risk_mode']}",
        f"• слом сценария: {v['invalidation_text']}",
        '• активация: только у края',
        *_consensus_line_ru(v.get('consensus')),
        *_extern_block_lines(payload, v),
        *_flow_block_lines(payload, v),
        *_pre_hedge_block_lines(payload, v),
    ]
    if v['reclaim']['visible']:
        lines.append(f"• reclaim / возврат: {v['reclaim']['state']}")
    if v['divergence']['visible']:
        lines.append(f"• дивергенция: {v['divergence_text']}")
    if payload.get('range_low') or payload.get('range_mid') or payload.get('range_high'):
        lines.append(f"• зоны: низ {_fmt_price(payload.get('range_low'))} | середина {_fmt_price(payload.get('range_mid'))} | верх {_fmt_price(payload.get('range_high'))}")
    lines += _execution_block_lines(payload, v)
    lines += _lifecycle_block_lines(payload, v)
    lines += _hedge_block_lines(payload, v)
    return '\n'.join(lines)


# Compatibility functions used elsewhere in the project

def format_final_decision_telegram(decision: Dict[str, Any], symbol: str, timeframe: str, price: float) -> str:
    payload = {'decision': decision, 'price': price}
    return format_v14_decision_text(payload, f'🧠 FINAL DECISION [{timeframe}]')


def format_btc_summary_telegram(decision: Dict[str, Any], symbol: str, timeframe: str, price: float) -> str:
    payload = {'decision': decision, 'price': price}
    return format_v14_summary_text(payload, f'📘 {symbol} SUMMARY [{timeframe}]')


def format_ginarea_telegram(decision: Dict[str, Any], symbol: str, timeframe: str, range_low: float | None = None, range_mid: float | None = None, range_high: float | None = None) -> str:
    payload = {'decision': decision, 'range_low': range_low, 'range_mid': range_mid, 'range_high': range_high}
    return format_v14_ginarea_text(payload, f'🧩 {symbol} GINAREA [{timeframe}]')


def format_forecast_telegram(decision: Dict[str, Any], symbol: str, timeframe: str) -> str:
    payload = {'decision': decision}
    return format_v14_forecast_text(payload, f'🔮 {symbol} FORECAST [{timeframe}]')


# Legacy helper names referenced by import paths

def build_btc_partial_exit_text(*args, **kwargs) -> str:
    return 'PARTIAL EXIT'


def build_btc_trailing_text(*args, **kwargs) -> str:
    return 'TRAILING'
