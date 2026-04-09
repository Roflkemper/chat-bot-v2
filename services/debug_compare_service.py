from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Iterable

from models.snapshots import AnalysisSnapshot


LONG_HINTS = ["LONG", "BULL", "BUY", "UP", "ЛОНГ", "РОСТ", "ВВЕРХ"]
SHORT_HINTS = ["SHORT", "BEAR", "SELL", "DOWN", "ШОРТ", "ПАД", "ВНИЗ"]
NEUTRAL_HINTS = ["NEUTRAL", "WAIT", "HOLD", "MIXED", "НЕЙТРАЛ", "ЖДАТЬ", "НЕТ ДАННЫХ"]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _contains_any(text: str, hints: Iterable[str]) -> bool:
    upper = text.upper()
    return any(h in upper for h in hints)


def _direction_from_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return "neutral"
    if _contains_any(text, LONG_HINTS):
        return "long"
    if _contains_any(text, SHORT_HINTS):
        return "short"
    if _contains_any(text, NEUTRAL_HINTS):
        return "neutral"
    return "neutral"


def _best_direction(snapshot: AnalysisSnapshot) -> str:
    for value in [
        snapshot.decision.direction_text,
        snapshot.decision.direction,
        snapshot.final_decision,
        snapshot.forecast_direction,
        snapshot.reversal_signal,
        snapshot.signal,
        snapshot.decision_summary,
    ]:
        direction = _direction_from_text(value)
        if direction != "neutral":
            return direction
    return "neutral"


def _normalize_pct(value: Any) -> float | None:
    try:
        if value is None:
            return None
        value = float(value)
    except Exception:
        return None
    if value <= 1:
        return value * 100.0
    return value


def _summary_lines(snapshot: AnalysisSnapshot) -> list[str]:
    return [
        f"signal={snapshot.signal or 'нет данных'}",
        f"final_decision={snapshot.final_decision or 'нет данных'}",
        f"forecast={snapshot.forecast_direction or 'нет данных'} ({round(_normalize_pct(snapshot.forecast_confidence) or 0.0, 1)}%)",
        f"reversal={snapshot.reversal_signal or 'нет данных'} ({round(_normalize_pct(snapshot.reversal_confidence) or 0.0, 1)}%)",
        f"decision.direction={snapshot.decision.direction_text or snapshot.decision.direction or 'нет данных'}",
        f"decision.action={snapshot.decision.action_text or snapshot.decision.action or 'нет данных'}",
        f"range_state={snapshot.range_state or 'нет данных'}",
        f"ct_now={snapshot.ct_now or 'нет данных'}",
    ]


def _conflicts(snapshot: AnalysisSnapshot) -> list[str]:
    conflicts: list[str] = []
    signal_dir = _direction_from_text(snapshot.signal)
    final_dir = _direction_from_text(snapshot.final_decision)
    forecast_dir = _direction_from_text(snapshot.forecast_direction)
    reversal_dir = _direction_from_text(snapshot.reversal_signal)
    decision_dir = _direction_from_text(snapshot.decision.direction_text or snapshot.decision.direction)
    reversal_conf = _normalize_pct(snapshot.reversal_confidence) or 0.0
    forecast_conf = _normalize_pct(snapshot.forecast_confidence) or 0.0
    range_state = _text(snapshot.range_state).lower()
    ct_now = _text(snapshot.ct_now).lower()

    if reversal_dir != "neutral" and reversal_conf >= 55 and signal_dir == "neutral":
        conflicts.append("Есть направленный reversal, но главный signal остался нейтральным.")
    if reversal_dir != "neutral" and reversal_conf >= 55 and final_dir == "neutral":
        conflicts.append("Есть направленный reversal, но final_decision остался нейтральным.")
    if forecast_dir != "neutral" and forecast_conf >= 55 and decision_dir == "neutral":
        conflicts.append("Forecast уже направленный, а decision-блок ещё нейтральный.")
    if signal_dir != "neutral" and final_dir != "neutral" and signal_dir != final_dir:
        conflicts.append("Signal и final_decision смотрят в разные стороны.")
    if reversal_dir != "neutral" and forecast_dir != "neutral" and reversal_dir != forecast_dir:
        conflicts.append("Reversal и forecast_direction конфликтуют между собой.")
    if reversal_dir != "neutral" and decision_dir != "neutral" and reversal_dir != decision_dir:
        conflicts.append("Reversal и decision.direction конфликтуют между собой.")
    if (reversal_dir != "neutral" or signal_dir != "neutral") and "середина диапазона" in range_state:
        conflicts.append("Есть направленный контекст внутри range mid — range-логика может гасить движение слишком рано.")
    if reversal_dir == "short" and "отскок" in ct_now:
        conflicts.append("CT-блок тянет к bounce, а reversal показывает short-rejection.")
    if reversal_dir == "long" and ("перекуп" in ct_now or "шорт" in ct_now):
        conflicts.append("CT-блок выглядит медвежьим, а reversal показывает long-rejection.")
    if snapshot.reversal_patterns and reversal_dir == "neutral":
        conflicts.append("Есть reversal patterns, но направление reversal_signal не нормализовано в явный bias.")
    return conflicts


