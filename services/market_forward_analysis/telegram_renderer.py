"""Telegram renderer for market_forward_analysis briefs and event alerts.

Formats:
  format_session_brief()    — SESSION BRIEF (4×day, on session open)
  format_phase_change_alert() — phase shift event
  format_bot_risk_alert()   — bot risk transition to ORANGE/RED
  format_full_brief()       — combined phase + projection + bot impact
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .phase_classifier import MTFPhaseState, Phase
from .forward_projection import ForwardProjection, ConfluenceStrength
from .bot_impact import PortfolioBotImpact, BotProjection, RiskClass
from .recommendations import Recommendation, ActionType

_PHASE_EMOJI = {
    Phase.ACCUMULATION: "🔵",
    Phase.MARKUP:       "🟢",
    Phase.DISTRIBUTION: "🟡",
    Phase.MARKDOWN:     "🔴",
    Phase.RANGE:        "⚪",
    Phase.TRANSITION:   "🔄",
}

_RISK_EMOJI = {
    RiskClass.GREEN:  "🟢",
    RiskClass.YELLOW: "🟡",
    RiskClass.ORANGE: "🟠",
    RiskClass.RED:    "🔴",
}

_SESSION_NAMES = {
    "ASIA":   "ASIA BRIEF",
    "LONDON": "LONDON BRIEF",
    "NY_AM":  "NY AM BRIEF",
    "NY_PM":  "NY PM BRIEF",
}


def _phase_block(phase_state: MTFPhaseState) -> str:
    lines: list[str] = ["PHASE"]
    tf_order = ["1d", "4h", "1h", "15m"]
    for tf in tf_order:
        p = phase_state.phases.get(tf)
        if p and p.confidence > 0:
            emoji = _PHASE_EMOJI.get(p.label, "⚪")
            lines.append(
                f"{emoji} {tf}: {p.label.value} ({p.confidence:.0f}%) "
                f"{p.bars_in_phase}b in phase"
            )
    lines.append(f"Coherence: {phase_state.coherence_note}")
    return "\n".join(lines)


_DIRECTION_LABEL = {
    "up":    "BULLISH",
    "down":  "BEARISH",
    "range": "RANGE-BOUND",
}

_DIRECTION_ARROW = {
    "up": "▲", "down": "▼", "range": "◆",
}

_CONFLUENCE_WATCH = {
    ConfluenceStrength.STRONG: "High conviction — all signals align",
    ConfluenceStrength.MEDIUM: "Moderate conviction — mixed signals",
    ConfluenceStrength.WEAK:   "Low conviction — single signal only",
    ConfluenceStrength.NONE:   "No clear signal — neutral stance",
}


def _watch_for_triggers(projection: ForwardProjection, current_price: float) -> list[str]:
    """Generate watch-for trigger bullets from projection context.

    No probability numbers — only qualitative conditions operator should watch.
    """
    triggers: list[str] = []
    fc4h = projection.forecasts.get("4h")
    fc1h = projection.forecasts.get("1h")

    if fc4h:
        if fc4h.direction == "up":
            if current_price > 0 and projection.key_resistance:
                triggers.append(
                    f"Watch for: break above ${projection.key_resistance:,.0f} confirming bullish continuation"
                )
            triggers.append("Watch for: higher-low structure on 1h, volume expansion on up-moves")
        elif fc4h.direction == "down":
            if current_price > 0 and projection.key_support:
                triggers.append(
                    f"Watch for: break below ${projection.key_support:,.0f} — bearish continuation signal"
                )
            triggers.append("Watch for: lower-high structure on 1h, volume spike on breakdowns")
        else:
            if projection.key_resistance and projection.key_support:
                triggers.append(
                    f"Watch for: range bounds ${projection.key_support:,.0f}–${projection.key_resistance:,.0f} "
                    f"— fade extremes, respect midpoint"
                )

    if fc1h and fc4h and fc1h.direction != fc4h.direction and fc4h.direction != "range":
        triggers.append(
            f"Watch for: 1h/4h divergence — 1h showing {fc1h.direction}, wait for alignment before acting"
        )

    if projection.micro_notes:
        triggers.append(f"Micro signal: {projection.micro_notes[0]}")

    if not triggers:
        triggers.append("Watch for: decisive break of current range before positioning")

    return triggers


def _forecast_block(projection: ForwardProjection, current_price: float) -> str:
    """Qualitative-only forecast block. No probability numbers, no CI.

    Per ETAP 1 spec (2026-05-03): briefs are qualitative until per-regime
    calibration reaches Brier ≤0.22. Numbers would be misleading at 0.257.
    """
    lines: list[str] = []
    fc4h = projection.forecasts.get("4h")
    fc1h = projection.forecasts.get("1h")
    fc1d = projection.forecasts.get("1d")

    bias_label = _DIRECTION_LABEL.get(
        fc4h.direction if fc4h else "range", "UNCLEAR"
    )
    arrow = _DIRECTION_ARROW.get(fc4h.direction if fc4h else "range", "◆")

    lines.append(f"BIAS {arrow} {bias_label}")

    if fc1h and fc4h:
        if fc1h.direction == fc4h.direction:
            lines.append(f"1h/4h aligned — consistent {bias_label.lower()} signal")
        else:
            lines.append(
                f"1h/4h diverging — 1h {_DIRECTION_LABEL.get(fc1h.direction,'?')} "
                f"vs 4h {_DIRECTION_LABEL.get(fc4h.direction,'?')}"
            )

    if fc1d:
        lines.append(f"Daily context: {_DIRECTION_LABEL.get(fc1d.direction, fc1d.direction)}")

    if fc4h:
        lines.append(f"Based on {fc4h.n_episodes} similar historical episodes")

    lines.append(f"\nConfluence: {_CONFLUENCE_WATCH.get(projection.confluence_strength, '')}")
    if projection.confluence_signals:
        lines.append("Signals: " + " | ".join(projection.confluence_signals[:3]))

    # Watch-for triggers
    triggers = _watch_for_triggers(projection, current_price)
    lines.append("")
    for t in triggers:
        lines.append(f"• {t}")

    return "\n".join(lines)


def _levels_block(projection: ForwardProjection, phase_state: MTFPhaseState) -> str:
    lines: list[str] = ["KEY LEVELS"]
    if projection.key_resistance:
        lines.append(f"Resistance: ${projection.key_resistance:,.0f}")
    if projection.key_support:
        lines.append(f"Support: ${projection.key_support:,.0f}")

    # From 1d phase key levels
    macro = phase_state.phases.get("1d") or phase_state.phases.get("4h")
    if macro:
        kl = macro.key_levels
        if kl.get("range_high"):
            lines.append(f"Range high: ${kl['range_high']:,.0f}")
        if kl.get("range_low"):
            lines.append(f"Range low: ${kl['range_low']:,.0f}")

    return "\n".join(lines)


def _micro_block(projection: ForwardProjection) -> str:
    if not projection.micro_notes:
        return ""
    return "MICROSTRUCTURE\n" + "\n".join(f"  {n}" for n in projection.micro_notes)


def _bots_block(impact: PortfolioBotImpact, recs: Optional[list[Recommendation]] = None) -> str:
    if not impact.bot_projections:
        return "YOUR BOTS\n  (no active positions)"

    recs_by_id = {r.bot_id: r for r in recs} if recs else {}
    lines: list[str] = [f"YOUR BOTS ({len(impact.bot_projections)} active)"]

    for bot in impact.bot_projections:
        emoji = _RISK_EMOJI.get(bot.risk_class, "⚪")
        s4h = bot.scenarios.get("4h", {})
        delta = s4h.get("unrealized_delta_usd", 0.0)
        new_liq = s4h.get("new_liq_dist_pct", 100.0)

        lines.append(
            f"\n{emoji} {bot.alias} {bot.side} {bot.position_size:.2f} BTC"
        )
        lines.append(
            f"  Avg: ${bot.avg_entry:,.0f}, Liq dist: {bot.distance_to_liq_pct:.1f}%"
        )
        if s4h:
            lines.append(
                f"  4h scenario: delta {delta:+.0f} USD, new liq dist {new_liq:.1f}%"
            )

        rec = recs_by_id.get(bot.bot_id)
        if rec:
            lines.append(f"  Risk: {bot.risk_class.value}")
            if rec.action_type != ActionType.MONITOR or bot.risk_class != RiskClass.GREEN:
                lines.append(f"  Action: {rec.action}")
                lines.append(f"  Reason: {rec.reason}")
                if rec.effect:
                    lines.append(f"  Effect: {rec.effect}")
            else:
                lines.append(f"  {rec.action}")

        if bot.ga_evidence:
            lines.append(f"  Evidence: {bot.ga_evidence}")

    return "\n".join(lines)


def format_session_brief(
    session_name: str,
    phase_state: MTFPhaseState,
    projection: ForwardProjection,
    impact: PortfolioBotImpact,
    recommendations: Optional[list[Recommendation]] = None,
    current_price: float = 0.0,
) -> str:
    """Full session brief for 4×day delivery."""
    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")
    header = f"📊 {_SESSION_NAMES.get(session_name, session_name)} {now_utc}"

    blocks = [
        header,
        "",
        _phase_block(phase_state),
        "",
        _forecast_block(projection, current_price),
        "",
        _levels_block(projection, phase_state),
    ]

    micro = _micro_block(projection)
    if micro:
        blocks += ["", micro]

    blocks += [
        "",
        _bots_block(impact, recommendations),
    ]

    # GA evidence anchor — surfaces after bot block
    if impact.portfolio_ga_summary:
        blocks += ["", f"📌 {impact.portfolio_ga_summary}"]

    return "\n".join(blocks)


def format_phase_change_alert(
    old_phase: str,
    new_phase: str,
    timeframe: str,
    confidence: float,
    current_price: float,
) -> str:
    """Event alert: phase shift detected."""
    return (
        f"⚡ PHASE SHIFT {timeframe}\n"
        f"{old_phase} → {new_phase} ({confidence:.0f}% confidence)\n"
        f"Price: ${current_price:,.0f}\n"
        f"Review active bot positions for updated impact"
    )


def format_bot_risk_alert(
    bot: BotProjection,
    rec: Recommendation,
    current_price: float,
) -> str:
    """Event alert: bot risk class changed to ORANGE or RED."""
    emoji = _RISK_EMOJI.get(bot.risk_class, "⚪")
    urgency_tag = " ‼️" if rec.urgency == "urgent" else ""
    return (
        f"{emoji} BOT RISK: {bot.alias}{urgency_tag}\n"
        f"Status: {bot.risk_class.value}\n"
        f"Trigger: {rec.trigger}\n"
        f"Impact: {rec.impact}\n"
        f"Action: {rec.action}\n"
        f"Price: ${current_price:,.0f}"
    )


def format_forecast_invalidation(
    horizon: str,
    expected_direction: str,
    actual_move_pct: float,
    current_price: float,
) -> str:
    """Event alert: forecast scenario not materializing."""
    return (
        f"⚠️ FORECAST UPDATE {horizon}\n"
        f"Expected: {expected_direction}\n"
        f"Actual move: {actual_move_pct:+.1f}%\n"
        f"Scenario may be invalidating — reassessing\n"
        f"Price: ${current_price:,.0f}"
    )
