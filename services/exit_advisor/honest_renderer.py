"""Honest exit advisor renderer v0.1 (2026-05-07).

Заменяет telegram_renderer.py format_advisory_alert который выдавал fake EV
(одинаковый +$2 для всех опций потому что _compute_ev_from_history читал
не-ту parquet). Полный аудит: docs/ANALYSIS/EXIT_ADVISOR_AUDIT_2026-05-07.md

Принципы:
1. Только ФАКТЫ состояния, без рекомендаций с EV.
2. HARD BAN list из MASTER §16.4 (P-5, P-8, P-10) как предупреждение.
3. Confirmed playbook actions (P-1, P-4, P-9) — без чисел EV до накопления
   реальных action-specific outcomes.
4. Что отслеживать для принятия решения — конкретные триггеры.
5. Никаких inline-кнопок [Действую] до того как log_decision callback wired.
"""
from __future__ import annotations

from .position_state import PositionStateSnapshot, ScenarioClass


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
    ScenarioClass.EARLY_INTERVENTION:  "Ранняя интервенция (DD <4h)",
    ScenarioClass.CYCLE_DEATH:         "Цикл смерти (>=4h DD)",
    ScenarioClass.MODERATE:            "Умеренная просадка",
    ScenarioClass.SEVERE:              "Тяжёлая просадка",
    ScenarioClass.CRITICAL:            "Критическая просадка",
    ScenarioClass.URGENT_PROTECTION:   "СРОЧНО: риск ликвидации",
}


# Per scenario_class, что говорит подтверждённый playbook (PLAYBOOK.md + MASTER §16).
# Это НЕ алгоритмические EV — это правила оператора, накопленные из реального опыта.
_SCENARIO_PLAYBOOK = {
    ScenarioClass.EARLY_INTERVENTION: {
        "context": "Один из ботов в DD недавно (<4h). Это нормально для grid в тренде — сетка работает.",
        "watch": [
            "Тренд продолжается? — смотри regime_4h в /advise",
            "OI растёт против тебя? — funding flip в /advise",
            "Расстояние до liq уменьшается быстро? — distance_to_liq в этом alert",
        ],
        "operator_options_confirmed": [
            "P-1 raise boundary (если тренд подтверждён) — расширяет диапазон работы",
            "P-4 paused (новые IN остановить) — защитное, не меняет позицию",
        ],
        "hard_ban": [
            "Force close в минус — P0 violation",
        ],
    },
    ScenarioClass.CYCLE_DEATH: {
        "context": "DD держится 4+ часов. Сетка не вытаскивает из движения.",
        "watch": [
            "Тренд ослабевает? — momentum в /advise",
            "Достижение уровня (PDH/PDL/asia high)? — session_levels в /advise",
            "Liquidation cascade? — если есть, может быть точка разворота",
        ],
        "operator_options_confirmed": [
            "P-1 raise boundary — если хочешь дать сетке дальнейший простор",
            "P-9 fix or reinforce — частичная фиксация на отскоках (не в DD!)",
            "P-12 adaptive grid tighten — больше оборотов, меньше exposure per IN",
        ],
        "hard_ban": [
            "P-5 partial unload в DD — статистика OPPORTUNITY_MAP_v2: avg -$26",
            "P-8 force close + restart — avg -$192",
            "P-10 rebalance close + reenter — avg -$46 + двойной spread",
        ],
    },
    ScenarioClass.MODERATE: {
        "context": "Заметная просадка (-3..-7%) при значительной длительности. Ситуация серьёзная.",
        "watch": [
            "Margin free уровень — сколько осталось до forced close",
            "Сравни с ранее прошедшими циклами — выходило ли из таких просадок без вмешательства?",
            "Конкурсный bonus период приближается?",
        ],
        "operator_options_confirmed": [
            "P-4 paused entries — защитное",
            "Booster bot 6399265299 — manual P-16 если impulse исчерпан у resistance",
        ],
        "hard_ban": [
            "Force close — P0 violation, исключение только при риске liq",
        ],
    },
    ScenarioClass.SEVERE: {
        "context": "Тяжёлая просадка (-7..-12%). Внимательно следить за liq distance.",
        "watch": [
            "Distance to liq < 30% — критический threshold",
            "Margin coefficient — если падает быстро, готовься к force-action",
            "Funding extreme — может быть squeeze момент",
        ],
        "operator_options_confirmed": [
            "P-4 paused — обязательно",
            "Подготовь сценарии частичного closure ЕСЛИ liq distance < 20%",
        ],
        "hard_ban": [
            "Не закрывать pre-emptively — wait for actual liq risk signal",
        ],
    },
    ScenarioClass.CRITICAL: {
        "context": "Критическая просадка (-12..-20%). Значимый убыток если закрывать.",
        "watch": [
            "Distance to liq — главная метрика сейчас",
            "Crypto market overall — каскад идёт?",
            "Подкрепление маржи возможно?",
        ],
        "operator_options_confirmed": [
            "Подкрепить margin (если возможно) — releases liq buffer",
            "P-1 raise boundary до уровня выше текущего экстремума — даёт время",
        ],
        "hard_ban": [
            "Panic close — статистика прямо отрицательная",
        ],
    },
    ScenarioClass.URGENT_PROTECTION: {
        "context": "Distance to liq < 20% — РЕАЛЬНЫЙ риск принудительного закрытия биржей.",
        "watch": [
            "Liq price vs current price — точное расстояние",
            "Скорость движения цены — если impulse, минуты до liq",
        ],
        "operator_options_confirmed": [
            "Подкрепление margin — главный приоритет (releases buffer)",
            "Частичное закрытие 25-50% — если подкрепить нельзя, чтобы спасти остальное",
            "P-1 hard boundary stop — если можно остановить новые IN мгновенно",
        ],
        "hard_ban": [
            "Полное паническое закрытие при distance > 5% — wait for actual margin call",
        ],
    },
}


