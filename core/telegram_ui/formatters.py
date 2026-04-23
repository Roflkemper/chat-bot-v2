from __future__ import annotations

import html
from typing import Any


def _e(v: Any) -> str:
    if v is None:
        return "—"
    return html.escape(str(v))


def _num(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return str(round(float(v), digits))
    except (TypeError, ValueError):
        return html.escape(str(v))


def _join_reasons(reasons: Any) -> str:
    if not reasons:
        return "ограничений нет"
    if isinstance(reasons, (list, tuple)):
        return ", ".join(str(x) for x in reasons)
    return str(reasons)


def _fmt_entry_zone(entry_zone: Any) -> str:
    if entry_zone is None:
        return "—"
    if isinstance(entry_zone, (list, tuple)):
        vals = [x for x in entry_zone if x is not None]
        if not vals:
            return "—"
        if len(vals) == 1:
            return _num(vals[0], 4)
        return f"{_num(vals[0], 4)} → {_num(vals[-1], 4)}"
    return _num(entry_zone, 4)


def _ru_regime(v: Any) -> str:
    m = {
        "trend": "тренд",
        "range": "флет",
        "panic": "паника",
        "compression": "сжатие",
        "trend_like": "похоже на тренд",
    }
    return m.get(str(v or "").lower(), str(v or "—"))


def _ru_action(v: Any) -> str:
    m = {
        "ENTER LONG": "искать long",
        "WAIT LONG": "ждать long",
        "ENTER SHORT": "искать short",
        "WAIT SHORT": "ждать short",
        "NO TRADE": "вне рынка",
    }
    return m.get(str(v or "").upper(), str(v or "—"))


def _ru_signal(v: Any) -> str:
    m = {
        "LONG": "long",
        "SHORT": "short",
        "STRONG_LONG": "сильный long",
        "STRONG_SHORT": "сильный short",
        "NO TRADE": "нет сделки",
    }
    return m.get(str(v or "").upper(), str(v or "—"))


def _ru_bool(v: Any) -> str:
    return "да" if bool(v) else "нет"


def _ru_ct_mode(v: Any) -> str:
    m = {
        "none": "нет контртрендового края",
        "stretch": "растяжение",
        "false_break": "ложный вынос",
        "reversal_watch": "наблюдение за разворотом",
    }
    return m.get(str(v or "").lower(), str(v or "—"))


def _ru_range_state(v: Any) -> str:
    m = {
        "range": "флет",
        "trend_like": "похоже на тренд",
        "breakout": "выход из диапазона",
        "unknown": "неопределённо",
    }
    return m.get(str(v or "").lower(), str(v or "—"))


def _ru_breakout_risk(v: Any) -> str:
    m = {
        "low": "низкий",
        "medium": "средний",
        "high": "высокий",
    }
    return m.get(str(v or "").lower(), str(v or "—"))


def _ru_reentry_mode(v: Any) -> str:
    m = {
        "none": "нет",
        "reclaim": "reclaim",
        "continuation": "continuation",
        "confirmation": "confirmation",
    }
    return m.get(str(v or "").lower(), str(v or "—"))


def _ru_text(s: Any) -> str:
    text = str(s or "—")
    repl = {
        "no countertrend edge": "контртрендового преимущества нет",
        "wait false break + reclaim before acting": "ждать ложный вынос и возврат уровня перед входом",
        "watch for reclaim / rejection confirmation before entry": "ждать возврат уровня или подтверждение отклонения перед входом",
        "stretched move, wait confirmation before countertrend entry": "движение растянуто, нужен сигнал подтверждения перед контртрендом",
        "avoid range bots, prefer trend continuation": "не запускать range-ботов, приоритет продолжению тренда",
        "prefer fade edges, cancel on structure break": "работать от краёв диапазона, отменять сценарий на сломе структуры",
        "watch for squeeze and breakout from range edges": "следить за сжатием и возможным выходом из диапазона",
        "range is stable, can work from boundaries": "диапазон стабильный, можно работать от границ",
        "RANGE PLAY: fade edge only, take profit quicker, cancel on breakout": "работа от границ флета: брать быстрее прибыль, отмена на выходе из диапазона",
        "NO TRADE: wait structure reclaim / invalidation / new urgency spike": "нет сделки: ждать возврат структуры, инвалидацию прошлого сценария или новый всплеск urgency",
        "move_to_BE_after_1.0R": "перенос в безубыток после 1.0R",
        "wait reclaim / confirmation after invalidation or tp hit": "ждать возврат уровня или подтверждение после инвалидации либо после достижения цели",
    }
    return html.escape(repl.get(text, text))


def _forecast_direction(x: dict[str, Any]) -> tuple[str, str]:
    signal = str(x.get("signal") or "").upper()
    final_decision = str(x.get("final_decision") or "").upper()
    regime = str(x.get("regime") or "").lower()
    confidence = float(x.get("confidence") or 0.0)
    urgency = float(x.get("urgency") or 0.0)
    execution_quality = float(x.get("execution_quality") or 0.0)
    filters = x.get("filters") or {}
    allow = bool(filters.get("allow", False))
    reasons = " ".join(str(r).lower() for r in (filters.get("reasons") or []))

    if "SHORT" in signal:
        side = "вниз"
    elif "LONG" in signal:
        side = "вверх"
    else:
        side = "вбок / без явного направления"

    if signal == "NO TRADE":
        if regime == "trend":
            return (
                "вероятнее продолжение текущего тренда, но без безопасной точки входа",
                "сигнал на вход не подтверждён, поэтому направление рынка может сохраняться, но бот не видит качественный вход прямо сейчас",
            )
        if regime == "range":
            return (
                "скорее рынок останется во флете до выхода из диапазона",
                "нет сильного directional edge, режим похож на боковик",
            )
        if regime == "compression":
            return (
                "вероятен сжатый рынок с последующим импульсом, но направление пока не подтверждено",
                "есть компрессия, однако нет подтверждения, в какую сторону пойдёт выход",
            )
        return (
            "направление не подтверждено",
            "модель не видит достаточно сильного преимущества ни в одну сторону",
        )

    if allow and final_decision in {"ENTER LONG", "ENTER SHORT"}:
        return (
            f"вероятнее движение {side}",
            f"сигнал разрешён фильтрами, confidence={round(confidence,1)} и urgency={round(urgency,1)} поддерживают сценарий",
        )

    if final_decision in {"WAIT LONG", "WAIT SHORT"}:
        return (
            f"базовый сценарий — движение {side}, но сначала нужно подтверждение",
            f"направление смотрит {side}, однако вход ещё не оптимален: confidence={round(confidence,1)}, urgency={round(urgency,1)}",
        )

    if "low_urgency" in reasons:
        return (
            f"идея пока {side}, но рынок ещё недостаточно созрел для движения",
            "направление просматривается, но urgency низкий, поэтому импульс может не развиться сразу",
        )

    if "rr<" in reasons:
        return (
            f"движение может продолжиться {side}, но текущая точка входа невыгодная",
            "идея по направлению есть, но соотношение риск/прибыль пока слабое",
        )

    if execution_quality >= 70 and confidence >= 60:
        return (
            f"вероятнее движение {side}",
            "качество исполнения и confidence поддерживают этот сценарий",
        )

    return (
        f"умеренный уклон {side}",
        "направление просматривается, но запас преимущества пока средний",
    )


def _tf_rank(tf: str) -> int:
    order = {"5m": 1, "15m": 2, "1h": 3, "4h": 4, "1d": 5}
    return order.get(str(tf), 999)


def _summary_bias(board: list[dict[str, Any]]) -> str:
    up = 0
    down = 0
    flat = 0
    compression = 0

    for x in board:
        signal = str(x.get("signal") or "").upper()
        regime = str(x.get("regime") or "").lower()

        if regime == "compression":
            compression += 1

        if "LONG" in signal:
            up += 1
        elif "SHORT" in signal:
            down += 1
        else:
            flat += 1

    if compression >= 3:
        return "BTC сейчас: compression / рынок сжат, возможен импульс"
    if up >= 3 and down == 0:
        return "BTC сейчас: intraday bullish"
    if down >= 3 and up == 0:
        return "BTC сейчас: intraday bearish"
    if up > down:
        return "BTC сейчас: умеренно bullish"
    if down > up:
        return "BTC сейчас: умеренно bearish"
    return "BTC сейчас: mixed / смешанная картина"


def fmt_snapshot(x: dict[str, Any]) -> str:
    plan = x.get("execution_plan", {}) or {}
    filt = x.get("filters", {}) or {}

    return (
        f"<b>{_e(x.get('symbol'))} {_e(x.get('timeframe'))}</b>\n"
        f"Сейчас: <b>{_e(_ru_action(x.get('final_decision')))}</b>\n"
        f"Сигнал: {_e(_ru_signal(x.get('signal')))}\n"
        f"Цена: {_num(x.get('price'), 4)}\n"
        f"Режим: {_e(_ru_regime(x.get('regime')))}\n"
        f"Confidence: {_num(x.get('confidence'))} | Urgency: {_num(x.get('urgency'))}\n"
        f"Вход: {_e(_fmt_entry_zone(plan.get('entry_zone')))}\n"
        f"SL: {_num(plan.get('invalidation'), 4)} | TP1: {_num(plan.get('tp1'), 4)} | TP2: {_num(plan.get('tp2'), 4)}\n"
        f"Почему: {_e(_join_reasons(filt.get('reasons')))}"
    )


def fmt_best_trade(x: dict[str, Any]) -> str:
    plan = x.get("execution_plan", {}) or {}
    return (
        f"<b>ЛУЧШАЯ СДЕЛКА СЕЙЧАС</b>\n"
        f"{_e(x.get('symbol'))} {_e(x.get('timeframe'))}\n"
        f"Сейчас: <b>{_e(_ru_action(x.get('final_decision')))}</b>\n"
        f"Сигнал: {_e(_ru_signal(x.get('signal')))}\n"
        f"Цена: {_num(x.get('price'), 4)}\n"
        f"Режим: {_e(_ru_regime(x.get('regime')))}\n"
        f"Confidence: {_num(x.get('confidence'))} | Urgency: {_num(x.get('urgency'))}\n"
        f"Вход: {_e(_fmt_entry_zone(plan.get('entry_zone')))}\n"
        f"SL: {_num(plan.get('invalidation'), 4)} | TP1: {_num(plan.get('tp1'), 4)} | TP2: {_num(plan.get('tp2'), 4)}"
    )


def fmt_btc_analysis(x: dict[str, Any]) -> str:
    plan = x.get("execution_plan", {}) or {}
    filt = x.get("filters", {}) or {}
    gin = x.get("ginarea", {}) or {}
    ct = gin.get("countertrend", {}) or {}
    rg = gin.get("range", {}) or {}
    conf = x.get("confidence_decomposition", {}) or {}

    action_now = x.get("telegram_action_now") or x.get("final_decision") or "NO TRADE"
    forecast_title, forecast_reason = _forecast_direction(x)

    header = (
        f"<b>BTC | {_e(x.get('timeframe'))}</b>\n"
        f"<b>СЕЙЧАС: {_e(action_now)}</b>\n"
        f"Сигнал: {_e(_ru_signal(x.get('signal')))}\n"
        f"Цена: {_num(x.get('price'), 4)}\n"
        f"{_e(x.get('telegram_summary') or x.get('final_summary'))}\n"
    )

    forecast_block = (
        f"\n<b>Куда вероятнее пойдёт рынок</b>\n"
        f"{_e(forecast_title)}\n"
        f"Почему: {_e(forecast_reason)}\n"
    )

    market = (
        f"\n<b>Контекст рынка</b>\n"
        f"Режим: {_e(_ru_regime(x.get('regime')))}\n"
        f"Кластер: {_e(x.get('cluster'))}\n"
        f"Перегруз по направлению: {_e(x.get('directional_overload'))}\n"
    )

    quality = (
        f"\n<b>Качество сигнала</b>\n"
        f"Confidence: {_num(x.get('confidence'))}\n"
        f"Urgency: {_num(x.get('urgency'))}\n"
        f"Setup: {_e(x.get('setup_quality'))}\n"
        f"Execution: {_num(x.get('execution_quality'))}\n"
        f"Env / Structure / Execution / Management: "
        f"{_num(conf.get('env'))} / {_num(conf.get('structure'))} / {_num(conf.get('execution'))} / {_num(conf.get('management'))}\n"
    )

    reasons = (
        f"\n<b>Почему</b>\n"
        f"{_e(_join_reasons(filt.get('reasons')))}\n"
    )

    plan_block = (
        f"\n<b>План</b>\n"
        f"Зона входа: {_e(_fmt_entry_zone(plan.get('entry_zone')))}\n"
        f"Инвалидация: {_num(plan.get('invalidation'), 4)}\n"
        f"TP1: {_num(plan.get('tp1'), 4)}\n"
        f"TP2: {_num(plan.get('tp2'), 4)}\n"
        f"Перенос в BE: {_ru_text(plan.get('be_move'))}\n"
        f"RR: {_num(plan.get('rr'))}\n"
    )

    context = (
        f"\n<b>Подсказка по стилю рынка</b>\n"
        f"Контртренд: {_e(_ru_ct_mode(ct.get('ct_mode')))} → {_ru_text(ct.get('ct_advice'))}\n"
        f"Флет/тренд: {_e(_ru_range_state(rg.get('range_state')))} → {_ru_text(rg.get('range_advice'))}\n"
        f"Диапазон: {_num(rg.get('range_low'), 4)} → {_num(rg.get('range_high'), 4)}\n"
        f"Итог ginarea: {_ru_text(gin.get('unified_advice'))}\n"
    )

    risk = (
        f"\n<b>Риск / отмена сценария</b>\n"
        f"Торговать сейчас: {_e(_ru_bool(filt.get('allow')))}\n"
        f"Повторный вход: {_e(_ru_reentry_mode(x.get('reentry_mode')))} | score={_num(x.get('reentry_score'))} | zone={_e(_fmt_entry_zone(x.get('reentry_zone')))}\n"
    )

    return header + forecast_block + market + quality + reasons + plan_block + context + risk


def fmt_ginarea_advice(x: dict[str, Any]) -> str:
    gin = x.get("ginarea", {}) or {}
    ct = gin.get("countertrend", {}) or {}
    rg = gin.get("range", {}) or {}
    range_low = rg.get("range_low")
    range_high = rg.get("range_high")
    plan_items = gin.get("tactical_plan") or []
    plan_text = "\n".join([f"• {_ru_text(item)}" for item in plan_items[:4]]) if isinstance(plan_items, list) and plan_items else "• ждать более чистый сетап"

    return (
        f"<b>GINAREA ADVICE | {_e(x.get('symbol'))} {_e(x.get('timeframe'))}</b>\n"
        f"\n<b>Контртренд</b>\n"
        f"Режим: {_e(_ru_ct_mode(ct.get('ct_mode')))}\n"
        f"Растяжение: {_num(ct.get('ct_stretch_atr'), 4)} ATR\n"
        f"Подсказка: {_ru_text(ct.get('ct_advice'))}\n"
        f"Инвалидация: {_num(ct.get('ct_invalidation'), 4)}\n"
        f"\n<b>Range / Trend контекст</b>\n"
        f"Состояние: {_e(_ru_range_state(rg.get('range_state')))}\n"
        f"Граница диапазона снизу: {_num(range_low, 4)}\n"
        f"Граница диапазона сверху: {_num(range_high, 4)}\n"
        f"Середина диапазона: {_num(rg.get('range_mid'), 4)}\n"
        f"Риск выхода: {_e(_ru_breakout_risk(rg.get('breakout_risk')))}\n"
        f"Подсказка: {_ru_text(rg.get('range_advice'))}\n"
        f"Инвалидация: {_num(rg.get('range_invalidation'), 4)}\n"
        f"\n<b>Execution / стиль</b>\n"
        f"Стиль: {_ru_text(gin.get('trade_style'))}\n"
        f"Scalp only: {_e(_ru_bool(gin.get('scalp_only')))}\n"
        f"Нужна подтверждение: {_e(_ru_bool(gin.get('confirmation_needed')))}\n"
        f"Зона re-entry: {_ru_text(gin.get('reentry_zone'))}\n"
        f"Отмена идеи: {_ru_text(gin.get('invalidation_hint'))}\n"
        f"\n<b>Что делать дальше</b>\n"
        f"{plan_text}\n"
        f"\n<b>Итог</b>\n"
        f"{_ru_text(gin.get('unified_advice'))}"
    )


def fmt_signals_board(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Нет сигналов"

    lines = ["<b>СИГНАЛЫ СЕЙЧАС</b>"]
    for x in items[:6]:
        lines.append(
            f"{_e(x.get('symbol'))} {_e(x.get('timeframe'))} | "
            f"<b>{_e(_ru_action(x.get('final_decision')))}</b> | "
            f"сигнал: {_e(_ru_signal(x.get('signal')))} | "
            f"conf {_num(x.get('confidence'))} | "
            f"urg {_num(x.get('urgency'))}"
        )
    return "\n".join(lines)


def fmt_final_decision(x: dict[str, Any]) -> str:
    return (
        f"<b>FINAL DECISION | {_e(x.get('symbol'))} {_e(x.get('timeframe'))}</b>\n"
        f"Сейчас: <b>{_e(x.get('telegram_action_now') or _ru_action(x.get('final_decision')))}</b>\n"
        f"Сигнал: {_e(_ru_signal(x.get('signal')))}\n"
        f"Итог: {_e(_ru_action(x.get('final_decision')))}\n"
        f"Сводка: {_e(x.get('telegram_summary') or x.get('final_summary'))}"
    )


def fmt_exec_plan(x: dict[str, Any]) -> str:
    plan = x.get("execution_plan", {}) or {}
    return (
        f"<b>EXEC PLAN | {_e(x.get('symbol'))} {_e(x.get('timeframe'))}</b>\n"
        f"Зона входа: {_e(_fmt_entry_zone(plan.get('entry_zone')))}\n"
        f"Инвалидация: {_num(plan.get('invalidation'), 4)}\n"
        f"TP1: {_num(plan.get('tp1'), 4)}\n"
        f"TP2: {_num(plan.get('tp2'), 4)}\n"
        f"BE: {_ru_text(plan.get('be_move'))}\n"
        f"Подсказка по повторному входу: {_ru_text(plan.get('reentry_hint'))}\n"
        f"RR: {_num(plan.get('rr'))}"
    )


def fmt_ct_now(x: dict[str, Any]) -> str:
    ct = (x.get("ginarea", {}) or {}).get("countertrend", {}) or {}
    return (
        f"<b>CT NOW | {_e(x.get('symbol'))} {_e(x.get('timeframe'))}</b>\n"
        f"Режим: {_e(_ru_ct_mode(ct.get('ct_mode')))}\n"
        f"Растяжение: {_num(ct.get('ct_stretch_atr'), 4)} ATR\n"
        f"Подсказка: {_ru_text(ct.get('ct_advice'))}\n"
        f"Инвалидация: {_num(ct.get('ct_invalidation'), 4)}"
    )


def fmt_range_now(x: dict[str, Any]) -> str:
    rg = (x.get("ginarea", {}) or {}).get("range", {}) or {}
    return (
        f"<b>RANGE NOW | {_e(x.get('symbol'))} {_e(x.get('timeframe'))}</b>\n"
        f"Состояние: {_e(_ru_range_state(rg.get('range_state')))}\n"
        f"Граница диапазона снизу: {_num(rg.get('range_low'), 4)}\n"
        f"Граница диапазона сверху: {_num(rg.get('range_high'), 4)}\n"
        f"Середина диапазона: {_num(rg.get('range_mid'), 4)}\n"
        f"Риск выхода: {_e(_ru_breakout_risk(rg.get('breakout_risk')))}\n"
        f"Подсказка: {_ru_text(rg.get('range_advice'))}\n"
        f"Инвалидация: {_num(rg.get('range_invalidation'), 4)}"
    )


def fmt_btc_forecast(board: list[dict[str, Any]]) -> str:
    if not board:
        return "Нет данных по BTC"

    board = sorted(board, key=lambda x: _tf_rank(str(x.get("timeframe"))))
    lines = ["<b>BTC FORECAST</b>", _summary_bias(board)]

    for x in board:
        title, reason = _forecast_direction(x)
        lines.append(
            f"\n<b>{_e(x.get('timeframe'))}</b>\n"
            f"Сейчас: {_e(x.get('telegram_action_now') or _ru_action(x.get('final_decision')))}\n"
            f"Сигнал: {_e(_ru_signal(x.get('signal')))}\n"
            f"Прогноз: {_e(title)}\n"
            f"Причина: {_e(reason)}\n"
            f"Confidence: {_num(x.get('confidence'))} | Urgency: {_num(x.get('urgency'))}"
        )
    return "\n".join(lines)


def fmt_btc_summary(board: list[dict[str, Any]]) -> str:
    if not board:
        return "Нет данных по BTC"

    board = sorted(board, key=lambda x: _tf_rank(str(x.get("timeframe"))))
    lines = ["<b>BTC SUMMARY</b>", _summary_bias(board)]

    for x in board:
        rg = ((x.get("ginarea") or {}).get("range") or {})
        lines.append(
            f"\n<b>{_e(x.get('timeframe'))}</b> | {_e(_ru_action(x.get('final_decision')))}\n"
            f"Сигнал: {_e(_ru_signal(x.get('signal')))} | Режим: {_e(_ru_regime(x.get('regime')))}\n"
            f"Conf {_num(x.get('confidence'))} | Urg {_num(x.get('urgency'))}\n"
            f"Диапазон: {_num(rg.get('range_low'), 4)} → {_num(rg.get('range_high'), 4)}"
        )

    return "\n".join(lines)