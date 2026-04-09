from __future__ import annotations

from typing import Any, Dict, Optional

from core.btc_plan import calc_long_score, calc_short_score, fmt_pct, fmt_price
from core.trade_manager import _management_snapshot, _state as _manager_state, _trailing_snapshot
from core.market_structure import analyze_market_structure
from core.import_compat import normalize_direction


def _side_from_journal_or_market(data: Dict[str, Any], journal: Optional[Dict[str, Any]]) -> str:
    for raw in ((journal or {}).get("side"), _manager_state(data), (data.get("decision") or {}).get("direction")):
        side = str(raw or "").upper()
        if side in ("LONG", "SHORT"):
            return side
    return "WAIT"


def _active_exit_classifier(snapshot: Dict[str, Any]) -> str:
    action = snapshot.get("primary_action")
    shift = snapshot.get("shift") or {}
    if action in ("ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ", "ЛУЧШЕ ЗАКРЫТЬ"):
        if shift.get("direction_flip"):
            return "STRUCTURE_BREAK"
        if shift.get("opposite_pressure"):
            return "OPPOSITE_PRESSURE"
        return "RISK_OFF"
    if action == "ЧАСТИЧНО ФИКСИРОВАТЬ":
        return "PROTECT_PROFIT"
    if action == "ПЕРЕНЕСТИ В BE":
        return "BREAKEVEN_PROTECTION"
    if action == "ТЯНУТЬ ОСТАТОК":
        return "RUNNER_MANAGEMENT"
    if action == "ДЕРЖАТЬ":
        return "HOLD_CONTINUATION"
    return "WAIT_CONFIRMATION"


def _active_exit_quality(snapshot: Dict[str, Any], journal: Optional[Dict[str, Any]]) -> str:
    flags = {
        "tp1": bool((journal or {}).get("tp1_hit")),
        "tp2": bool((journal or {}).get("tp2_hit")),
        "be": bool((journal or {}).get("be_moved")),
        "partial": bool((journal or {}).get("partial_exit_done")),
    }
    action = snapshot.get("primary_action")
    if action == "ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ" and flags["tp2"]:
        return "STRONG"
    if action in ("ЧАСТИЧНО ФИКСИРОВАТЬ", "ПЕРЕНЕСТИ В BE", "ТЯНУТЬ ОСТАТОК") and (flags["tp1"] or flags["be"] or flags["partial"]):
        return "GOOD"
    if action == "ДЕРЖАТЬ":
        return "GOOD"
    if action == "ЖДАТЬ":
        return "MID"
    if action == "ЛУЧШЕ ЗАКРЫТЬ":
        return "WEAK"
    return "MID"


def _closed_exit_quality(journal: Optional[Dict[str, Any]]) -> str:
    journal = journal or {}
    result_pct = journal.get("result_pct")
    try:
        result_pct = float(result_pct) if result_pct is not None else None
    except Exception:
        result_pct = None
    if result_pct is None:
        return "UNKNOWN"
    if result_pct >= 2.0:
        return "STRONG"
    if result_pct >= 0.5:
        return "GOOD"
    if result_pct >= -0.2:
        return "OK"
    if result_pct >= -1.0:
        return "WEAK"
    return "BAD"


def _closed_reason_classifier(journal: Optional[Dict[str, Any]]) -> str:
    journal = journal or {}
    stored = journal.get("exit_reason_classifier")
    if stored:
        return str(stored)
    reason = str(journal.get("close_reason") or "").lower()
    if "tp2" in reason or reason == "target_completed":
        return "TARGET_COMPLETED"
    if "manual" in reason or "button" in reason:
        return "MANUAL_EXIT"
    result_pct = journal.get("result_pct")
    try:
        result_pct = float(result_pct) if result_pct is not None else None
    except Exception:
        result_pct = None
    if result_pct is not None and result_pct < 0:
        return "STOP_OR_INVALIDATION"
    if journal.get("partial_exit_done") or journal.get("be_moved"):
        return "PROTECTED_MANAGEMENT_EXIT"
    return "UNKNOWN"


def _closed_summary(journal: Optional[Dict[str, Any]]) -> str:
    journal = journal or {}
    return str(journal.get("post_trade_summary") or "Итог сделки ещё не сформирован.")