def _format_state_header(state: PositionStateSnapshot) -> str:
    icon = _SCENARIO_ICONS.get(state.scenario_class, "⚠️")
    label = _SCENARIO_LABELS_RU.get(state.scenario_class, state.scenario_class.value)
    ts = state.captured_at.strftime("%H:%M UTC")

    lines = [
        f"{icon} ПОЗИЦИЯ — наблюдение | {ts}",
        f"",
        f"Сценарий: {label}",
        f"Цена BTC: ${state.current_price:,.1f}",
        f"Нереализованный итог: {state.total_unrealized_usd:+,.0f} USD",
        f"Свободная маржа: ${state.free_margin_usd:,.0f} ({state.free_margin_pct:.1f}%)",
    ]

    if state.worst_bot:
        wb = state.worst_bot
        lines.append("")
        lines.append("Худший бот:")
        lines.append(
            f"  {wb.alias} | поз. {wb.position_btc:+.3f} BTC "
            f"| P&L {wb.unrealized_usd:+.0f}$ ({wb.unrealized_pct_deposit:+.1f}%)"
        )
        if wb.duration_in_dd_h > 0:
            lines.append(f"  Время в DD: {wb.duration_in_dd_h:.1f}h")
        lines.append(f"  До ликвидации: {wb.distance_to_liq_pct:.1f}%")

    if state.short_side.bot_count > 0:
        lines.append("")
        lines.append(
            f"SHORT total: {state.short_side.bot_count} ботов "
            f"| {state.short_side.total_position_btc:+.3f} BTC "
            f"| {state.short_side.total_unrealized_usd:+,.0f} USD"
        )
    if state.long_side.bot_count > 0:
        lines.append(
            f"LONG total: {state.long_side.bot_count} ботов "
            f"| {state.long_side.total_position_btc:+.3f} BTC "
            f"| {state.long_side.total_unrealized_usd:+,.0f} USD"
        )

    return "\n".join(lines)


def _format_playbook_block(state: PositionStateSnapshot) -> str:
    pb = _SCENARIO_PLAYBOOK.get(state.scenario_class)
    if not pb:
        return ""

    lines = []
    lines.append("📋 ЧТО ГОВОРИТ ПЛЕЙБУК (MASTER §16 + PLAYBOOK)")
    lines.append("")
    lines.append(f"Контекст: {pb['context']}")
    lines.append("")

    if pb.get("watch"):
        lines.append("👀 Что отслеживать:")
        for item in pb["watch"]:
            lines.append(f"  • {item}")
        lines.append("")

    if pb.get("operator_options_confirmed"):
        lines.append("✅ Подтверждённые опции (Confirmed playbook):")
        for item in pb["operator_options_confirmed"]:
            lines.append(f"  • {item}")
        lines.append("")

    if pb.get("hard_ban"):
        lines.append("⛔ HARD BAN (MASTER §16.4):")
        for item in pb["hard_ban"]:
            lines.append(f"  • {item}")

    return "\n".join(lines)


def format_honest_advisory(state: PositionStateSnapshot) -> str:
    """Format honest advisory: facts + playbook context, NO fake EV.

    Когда применять (caller responsibility):
    - state.has_active_position == True
    - state.scenario_class != ScenarioClass.MONITORING
    """
    if not state.has_active_position:
        return ""
    if state.scenario_class == ScenarioClass.MONITORING:
        return ""

    parts = [
        _format_state_header(state),
        "",
        _format_playbook_block(state),
        "",
        "─" * 30,
        "Это observation, не команда к действию.",
        "Решение остаётся за оператором. /advise для рыночного контекста.",
    ]
    return "\n".join(parts)
