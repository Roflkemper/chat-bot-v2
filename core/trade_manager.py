from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.import_compat import normalize_direction, to_float
from core.market_structure import analyze_market_structure
from core.setup_quality import analyze_setup_quality
from core.trade_flow import build_trade_flow_summary
from core.liquidation_character import analyze_fast_move
from core.execution_advisor import evaluate_entry_window
from core.confluence_engine import analyze_confluence
from core.tactical_edge import build_tactical_edge
from core.ux_mode import build_ultra_wait_block, is_no_trade_context
from core.priority_engine import build_priority_context
from core.market_phase_engine import classify_market_phase
from core.btc_plan import calc_long_score, calc_short_score, fmt_pct, fmt_price


def _state(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    decision_direction = str(decision.get("direction") or "").upper()

    if decision_direction in ("LONG", "SHORT"):
        return decision_direction

    long_score = calc_long_score(data)
    short_score = calc_short_score(data)

    if long_score >= short_score + 0.12:
        return "LONG"
    if short_score >= long_score + 0.12:
        return "SHORT"
    return "WAIT"


def _get_levels(data: Dict[str, Any]) -> Tuple[float | None, float | None, float | None, float | None]:
    return (
        to_float(data.get("price")),
        to_float(data.get("range_low")),
        to_float(data.get("range_mid")),
        to_float(data.get("range_high")),
    )


def _long_targets(data: Dict[str, Any]) -> Tuple[str, str]:
    price, _, _, high = _get_levels(data)
    if high is not None:
        return fmt_price(high), fmt_price(high * 1.005)
    if price is not None:
        return fmt_price(price * 1.008), fmt_price(price * 1.015)
    return "не указано", "не указано"


def _short_targets(data: Dict[str, Any]) -> Tuple[str, str]:
    price, low, _, _ = _get_levels(data)
    if low is not None:
        return fmt_price(low), fmt_price(low * 0.995)
    if price is not None:
        return fmt_price(price * 0.992), fmt_price(price * 0.985)
    return "не указано", "не указано"


def _be_level_long(data: Dict[str, Any]) -> str:
    price, _, mid, _ = _get_levels(data)
    return fmt_price(mid if mid is not None else price)


def _be_level_short(data: Dict[str, Any]) -> str:
    price, _, mid, _ = _get_levels(data)
    return fmt_price(mid if mid is not None else price)


def _trail_anchor_long(data: Dict[str, Any]) -> str:
    _, low, mid, _ = _get_levels(data)
    return fmt_price(mid if mid is not None else low)


def _trail_anchor_short(data: Dict[str, Any]) -> str:
    _, _, mid, high = _get_levels(data)
    return fmt_price(mid if mid is not None else high)


def _journal_flags(journal: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    journal = journal or {}
    return {
        "has_trade": bool(journal.get("trade_id")),
        "active": bool(journal.get("has_active_trade")),
        "tp1_hit": bool(journal.get("tp1_hit")),
        "tp2_hit": bool(journal.get("tp2_hit")),
        "be_moved": bool(journal.get("be_moved")),
        "partial_exit_done": bool(journal.get("partial_exit_done")),
        "closed": bool(journal.get("closed")),
    }




def _has_open_manual_bot_state(data: Dict[str, Any]) -> bool:
    for card in (data.get("bot_cards") or []):
        if isinstance(card, dict) and bool(card.get("position_open")):
            return True
    return bool(data.get("position_open"))


def _open_position_state_line(journal: Optional[Dict[str, Any]], data: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    if journal and journal.get("trade_id"):
        return "journal / tracked trade"
    if _has_open_manual_bot_state(data) or str(snapshot.get("stage") or "").upper() not in {"", "WAIT", "NONE"}:
        return "manual bot-state / external open position"
    return "none"

def _journal_lines(journal: Optional[Dict[str, Any]]) -> list[str]:
    if not journal or not journal.get("trade_id"):
        return ["• journal: нет активной журнальной записи"]

    flags = _journal_flags(journal)
    decision_snapshot = journal.get("decision_snapshot") or {}
    analysis_snapshot = journal.get("analysis_snapshot") or {}

    lines = [
        f"• journal id: {journal.get('trade_id')}",
        f"• journal status: {journal.get('status')}",
        f"• tp1_hit: {flags['tp1_hit']}",
        f"• tp2_hit: {flags['tp2_hit']}",
        f"• be_moved: {flags['be_moved']}",
        f"• partial_exit_done: {flags['partial_exit_done']}",
    ]

    if decision_snapshot:
        lines.extend([
            f"• entry decision: {decision_snapshot.get('direction_text') or decision_snapshot.get('direction') or 'нет'}",
            f"• entry action: {decision_snapshot.get('action_text') or decision_snapshot.get('action') or 'нет'}",
            f"• entry mode: {decision_snapshot.get('mode') or 'нет'}",
            f"• entry confidence: {round(decision_snapshot.get('confidence_pct') or 0.0, 1)}%",
        ])

    if analysis_snapshot:
        lines.extend([
            f"• entry signal: {analysis_snapshot.get('signal') or 'нет'}",
            f"• entry forecast: {analysis_snapshot.get('forecast_direction') or 'нет'}",
            f"• entry range_state: {analysis_snapshot.get('range_state') or 'нет'}",
        ])

    return lines




def _setup_stats_lines(data: Dict[str, Any]) -> list[str]:
    stats = data.get("setup_stats") if isinstance(data.get("setup_stats"), dict) else {}
    adj = data.get("setup_stats_adjustment") if isinstance(data.get("setup_stats_adjustment"), dict) else {}
    exec_plan = data.get("learning_execution_plan") if isinstance(data.get("learning_execution_plan"), dict) else {}
    if not stats:
        return ["• learning engine: нет данных"]
    lines = [
        f"• summary: {stats.get('summary') or 'нет данных'}",
        f"• favored side: {stats.get('favored_side') or 'NEUTRAL'}",
        f"• current family: {str(stats.get('current_family') or 'UNKNOWN').replace('_', ' ')}",
        f"• recent closed: {int(stats.get('closed_trades_recent') or 0)} | win {round(float(stats.get('recent_winrate') or 0.0) * 100, 1)}% | avg RR {float(stats.get('recent_avg_rr') or 0.0):.2f}",
    ]
    active = stats.get('active_bot') if isinstance(stats.get('active_bot'), dict) else {}
    if active:
        lines.append(
            f"• active bot history: {active.get('bot_label') or active.get('bot_key')} | samples {int(active.get('samples') or 0)} | win {round(float(active.get('winrate') or 0.0) * 100, 1)}% | avg RR {float(active.get('avg_rr') or 0.0):.2f}"
        )
    active_family = stats.get('active_family') if isinstance(stats.get('active_family'), dict) else {}
    if active_family:
        lines.append(
            f"• active family: {active_family.get('label') or active_family.get('family')} | samples {int(active_family.get('samples') or 0)} | win {round(float(active_family.get('winrate') or 0.0) * 100, 1)}% | avg RR {float(active_family.get('avg_rr') or 0.0):.2f}"
        )
        lines.append(f"• failure profile: {active_family.get('failure_profile') or 'нет данных'}")
    best = stats.get('strongest_family') if isinstance(stats.get('strongest_family'), dict) else {}
    if best:
        lines.append(
            f"• strongest family: {best.get('label') or best.get('family')} | hold quality {float(best.get('hold_quality') or 0.0):.1f}m | avg RR {float(best.get('avg_rr') or 0.0):.2f}"
        )
    weak = stats.get('weakest_family') if isinstance(stats.get('weakest_family'), dict) else {}
    if weak:
        lines.append(
            f"• weakest family: {weak.get('label') or weak.get('family')} | avg RR {float(weak.get('avg_rr') or 0.0):.2f} | win {round(float(weak.get('winrate') or 0.0) * 100, 1)}%"
        )
    if adj and abs(float(adj.get('delta') or 0.0)) >= 0.005:
        sign = '+' if float(adj.get('delta') or 0.0) >= 0 else ''
        lines.append(f"• adjustment: {sign}{float(adj.get('delta') or 0.0) * 100:.1f}% | aggression {adj.get('aggressiveness') or 'NEUTRAL'}")
    if exec_plan:
        lines.extend([
            f"• action posture: {exec_plan.get('posture') or 'NEUTRAL'}",
            f"• size mode: {exec_plan.get('size_mode') or 'x1.00'}",
            f"• execution map: {exec_plan.get('execution') or 'STANDARD'}",
            f"• top family: {exec_plan.get('strongest_family_label') or 'нет данных'}",
            f"• avoid family: {exec_plan.get('weakest_family_label') or 'нет данных'}",
            f"• summary: {exec_plan.get('summary') or 'нет данных'}",
        ])
        for reason in (exec_plan.get('reasons') or [])[:2]:
            lines.append(f"• {reason}")
    return lines

def _entry_context_line(journal: Optional[Dict[str, Any]]) -> str:
    return fmt_price(journal.get("entry_price")) if journal and journal.get("trade_id") else "не сохранён"


def _decision_direction(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    raw = str(decision.get("direction") or "").upper()
    if raw in ("LONG", "SHORT", "NONE"):
        return raw

    state = _state(data)
    if state in ("LONG", "SHORT"):
        return state
    return "NONE"


def _decision_action(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    raw = str(decision.get("action") or "").upper()
    if raw:
        return raw
    side = _state(data)
    if side == "WAIT":
        return "WAIT"
    return "WATCH"


def _decision_mode(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    return str(decision.get("mode") or "MIXED").upper()


def _decision_risk(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    return str(decision.get("risk_level") or decision.get("risk") or "HIGH").upper()




def _decision_trap_risk(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    return str(decision.get("trap_risk") or "MEDIUM").upper()


def _decision_breakout_risk(data: Dict[str, Any]) -> str:
    decision = data.get("decision") or {}
    return str(decision.get("breakout_risk") or "LOW").upper()



def _normalize_confidence_pct(value: Any) -> float:
    num = to_float(value)
    if num is None:
        return 0.0
    num = float(num)
    if 0.0 <= num <= 1.0:
        num *= 100.0
    return max(0.0, min(num, 100.0))

def _decision_confidence(data: Dict[str, Any]) -> float:
    decision = data.get("decision") or {}
    value = decision.get("final_confidence")
    if value is None:
        value = decision.get("confidence_pct")
    if value is None:
        value = decision.get("confidence")
    num = to_float(value)
    if num is not None:
        return _normalize_confidence_pct(num)
    long_score = calc_long_score(data)
    short_score = calc_short_score(data)
    return _normalize_confidence_pct(max(long_score, short_score))


def _entry_snapshot_context(journal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    journal = journal or {}
    decision_snapshot = journal.get("decision_snapshot") or {}
    analysis_snapshot = journal.get("analysis_snapshot") or {}

    entry_direction = str(decision_snapshot.get("direction") or "").upper()
    if entry_direction not in ("LONG", "SHORT", "NONE"):
        nd = normalize_direction(analysis_snapshot.get("final_decision"))
        if nd == "ЛОНГ":
            entry_direction = "LONG"
        elif nd == "ШОРТ":
            entry_direction = "SHORT"
        else:
            entry_direction = "NONE"

    entry_action = str(decision_snapshot.get("action") or "").upper() or "WAIT"
    entry_mode = str(decision_snapshot.get("mode") or "").upper() or "MIXED"
    entry_risk = str(decision_snapshot.get("risk_level") or "").upper() or "HIGH"
    entry_confidence = decision_snapshot.get("final_confidence")
    if entry_confidence is None:
        entry_confidence = decision_snapshot.get("confidence_pct")
    if entry_confidence is None:
        entry_confidence = decision_snapshot.get("confidence")
    entry_confidence = _normalize_confidence_pct(entry_confidence)

    return {
        "entry_direction": entry_direction,
        "entry_action": entry_action,
        "entry_mode": entry_mode,
        "entry_risk": entry_risk,
        "entry_confidence": float(entry_confidence),
        "decision_snapshot": decision_snapshot,
        "analysis_snapshot": analysis_snapshot,
    }


def _risk_rank(level: str) -> int:
    mapping = {"LOW": 1, "MID": 2, "HIGH": 3}
    return mapping.get(str(level or "").upper(), 3)


def _build_context_shift(side: str, data: Dict[str, Any], journal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    side = side.upper()
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
    else:
        side_score_now = short_score
        opp_score_now = long_score

    direction_flip = current_direction not in (side, "NONE")
    action_weaker = current_action in ("WAIT",)
    confidence_drop = entry_confidence > 0 and current_confidence <= max(entry_confidence - 0.18, 0.35)
    opposite_pressure = opp_score_now >= side_score_now + 0.12
    risk_worse = _risk_rank(current_risk) > _risk_rank(entry_risk)
    mode_changed_against = entry_mode != "MIXED" and current_mode != entry_mode and current_direction not in (side,)

    reasons: list[str] = []

    if entry_direction == side and current_direction == side:
        reasons.append("базовое направление сделки пока не сломано")
    elif current_direction == "NONE":
        reasons.append("сейчас у рынка нет такого же чистого перевеса, как на входе")
    elif direction_flip:
        reasons.append("decision engine теперь смотрит в противоположную сторону")

    if action_weaker:
        reasons.append("текущее действие decision engine — ждать, а не держать агрессивно")
    if confidence_drop:
        reasons.append("уверенность стала слабее, чем была на входе")
    if opposite_pressure:
        reasons.append("противоположная сторона усилилась")
    if risk_worse:
        reasons.append("текущий риск стал хуже относительно точки входа")
    if mode_changed_against:
        reasons.append("режим рынка изменился относительно точки входа")

    return {
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
        "side_score_now": side_score_now,
        "opp_score_now": opp_score_now,
        "direction_flip": direction_flip,
        "action_weaker": action_weaker,
        "confidence_drop": confidence_drop,
        "opposite_pressure": opposite_pressure,
        "risk_worse": risk_worse,
        "mode_changed_against": mode_changed_against,
        "reasons": reasons,
    }


def _structure_warning(side: str, data: Dict[str, Any]) -> str:
    side = side.upper()
    price, low, mid, high = _get_levels(data)
    if price is None:
        return "структура неясна: нет цены"
    if side == "LONG":
        if low is not None and price < low:
            return "лонг-структура уже сломана ниже range low"
        if mid is not None and price < mid:
            return "цена ушла ниже range mid: лонг ослаб"
        return "цена держится выше ключевой середины range"
    if side == "SHORT":
        if high is not None and price > high:
            return "шорт-структура уже сломана выше range high"
        if mid is not None and price > mid:
            return "цена ушла выше range mid: шорт ослаб"
        return "цена держится ниже ключевой середины range"
    return "структура нейтральна"


def _momentum_warning(side: str, shift: Dict[str, Any]) -> str:
    side = side.upper()
    signals = []
    if shift.get("direction_flip"):
        signals.append("decision engine развернулся против позиции")
    if shift.get("opposite_pressure"):
        signals.append("противоположная сторона усилилась")
    if shift.get("confidence_drop"):
        signals.append("confidence заметно просела")
    if shift.get("action_weaker"):
        signals.append("агрессивного продолжения уже нет")
    if not signals:
        return f"momentum по стороне {side} пока не выглядит сломанным"
    return "; ".join(signals[:3])


def _recommended_partial_size_pct(side: str, data: Dict[str, Any], journal: Optional[Dict[str, Any]], setup: Dict[str, Any]) -> int:
    flags = _journal_flags(journal)
    shift = _build_context_shift(side, data, journal)

    if flags["tp2_hit"] or shift["direction_flip"] or setup.get("invalidation_type") == "structure_break":
        return 100
    if setup.get("trap_risk") == "HIGH" or (shift["opposite_pressure"] and shift["risk_worse"]):
        return 50
    if shift["opposite_pressure"] or shift["confidence_drop"] or shift["risk_worse"]:
        return 50
    if flags["tp1_hit"] and not flags["partial_exit_done"]:
        return 33
    if shift["current_direction"] == side and shift["current_action"] in ("WATCH", "WAIT_CONFIRMATION"):
        return 25
    return 25


def _partial_size_comment(size_pct: int) -> str:
    mapping = {
        25: "лёгкая разгрузка: фиксируем немного, чтобы не убивать сильный сценарий",
        33: "базовая частичная фиксация после первого подтверждённого хода",
        50: "агрессивнее режем размер, потому что контекст уже заметно хуже",
        100: "частичный выход уже неактуален — логичнее закрывать всё",
    }
    return mapping.get(int(size_pct or 25), "размер фиксации выбираем аккуратно по силе контекста")


def _management_stage_label(primary_action: str, flags: Dict[str, bool], trade_flow: Optional[Dict[str, Any]] = None) -> str:
    trade_flow = trade_flow or {}
    flow_state = str(trade_flow.get("continuation_state") or "").upper()
    if primary_action in {"ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ", "ЛУЧШЕ ЗАКРЫТЬ"}:
        return "EXIT"
    if primary_action == "ЧАСТИЧНО ФИКСИРОВАТЬ":
        return "REDUCE"
    if primary_action == "ПЕРЕНЕСТИ В BE":
        return "PROTECT"
    if primary_action == "ТЯНУТЬ ОСТАТОК":
        return "RUNNER"
    if primary_action == "ДЕРЖАТЬ АККУРАТНО":
        return "HOLD CAREFUL"
    if primary_action == "ДЕРЖАТЬ":
        return "HOLD"
    if flags.get("tp1_hit") and flow_state == "ALIVE":
        return "RUNNER"
    return "WAIT"


def _management_priority_lines(snapshot: Dict[str, Any], trade_flow: Optional[Dict[str, Any]] = None, execution: Optional[Dict[str, Any]] = None) -> list[str]:
    trade_flow = trade_flow or {}
    execution = execution or {}
    action = str(snapshot.get("primary_action") or "ЖДАТЬ")
    if action == "ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ":
        first = "закрыть сделку полностью"
    elif action == "ЛУЧШЕ ЗАКРЫТЬ":
        first = "сократить риск и готовить выход"
    elif action == "ЧАСТИЧНО ФИКСИРОВАТЬ":
        first = f"снять {int(snapshot.get('partial_size_pct') or 25)}% позиции"
    elif action == "ПЕРЕНЕСТИ В BE":
        first = "перевести stop в безубыток"
    elif action == "ТЯНУТЬ ОСТАТОК":
        first = "оставить только runner и тащить остаток"
    elif action == "ДЕРЖАТЬ АККУРАТНО":
        first = "держать без добора и не расширять риск"
    elif action == "ДЕРЖАТЬ":
        first = "держать базовый сценарий без суеты"
    else:
        first = "ждать новый триггер"

    second = str(snapshot.get("next_step") or "дождаться следующего подтверждения")
    third = str(trade_flow.get("movement_comment") or execution.get("comment") or "контекст нужно подтверждать дальше")
    fourth = str(execution.get("action_now") or "ЖДАТЬ")
    return [first, second, third, fourth]


def _action_forbidden_text(snapshot: Dict[str, Any], execution: Optional[Dict[str, Any]] = None, setup: Optional[Dict[str, Any]] = None) -> str:
    execution = execution or {}
    setup = setup or {}
    trap = str(setup.get("trap_risk") or "").upper()
    late = str(setup.get("late_entry_risk") or "").upper()
    chase = str(execution.get("chase_risk") or "").upper()
    action = str(snapshot.get("primary_action") or "")
    if action in {"ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ", "ЛУЧШЕ ЗАКРЫТЬ"}:
        return "не пересиживать и не усреднять против ухудшившегося контекста"
    if action == "ЧАСТИЧНО ФИКСИРОВАТЬ":
        return "не добавляться в позицию до нового clean trigger"
    if chase == "HIGH" or late == "HIGH":
        return "не входить в догонку и не расширять размер на эмоциях"
    if trap == "HIGH":
        return "не доверять первому импульсу без reclaim / retest"
    return "не форсировать добор без нового подтверждения"


def _management_decision(
    side: str,
    data: Dict[str, Any],
    journal: Optional[Dict[str, Any]],
    setup: Dict[str, Any],
    trade_flow: Optional[Dict[str, Any]] = None,
    execution: Optional[Dict[str, Any]] = None,
) -> str:
    flags = _journal_flags(journal)
    side = side.upper()
    trade_flow = trade_flow or {}
    execution = execution or {}

    if flags["tp2_hit"]:
        return "ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ"
    if setup.get("invalidation_type") in ("structure_break", "level_break"):
        return "ЛУЧШЕ ЗАКРЫТЬ"
    if setup.get("grade") == "NO TRADE" and setup.get("trap_risk") == "HIGH":
        return "ЛУЧШЕ ЗАКРЫТЬ"

    shift = _build_context_shift(side, data, journal)
    flow_state = str(trade_flow.get("continuation_state") or "").upper()
    mgmt_state = str(trade_flow.get("management_state") or "").upper()
    move_type = str((analyze_fast_move(data) or {}).get("move_type") or "").upper()
    chase_risk = str(execution.get("chase_risk") or "").upper()

    if shift["direction_flip"]:
        return "ЛУЧШЕ ЗАКРЫТЬ"

    if flow_state in {"EXHAUSTED", "POSSIBLE_FALSE_BREAK"}:
        if flags["tp1_hit"]:
            return "ЛУЧШЕ ЗАКРЫТЬ"
        return "ЧАСТИЧНО ФИКСИРОВАТЬ" if move_type in {"FALSE_BREAK", "LIQUIDITY_SWEEP"} else "ЖДАТЬ"

    if shift["current_direction"] == "NONE" and shift["current_action"] == "WAIT":
        if flags["tp1_hit"]:
            return "ТЯНУТЬ ОСТАТОК" if flags["be_moved"] else "ПЕРЕНЕСТИ В BE"
        return "ЖДАТЬ"

    if shift["opposite_pressure"] and shift["risk_worse"]:
        return "ЛУЧШЕ ЗАКРЫТЬ"

    if flags["tp1_hit"] and flags["be_moved"] and flags["partial_exit_done"]:
        return "ТЯНУТЬ ОСТАТОК"

    if flags["tp1_hit"] and not flags["be_moved"]:
        return "ПЕРЕНЕСТИ В BE"

    if flags["tp1_hit"] and not flags["partial_exit_done"]:
        return "ЧАСТИЧНО ФИКСИРОВАТЬ"

    if setup.get("trap_risk") == "HIGH" and setup.get("late_entry_risk") == "HIGH":
        return "ЧАСТИЧНО ФИКСИРОВАТЬ"

    if shift["current_direction"] == side:
        if mgmt_state == "HOLD STRONG" and setup.get("setup_valid") and shift["current_action"] == "ENTER" and shift["current_risk"] == "LOW":
            return "ДЕРЖАТЬ"
        if mgmt_state == "PARTIAL TAKE":
            return "ЧАСТИЧНО ФИКСИРОВАТЬ"
        if mgmt_state == "HOLD CAREFULLY":
            return "ДЕРЖАТЬ АККУРАТНО"
        if mgmt_state == "EXIT ON WEAKNESS":
            return "ЧАСТИЧНО ФИКСИРОВАТЬ"
        if chase_risk == "HIGH" and not flags["tp1_hit"]:
            return "ЖДАТЬ"
        if shift["current_action"] in ("WATCH", "WAIT_CONFIRMATION"):
            return "ЖДАТЬ"
        if shift["risk_worse"] or shift["confidence_drop"] or setup.get("grade") in ("D", "NO TRADE"):
            return "ЧАСТИЧНО ФИКСИРОВАТЬ"
        return "ДЕРЖАТЬ"

    if shift["current_direction"] == "NONE":
        if shift["opposite_pressure"]:
            return "ЧАСТИЧНО ФИКСИРОВАТЬ"
        return "ЖДАТЬ"

    return "ЖДАТЬ"


def _management_snapshot(side: str, data: Dict[str, Any], journal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    flags = _journal_flags(journal)
    setup = analyze_setup_quality(data, side=side, journal=journal)
    shift = _build_context_shift(side, data, journal)
    trade_flow = build_trade_flow_summary(data)
    execution = evaluate_entry_window(data)
    primary_action = _management_decision(side, data, journal, setup, trade_flow=trade_flow, execution=execution)

    hard_close = bool(
        shift["direction_flip"]
        or (shift["opposite_pressure"] and shift["risk_worse"])
        or flags["tp2_hit"]
        or setup.get("invalidation_type") in ("structure_break", "level_break")
        or (setup.get("grade") == "NO TRADE" and setup.get("trap_risk") == "HIGH")
    )
    reduce = primary_action == "ЧАСТИЧНО ФИКСИРОВАТЬ"
    protect = primary_action == "ПЕРЕНЕСТИ В BE" or (flags["tp1_hit"] and not flags["be_moved"])
    trail = flags["be_moved"] or primary_action == "ТЯНУТЬ ОСТАТОК"
    hold = primary_action in ("ДЕРЖАТЬ", "ТЯНУТЬ ОСТАТОК")

    if hard_close:
        urgency = "HIGH"
    elif reduce or protect:
        urgency = "MID"
    elif hold:
        urgency = "LOW"
    else:
        urgency = "MID"

    if primary_action == "ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ":
        next_step = "закрыть сделку полностью и записать финальный close в journal"
    elif primary_action == "ЛУЧШЕ ЗАКРЫТЬ":
        next_step = "сократить риск сразу: либо ручной close, либо быстрое подтверждение выхода"
    elif primary_action == "ЧАСТИЧНО ФИКСИРОВАТЬ":
        next_step = "снять часть позиции, остаток защитить через BE/trailing"
    elif primary_action == "ПЕРЕНЕСТИ В BE":
        next_step = "перевести stop в безубыток и дальше смотреть реакцию у TP2"
    elif primary_action == "ТЯНУТЬ ОСТАТОК":
        next_step = "держать только остаток позиции и подтягивать защиту по мере движения"
    elif primary_action == "ДЕРЖАТЬ":
        next_step = "ничего не форсировать: держать и не расширять риск"
    else:
        next_step = "дождаться подтверждения перед следующим действием"

    why_now = [
        _structure_warning(side, data),
        _momentum_warning(side, shift),
        f"setup grade: {setup.get('grade')} / status: {setup.get('setup_status_text')}",
        f"trap risk: {setup.get('trap_risk')} / late entry: {setup.get('late_entry_risk')}",
    ]
    if setup.get("invalidation_type") in ("structure_break", "level_break"):
        why_now.append(f"триггер отмены уже рядом: {setup.get('invalidation_type')}")
    elif shift.get("risk_worse"):
        why_now.append("риск-профиль хуже, чем на входе")
    elif shift.get("current_risk") == "LOW":
        why_now.append("риск пока остаётся контролируемым")

    partial_size_pct = _recommended_partial_size_pct(side, data, journal, setup)
    structure = analyze_market_structure(data, side=side, journal=journal)

    return {
        "primary_action": primary_action,
        "urgency": urgency,
        "hard_close": hard_close,
        "reduce": reduce,
        "protect": protect,
        "trail": trail,
        "hold": hold,
        "shift": shift,
        "next_step": next_step,
        "why_now": why_now,
        "partial_size_pct": partial_size_pct,
        "partial_size_comment": _partial_size_comment(partial_size_pct),
        "stage": _management_stage_label(primary_action, flags, trade_flow),
        "priority_lines": _management_priority_lines({"primary_action": primary_action, "partial_size_pct": partial_size_pct, "next_step": next_step}, trade_flow, execution),
        "forbidden_text": _action_forbidden_text({"primary_action": primary_action}, execution, setup),
        "trade_flow": trade_flow,
        "execution": execution,
        "structure": structure,
        "setup": setup,
    }


def _management_comment(action: str) -> str:
    return {
        "ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ": "цели почти исчерпаны, и сделку уже логично завершать",
        "ЛУЧШЕ ЗАКРЫТЬ": "контекст после входа заметно ухудшился, и удержание позиции стало слабее",
        "ТЯНУТЬ ОСТАТОК": "часть сделки уже защищена, поэтому остаток логично вести дальше",
        "ПЕРЕНЕСТИ В BE": "после первого результата сделку уже лучше защищать безубытком",
        "ЧАСТИЧНО ФИКСИРОВАТЬ": "перевес ещё не полностью сломан, но часть позиции разумно разгрузить",
        "ДЕРЖАТЬ": "текущий контекст всё ещё поддерживает позицию",
        "ЖДАТЬ": "сейчас лучше не форсировать действия и дождаться более чистого подтверждения",
    }.get(action, "лучше дождаться дополнительного подтверждения")


def _shift_lines(side: str, data: Dict[str, Any], journal: Optional[Dict[str, Any]]) -> list[str]:
    shift = _build_context_shift(side, data, journal)

    lines = [
        f"• entry direction: {shift['entry_direction'] or 'NONE'}",
        f"• now direction: {shift['current_direction'] or 'NONE'}",
        f"• entry action: {shift['entry_action'] or 'WAIT'}",
        f"• now action: {shift['current_action'] or 'WAIT'}",
        f"• entry mode: {shift['entry_mode'] or 'MIXED'}",
        f"• now mode: {shift['current_mode'] or 'MIXED'}",
        f"• entry risk: {shift['entry_risk'] or 'HIGH'}",
        f"• now risk: {shift['current_risk'] or 'HIGH'}",
        f"• entry confidence: {round(_normalize_confidence_pct(shift['entry_confidence']), 1)}%",
        f"• now confidence: {round(_normalize_confidence_pct(shift['current_confidence']), 1)}%",
    ]

    if shift["reasons"]:
        lines.append("• context shift:")
        for reason in shift["reasons"][:4]:
            lines.append(f"  - {reason}")
    else:
        lines.append("• context shift: заметного ухудшения относительно входа не видно")

    return lines


def build_btc_tp_plan_text(data: Dict[str, Any], side: str = "AUTO") -> str:
    timeframe = data.get("timeframe", "1h")
    side = side.upper() if side != "AUTO" else _state(data)

    if side == "LONG":
        tp1, tp2 = _long_targets(data)
    elif side == "SHORT":
        tp1, tp2 = _short_targets(data)
    else:
        return "\n".join([f"🎯 BTC TP PLAN [{timeframe}]", "", "Сейчас нет сильного направленного преимущества."])

    return "\n".join([f"🎯 BTC TP PLAN [{side}] [{timeframe}]", "", f"TP1: {tp1}", f"TP2: {tp2}"])


def build_btc_be_plan_text(data: Dict[str, Any], side: str = "AUTO") -> str:
    timeframe = data.get("timeframe", "1h")
    side = side.upper() if side != "AUTO" else _state(data)

    if side == "LONG":
        be = _be_level_long(data)
    elif side == "SHORT":
        be = _be_level_short(data)
    else:
        return "\n".join([f"🛡 BTC BE PLAN [{timeframe}]", "", "Сейчас нет понятной стороны для переноса в безубыток."])

    return "\n".join([f"🛡 BTC BE PLAN [{side}] [{timeframe}]", "", f"BE level: {be}"])



def _trailing_snapshot(side: str, data: Dict[str, Any], journal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    side = str(side or "WAIT").upper()
    if side not in ("LONG", "SHORT"):
        return {
            "stage": "INACTIVE",
            "action_now": "WAIT",
            "next_level": "не указано",
            "anchor": "не указано",
            "reason": "нет активной стороны для trailing",
        }

    flags = _journal_flags(journal)
    snapshot = _management_snapshot(side, data, journal)
    setup = snapshot.get("setup") or {}

    anchor = _trail_anchor_long(data) if side == "LONG" else _trail_anchor_short(data)
    tp1, tp2 = _long_targets(data) if side == "LONG" else _short_targets(data)

    if snapshot.get("hard_close"):
        stage = "EXIT"
        action_now = "CLOSE"
        next_level = fmt_price(data.get("price"))
        reason = "контекст сломан или риск уже слишком высокий"
    elif flags.get("tp2_hit"):
        stage = "FINAL"
        action_now = "LOCK_PROFIT"
        next_level = tp2
        reason = "финальная цель уже достигнута"
    elif snapshot.get("trail") or flags.get("be_moved"):
        stage = "TRAILING"
        action_now = "TRAIL"
        next_level = anchor
        reason = "позиция уже в режиме защиты остатка"
    elif snapshot.get("protect") or flags.get("tp1_hit"):
        stage = "BREAKEVEN"
        action_now = "MOVE_BE"
        next_level = _be_level_long(data) if side == "LONG" else _be_level_short(data)
        reason = "после первого результата логично защищать позицию"
    elif snapshot.get("hold"):
        stage = "HOLD"
        action_now = "HOLD"
        next_level = tp1
        reason = "позицию пока можно держать без форсирования выхода"
    else:
        stage = "WAIT"
        action_now = "WAIT_CONFIRMATION"
        next_level = anchor
        reason = "нет чистого сигнала для активного trailing"

    if setup.get("invalidation") not in (None, "", "не указано"):
        next_level = fmt_price(setup.get("invalidation")) if isinstance(setup.get("invalidation"), (int, float)) else str(setup.get("invalidation"))

    return {
        "stage": stage,
        "action_now": action_now,
        "next_level": next_level,
        "anchor": anchor,
        "reason": reason,
    }

def build_btc_trailing_plan_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    side = side.upper() if side != "AUTO" else _state(data)

    if side == "WAIT":
        return "\n".join([f"🧭 BTC TRAILING PLAN [{timeframe}]", "", "Сейчас нет сильной стороны для нормального trailing."])

    trail_anchor = _trail_anchor_long(data) if side == "LONG" else _trail_anchor_short(data)
    snapshot = _management_snapshot(side, data, journal)
    return "\n".join([
        f"🧭 BTC TRAILING PLAN [{timeframe}]",
        "",
        f"Сторона: {side}",
        f"Trailing now: {'да' if snapshot['trail'] else 'нет'}",
        f"Anchor: {trail_anchor}",
        f"Action: {snapshot['primary_action']}",
        f"Urgency: {snapshot['urgency']}",
    ])



def build_btc_trailing_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    return build_btc_trailing_plan_text(data, side=side, journal=journal)

def build_btc_partial_exit_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    side = side.upper() if side != "AUTO" else _state(data)

    if side == "WAIT":
        decision = data.get("decision") or {}
        action = str(decision.get("action_text") or decision.get("action") or "WAIT").upper()
        return "\n".join([
            f"✂️ BTC PARTIAL EXIT [{timeframe}]",
            "",
            "• статус: NO POSITION",
            f"• действие: {action}",
            "• причина: активной позиции нет, partial не нужен",
        ])

    snapshot = _management_snapshot(side, data, journal)
    setup = snapshot.get("setup") or {}
    flags = snapshot.get("flags") or {}

    if snapshot.get("hard_close"):
        action_now = "EXIT"
        reason = "сценарий сломан, partial пропускаем"
    elif flags.get("partial_exit_done"):
        action_now = "HOLD RUNNER"
        reason = "часть уже зафиксирована, держим остаток"
    elif snapshot.get("protect") or flags.get("tp1_hit") or snapshot.get("rr_now", 0) >= 1.0:
        action_now = "PARTIAL"
        reason = "цель TP1/1R достигнута, можно фиксировать часть"
    else:
        action_now = "WAIT"
        reason = "до partial ещё нет подтверждения"

    lines = [
        f"✂️ BTC PARTIAL EXIT [{timeframe}]",
        "",
        f"• сторона: {side}",
        f"• действие: {action_now}",
        f"• причина: {reason}",
        f"• размер: {snapshot.get('partial_size_pct', 25)}%",
    ]
    tp1 = setup.get("tp1")
    if tp1 not in (None, "", "не указано"):
        lines.append(f"• TP1: {fmt_price(tp1) if isinstance(tp1, (int, float)) else tp1}")
    inv = setup.get("invalidation")
    if inv not in (None, "", "не указано"):
        lines.append(f"• отмена: {fmt_price(inv) if isinstance(inv, (int, float)) else inv}")
    return "\n".join(lines)

def build_btc_partial_size_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    side = side.upper() if side != "AUTO" else _state(data)

    if side == "WAIT":
        return "\n".join([
            f"📏 BTC PARTIAL SIZE [{timeframe}]",
            "",
            "Сейчас нет понятной стороны, поэтому partial size считать рано.",
            f"Лонг-сила: {fmt_pct(calc_long_score(data))}",
            f"Шорт-сила: {fmt_pct(calc_short_score(data))}",
        ])

    snapshot = _management_snapshot(side, data, journal)
    shift = snapshot["shift"]
    setup = snapshot["setup"]
    lines = [
        f"📏 BTC PARTIAL SIZE [{timeframe}]",
        "",
        f"Сторона: {side}",
        f"Partial size now: {snapshot['partial_size_pct']}%",
        f"Главное действие рядом с partial: {snapshot['primary_action']}",
        f"Срочность: {snapshot['urgency']}",
        "",
        f"Логика размера: {snapshot['partial_size_comment']}",
        f"Setup grade: {setup.get('grade')}",
        f"Trap risk: {setup.get('trap_risk')}",
        f"Late entry risk: {setup.get('late_entry_risk')}",
        "",
        "Почему такой размер:",
    ]
    for reason in shift.get("reasons")[:4]:
        lines.append(f"• {reason}")
    if not shift.get("reasons"):
        lines.append("• заметного ухудшения контекста пока нет")
    text = "\n".join(lines)
    try:
        return text
    except Exception:
        return text




def _tp_probability_estimate(trade_flow: Dict[str, Any], execution: Dict[str, Any], tp1: Any, tp2: Any) -> Dict[str, float]:
    try:
        cont = float(trade_flow.get('continuation_score') or 0.0)
    except Exception:
        cont = 0.0
    try:
        ex = float((trade_flow.get('exhaustion_score') if isinstance(trade_flow.get('exhaustion_score'), (int,float)) else 100.0 - cont) or 0.0)
    except Exception:
        ex = max(0.0, 100.0 - cont)
    try:
        rr = float(execution.get('rr_estimate'))
    except Exception:
        rr = None
    tp1_prob = max(0.0, min(92.0, cont * 0.82 + 12.0)) if tp1 is not None else 0.0
    tp2_prob = max(0.0, min(78.0, cont * 0.60 - ex * 0.18 + (8.0 if rr is not None and rr <= 2.2 else 0.0))) if tp2 is not None else 0.0
    return {'tp1': tp1_prob, 'tp2': tp2_prob, 'rr': rr}


def _manual_fix_map_lines(tp1: Any, tp2: Any, be_level: Any, invalidation: Any, snapshot: Dict[str, Any]) -> list[str]:
    lines = ['РУЧНАЯ ФИКСАЦИЯ:']
    part = snapshot.get('partial_size_pct')
    if tp1 is not None:
        lines.append(f"• у TP1 {tp1}: снять {part or 25}% позиции")
    else:
        lines.append('• TP1: нет данных')
    if be_level is not None:
        lines.append(f"• после первой фиксации: перевести остаток в BE {be_level}")
    else:
        lines.append('• после первой фиксации: убрать риск в безубыток')
    if tp2 is not None:
        lines.append(f"• у TP2 {tp2}: решать hold/финальную фиксацию")
    else:
        lines.append('• TP2: нет данных')
    lines.append(f"• отмена сценария: {invalidation or 'нет данных'}")
    return lines


def _manager_action_label(snapshot: Dict[str, Any]) -> str:
    action = str(snapshot.get("primary_action") or "ЖДАТЬ").upper()
    if action in {"ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ", "ЛУЧШЕ ЗАКРЫТЬ"}:
        return "EXIT"
    if action == "ЧАСТИЧНО ФИКСИРОВАТЬ":
        return "PARTIAL"
    if action == "ПЕРЕНЕСТИ В BE":
        return "BREAKEVEN"
    if action == "ТЯНУТЬ ОСТАТОК":
        return "HOLD RUNNER"
    if action in {"ДЕРЖАТЬ", "ДЕРЖАТЬ АККУРАТНО"}:
        return "HOLD"
    return "WAIT"


def _manager_reason_line(snapshot: Dict[str, Any], trade_flow: Dict[str, Any], setup: Dict[str, Any]) -> str:
    action = _manager_action_label(snapshot)
    if action == "EXIT":
        if snapshot.get("hard_close"):
            return "сценарий сломан или риск стал хуже"
        return "движение ослабло, удержание невыгодно"
    if action == "PARTIAL":
        return f"фикс части уместен: {snapshot.get('partial_size_pct') or 25}%"
    if action == "BREAKEVEN":
        return "первый результат есть, риск пора убирать"
    if action == "HOLD RUNNER":
        return "основная часть уже защищена, ведём остаток"
    if action == "HOLD":
        cont = trade_flow.get('continuation_state') or 'ALIVE'
        return f"контекст ещё держится: {str(cont).lower()}"
    return "подтверждения для активного ведения пока нет"


def _manager_block_lines(data: Dict[str, Any], side: str, snapshot: Dict[str, Any], journal: Optional[Dict[str, Any]], tp1: Any, tp2: Any, be_level: Any) -> list[str]:
    trade_flow = snapshot.get('trade_flow') or {}
    setup = snapshot.get('setup') or {}
    price = data.get('price')
    stage = snapshot.get('stage') or 'WAIT'
    action_main = _manager_action_label(snapshot)
    has_position = bool((journal or {}).get('has_active_trade') or (journal or {}).get('trade_id') or _has_open_manual_bot_state(data))
    lines = [f"🛠 BTC TRADE MANAGER [{data.get('timeframe', '1h')}]", ""]
    if price is not None:
        lines.append(f"Цена: {fmt_price(price)}")
        lines.append("")
    lines += [
        f"• сторона: {side}",
        f"• стадия: {stage}",
        f"• действие: {action_main}",
        f"• причина: {_manager_reason_line(snapshot, trade_flow, setup)}",
    ]
    if not has_position:
        lines += [
            f"• статус: NO POSITION",
            f"• next: {snapshot.get('next_step')}",
        ]
        inv = setup.get('invalidation')
        if inv not in (None, '', 'не указано'):
            lines.append(f"• отмена: {inv}")
        return lines
    lines += [
        f"• TP1: {tp1}",
        f"• TP2: {tp2}",
        f"• BE: {be_level}",
    ]
    next_line = snapshot.get('next_step')
    if action_main == 'PARTIAL':
        next_line = f"снять {snapshot.get('partial_size_pct') or 25}% и защитить остаток"
    elif action_main == 'BREAKEVEN':
        next_line = f"перевести стоп в BE {be_level}"
    elif action_main == 'HOLD RUNNER':
        next_line = 'держать остаток и подтягивать защиту'
    elif action_main == 'EXIT':
        next_line = 'сократить риск / закрыть позицию'
    lines.append(f"• next: {next_line}")
    inv = setup.get('invalidation')
    if inv not in (None, '', 'не указано'):
        lines.append(f"• отмена: {inv}")
    cont = trade_flow.get('continuation_state')
    if cont:
        lines.append(f"• движение: {str(cont).replace('_', ' ')}")
    return lines

def build_btc_trade_manager_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    side = side.upper() if side != "AUTO" else _state(data)
    if side == "WAIT":
        decision = data.get("decision") or {}
        action = str(decision.get("action_text") or decision.get("action") or "WAIT").upper()
        lines = [
            f"🛠 BTC TRADE MANAGER [{data.get('timeframe', '1h')}]",
            "",
            f"• статус: NO POSITION",
            f"• действие: {action}",
            "• причина: новой позиции сейчас нет",
        ]
        summary = decision.get('summary') or decision.get('expectation_text')
        if summary:
            lines.append(f"• next: {summary}")
        return "\n".join(lines)

    tp1, tp2 = _long_targets(data) if side == "LONG" else _short_targets(data)
    be_level = _be_level_long(data) if side == "LONG" else _be_level_short(data)
    snapshot = _management_snapshot(side, data, journal)
    return "\n".join(_manager_block_lines(data, side, snapshot, journal, tp1, tp2, be_level))


def build_btc_journal_manager_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    base = build_btc_trade_manager_text(data, side=side, journal=journal)
    if not journal or not journal.get("trade_id"):
        return "\n".join(["📘 JOURNAL MANAGER", "", base, "", "• journal: нет активной журнальной записи"])

    status = journal.get("status") or "OPEN"
    flags = _journal_flags(journal)
    lines = ["📘 JOURNAL MANAGER", "", base, "", f"• journal id: {journal.get('trade_id')}", f"• journal status: {status}"]
    if flags.get('tp1_hit'):
        lines.append("• TP1: выполнен")
    if flags.get('partial_exit_done'):
        lines.append("• partial: выполнен")
    if flags.get('be_moved'):
        lines.append("• BE: перенесён")
    if flags.get('tp2_hit'):
        lines.append("• TP2: выполнен")
    return "\n".join(lines)


__all__ = [
    "_management_snapshot",
    "_state",
    "_trailing_snapshot",
    "build_btc_tp_plan_text",
    "build_btc_be_plan_text",
    "build_btc_trailing_text",
    "build_btc_trailing_plan_text",
    "build_btc_partial_exit_text",
    "build_btc_partial_size_text",
    "build_btc_trade_manager_text",
    "build_btc_journal_manager_text",
]
