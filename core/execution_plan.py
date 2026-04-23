from __future__ import annotations

from typing import Any, Dict, Optional

from core.import_compat import normalize_direction, to_float
from core.btc_plan import calc_long_score, calc_short_score, fmt_pct, fmt_price


def _state(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    direction = str(decision.get("direction") or "").upper()
    if direction in ("LONG", "SHORT"):
        return direction

    long_score = calc_long_score(data)
    short_score = calc_short_score(data)

    if long_score >= short_score + 0.12:
        return "LONG"
    if short_score >= long_score + 0.12:
        return "SHORT"
    return "WAIT"


def _decision(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("decision") or {}


def _decision_direction(data: Dict[str, Any]) -> str:
    raw = str(_decision(data).get("direction") or "").upper()
    if raw in ("LONG", "SHORT", "NONE", "NEUTRAL"):
        return "NONE" if raw == "NEUTRAL" else raw
    side = _state(data)
    if side in ("LONG", "SHORT"):
        return side
    return "NONE"


def _decision_action(data: Dict[str, Any]) -> str:
    raw = str(_decision(data).get("action") or "").upper()
    if raw:
        return raw
    return "WAIT" if _state(data) == "WAIT" else "WATCH"


def _decision_mode(data: Dict[str, Any]) -> str:
    return str(_decision(data).get("mode") or "MIXED").upper()


def _decision_risk(data: Dict[str, Any]) -> str:
    return str(_decision(data).get("risk_level") or "HIGH").upper()


def _decision_confidence(data: Dict[str, Any]) -> float:
    value = to_float(_decision(data).get("confidence"))
    if value is not None:
        return float(value)
    return max(calc_long_score(data), calc_short_score(data))


def _risk_rank(level: str) -> int:
    mapping = {"LOW": 1, "MID": 2, "HIGH": 3}
    return mapping.get(str(level or "").upper(), 3)


def _entry_snapshot_context(journal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    journal = journal or {}
    decision_snapshot = journal.get("decision_snapshot") or {}
    analysis_snapshot = journal.get("analysis_snapshot") or {}

    entry_direction = str(decision_snapshot.get("direction") or "").upper()
    if entry_direction not in ("LONG", "SHORT", "NONE"):
        fd = normalize_direction(analysis_snapshot.get("final_decision"))
        if fd == "ЛОНГ":
            entry_direction = "LONG"
        elif fd == "ШОРТ":
            entry_direction = "SHORT"
        else:
            entry_direction = "NONE"

    entry_action = str(decision_snapshot.get("action") or "WAIT").upper()
    entry_mode = str(decision_snapshot.get("mode") or "MIXED").upper()
    entry_risk = str(decision_snapshot.get("risk_level") or "HIGH").upper()
    entry_confidence = to_float(decision_snapshot.get("confidence"))
    if entry_confidence is None:
        entry_confidence = 0.0

    return {
        "decision_snapshot": decision_snapshot,
        "analysis_snapshot": analysis_snapshot,
        "entry_direction": entry_direction,
        "entry_action": entry_action,
        "entry_mode": entry_mode,
        "entry_risk": entry_risk,
        "entry_confidence": float(entry_confidence),
    }


def _build_context_shift(data: Dict[str, Any], journal: Optional[Dict[str, Any]], side: str = "AUTO") -> Dict[str, Any]:
    side = side.upper()
    if side == "AUTO":
        side = (journal or {}).get("side") or _state(data)
        side = str(side).upper()

    current_direction = _decision_direction(data)
    current_action = _decision_action(data)
    current_mode = _decision_mode(data)
    current_risk = _decision_risk(data)
    current_confidence = _decision_confidence(data)

    long_score = calc_long_score(data)
    short_score = calc_short_score(data)

    entry_ctx = _entry_snapshot_context(journal)
    entry_direction = entry_ctx["entry_direction"]
    entry_action = entry_ctx["entry_action"]
    entry_mode = entry_ctx["entry_mode"]
    entry_risk = entry_ctx["entry_risk"]
    entry_confidence = entry_ctx["entry_confidence"]

    if side == "LONG":
        side_score_now = long_score
        opp_score_now = short_score
    elif side == "SHORT":
        side_score_now = short_score
        opp_score_now = long_score
    else:
        side_score_now = max(long_score, short_score)
        opp_score_now = min(long_score, short_score)

    direction_flip = side in ("LONG", "SHORT") and current_direction not in (side, "NONE")
    action_weaker = current_action in ("WAIT",)
    confidence_drop = entry_confidence > 0 and current_confidence <= max(entry_confidence - 0.18, 0.35)
    opposite_pressure = opp_score_now >= side_score_now + 0.12
    risk_worse = _risk_rank(current_risk) > _risk_rank(entry_risk)
    mode_changed = entry_mode != "MIXED" and current_mode != entry_mode

    reasons: list[str] = []

    if side in ("LONG", "SHORT"):
        if current_direction == side:
            reasons.append("текущее направление ещё поддерживает исходную сторону сделки")
        elif current_direction == "NONE":
            reasons.append("направленный перевес ослаб и стал менее чистым")
        elif direction_flip:
            reasons.append("decision engine развернулся против стороны входа")

    if action_weaker:
        reasons.append("текущее действие перешло в режим ожидания")
    if confidence_drop:
        reasons.append("уверенность решения просела относительно точки входа")
    if opposite_pressure:
        reasons.append("противоположная сторона стала сильнее")
    if risk_worse:
        reasons.append("риск по текущему контексту стал хуже")
    if mode_changed:
        reasons.append("режим рынка изменился относительно входа")

    return {
        "side": side,
        "entry_direction": entry_direction,
        "entry_action": entry_action,
        "entry_mode": entry_mode,
        "entry_risk": entry_risk,
        "entry_confidence": entry_confidence,
        "current_direction": current_direction,
        "current_action": current_action,
        "current_mode": current_mode,
        "current_risk": current_risk,
        "current_confidence": current_confidence,
        "direction_flip": direction_flip,
        "action_weaker": action_weaker,
        "confidence_drop": confidence_drop,
        "opposite_pressure": opposite_pressure,
        "risk_worse": risk_worse,
        "mode_changed": mode_changed,
        "reasons": reasons,
        "side_score_now": side_score_now,
        "opp_score_now": opp_score_now,
        "long_score": long_score,
        "short_score": short_score,
    }


def _execution_action(data: Dict[str, Any], journal: Optional[Dict[str, Any]] = None, side: str = "AUTO") -> str:
    shift = _build_context_shift(data, journal, side=side)

    if shift["side"] not in ("LONG", "SHORT"):
        return "ЖДАТЬ / НЕТ АКТИВНОЙ СТОРОНЫ"


    neutral_guard = (
        shift["current_direction"] == "NONE"
        or (abs(shift["long_score"] - shift["short_score"]) < 8 and shift["current_confidence"] <= 15)
    )
    if neutral_guard:
        return "ЖДАТЬ / НЕТ АКТИВНОЙ СТОРОНЫ"

    if shift["direction_flip"]:
        return "ЛУЧШЕ ЗАКРЫТЬ"

    if shift["current_direction"] == "NONE":
        if shift["current_action"] == "WAIT":
            return "ЖДАТЬ"
        return "ДЕРЖАТЬ АККУРАТНО"

    if shift["opposite_pressure"] and shift["risk_worse"]:
        return "ЛУЧШЕ ЗАКРЫТЬ"

    if shift["current_direction"] == shift["side"]:
        if shift["current_action"] == "ENTER" and shift["current_risk"] == "LOW":
            return "ДЕРЖАТЬ"
        if shift["current_action"] in ("WATCH", "WAIT_CONFIRMATION"):
            return "ЖДАТЬ ПОДТВЕРЖДЕНИЕ"
        if shift["confidence_drop"] or shift["risk_worse"]:
            return "ДЕРЖАТЬ АККУРАТНО"
        return "ДЕРЖАТЬ"

    return "ЖДАТЬ"


def _execution_comment(action: str) -> str:
    return {
        "МОЖНО ИСКАТЬ ВХОД": "контекст выглядит достаточно собранным для поиска входа",
        "ЖДАТЬ ПОДТВЕРЖДЕНИЕ": "идея есть, но вход лучше брать только после подтверждения",
        "ЖДАТЬ": "сейчас лучше не форсировать решение и дождаться более чистого сигнала",
        "ЖДАТЬ / НЕТ АКТИВНОЙ СТОРОНЫ": "активной стороны сейчас нет: бот ждёт край диапазона или сборку чистого импульса",
        "ДЕРЖАТЬ": "позиционный контекст пока остаётся рабочим",
        "ДЕРЖАТЬ АККУРАТНО": "сценарий ещё не сломан, но запас прочности уже слабее",
        "ЛУЧШЕ ЗАКРЫТЬ": "текущий decision-контекст уже заметно хуже точки входа",
    }.get(action, "лучше действовать аккуратно и без форсирования")




def _decision_field(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    return (_decision(data) or {}).get(key, default)


def _execution_style_hint(data: Dict[str, Any], side: str) -> str:
    side = side.upper()
    entry_type = str(_decision_field(data, "entry_type", "no_trade") or "no_trade").lower()
    execution_mode = str(_decision_field(data, "execution_mode", "conservative") or "conservative").lower()
    late_risk = str(_decision_field(data, "late_entry_risk", "MEDIUM") or "MEDIUM").upper()
    trap_risk = str(_decision_field(data, "trap_risk", "MEDIUM") or "MEDIUM").upper()
    location_quality = str(_decision_field(data, "location_quality", "C") or "C").upper()
    breakout_risk = str(_decision_field(data, "breakout_risk", "LOW") or "LOW").upper()

    if side not in ("LONG", "SHORT"):
        return "без стороны сделки лучше не форсировать исполнение"
    if trap_risk == "HIGH":
        return "контекст ловушки высокий: вход только после подтверждения, без удержания на эмоциях"
    if late_risk == "HIGH":
        return "вход уже поздний: лучше ждать откат или re-entry, а не догонку"
    if breakout_risk == "HIGH":
        return "риск выноса высокий: если брать, то только scalp/partial и с быстрым контролем уровня"
    if entry_type == "reversal":
        return "это разворотный сценарий: нужен reclaim/retest, первая свеча сама по себе не повод держать долго"
    if entry_type == "pullback":
        return "лучший формат — вход после отката и реакции от зоны, не на пике импульса"
    if execution_mode == "aggressive" and location_quality in {"A", "B"}:
        return "edge неплохой, но всё равно лучше подтверждать удержание зоны перед увеличением размера"
    return "исполнять аккуратно: сначала подтверждение, потом удержание, потом попытка hold"


def _partial_plan(data: Dict[str, Any], side: str) -> str:
    side = side.upper()
    location_quality = str(_decision_field(data, "location_quality", "C") or "C").upper()
    trap_risk = str(_decision_field(data, "trap_risk", "MEDIUM") or "MEDIUM").upper()
    late_risk = str(_decision_field(data, "late_entry_risk", "MEDIUM") or "MEDIUM").upper()
    entry_type = str(_decision_field(data, "entry_type", "no_trade") or "no_trade").lower()
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))

    if side == "LONG":
        if trap_risk == "HIGH" or late_risk == "HIGH":
            return f"часть логично фиксировать ближе к {fmt_price(mid) if mid is not None else 'ближайшей середине импульса'}; остаток держать только если покупатель удерживает уровень"
        if entry_type == "reversal":
            return f"по reversal-лонгу partial логичен в районе {fmt_price(mid) if mid is not None else 'середины диапазона'}, дальше смотреть силу выкупа"
        if location_quality in {"A", "B"}:
            return f"можно держать основную часть до {fmt_price(high) if high is not None else 'верхней зоны'}, частично фиксируя по пути"
    elif side == "SHORT":
        if trap_risk == "HIGH" or late_risk == "HIGH":
            return f"часть логично фиксировать ближе к {fmt_price(mid) if mid is not None else 'середине диапазона'}; остаток держать только если продавец не отдаёт уровень"
        if entry_type == "reversal":
            return f"по reversal-шорту partial логичен в районе {fmt_price(mid) if mid is not None else 'середины диапазона'}, дальше смотреть продавца"
        if location_quality in {"A", "B"}:
            return f"можно тянуть часть позиции к {fmt_price(low) if low is not None else 'нижней зоне'}, но не игнорировать фиксацию по дороге"
    return "частичную фиксацию лучше делать раньше обычного, пока сетап не доказал способность к hold"


def _reentry_plan(data: Dict[str, Any], side: str) -> str:
    side = side.upper()
    false_break_signal = str(data.get("false_break_signal") or _decision_field(data, "false_break_signal", "NONE") or "NONE").upper()
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))

    if false_break_signal == "UP_TRAP":
        return f"re-entry в шорт лучше искать после слабого retest зоны {fmt_price(mid) if mid is not None else 'mid'}–{fmt_price(high) if high is not None else 'high'}"
    if false_break_signal == "DOWN_TRAP":
        return f"re-entry в лонг лучше искать после выкупа зоны {fmt_price(low) if low is not None else 'low'}–{fmt_price(mid) if mid is not None else 'mid'}"
    if side == "LONG":
        return f"re-entry для лонга лучше после отката в {fmt_price(low) if low is not None else 'support'}–{fmt_price(mid) if mid is not None else 'mid'} и новой реакции покупателя"
    if side == "SHORT":
        return f"re-entry для шорта лучше после отката в {fmt_price(mid) if mid is not None else 'mid'}–{fmt_price(high) if high is not None else 'resistance'} и нового rejection"
    return "повторный вход лучше искать только после новой реакции от понятной зоны"


