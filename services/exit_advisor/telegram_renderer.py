"""Telegram alert renderer for exit advisor recommendations.

Formats PositionStateSnapshot + RankedStrategy list into a Russian-language
advisory message with inline buttons per option.

Alert priority:
  INFO     — monitoring / early
  WARN     — cycle_death
  CRITICAL — severe / critical / urgent_protection
"""
from __future__ import annotations

from datetime import datetime, timezone

from .margin_calculator import MarginRequirement
from .position_state import PositionStateSnapshot, ScenarioClass
from .strategy_ranker import ConfidenceLevel, ExitFamily, RankedStrategy

_SCENARIO_ICONS = {
    ScenarioClass.MONITORING:          "📊",
    ScenarioClass.EARLY_INTERVENTION:  "⚠️",
    ScenarioClass.CYCLE_DEATH:         "🔴",
    ScenarioClass.MODERATE:            "🔴",
    ScenarioClass.SEVERE:              "🚨",
    ScenarioClass.CRITICAL:            "🚨",
    ScenarioClass.URGENT_PROTECTION:   "🆘",
}

_SCENARIO_LABELS_RU = {
    ScenarioClass.MONITORING:          "Мониторинг",
    ScenarioClass.EARLY_INTERVENTION:  "Ранняя интервенция (<4h)",
    ScenarioClass.CYCLE_DEATH:         "Цикл смерти (>=4h DD)",
    ScenarioClass.MODERATE:            "Умеренная просадка (>-7%)",
    ScenarioClass.SEVERE:              "Тяжёлая просадка (>-12%)",
    ScenarioClass.CRITICAL:            "Критическая просадка (>-20%)",
    ScenarioClass.URGENT_PROTECTION:   "СРОЧНО: риск ликвидации",
}

_FAMILY_LABELS_RU = {
    ExitFamily.A: "Частичное закрытие (A)",
    ExitFamily.B: "Контр-хедж LONG (B)",
    ExitFamily.C: "Сдвиг границы (C)",
    ExitFamily.D: "Сжатие сетки (D)",
    ExitFamily.F: "Комбо (F)",
}

_CONFIDENCE_LABELS = {
    ConfidenceLevel.HIGH:   "ВЫСОКАЯ уверенность",
    ConfidenceLevel.MEDIUM: "СРЕДНЯЯ уверенность",
    ConfidenceLevel.LOW:    "НИЗКАЯ уверенность",
}


def _format_state_header(state: PositionStateSnapshot) -> str:
    icon = _SCENARIO_ICONS.get(state.scenario_class, "⚠️")
    label = _SCENARIO_LABELS_RU.get(state.scenario_class, state.scenario_class.value)
    ts = state.captured_at.strftime("%H:%M UTC")

    lines = [
        f"{icon} ПОЗИЦИОННЫЙ СОВЕТНИК | {ts}",
        f"",
        f"Сценарий: {label}",
        f"Цена BTC: ${state.current_price:,.1f}",
        f"Нереализ. итого: {state.total_unrealized_usd:+,.0f} USD",
        f"Свободная маржа: ${state.free_margin_usd:,.0f} ({state.free_margin_pct:.1f}%)",
    ]

    # Worst bot detail
    if state.worst_bot:
        wb = state.worst_bot
        lines.append(
            f"Худший бот: {wb.alias} "
            f"| поз. {wb.position_btc:+.3f} BTC "
            f"| P&L {wb.unrealized_usd:+.0f}$ ({wb.unrealized_pct_deposit:+.1f}%)"
        )
        if wb.duration_in_dd_h > 0:
            lines.append(f"Время в просадке: {wb.duration_in_dd_h:.1f}h")
        lines.append(f"До ликвидации: {wb.distance_to_liq_pct:.1f}%")

    # Side summary
    if state.short_side.bot_count > 0:
        lines.append(
            f"SHORT боты: {state.short_side.bot_count} "
            f"| {state.short_side.total_position_btc:+.3f} BTC "
            f"| {state.short_side.total_unrealized_usd:+,.0f} USD"
        )

    return "\n".join(lines)


def _format_strategy_block(
    req: MarginRequirement,
    idx: int,
) -> str:
    s = req.strategy
    conf_label = _CONFIDENCE_LABELS.get(s.confidence, s.confidence.value)
    family_label = _FAMILY_LABELS_RU.get(s.family, s.family.value)
    rev_label = "обратимо" if s.reversible else "необратимо"

    lines = [
        f"Вариант {idx}: {family_label}",
        f"  {s.description}",
        f"  Уверенность: {conf_label} (n={s.n_samples})",
    ]

    if s.mean_pnl_usd != 0:
        lines.append(
            f"  EV: {s.mean_pnl_usd:+.0f}$ "
            f"[CI: {s.ci_lower_usd:+.0f}..{s.ci_upper_usd:+.0f}] "
            f"| WR: {s.win_rate_pct:.0f}%"
        )

    if req.required_usd > 0:
        afford = "OK" if req.affordable else "НЕДОСТАТОЧНО"
        lines.append(f"  Маржа: ${req.required_usd:.0f} нужно ({afford})")
    else:
        lines.append(f"  Маржа: не нужна")

    lines.append(f"  Обратимость: {rev_label}")
    if req.notes:
        lines.append(f"  Детали: {req.notes}")

    return "\n".join(lines)


def format_advisory_alert(
    state: PositionStateSnapshot,
    strategies: list[RankedStrategy],
    margin_reqs: list[MarginRequirement],
    max_shown: int = 4,
) -> str:
    """Format full advisory alert message."""
    if not state.has_active_position:
        return ""
    if state.scenario_class == ScenarioClass.MONITORING:
        return ""

    parts = [_format_state_header(state), ""]

    if not strategies:
        parts.append("Рекомендаций нет для текущего сценария.")
        return "\n".join(parts)

    parts.append("Рекомендации (по EV):")
    parts.append("")

    shown = min(max_shown, len(margin_reqs))
    for i, req in enumerate(margin_reqs[:shown], start=1):
        parts.append(_format_strategy_block(req, i))
        parts.append("")

    remaining = len(margin_reqs) - shown
    if remaining > 0:
        parts.append(f"[+ ещё {remaining} вариантов]")

    parts.append("[Действую] [Наблюдаю] [Отклонить]")

    return "\n".join(parts)


def format_outcome_followup(
    decision_ts: str,
    option_idx: int,
    strategy_desc: str,
    delta_1h: float | None,
    delta_4h: float | None,
    delta_24h: float | None,
) -> str:
    """Format follow-up outcome message after operator action."""
    lines = [
        f"📋 ИТОГ ИНТЕРВЕНЦИИ",
        f"Решение: Вариант {option_idx} — {strategy_desc}",
        f"Принято: {decision_ts}",
        "",
    ]
    if delta_1h is not None:
        lines.append(f"После 1h: {delta_1h:+.0f}$")
    if delta_4h is not None:
        lines.append(f"После 4h: {delta_4h:+.0f}$")
    if delta_24h is not None:
        lines.append(f"После 24h: {delta_24h:+.0f}$")

    return "\n".join(lines)