def _expectation_template(snapshot: AnalysisSnapshot) -> dict[str, Any]:
    bot_bias = _best_direction(snapshot)
    return {
        "timeframe": snapshot.timeframe,
        "what_trader_expected": "fill manually",
        "expected_direction": "long | short | neutral",
        "expected_pattern": "pinbar | false breakout | rejection | continuation | other",
        "why_trader_expected_it": [
            "опиши глазами трейдера, что ты увидел на графике",
            "если это пинбар — напиши где был хвост и где закрылась свеча",
            "если это false breakout — напиши какой уровень вынесли и вернули назад",
        ],
        "bot_current_bias": bot_bias,
        "bot_current_summary": _summary_lines(snapshot),
    }


def build_debug_comparison_pack(analyses: dict[str, AnalysisSnapshot | dict[str, Any]]) -> dict[str, Any]:
    normalized: dict[str, AnalysisSnapshot] = {}
    for tf, value in analyses.items():
        if isinstance(value, AnalysisSnapshot):
            normalized[tf] = value
        else:
            normalized[tf] = AnalysisSnapshot.from_dict(value, timeframe=tf)

    per_tf: dict[str, Any] = {}
    directional_bias: dict[str, int] = {"long": 0, "short": 0, "neutral": 0}
    high_conflict_tfs: list[str] = []

    for tf, snapshot in normalized.items():
        bias = _best_direction(snapshot)
        directional_bias[bias] = directional_bias.get(bias, 0) + 1
        conflicts = _conflicts(snapshot)
        if len(conflicts) >= 2:
            high_conflict_tfs.append(tf)
        per_tf[tf] = {
            "timeframe": tf,
            "bot_bias": bias,
            "bot_saw": {
                "signal": snapshot.signal,
                "final_decision": snapshot.final_decision,
                "forecast_direction": snapshot.forecast_direction,
                "forecast_confidence": _normalize_pct(snapshot.forecast_confidence),
                "reversal_signal": snapshot.reversal_signal,
                "reversal_confidence": _normalize_pct(snapshot.reversal_confidence),
                "reversal_patterns": list(snapshot.reversal_patterns),
                "decision_direction": snapshot.decision.direction_text or snapshot.decision.direction,
                "decision_action": snapshot.decision.action_text or snapshot.decision.action,
                "decision_risk": snapshot.decision.risk_level,
                "range_state": snapshot.range_state,
                "ct_now": snapshot.ct_now,
                "decision_summary": snapshot.decision_summary,
            },
            "internal_conflicts": conflicts,
            "trader_expectation_template": _expectation_template(snapshot),
        }

    overall_bias = max(directional_bias, key=lambda x: directional_bias.get(x, 0)) if directional_bias else "neutral"
    return {
        "overall_bias": overall_bias,
        "bias_counts": directional_bias,
        "high_conflict_timeframes": high_conflict_tfs,
        "timeframes": per_tf,
    }


def build_comparison_summary_text(pack: dict[str, Any]) -> str:
    lines = [
        "DEBUG COMPARISON PACK",
        "",
        f"Общий bias по snapshots: {pack.get('overall_bias', 'neutral')}",
        f"Bias counts: {json.dumps(pack.get('bias_counts', {}), ensure_ascii=False)}",
        f"High-conflict TF: {', '.join(pack.get('high_conflict_timeframes') or []) or 'нет'}",
        "",
        "Что бот увидел и где есть конфликт:",
    ]
    for tf, entry in (pack.get("timeframes") or {}).items():
        bot_saw = entry.get("bot_saw") or {}
        conflicts = entry.get("internal_conflicts") or []
        lines.extend([
            "",
            f"[{tf}] bias={entry.get('bot_bias')}",
            f"- signal: {bot_saw.get('signal') or 'нет данных'}",
            f"- final_decision: {bot_saw.get('final_decision') or 'нет данных'}",
            f"- forecast: {bot_saw.get('forecast_direction') or 'нет данных'} ({round(bot_saw.get('forecast_confidence') or 0.0, 1)}%)",
            f"- reversal: {bot_saw.get('reversal_signal') or 'нет данных'} ({round(bot_saw.get('reversal_confidence') or 0.0, 1)}%)",
            f"- decision.direction: {bot_saw.get('decision_direction') or 'нет данных'}",
            f"- range_state: {bot_saw.get('range_state') or 'нет данных'}",
            f"- ct_now: {bot_saw.get('ct_now') or 'нет данных'}",
        ])
        if conflicts:
            lines.append("- conflicts:")
            for item in conflicts:
                lines.append(f"  • {item}")
        else:
            lines.append("- conflicts: явных внутренних конфликтов не найдено")
    lines.extend([
        "",
        "Как использовать:",
        "1) Открой trader_expectation_template.json и заполни глазами трейдера expected_direction/expected_pattern.",
        "2) Сравни это с comparison_pack.json — там уже есть what bot saw и internal_conflicts.",
        "3) Если бот нейтрален при сильном reversal, ищи конфликт signal/final_decision/range/ct.",
    ])
    return "\n".join(lines)