def _hold_plan(data: Dict[str, Any], side: str) -> str:
    side = side.upper()
    execution_mode = str(_decision_field(data, "execution_mode", "conservative") or "conservative").lower()
    trap_risk = str(_decision_field(data, "trap_risk", "MEDIUM") or "MEDIUM").upper()
    late_risk = str(_decision_field(data, "late_entry_risk", "MEDIUM") or "MEDIUM").upper()
    if side not in ("LONG", "SHORT"):
        return "без выраженной стороны сделки hold сейчас не выглядит качественно"
    if trap_risk == "HIGH":
        return "hold допустим только если рынок сразу подтверждает сторону сделки; иначе лучше быстро сокращать риск"
    if late_risk == "HIGH":
        return "полноценный hold хуже обычного: позицию лучше вести короче и агрессивнее защищать"
    if execution_mode == "aggressive":
        return "hold допустим, но после первого нормального импульса часть позиции лучше уже защитить"
    return "hold рабочий, пока рынок не теряет уровень и не начинает отдавать импульс назад"


def _invalidation_line(data: Dict[str, Any], side: str) -> str:
    price = to_float(data.get("price"))
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))

    side = side.upper()

    if side == "LONG":
        if low is not None:
            return f"слом лонг-сценария ниже {fmt_price(low)}"
        if mid is not None:
            return f"возврат ниже {fmt_price(mid)} ослабит лонг-сценарий"
        if price is not None:
            return f"уход заметно ниже {fmt_price(price * 0.995)} ослабит лонг"
        return "лонг-сценарий ломается при потере поддержки"
    if side == "SHORT":
        if high is not None:
            return f"слом шорт-сценария выше {fmt_price(high)}"
        if mid is not None:
            return f"возврат выше {fmt_price(mid)} ослабит шорт-сценарий"
        if price is not None:
            return f"уход заметно выше {fmt_price(price * 1.005)} ослабит шорт"
        return "шорт-сценарий ломается при возврате выше сопротивления"
    return "без явного перевеса нет чистой invalidation-зоны"