def build_btc_smart_exit_text(data: Dict[str, Any], journal: Optional[Dict[str, Any]] = None) -> str:
    journal = journal or {}
    timeframe = data.get("timeframe", "1h")
    price = fmt_price(data.get("price"))
    decision = data.get("decision") or {}

    if journal.get("closed"):
        quality = _closed_exit_quality(journal)
        classifier = _closed_reason_classifier(journal)
        lines = [
            f"🚪 BTC SMART EXIT [{timeframe}]",
            "",
            "Статус: сделка уже закрыта",
            f"Exit quality: {quality}",
            f"Exit reason classifier: {classifier}",
            f"Exit price: {fmt_price(journal.get('exit_price'))}",
            f"Result pct: {fmt_pct(journal.get('result_pct')) if journal.get('result_pct') is not None else 'нет'}",
            f"Result rr: {journal.get('result_rr') if journal.get('result_rr') is not None else 'нет'}",
            f"Holding time: {journal.get('holding_time_minutes') if journal.get('holding_time_minutes') is not None else 'нет'} min",
            "",
            "Post-trade summary:",
            _closed_summary(journal),
        ]
        return "\n".join(lines)

    side = _side_from_journal_or_market(data, journal)
    if side == "WAIT":
        return "\n".join([
            f"🚪 BTC SMART EXIT [{timeframe}]",
            "",
            "Сейчас нет активной понятной стороны для exit-логики.",
            f"Цена: {price}",
            f"Long score: {fmt_pct(calc_long_score(data))}",
            f"Short score: {fmt_pct(calc_short_score(data))}",
            "Вывод: сначала нужен понятный вход или активная позиция.",
        ])

    snapshot = _management_snapshot(side, data, journal)
    classifier = _active_exit_classifier(snapshot)
    quality = _active_exit_quality(snapshot, journal)
    shift = snapshot.get("shift") or {}
    structure = analyze_market_structure(data, side=side, journal=journal)

    if snapshot["hard_close"]:
        exit_now = "close now"
    elif snapshot["reduce"]:
        exit_now = "reduce now"
    elif snapshot["hold"]:
        exit_now = "hold"
    else:
        exit_now = "wait / confirm"

    why = list(snapshot.get("why_now") or [])
    if shift.get("direction_flip"):
        why.append("decision engine уже смотрит против позиции")
    elif shift.get("opposite_pressure"):
        why.append("противоположная сторона усилилась и давит на сделку")
    elif snapshot["trail"]:
        why.append("позиция уже в режиме защиты остатка, а не агрессивного удержания")

    lines = [
        f"🚪 BTC SMART EXIT [{timeframe}]",
        "",
        f"Сторона: {side}",
        f"Цена сейчас: {price}",
        f"Exit verdict: {exit_now}",
        f"Exit quality now: {quality}",
        f"Exit reason classifier: {classifier}",
        f"Urgency: {snapshot['urgency']}",
        f"Recommended partial size: {snapshot['partial_size_pct']}%",
        "",
        f"Главное действие: {snapshot['primary_action']}",
        f"Следующий шаг: {snapshot['next_step']}",
        "",
        "Почему именно такой exit:",
    ]
    lines.extend([f"• {item}" for item in why[:5]])
    trail = _trailing_snapshot(side, data, journal)
    lines.extend([
        "",
        "Control flags:",
        f"• close now: {'да' if snapshot['hard_close'] else 'нет'}",
        f"• reduce now: {'да' if snapshot['reduce'] else 'нет'}",
        f"• partial size now: {snapshot['partial_size_pct']}%",
        f"• hold allowed: {'да' if snapshot['hold'] else 'нет'}",
        f"• BE protection: {'да' if snapshot['protect'] else 'нет'}",
        f"• trailing mode: {'да' if snapshot['trail'] else 'нет'}",
        f"• trailing stage: {trail.get('stage')}",
        f"• trailing action now: {trail.get('action_now')}",
        f"• trailing next level: {trail.get('next_level')}",
        f"• structure status: {structure.get('status')}",
        f"• continuation quality: {structure.get('continuation_quality')}",
        f"• CHOCH risk: {'да' if structure.get('choch_risk') else 'нет'}",
        "",
        "Decision snapshot now:",
        f"• direction: {decision.get('direction_text') or decision.get('direction') or 'NONE'}",
        f"• action: {decision.get('action_text') or decision.get('action') or 'WAIT'}",
        f"• risk: {decision.get('risk_level') or 'HIGH'}",
        f"• confidence: {round(decision.get('confidence_pct') or 0.0, 1)}%",
        f"• forecast: {normalize_direction(data.get('forecast_direction'))}",
    ])
    return "\n".join(lines)


__all__ = ["build_btc_smart_exit_text"]
