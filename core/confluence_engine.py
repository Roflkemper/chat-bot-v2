from __future__ import annotations

from typing import Any, Dict, Optional

from core.btc_plan import calc_long_score, calc_short_score, fmt_pct
from core.import_compat import normalize_direction
from core.market_structure import analyze_market_structure
from core.setup_quality import analyze_setup_quality
from core.reversal_engine import analyze_reversal


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


def analyze_confluence(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    journal = journal or {}
    decision = _decision(data)
    picked = _pick_side(data, side=side)
    setup = analyze_setup_quality(data, side=picked, journal=journal)
    structure = analyze_market_structure(data, side=picked if picked in ("LONG", "SHORT") else None, journal=journal)

    long_score = float(calc_long_score(data) or 0.0)
    short_score = float(calc_short_score(data) or 0.0)
    side_score = long_score if picked == "LONG" else short_score if picked == "SHORT" else max(long_score, short_score)
    opp_score = short_score if picked == "LONG" else long_score if picked == "SHORT" else min(long_score, short_score)
    score_gap = max(0.0, side_score - opp_score)

    grade = str(setup.get("grade") or "NO TRADE").upper()
    status = str(structure.get("status") or "NEUTRAL").upper()
    cq = str(structure.get("continuation_quality") or "MID").upper()
    risk = str(decision.get("risk_level") or "HIGH").upper()
    action = str(decision.get("action") or "WAIT").upper()
    mode = str(decision.get("mode") or "MIXED").upper()
    confidence_pct = float(decision.get("confidence_pct") or 0.0)
    reversal_direction = str(data.get("reversal_direction") or "").upper()
    reversal_conf = float(data.get("reversal_confidence") or 0.0)
    reversal_patterns = data.get("reversal_patterns") or []

    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    if picked == "WAIT":
        warnings.append("нет чистой стороны — confluence не собран")
        score += 10.0
    else:
        direction = str(decision.get("direction") or "NONE").upper()
        if reversal_direction == picked:
            score += 16.0 + reversal_conf * 10.0
            reasons.append("reversal engine подтверждает выбранную сторону")
        elif reversal_direction in ("LONG", "SHORT") and reversal_direction != picked:
            warnings.append("reversal engine спорит с выбранной стороной")
            score -= 14.0

        if direction == picked:
            score += 25.0
            reasons.append("decision engine смотрит в ту же сторону")
        elif direction == "NONE":
            score += 8.0
            warnings.append("decision engine пока без чёткого направления")
        else:
            warnings.append("decision engine против выбранной стороны")
            score -= 20.0

        if action == "ENTER":
            score += 15.0
            reasons.append("decision action позволяет искать вход")
        elif action in ("WATCH", "WAIT_CONFIRMATION"):
            score += 8.0
            reasons.append("идея есть, но нужен confirm")
        else:
            warnings.append("decision action не подтверждает агрессивный сценарий")
            score -= 8.0

        if risk == "LOW":
            score += 10.0
            reasons.append("risk level низкий")
        elif risk == "MID":
            score += 5.0
        else:
            warnings.append("risk level высокий")
            score -= 8.0

        grade_points = {"A": 24.0, "B": 17.0, "C": 9.0, "NO TRADE": -14.0}
        score += grade_points.get(grade, -14.0)
        if grade in ("A", "B"):
            reasons.append(f"setup quality = {grade}")
        else:
            warnings.append(f"setup quality = {grade}")

        if structure.get("structure_break"):
            score -= 25.0
            warnings.append("structure break ломает базовую идею")
        elif structure.get("choch_risk"):
            score -= 10.0
            warnings.append("есть CHOCH risk против сценария")
        elif status in ("BOS_UP", "BOS_DOWN"):
            score += 14.0
            reasons.append(f"структура уже показывает {status}")
        elif status.startswith("HOLDING"):
            score += 9.0
            reasons.append("структура пока удерживается")

        cq_points = {"HIGH": 10.0, "GOOD": 7.0, "MID": 3.0, "LOW": -8.0, "UNKNOWN": 0.0}
        score += cq_points.get(cq, 0.0)

        if score_gap >= 0.18:
            score += 12.0
            reasons.append("score gap сильный")
        elif score_gap >= 0.10:
            score += 7.0
            reasons.append("score gap достаточный")
        elif score_gap >= 0.06:
            score += 3.0
        else:
            warnings.append("score gap узкий")
            score -= 6.0

        forecast = normalize_direction(data.get("forecast_direction"))
        if (picked == "LONG" and forecast == "ЛОНГ") or (picked == "SHORT" and forecast == "ШОРТ"):
            score += 4.0
        elif forecast in ("ЛОНГ", "ШОРТ"):
            warnings.append("forecast спорит с выбранной стороной")
            score -= 4.0

    if journal.get("trade_id") and not journal.get("closed"):
        if journal.get("tp1_hit"):
            score += 3.0
            reasons.append("TP1 уже отмечен — часть пути подтверждена")
        if journal.get("be_moved"):
            score += 2.0
        if journal.get("partial_exit_done"):
            score -= 1.0
        if journal.get("tp2_hit"):
            warnings.append("TP2 уже отмечен — upside/downside может быть почти исчерпан")
            score -= 8.0

    score = max(0.0, min(100.0, score))

    if picked == "WAIT" or grade == "NO TRADE" or structure.get("structure_break"):
        conviction = "LOW"
        action_bias = "NO TRADE"
    elif score >= 78.0:
        conviction = "HIGH"
        action_bias = "PRESS ADVANTAGE"
    elif score >= 58.0:
        conviction = "GOOD"
        action_bias = "WORKABLE"
    elif score >= 40.0:
        conviction = "MIXED"
        action_bias = "SELECTIVE"
    else:
        conviction = "LOW"
        action_bias = "REDUCE AGGRESSION"

    summary_map = {
        "HIGH": "факторы хорошо собраны в одну сторону — сценарий выглядит сильным",
        "GOOD": "перевес рабочий, но не идеальный — лучше действовать аккуратно",
        "MIXED": "есть и плюсы, и помехи — нужен более выборочный execution",
        "LOW": "confluence слабый — лучше не форсировать риск",
    }

    return {
        "side": picked,
        "score": round(score, 1),
        "conviction": conviction,
        "action_bias": action_bias,
        "summary": summary_map[conviction],
        "decision_direction": str(decision.get("direction_text") or decision.get("direction") or "NONE"),
        "decision_action": str(decision.get("action_text") or decision.get("action") or "WAIT"),
        "decision_mode": mode,
        "risk": risk,
        "confidence_pct": round(confidence_pct, 1),
        "setup_grade": grade,
        "setup_score": setup.get("score_total"),
        "structure_status": status,
        "continuation_quality": cq,
        "score_gap": score_gap,
        "side_score": side_score,
        "opp_score": opp_score,
        "reasons": reasons,
        "warnings": warnings,
        "reversal_direction": reversal_direction or "NEUTRAL",
        "reversal_confidence": round(reversal_conf, 3),
        "reversal_patterns": reversal_patterns[:4],
        "setup": setup,
        "structure": structure,
    }


def build_btc_confluence_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    snap = analyze_confluence(data, side=side, journal=journal)
    lines = [
        f"🧩 BTC CONFLUENCE [{timeframe}]",
        "",
        f"Confluence side: {snap['side']}",
        f"Conviction: {snap['conviction']}",
        f"Final confluence score: {snap['score']}/100",
        f"Action bias: {snap['action_bias']}",
        "",
        f"Коротко: {snap['summary']}",
        "",
        "Что собирает перевес:",
    ]
    if snap['reasons']:
        lines.extend([f"• {x}" for x in snap['reasons'][:6]])
    else:
        lines.append("• сильных подтверждений сейчас мало")
    lines.extend([
        "",
        "Что мешает confluence:",
    ])
    if snap['warnings']:
        lines.extend([f"• {x}" for x in snap['warnings'][:6]])
    else:
        lines.append("• жёстких помех confluence сейчас не видно")
    lines.extend([
        "",
        "Снимок факторов v8.6:",
        f"• decision direction: {snap['decision_direction']}",
        f"• decision action: {snap['decision_action']}",
        f"• decision mode: {snap['decision_mode']}",
        f"• risk: {snap['risk']}",
        f"• decision confidence: {snap['confidence_pct']}%",
        f"• reversal direction: {snap['reversal_direction']}",
        f"• reversal confidence: {round((snap['reversal_confidence'] or 0.0) * 100, 1)}%",
        f"• setup grade: {snap['setup_grade']}",
        f"• setup score: {snap['setup_score']}",
        f"• structure status: {snap['structure_status']}",
        f"• continuation quality: {snap['continuation_quality']}",
        f"• side score: {fmt_pct(snap['side_score'])}",
        f"• opposite score: {fmt_pct(snap['opp_score'])}",
        f"• score gap: {fmt_pct(snap['score_gap'])}",
        "",
        "Логика v8.6:",
        "• HIGH — confluence реально собран, можно действовать увереннее",
        "• GOOD — сценарий рабочий, но execution должен быть аккуратным",
        "• MIXED — перевес неплохой, но без права на небрежный вход/удержание",
        "• LOW — confluence слабый, риск форсировать не стоит",
    ])
    return "\n".join(lines)


__all__ = ["analyze_confluence", "build_btc_confluence_text"]