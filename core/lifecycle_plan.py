from __future__ import annotations

from typing import Any, Dict, Optional

from core.import_compat import normalize_direction, to_float
from core.btc_plan import calc_long_score, calc_short_score, fmt_pct, fmt_price
from core.trade_manager import _management_snapshot, _state as _manager_state, _trailing_snapshot
from core.setup_quality import analyze_setup_quality
from core.confluence_engine import analyze_confluence
from core.market_structure import analyze_market_structure


def _decision(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("decision") or {}


def _side_from_context(data: Dict[str, Any], position: Optional[Dict[str, Any]], journal: Optional[Dict[str, Any]]) -> str:
    for raw in (
        (position or {}).get("side"),
        (journal or {}).get("side"),
        _decision(data).get("direction"),
        _manager_state(data),
    ):
        side = str(raw or "").upper()
        if side in ("LONG", "SHORT"):
            return side
    return "WAIT"


def _stage(position: Optional[Dict[str, Any]], journal: Optional[Dict[str, Any]]) -> str:
    position = position or {}
    journal = journal or {}
    lifecycle_state = str(journal.get("lifecycle_state") or "").upper()
    if lifecycle_state == "EXIT" or journal.get("closed"):
        return "EXIT"
    if lifecycle_state in ("TP1", "PARTIAL_DONE", "BE_MOVED", "HOLD_RUNNER"):
        return "MANAGE"
    if lifecycle_state == "ENTRY":
        return "MANAGE" if (position.get("has_position") or journal.get("has_active_trade")) else "ENTRY"
    if position.get("has_position") or journal.get("has_active_trade"):
        return "MANAGE"
    return "ENTRY"


def _entry_block(data: Dict[str, Any], side: str) -> Dict[str, Any]:
    decision = _decision(data)
    action = str(decision.get("action_text") or decision.get("action") or "WAIT").upper()
    risk = str(decision.get("risk_level") or "HIGH").upper()
    direction_text = decision.get("direction_text") or normalize_direction(data.get("final_decision")) or side
    confidence_pct = round(decision.get("confidence_pct") or 0.0, 1)

    if side not in ("LONG", "SHORT"):
        return {
            "headline": "ЖДАТЬ",
            "urgency": "LOW",
            "summary": "Сейчас нет достаточно чистого перевеса для нового входа.",
            "next_step": "не форсировать вход, дождаться более собранного decision-контекста",
            "why": [
                f"лонг-сила: {fmt_pct(calc_long_score(data))}",
                f"шорт-сила: {fmt_pct(calc_short_score(data))}",
                "направление пока недостаточно чистое",
            ],
        }

    if action == "ENTER" and risk == "LOW":
        headline = f"ИСКАТЬ {side} ВХОД"
        urgency = "MID"
        summary = f"Есть рабочий сценарий на {direction_text.lower()} с контролируемым риском."
        next_step = f"искать аккуратный {side.lower()}-вход без погони за ценой"
    elif action in ("WATCH", "WAIT_CONFIRMATION"):
        headline = "ЖДАТЬ ПОДТВЕРЖДЕНИЕ"
        urgency = "LOW"
        summary = f"Идея в сторону {direction_text.lower()} есть, но вход лучше не форсировать."
        next_step = "дождаться подтверждения и только потом открывать позицию"
    else:
        headline = "ЖДАТЬ"
        urgency = "LOW"
        summary = "Decision engine пока не даёт чистого входа."
        next_step = "наблюдать, не открывать позицию против слабого контекста"

    why = [
        f"decision direction: {direction_text}",
        f"decision action: {decision.get('action_text') or decision.get('action') or 'WAIT'}",
        f"decision risk: {risk}",
        f"decision confidence: {confidence_pct}%",
    ]

    return {
        "headline": headline,
        "urgency": urgency,
        "summary": summary,
        "next_step": next_step,
        "why": why,
    }


def _manage_block(data: Dict[str, Any], side: str, journal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    snapshot = _management_snapshot(side, data, journal)
    action = snapshot["primary_action"]
    mapping = {
        "ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ": "EXIT",
        "ЛУЧШЕ ЗАКРЫТЬ": "EXIT",
        "ЧАСТИЧНО ФИКСИРОВАТЬ": "MANAGE",
        "ПЕРЕНЕСТИ В BE": "MANAGE",
        "ТЯНУТЬ ОСТАТОК": "MANAGE",
        "ДЕРЖАТЬ": "MANAGE",
        "ЖДАТЬ": "MANAGE",
    }
    next_phase = mapping.get(action, "MANAGE")
    return {
        "headline": action,
        "urgency": snapshot["urgency"],
        "summary": snapshot["next_step"],
        "next_step": snapshot["next_step"],
        "why": snapshot["why_now"],
        "next_phase": next_phase,
        "flags": {
            "hold": snapshot["hold"],
            "reduce": snapshot["reduce"],
            "protect": snapshot["protect"],
            "trail": snapshot["trail"],
            "close": snapshot["hard_close"],
        },
        "partial_size_pct": snapshot["partial_size_pct"],
        "partial_size_comment": snapshot["partial_size_comment"],
    }


def _exit_block(data: Dict[str, Any], journal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    journal = journal or {}
    close_ctx = journal.get("close_context_snapshot") or {}
    decision = close_ctx.get("decision") or {}
    result_pct = journal.get("result_pct")
    result_rr = journal.get("result_rr")
    holding = journal.get("holding_time_minutes")

    lines = [
        f"close reason: {journal.get('close_reason') or 'нет'}",
        f"exit price: {fmt_price(journal.get('exit_price'))}",
        f"result pct: {fmt_pct(result_pct) if result_pct is not None else 'нет'}",
        f"result rr: {result_rr if result_rr is not None else 'нет'}",
    ]
    if holding is not None:
        lines.append(f"holding time: {holding} min")
    if close_ctx:
        lines.append(f"close signal: {close_ctx.get('signal') or 'нет'}")
        lines.append(f"close forecast: {close_ctx.get('forecast_direction') or 'нет'}")
        lines.append(f"close decision action: {decision.get('action_text') or decision.get('action') or 'нет'}")

    return {
        "headline": "СДЕЛКА ЗАКРЫТА",
        "urgency": "LOW",
        "summary": "Lifecycle дошёл до этапа EXIT, финальные метрики уже записаны в journal.",
        "next_step": "оценить результат сделки и ждать новый качественный ENTRY",
        "why": lines,
    }



def build_btc_lifecycle_text(data: Dict[str, Any], position: Optional[Dict[str, Any]] = None, journal: Optional[Dict[str, Any]] = None) -> str:
    position = position or {}
    journal = journal or {}

    stage = _stage(position, journal)
    side = _side_from_context(data, position, journal)
    timeframe = data.get("timeframe", "1h")
    price = fmt_price(data.get("price"))

    if stage == "ENTRY":
        block = _entry_block(data, side)
        setup = analyze_setup_quality(data, side=side, journal=journal)
    elif stage == "MANAGE":
        if side not in ("LONG", "SHORT"):
            side = str((journal or {}).get("side") or (position or {}).get("side") or "WAIT").upper()
        block = _manage_block(data, side, journal)
        setup = analyze_setup_quality(data, side=side, journal=journal)
    else:
        block = _exit_block(data, journal)
        setup = analyze_setup_quality(data, side=side, journal=journal)

    lifecycle_state = str(journal.get("lifecycle_state") or ("ENTRY" if stage == "ENTRY" else "NO_TRADE")).upper()
    history = journal.get("lifecycle_history") or []
    lines = [
        f"🔄 BTC LIFECYCLE [{timeframe}]",
        "",
        f"Стадия сейчас: {stage}",
        f"Lifecycle state: {lifecycle_state}",
        f"Сторона: {side}",
        f"Цена сейчас: {price}",
        f"Главное действие: {block['headline']}",
        f"Срочность: {block['urgency']}",
        "",
        f"Коротко: {block['summary']}",
        f"Следующий шаг: {block['next_step']}",
        "",
        "Почему:",
    ]
    lines.extend([f"• {x}" for x in block.get("why", [])])

    if history:
        recent = history[-4:]
        lines.extend(["", "Последние переходы state machine:"])
        for item in recent:
            note = f" | {item.get('note')}" if item.get('note') else ""
            lines.append(f"• {item.get('state')} @ {item.get('at')}{note}")

    if stage == "ENTRY":
        lines.extend([
            "",
            "Setup quality v8.5:",
            f"• grade: {setup.get('grade')}",
            f"• entry filter status: {setup.get('entry_status')}",
            f"• setup score: {setup.get('score_total')}",
            f"• entry style: {setup.get('entry_style')}",
            f"• trigger zone: {setup.get('trigger_zone')}",
            f"• invalidation: {setup.get('invalidation')}",
        ])

    if stage == "ENTRY":
        lines.extend([
            "",
            "Переходы lifecycle:",
            "• ENTRY → TP1: после первого подтверждённого целевого хода",
            "• TP1 → PARTIAL_DONE: после первой частичной фиксации",
            "• PARTIAL_DONE → BE_MOVED: после переноса остатка в безубыток",
            "• BE_MOVED → HOLD_RUNNER: держать остаток только пока структура жива",
            "• HOLD_RUNNER → EXIT: финальный выход по слому, цели или ручному закрытию",
        ])
    elif stage == "MANAGE":
        flags = block.get("flags") or {}
        trail = _trailing_snapshot(side, data, journal)
        lines.extend([
            "",
            f"Runner active: {'да' if (journal or {}).get('runner_active') else 'нет'}",
            f"Runner mode: {((data.get('decision') or {}).get('runner_mode') or '-')}",
            "",
            "Флаги управления:",
            f"• hold allowed: {'да' if flags.get('hold') else 'нет'}",
            f"• partial reduce now: {'да' if flags.get('reduce') else 'нет'}",
            f"• BE protection now: {'да' if flags.get('protect') else 'нет'}",
            f"• trailing mode now: {'да' if flags.get('trail') else 'нет'}",
            f"• close now: {'да' if flags.get('close') else 'нет'}",
            f"• recommended partial size: {block.get('partial_size_pct')}%",
            f"• partial size logic: {block.get('partial_size_comment')}",
            f"• trailing stage: {trail.get('stage')}",
            f"• trailing action now: {trail.get('action_now')}",
            f"• trailing next level: {trail.get('next_level')}",
            "",
            "Переходы lifecycle:",
            "• MANAGE → EXIT: при явном сломе контекста, финальном close или достижении финальных целей",
            "• MANAGE → MANAGE: пока позиция ещё жива и её нужно вести дальше",
        ])
    else:
        lines.extend([
            "",
            "Переходы lifecycle:",
            "• EXIT → ENTRY: только после нового чистого сетапа",
            "• EXIT → WAIT: если новый перевес пока не собрался",
        ])

    if position.get("has_position"):
        lines.extend([
            "",
            "Позиция:",
            f"• entry price: {fmt_price(position.get('entry_price'))}",
            f"• opened at: {position.get('opened_at') or 'нет'}",
        ])
    elif journal.get("entry_price") is not None:
        lines.extend([
            "",
            "История сделки:",
            f"• entry price: {fmt_price(journal.get('entry_price'))}",
            f"• opened at: {journal.get('opened_at') or 'нет'}",
        ])

    decision = _decision(data)
    structure = analyze_market_structure(data, side=journal.get("side") if isinstance(journal, dict) else None, journal=journal)
    confluence = analyze_confluence(data, side=side, journal=journal)
    lines.extend([
        "",
        "Decision snapshot now:",
        f"• direction: {decision.get('direction_text') or decision.get('direction') or 'NONE'}",
        f"• action: {decision.get('action_text') or decision.get('action') or 'WAIT'}",
        f"• mode: {decision.get('mode') or 'MIXED'}",
        f"• risk: {decision.get('risk_level') or 'HIGH'}",
        f"• confidence: {round(decision.get('confidence_pct') or 0.0, 1)}%",
        f"• long score: {fmt_pct(calc_long_score(data))}",
        f"• short score: {fmt_pct(calc_short_score(data))}",
        "",
        "Setup filter snapshot v8.5:",
        f"• grade: {setup.get('grade')}",
        f"• entry filter status: {setup.get('entry_status')}",
        f"• setup score: {setup.get('score_total')}",
        "",
        "Structure snapshot v8.4:",
        f"• status: {structure.get('status')}",
        f"• continuation quality: {structure.get('continuation_quality')}",
        f"• structure break: {'да' if structure.get('structure_break') else 'нет'}",
        f"• CHOCH risk: {'да' if structure.get('choch_risk') else 'нет'}",
        "",
        "Confluence snapshot v8.6:",
        f"• conviction: {confluence.get('conviction')}",
        f"• final score: {confluence.get('score')}/100",
        f"• action bias: {confluence.get('action_bias')}",
        f"• summary: {confluence.get('summary')}",
    ])

    return "\n".join(lines)


__all__ = ["build_btc_lifecycle_text"]
