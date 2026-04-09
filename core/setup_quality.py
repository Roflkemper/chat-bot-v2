from __future__ import annotations

from typing import Any, Dict, Optional

from core.import_compat import normalize_direction, to_float
from core.btc_plan import calc_long_score, calc_short_score, fmt_pct, fmt_price
from core.market_structure import analyze_market_structure


GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "NO TRADE": 1}


def _decision(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("decision") or {}


def _pick_side(data: Dict[str, Any], side: str = "AUTO") -> str:
    requested = str(side or "AUTO").upper()
    if requested in ("LONG", "SHORT"):
        return requested
    decision = _decision(data)
    raw = str(decision.get("direction") or "").upper()
    if raw in ("LONG", "SHORT"):
        return raw
    ls = calc_long_score(data)
    ss = calc_short_score(data)
    if ls >= ss + 0.10:
        return "LONG"
    if ss >= ls + 0.10:
        return "SHORT"
    return "WAIT"


def _invalidation_type(side: str, structure: Dict[str, Any], price: float | None, low: float | None, mid: float | None, high: float | None) -> str:
    if structure.get("structure_break"):
        return "structure_break"
    if side == "LONG":
        if low is not None and price is not None and price < low:
            return "level_break"
        if mid is not None and price is not None and price < mid:
            return "momentum_fail"
    elif side == "SHORT":
        if high is not None and price is not None and price > high:
            return "level_break"
        if mid is not None and price is not None and price > mid:
            return "momentum_fail"
    return "context_fail"


def _execution_mode_from_grade(grade: str, decision_mode: str, trap_risk: str) -> str:
    decision_mode = str(decision_mode or "MIXED").upper()
    if grade == "A" and trap_risk == "LOW":
        return "aggressive"
    if grade in ("A", "B"):
        return "balanced"
    if grade in ("C", "D"):
        return "conservative"
    return "defensive" if decision_mode == "RANGE" else "conservative"


def _entry_type_from_context(side: str, structure: Dict[str, Any], setup_status: str, score_gap: float) -> str:
    status = str(structure.get("status") or "NEUTRAL").upper()
    if side not in ("LONG", "SHORT"):
        return "no_trade"
    if setup_status == "LATE":
        return "no_trade"
    if setup_status == "EARLY":
        return "wait_confirmation"
    if status in ("BOS_UP", "BOS_DOWN") and score_gap >= 0.10:
        return "breakout"
    if status in ("HOLDING_UP", "HOLDING_DOWN"):
        return "pullback"
    if structure.get("choch_risk"):
        return "reversal"
    return "selective"


def analyze_setup_quality(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    journal = journal or {}
    decision = _decision(data)
    picked = _pick_side(data, side=side)
    structure = analyze_market_structure(data, side=picked if picked in ("LONG", "SHORT") else None, journal=journal)
    price = to_float(data.get("price"))
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))

    long_score = calc_long_score(data)
    short_score = calc_short_score(data)
    side_score = long_score if picked == "LONG" else short_score if picked == "SHORT" else max(long_score, short_score)
    opp_score = short_score if picked == "LONG" else long_score if picked == "SHORT" else min(long_score, short_score)
    score_gap = max(0.0, side_score - opp_score)

    forecast = normalize_direction(data.get("forecast_direction"))
    action = str(decision.get("action") or "WAIT").upper()
    risk = str(decision.get("risk_level") or decision.get("risk") or "HIGH").upper()
    direction = str(decision.get("direction") or "NONE").upper()
    market_state = str(decision.get("market_state") or "UNKNOWN").upper()
    market_state_text = str(decision.get("market_state_text") or market_state).upper()
    base_setup_status = str(decision.get("setup_status") or "WAIT").upper()
    base_setup_status_text = str(decision.get("setup_status_text") or "ЖДАТЬ")
    late_entry_risk = str(decision.get("late_entry_risk") or "HIGH").upper()
    location_quality = str(decision.get("location_quality") or "C").upper()
    trap_risk = str(decision.get("trap_risk") or "MEDIUM").upper()
    decision_entry_type = str(decision.get("entry_type") or "no_trade")
    decision_exec_mode = str(decision.get("execution_mode") or "conservative")
    breakout_risk = str(decision.get("breakout_risk") or "LOW").upper()
    false_break_signal = str(decision.get("false_break_signal") or "NONE").upper()
    edge_bias = str(decision.get("edge_bias") or "NONE").upper()

    total = 0.0
    positives: list[str] = []
    blockers: list[str] = []
    next_conditions: list[str] = []

    if picked == "WAIT":
        blockers.append("нет чистого directional перевеса для нового входа")
    else:
        if direction == picked:
            total += 2.0
            positives.append("decision engine смотрит в ту же сторону")
        elif direction == "NONE":
            blockers.append("decision engine пока не даёт чистого направления")
        else:
            blockers.append("decision engine сейчас против этого входа")
            total -= 2.0

        if market_state == "BIASED":
            total += 1.5
            positives.append("рынок даёт рабочий bias, а не просто шум")
        elif market_state == "NEUTRAL":
            blockers.append("рынок без явного перевеса")
            total -= 0.7
        elif market_state == "CONFLICTED":
            blockers.append("между факторами есть конфликт")
            total -= 1.8
        else:
            blockers.append("данных для чистого сетапа пока маловато")
            total -= 1.0

        if action == "ENTER":
            total += 2.0
            positives.append("decision action уже позволяет искать вход")
        elif action in ("WATCH", "WAIT_CONFIRMATION"):
            total += 0.8
            positives.append("идея есть, но нужен confirm before entry")
            next_conditions.append("дождаться подтверждающей свечи или retest-реакции")
        else:
            blockers.append("decision action пока не подтверждает вход")
            total -= 1.0

        if risk == "LOW":
            total += 2.0
            positives.append("risk level низкий")
        elif risk == "MID":
            total += 0.8
            positives.append("risk level умеренный")
        else:
            blockers.append("risk level высокий")
            total -= 1.2

        status = str(structure.get("status") or "NEUTRAL").upper()
        cq = str(structure.get("continuation_quality") or "MID").upper()
        if structure.get("structure_break"):
            blockers.append("structure break уже сломал идею входа")
            total -= 2.5
        elif status.startswith("BOS") and ((picked == "LONG" and status == "BOS_UP") or (picked == "SHORT" and status == "BOS_DOWN")):
            total += 1.8
            positives.append("структура уже подтверждает движение в сторону входа")
        elif status.startswith("HOLDING"):
            total += 1.2
            positives.append("базовая структура пока держится")
        elif structure.get("choch_risk"):
            blockers.append("есть CHOCH risk против входа")
            total -= 0.8
            next_conditions.append("дождаться снятия CHOCH риска или возврата структуры")

        if cq == "HIGH":
            total += 1.5
        elif cq == "GOOD":
            total += 1.0
        elif cq == "LOW":
            total -= 1.5

        if location_quality == "A":
            total += 1.4
            positives.append("локация для входа очень хорошая")
        elif location_quality == "B":
            total += 0.8
            positives.append("локация для входа приемлемая")
        elif location_quality == "D":
            total -= 1.5
            blockers.append("локация для входа плохая")
        else:
            blockers.append("локация средняя — запас по качеству ограничен")
            total -= 0.3

        if trap_risk == "LOW":
            total += 0.8
            positives.append("ловушка сейчас маловероятна")
        elif trap_risk == "HIGH":
            total -= 1.6
            blockers.append("ловушка / trap risk высокий")
            next_conditions.append("не заходить без явного подтверждения продолжения")

        if breakout_risk == "HIGH" and location_quality in ("C", "D"):
            total -= 0.8
            blockers.append("край диапазона выглядит как риск ложного пробоя, а не как clean entry")
        elif false_break_signal != "NONE" and decision_entry_type == "reversal":
            total += 0.9
            positives.append("есть сигнал на trap/reversal у края диапазона")

        if picked == "LONG" and edge_bias == "SHORT_EDGE":
            total -= 0.8
            blockers.append("лонг идёт против edge-контекста диапазона")
        elif picked == "SHORT" and edge_bias == "LONG_EDGE":
            total -= 0.8
            blockers.append("шорт идёт против edge-контекста диапазона")

        if late_entry_risk == "LOW":
            total += 0.8
            positives.append("вход пока не выглядит запоздалым")
        elif late_entry_risk == "MEDIUM":
            total -= 0.1
        else:
            total -= 1.2
            blockers.append("вход выглядит поздним")
            next_conditions.append("нужен откат или новая безопасная точка входа")

        if score_gap >= 0.18:
            total += 2.0
            positives.append("перевес по score уже сильный")
        elif score_gap >= 0.10:
            total += 1.0
            positives.append("по score есть нормальный запас над противоположной стороной")
        elif score_gap < 0.06:
            blockers.append("score gap слишком маленький")
            total -= 1.0

        if picked == "LONG":
            if forecast == "ЛОНГ":
                total += 0.8
                positives.append("forecast подтверждает long bias")
            elif forecast == "ШОРТ":
                blockers.append("forecast смотрит против long entry")
                total -= 0.8
            if low is not None and mid is not None and price is not None:
                if price <= mid:
                    total += 1.0
                    positives.append("цена ещё не выглядит слишком вытянутой вверх")
                elif high is not None and price >= high:
                    blockers.append("цена уже у/выше range high — вход может быть запоздалым")
                    total -= 0.6
        elif picked == "SHORT":
            if forecast == "ШОРТ":
                total += 0.8
                positives.append("forecast подтверждает short bias")
            elif forecast == "ЛОНГ":
                blockers.append("forecast смотрит против short entry")
                total -= 0.8
            if high is not None and mid is not None and price is not None:
                if price >= mid:
                    total += 1.0
                    positives.append("цена ещё не выглядит слишком вытянутой вниз")
                elif low is not None and price <= low:
                    blockers.append("цена уже у/ниже range low — вход может быть запоздалым")
                    total -= 0.6

    hard_fail = any(x for x in blockers if any(k in x for k in ["против", "structure break", "нет чистого directional", "не даёт чистого направления"]))
    invalidation_type = _invalidation_type(picked, structure, price, low, mid, high)

    if picked == "WAIT" or hard_fail:
        grade = "NO TRADE"
        entry_status = "BLOCK"
    elif total >= 9.0 and risk != "HIGH" and trap_risk != "HIGH" and late_entry_risk == "LOW":
        grade = "A"
        entry_status = "READY"
    elif total >= 6.5 and trap_risk != "HIGH":
        grade = "B"
        entry_status = "WAIT_CONFIRMATION" if action != "ENTER" else "READY"
    elif total >= 4.0:
        grade = "C"
        entry_status = "LIGHT / SELECTIVE"
    elif total >= 2.0:
        grade = "D"
        entry_status = "SMALL / REACTIVE"
    else:
        grade = "NO TRADE"
        entry_status = "BLOCK"

    if market_state == "CONFLICTED" and grade in ("A", "B"):
        grade = "C"
        entry_status = "WAIT_CONFIRMATION"
    if late_entry_risk == "HIGH" and grade == "A":
        grade = "B"
        entry_status = "WAIT_CONFIRMATION"
    if trap_risk == "HIGH" and GRADE_ORDER.get(grade, 0) > GRADE_ORDER["C"]:
        grade = "C"
        entry_status = "WAIT_CONFIRMATION"
    if base_setup_status == "INVALID":
        grade = "NO TRADE"
        entry_status = "BLOCK"
    elif base_setup_status == "LATE" and grade in ("A", "B"):
        grade = "C"
        entry_status = "LIGHT / SELECTIVE"
    elif base_setup_status == "EARLY" and grade == "A":
        grade = "B"
        entry_status = "WAIT_CONFIRMATION"

    setup_valid = grade in ("A", "B") and entry_status in ("READY", "WAIT_CONFIRMATION")
    if grade == "NO TRADE":
        setup_status = "INVALID"
        setup_status_text = "ПРОПУСТИТЬ"
    elif late_entry_risk == "HIGH":
        setup_status = "LATE"
        setup_status_text = "ПОЗДНИЙ / НЕ ГНАТЬСЯ"
    elif entry_status == "READY":
        setup_status = "VALID"
        setup_status_text = "СЕТАП ВАЛИДЕН"
    elif entry_status == "WAIT_CONFIRMATION":
        setup_status = "EARLY"
        setup_status_text = "НУЖНО ПОДТВЕРЖДЕНИЕ"
    else:
        setup_status = "SELECTIVE"
        setup_status_text = "ТОЛЬКО ВЫБОРОЧНО"

    entry_type = _entry_type_from_context(picked, structure, setup_status, score_gap)
    execution_mode = _execution_mode_from_grade(grade, decision.get("mode"), trap_risk)

    if picked == "LONG":
        trigger_zone = fmt_price(mid if mid is not None else low if low is not None else price)
        invalidation = fmt_price(low if low is not None else mid if mid is not None else price)
        entry_style = "continuation long" if structure.get("status") in ("BOS_UP", "HOLDING_UP") else "selective long"
    elif picked == "SHORT":
        trigger_zone = fmt_price(mid if mid is not None else high if high is not None else price)
        invalidation = fmt_price(high if high is not None else mid if mid is not None else price)
        entry_style = "continuation short" if structure.get("status") in ("BOS_DOWN", "HOLDING_DOWN") else "selective short"
    else:
        trigger_zone = "не определено"
        invalidation = "не определено"
        entry_style = "wait"

    summary = {
        "A": "сетап выглядит качественно: можно искать аккуратный вход без погони",
        "B": "идея рабочая, но лучше дождаться подтверждения и не форсировать entry",
        "C": "сетап средний: вход только выборочно и через жёсткий риск-контроль",
        "D": "сетап слабый: только реактивный маленький риск или полный пропуск",
        "NO TRADE": "сетап сейчас лучше пропустить — фильтр входа не даёт чистого качества",
    }[grade]

    if not next_conditions and grade in ("B", "C", "D"):
        next_conditions.append("дождаться более чистого перевеса по score и структуре")
    if grade == "NO TRADE" and not next_conditions:
        next_conditions.append("не открывать новую позицию до нормализации market state")

    return {
        "side": picked,
        "grade": grade,
        "entry_status": entry_status,
        "setup_valid": setup_valid,
        "setup_status": setup_status,
        "setup_status_text": setup_status_text,
        "score_total": round(total, 2),
        "summary": summary,
        "entry_style": entry_style,
        "entry_type": entry_type,
        "execution_mode": execution_mode,
        "trigger_zone": trigger_zone,
        "invalidation": invalidation,
        "invalidation_type": invalidation_type,
        "late_entry_risk": late_entry_risk,
        "location_quality": location_quality,
        "trap_risk": trap_risk,
        "market_state": market_state,
        "market_state_text": market_state_text,
        "base_setup_status": base_setup_status,
        "base_setup_status_text": base_setup_status_text,
        "decision_entry_type": decision_entry_type,
        "decision_execution_mode": decision_exec_mode,
        "positives": positives,
        "blockers": blockers,
        "next_conditions": next_conditions,
        "score_gap": score_gap,
        "side_score": side_score,
        "opp_score": opp_score,
        "decision_direction": direction,
        "decision_action": action,
        "risk": risk,
        "forecast": forecast,
        "structure": structure,
    }