def _entry_idea(data: Dict[str, Any], side: str) -> str:
    side = side.upper()
    price = to_float(data.get("price"))
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))

    if side == "LONG":
        if low is not None and mid is not None:
            return f"условие long-входа: цена должна зайти в зону {fmt_price(low)}–{fmt_price(mid)}, удержать low и дать подтверждающую свечу вверх"
        if price is not None:
            return f"условие long-входа: не покупать на пике; ждать откат от {fmt_price(price)} и реакцию покупателя"
        return "лонг лучше брать только от понятной поддержки"
    if side == "SHORT":
        if mid is not None and high is not None:
            return f"условие short-входа: цена должна зайти в зону {fmt_price(mid)}–{fmt_price(high)}, удержать high продавцом и дать свечу вниз"
        if price is not None:
            return f"условие short-входа: не шортить низ; ждать откат от {fmt_price(price)} и реакцию продавца"
        return "шорт лучше брать только от понятного сопротивления"
    return "сейчас лучше не форсировать вход"




def _activation_condition(data: Dict[str, Any], side: str) -> str:
    side = side.upper()
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))
    if side == "LONG":
        zone = f"{fmt_price(low)}–{fmt_price(mid)}" if low is not None and mid is not None else "зоне поддержки"
        return f"бот сам переведёт сценарий во вход, когда цена зайдёт в {zone}, покупатель удержит low и появится свеча продолжения вверх"
    if side == "SHORT":
        zone = f"{fmt_price(mid)}–{fmt_price(high)}" if mid is not None and high is not None else "зоне сопротивления"
        return f"бот сам переведёт сценарий во вход, когда цена зайдёт в {zone}, продавец удержит high и появится свеча продолжения вниз"
    return "пока активной стороны нет: бот ждёт край диапазона или сборку чистого импульса и сам покажет переход из WAIT во вход"