def build_btc_setup_quality_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    snap = analyze_setup_quality(data, side=side, journal=journal)
    structure = snap.get("structure") or {}
    lines = [
        f"🎯 BTC SETUP QUALITY [{timeframe}]",
        "",
        f"Setup side: {snap['side']}",
        f"Grade: {snap['grade']}",
        f"Setup valid: {'да' if snap['setup_valid'] else 'нет'}",
        f"Entry filter status: {snap['entry_status']}",
        f"Setup status: {snap['setup_status_text']}",
        f"Setup score: {snap['score_total']}",
        "",
        f"Коротко: {snap['summary']}",
        f"Entry style: {snap['entry_style']}",
        f"Entry type: {snap['entry_type']}",
        f"Execution mode: {snap['execution_mode']}",
        f"Trigger zone: {snap['trigger_zone']}",
        f"Invalidation: {snap['invalidation']} ({snap['invalidation_type']})",
        "",
        "Что поддерживает вход:",
    ]
    if snap['positives']:
        lines.extend([f"• {x}" for x in snap['positives'][:6]])
    else:
        lines.append("• сейчас нет факторов, которые собирают качественный новый entry")
    lines.extend([
        "",
        "Что блокирует или ухудшает вход:",
    ])
    if snap['blockers']:
        lines.extend([f"• {x}" for x in snap['blockers'][:6]])
    else:
        lines.append("• жёстких блокеров сейчас не видно")
    lines.extend([
        "",
        "Что должно измениться для входа:",
    ])
    if snap['next_conditions']:
        lines.extend([f"• {x}" for x in snap['next_conditions'][:5]])
    else:
        lines.append("• текущий сетап уже не требует дополнительных условий")
    lines.extend([
        "",
        "Снимок фильтров:",
        f"• market state: {snap.get('market_state_text')}",
        f"• decision setup status: {snap.get('base_setup_status_text')}",
        f"• decision direction: {normalize_direction((data.get('decision') or {}).get('direction_text') or snap.get('decision_direction'))}",
        f"• decision action: {(data.get('decision') or {}).get('action_text') or snap.get('decision_action')}",
        f"• risk: {snap.get('risk')}",
        f"• forecast: {snap.get('forecast')}",
        f"• location quality: {snap.get('location_quality')}",
        f"• late entry risk: {snap.get('late_entry_risk')}",
        f"• trap risk: {snap.get('trap_risk')}",
        f"• side score: {fmt_pct(snap.get('side_score'))}",
        f"• opposite score: {fmt_pct(snap.get('opp_score'))}",
        f"• score gap: {fmt_pct(snap.get('score_gap'))}",
        f"• structure status: {structure.get('status')}",
        f"• continuation quality: {structure.get('continuation_quality')}",
        f"• CHOCH risk: {'да' if structure.get('choch_risk') else 'нет'}",
        f"• structure break: {'да' if structure.get('structure_break') else 'нет'}",
        "",
        "Логика v8.6:",
        "• A — качественный сетап, можно искать вход аккуратно и без погони",
        "• B — идея нормальная, но лучше дождаться confirm / retest / clean trigger",
        "• C — сетап средний, вход только выборочно и с жёстким риском",
        "• D — слабый сетап, только реактивный маленький риск",
        "• NO TRADE — фильтр входа говорит пропустить сетап",
    ])
    return "\n".join(lines)


__all__ = ["analyze_setup_quality", "build_btc_setup_quality_text"]