def _wait_what_exactly(data: Dict[str, Any], side: str) -> str:
    side = side.upper()
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))
    if side == "LONG":
        return f"ждать откат/касание зоны {fmt_price(low) if low is not None else 'support'}–{fmt_price(mid) if mid is not None else 'mid'}, удержание уровня и подтверждающую bullish-свечу"
    if side == "SHORT":
        return f"ждать откат/касание зоны {fmt_price(mid) if mid is not None else 'mid'}–{fmt_price(high) if high is not None else 'resistance'}, rejection сверху и подтверждающую bearish-свечу"
    return "ждать подхода к краю диапазона, явного удержания уровня и чистого импульса; в середине диапазона бот вход не форсирует"


def _can_auto_flip_to_enter(data: Dict[str, Any], side: str) -> str:
    decision = _decision(data) or {}
    action = str(decision.get("action") or "WAIT").upper()
    if side not in ("LONG", "SHORT"):
        return "нет: пока нет активной стороны"
    if action == "ENTER":
        return "да: условие уже собрано, вход разрешён"
    if action in {"WATCH", "WAIT_CONFIRMATION", "WAIT_PULLBACK", "WAIT_RANGE_EDGE", "WAIT"}:
        return "да: как только условия у уровня соберутся, бот сам сменит WAIT/WATCH на ВХОДИТЬ"
    return "пока нет"


def _trade_plan_levels(data: Dict[str, Any], side: str) -> Dict[str, Any]:
    side = side.upper()
    decision = _decision(data) or {}
    edge_label = str(decision.get("edge_label") or "NO_EDGE").upper()
    edge_action = str(decision.get("edge_action") or "NO_TRADE").upper()
    trade_authorized = bool(decision.get("trade_authorized") or (edge_label == "STRONG" and edge_action == "CAN_EXECUTE"))
    price = to_float(data.get("price"))
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))

    if side not in {"LONG", "SHORT"}:
        return {
            "entry_zone": "нет активной entry-зоны",
            "trigger": "ждать край диапазона / подтверждение",
            "stop": None,
            "tp1": None,
            "tp2": None,
            "be": None,
            "rr": None,
        }

    if not trade_authorized:
        trigger = "ждать подтверждение у края диапазона: сценарий есть, но execution ещё не разрешён"
        if side == "LONG":
            zone = f"{fmt_price(low)}–{fmt_price(mid)}" if low is not None and mid is not None else "нет данных"
        else:
            zone = f"{fmt_price(mid)}–{fmt_price(high)}" if mid is not None and high is not None else "нет данных"
        return {
            "entry_zone": zone,
            "trigger": trigger,
            "stop": None,
            "tp1": None,
            "tp2": None,
            "be": None,
            "rr": None,
        }

    if side == "LONG":
        entry_a = low if low is not None else (price * 0.997 if price is not None else None)
        entry_b = mid if mid is not None else price
        stop = (low * 0.995) if low is not None else (price * 0.992 if price is not None else None)
        tp1 = mid if mid is not None else (price * 1.005 if price is not None else None)
        tp2 = high if high is not None else (price * 1.01 if price is not None else None)
        be = tp1
        trigger = "удержание поддержки + bullish confirm"
    else:
        entry_a = mid if mid is not None else price
        entry_b = high if high is not None else (price * 1.003 if price is not None else None)
        stop = (high * 1.005) if high is not None else (price * 1.008 if price is not None else None)
        tp1 = mid if mid is not None else (price * 0.995 if price is not None else None)
        tp2 = low if low is not None else (price * 0.99 if price is not None else None)
        be = tp1
        trigger = "rejection от сопротивления + bearish confirm"

    zone = "нет данных"
    if entry_a is not None and entry_b is not None:
        lo = min(float(entry_a), float(entry_b))
        hi = max(float(entry_a), float(entry_b))
        if abs(hi - lo) < 1e-9 and price is not None:
            pad = max(abs(float(price)) * 0.0015, 25.0)
            lo -= pad
            hi += pad
        zone = f"{fmt_price(lo)}–{fmt_price(hi)}"
    elif entry_a is not None:
        zone = fmt_price(entry_a)

    rr = None
    try:
        if None not in (entry_a, entry_b, stop, tp2):
            entry_mid = (float(entry_a) + float(entry_b)) / 2.0
            risk = abs(entry_mid - float(stop))
            reward = abs(float(tp2) - entry_mid)
            if risk > 0:
                rr = reward / risk
    except Exception:
        rr = None

    return {
        "entry_zone": zone,
        "trigger": trigger,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "be": be,
        "rr": rr,
    }


def _snapshot_lines(journal: Optional[Dict[str, Any]]) -> list[str]:
    journal = journal or {}
    decision_snapshot = journal.get("decision_snapshot") or {}
    analysis_snapshot = journal.get("analysis_snapshot") or {}

    if not decision_snapshot and not analysis_snapshot:
        return ["• entry snapshot: не сохранён"]

    lines: list[str] = []

    if decision_snapshot:
        lines.extend([
            f"• entry direction: {decision_snapshot.get('direction_text') or decision_snapshot.get('direction') or 'нет'}",
            f"• entry action: {decision_snapshot.get('action_text') or decision_snapshot.get('action') or 'нет'}",
            f"• entry mode: {decision_snapshot.get('mode') or 'нет'}",
            f"• entry confidence: {round(decision_snapshot.get('confidence_pct') or 0.0, 1)}%",
            f"• entry risk: {decision_snapshot.get('risk_level') or 'нет'}",
        ])

    if analysis_snapshot:
        lines.extend([
            f"• entry signal: {analysis_snapshot.get('signal') or 'нет'}",
            f"• entry forecast: {analysis_snapshot.get('forecast_direction') or 'нет'}",
            f"• entry range_state: {analysis_snapshot.get('range_state') or 'нет'}",
            f"• entry ct_now: {analysis_snapshot.get('ct_now') or 'нет'}",
        ])

    return lines


def build_btc_execution_plan_text(data: Dict[str, Any], journal: Optional[Dict[str, Any]] = None, side: str = "AUTO") -> str:
    timeframe = data.get("timeframe", "1h")
    shift = _build_context_shift(data, journal, side=side)
    action = _execution_action(data, journal, side=side)
    comment = _execution_comment(action)
    decision = _decision(data)

    if shift["side"] not in ("LONG", "SHORT"):
        plan_side = _decision_direction(data)
    else:
        plan_side = shift["side"]
    if plan_side not in ("LONG", "SHORT"):
        plan_side = "WAIT"

    lines = [
        f"🧭 BTC EXECUTION PLAN [{timeframe}]",
        "",
        f"Текущее действие: {action}",
        f"Комментарий: {comment}",
        "",
        "Decision сейчас:",
        f"• direction: {decision.get('direction_text') or decision.get('direction') or 'NONE'}",
        f"• action: {decision.get('action_text') or decision.get('action') or 'WAIT'}",
        f"• manager action: {decision.get('manager_action_text') or decision.get('manager_action') or 'ЖДАТЬ'}",
        f"• position state: {'IN POSITION' if decision.get('has_position') else 'FLAT'}",
        f"• position side: {decision.get('position_side') or 'NONE'}",
        f"• lifecycle state: {decision.get('lifecycle_state') or ((journal or {}).get('lifecycle_state') or 'NO_TRADE')}",
        f"• runner active: {'YES' if (decision.get('runner_active') or (journal or {}).get('runner_active')) else 'NO'}",
        f"• runner mode: {decision.get('runner_mode') or '-'}",
        f"• mode: {decision.get('mode') or 'MIXED'}",
        f"• confidence: {round(decision.get('confidence_pct') or 0.0, 1)}%",
        f"• risk: {decision.get('risk_level') or 'HIGH'}",
        f"• edge score: {round(float(decision.get('edge_score') or 0.0), 1)}% | {str(decision.get('edge_label') or 'NO_EDGE').upper()}",
        f"• edge action: {decision.get('edge_action') or 'WAIT'}",
        f"• manager note: {decision.get('manager_reason') or '-'}",
        "",
        "Сила сторон сейчас:",
        f"• long score: {fmt_pct(calc_long_score(data))}",
        f"• short score: {fmt_pct(calc_short_score(data))}",
        "",
        "Сравнение со входом:",
        *_snapshot_lines(journal),
    ]

    if shift["reasons"]:
        lines.extend(["", "Что изменилось:"])
        lines.extend([f"• {x}" for x in shift["reasons"][:5]])

    trade_plan = _trade_plan_levels(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')

    lines.extend([
        "",
        "TRADE PLAN:",
        f"• entry zone: {trade_plan['entry_zone']}",
        f"• trigger: {trade_plan['trigger']}",
        f"• stop: {fmt_price(trade_plan['stop']) if trade_plan['stop'] is not None else 'нет данных'}",
        f"• TP1: {fmt_price(trade_plan['tp1']) if trade_plan['tp1'] is not None else 'нет данных'}",
        f"• TP2: {fmt_price(trade_plan['tp2']) if trade_plan['tp2'] is not None else 'нет данных'}",
        f"• BE after TP1: {fmt_price(trade_plan['be']) if trade_plan['be'] is not None else 'нет данных'}",
        f"• RR to TP2: {round(float(trade_plan['rr']), 2)}" if trade_plan['rr'] is not None else "• RR to TP2: нет данных",
        "",
        "Тактика:",
        f"• идея входа: {_entry_idea(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• условия входа: {_wait_what_exactly(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• авто-сигнал входа: {_activation_condition(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• бот сам переключит во вход: {_can_auto_flip_to_enter(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• стиль исполнения: {_execution_style_hint(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• partial / фиксация: {_partial_plan(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• re-entry: {_reentry_plan(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• hold: {_hold_plan(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
        f"• invalidation: {_invalidation_line(data, plan_side if plan_side in ('LONG', 'SHORT') else 'WAIT')}",
    ])

    return "\n".join(lines)


def build_btc_invalidation_text(data: Dict[str, Any], journal: Optional[Dict[str, Any]] = None, side: str = "AUTO") -> str:
    timeframe = data.get("timeframe", "1h")
    shift = _build_context_shift(data, journal, side=side)
    working_side = shift["side"] if shift["side"] in ("LONG", "SHORT") else _state(data)

    lines = [
        f"⛔ BTC INVALIDATION [{timeframe}]",
        "",
        f"Рабочая сторона: {working_side if working_side in ('LONG', 'SHORT') else 'WAIT'}",
        f"Главная invalidation-зона: {_invalidation_line(data, working_side if working_side in ('LONG', 'SHORT') else 'WAIT')}",
    ]

    if journal and journal.get("decision_snapshot"):
        lines.extend([
            "",
            "Сравнение со входом:",
            f"• entry direction: {(_entry_snapshot_context(journal)).get('entry_direction') or 'NONE'}",
            f"• now direction: {shift.get('current_direction') or 'NONE'}",
            f"• entry mode: {(_entry_snapshot_context(journal)).get('entry_mode') or 'MIXED'}",
            f"• now mode: {shift.get('current_mode') or 'MIXED'}",
            f"• entry risk: {(_entry_snapshot_context(journal)).get('entry_risk') or 'HIGH'}",
            f"• now risk: {shift.get('current_risk') or 'HIGH'}",
        ])

    if shift["direction_flip"]:
        lines.extend([
            "",
            "Вывод:",
            "• decision engine уже смотрит против позиции",
            "• это сильный сигнал, что сценарий сломан",
        ])
    elif shift["current_direction"] == "NONE":
        lines.extend([
            "",
            "Вывод:",
            "• сценарий не сломан окончательно, но стал менее чистым",
            f"• hold / защита: {_hold_plan(data, working_side if working_side in ('LONG', 'SHORT') else 'WAIT')}",
            "• нужен дополнительный контроль",
        ])

    return "\n".join(lines)


def build_btc_hold_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    shift = _build_context_shift(data, journal, side=side)
    action = _execution_action(data, journal, side=side)

    hold_allowed = action in ("ДЕРЖАТЬ", "ДЕРЖАТЬ АККУРАТНО")
    title = "🟩 HOLD BTC" if hold_allowed else "🟨 HOLD BTC"

    lines = [
        f"{title} [{timeframe}]",
        "",
        f"Решение: {'ДА' if hold_allowed else 'НЕ ИДЕАЛЬНО'}",
        f"Текущее действие: {action}",
        f"Комментарий: {_execution_comment(action)}",
        "",
        f"Сторона: {shift['side'] if shift['side'] in ('LONG', 'SHORT') else 'WAIT'}",
        f"Now direction: {shift['current_direction']}",
        f"Now action: {shift['current_action']}",
        f"Now mode: {shift['current_mode']}",
        f"Now risk: {shift['current_risk']}",
        f"Now confidence: {round((shift['current_confidence'] or 0.0) * 100, 1)}%",
    ]

    if journal and journal.get("decision_snapshot"):
        lines.extend([
            "",
            "Относительно входа:",
            f"• entry direction: {shift['entry_direction']}",
            f"• entry action: {shift['entry_action']}",
            f"• entry mode: {shift['entry_mode']}",
            f"• entry risk: {shift['entry_risk']}",
            f"• entry confidence: {round((shift['entry_confidence'] or 0.0) * 100, 1)}%",
        ])

    if shift["reasons"]:
        lines.extend(["", "Почему:"])
        lines.extend([f"• {x}" for x in shift["reasons"][:4]])

    lines.extend(["", "Тактика hold:", f"• {_hold_plan(data, shift['side'] if shift['side'] in ('LONG', 'SHORT') else 'WAIT')}", f"• partial: {_partial_plan(data, shift['side'] if shift['side'] in ('LONG', 'SHORT') else 'WAIT')}"])

    return "\n".join(lines)


def build_btc_close_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    shift = _build_context_shift(data, journal, side=side)
    action = _execution_action(data, journal, side=side)

    should_close = action == "ЛУЧШЕ ЗАКРЫТЬ" or shift["direction_flip"] or (shift["opposite_pressure"] and shift["risk_worse"])

    lines = [
        f"🟥 CLOSE BTC [{timeframe}]",
        "",
        f"Решение: {'ДА, ЛУЧШЕ ЗАКРЫТЬ' if should_close else 'ПОКА НЕ ОБЯЗАТЕЛЬНО'}",
        f"Текущее действие: {action}",
        "",
        f"Now direction: {shift['current_direction']}",
        f"Now action: {shift['current_action']}",
        f"Now mode: {shift['current_mode']}",
        f"Now risk: {shift['current_risk']}",
        f"Now confidence: {round((shift['current_confidence'] or 0.0) * 100, 1)}%",
    ]

    if journal and journal.get("decision_snapshot"):
        lines.extend([
            "",
            "Сравнение со входом:",
            f"• entry direction: {shift['entry_direction']}",
            f"• entry action: {shift['entry_action']}",
            f"• entry mode: {shift['entry_mode']}",
            f"• entry risk: {shift['entry_risk']}",
            f"• entry confidence: {round((shift['entry_confidence'] or 0.0) * 100, 1)}%",
        ])

    if shift["reasons"]:
        lines.extend(["", "Почему:"])
        lines.extend([f"• {x}" for x in shift["reasons"][:5]])

    lines.extend(["", "После закрытия / partial:", f"• {_reentry_plan(data, shift['side'] if shift['side'] in ('LONG', 'SHORT') else 'WAIT')}", f"• {_partial_plan(data, shift['side'] if shift['side'] in ('LONG', 'SHORT') else 'WAIT')}"])

    if should_close:
        lines.extend([
            "",
            "Вывод:",
            "• текущий контекст заметно слабее точки входа",
            f"• partial/re-entry: {_reentry_plan(data, shift['side'] if shift['side'] in ('LONG', 'SHORT') else 'WAIT')}",
            "• держать позицию дальше уже рискованнее",
        ])
    else:
        lines.extend([
            "",
            "Вывод:",
            "• контекст ухудшился не критично или ещё не сломался окончательно",
            "• закрытие пока не выглядит обязательным",
        ])

    return "\n".join(lines)


def build_btc_wait_text(data: Dict[str, Any], journal: Optional[Dict[str, Any]] = None, side: str = "AUTO") -> str:
    timeframe = data.get("timeframe", "1h")
    shift = _build_context_shift(data, journal, side=side)
    action = _execution_action(data, journal, side=side)

    should_wait = action in ("ЖДАТЬ", "ЖДАТЬ ПОДТВЕРЖДЕНИЕ") or shift["current_direction"] == "NONE"

    lines = [
        f"🟦 WAIT BTC [{timeframe}]",
        "",
        f"Решение: {'ДА, ЛУЧШЕ ПОДОЖДАТЬ' if should_wait else 'НЕТ, ЕСТЬ РАБОЧИЙ СЦЕНАРИЙ'}",
        f"Текущее действие: {action}",
        f"Комментарий: {_execution_comment(action)}",
        "",
        f"Now direction: {shift['current_direction']}",
        f"Now action: {shift['current_action']}",
        f"Now mode: {shift['current_mode']}",
        f"Now risk: {shift['current_risk']}",
        f"Now confidence: {round((shift['current_confidence'] or 0.0) * 100, 1)}%",
        "",
        f"Long score: {fmt_pct(shift['long_score'])}",
        f"Short score: {fmt_pct(shift['short_score'])}",
    ]

    if journal and journal.get("decision_snapshot"):
        lines.extend([
            "",
            "Контекст входа:",
            f"• entry direction: {shift['entry_direction']}",
            f"• entry action: {shift['entry_action']}",
            f"• entry mode: {shift['entry_mode']}",
            f"• entry risk: {shift['entry_risk']}",
        ])

    if shift["reasons"]:
        lines.extend(["", "Почему:"])
        lines.extend([f"• {x}" for x in shift["reasons"][:5]])

    return "\n".join(lines)


__all__ = [
    "build_btc_execution_plan_text",
    "build_btc_invalidation_text",
    "build_btc_hold_text",
    "build_btc_close_text",
    "build_btc_wait_text",
]
