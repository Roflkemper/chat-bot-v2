"""Recommendations engine — per-bot risk class → actionable recommendation.

Format per recommendation:
  trigger:    what market signal triggered this
  impact:     what will happen to the bot mechanically
  action:     what operator should do
  reason:     why this action improves the projected outcome
  effect:     expected improvement vs do-nothing
  confidence: based on projection confidence + GA evidence + mechanical clarity
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .bot_impact import BotProjection, PortfolioBotImpact, RiskClass
from .forward_projection import ForwardProjection, ConfluenceStrength

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    MONITOR           = "monitor"
    BOUNDARY_WIDEN    = "boundary_widen"
    BOUNDARY_TIGHTEN  = "boundary_tighten"
    PAUSE_IN          = "pause_new_in"
    MANUAL_STOP       = "manual_stop"
    COUNTER_HEDGE     = "counter_hedge"       # P-3 / P-15 reference
    COMPOSITE         = "composite"


@dataclass
class Recommendation:
    bot_id: str
    alias: str
    risk_class: RiskClass
    action_type: ActionType

    trigger: str          # what on the market triggers this
    impact: str           # projected mechanical impact on bot
    action: str           # specific action text
    reason: str           # why this action helps
    effect: str           # expected outcome improvement
    confidence: str       # LOW / MEDIUM / HIGH

    urgency: str = "normal"   # "normal" | "urgent" | "watch"
    params: dict = field(default_factory=dict)   # specific values (boundary offset, etc.)


def _confidence_label(
    confluence: ConfluenceStrength,
    n_episodes: int,
    mechanical_clear: bool,
) -> str:
    score = 0
    if confluence in (ConfluenceStrength.STRONG, ConfluenceStrength.MEDIUM):
        score += 1
    if n_episodes >= 50:
        score += 1
    if mechanical_clear:
        score += 1
    if score >= 2:
        return "HIGH"
    if score == 1:
        return "MEDIUM"
    return "LOW"


def _build_recommendation(
    bot: BotProjection,
    projection: ForwardProjection,
) -> Recommendation:
    """Build a specific recommendation for one bot given its risk class."""
    risk = bot.risk_class
    side = bot.side
    phase = projection.phase_label
    bias  = projection.phase_bias
    fc4h  = projection.forecasts.get("4h")
    n_ep  = fc4h.n_episodes if fc4h else 0
    conf_strength = projection.confluence_strength

    # Scenario data
    s4h = bot.scenarios.get("4h", {})
    projected_price = s4h.get("projected_price", 0.0)
    delta_usd       = s4h.get("unrealized_delta_usd", 0.0)
    new_liq_dist    = s4h.get("new_liq_dist_pct", 100.0)
    triggers_in     = s4h.get("triggers_in", False)

    trigger = (
        f"Phase: {phase} (bias {'bullish' if bias > 0 else 'bearish' if bias < 0 else 'neutral'}), "
        f"confluence: {conf_strength.value}"
    )

    if risk == RiskClass.GREEN:
        return Recommendation(
            bot_id=bot.bot_id,
            alias=bot.alias,
            risk_class=risk,
            action_type=ActionType.MONITOR,
            trigger=trigger,
            impact=f"Projected move favorable for {side}: ~{delta_usd:+.0f} USD at 4h target",
            action=f"Hold current position — no action required",
            reason="Projected move aligns with bot direction, position is in EV+ zone",
            effect=f"Expected unrealized improvement ~{abs(delta_usd):.0f} USD",
            confidence=_confidence_label(conf_strength, n_ep, True),
            urgency="watch",
        )

    if risk == RiskClass.YELLOW:
        return Recommendation(
            bot_id=bot.bot_id,
            alias=bot.alias,
            risk_class=risk,
            action_type=ActionType.MONITOR,
            trigger=trigger,
            impact="Direction unclear — position may face short-term drawdown",
            action="Monitor every 30 minutes. No action until clearer signal",
            reason="Insufficient confluence to recommend specific action",
            effect="Preserve optionality",
            confidence=_confidence_label(conf_strength, n_ep, False),
            urgency="normal",
        )

    if risk == RiskClass.ORANGE:
        if side == "LONG" and bias < 0:
            # LONG bot, bearish projection — IN orders will accumulate below
            boundary_target = round(projected_price * 0.98, 0) if projected_price > 0 else 0
            return Recommendation(
                bot_id=bot.bot_id,
                alias=bot.alias,
                risk_class=risk,
                action_type=ActionType.BOUNDARY_WIDEN,
                trigger=trigger,
                impact=(
                    f"Bearish move to ~{projected_price:,.0f} projected. "
                    f"Bot will open IN orders below current price, "
                    f"position grows if move continues. "
                    f"Unrealized: ~{delta_usd:+.0f} USD, liq dist: {new_liq_dist:.1f}%"
                ),
                action=(
                    f"Expand lower boundary to ~{boundary_target:,.0f} "
                    f"(below projected target {projected_price:,.0f}). "
                    f"This caps IN accumulation in the danger zone."
                ),
                reason=(
                    "Widening lower boundary prevents the bot from opening "
                    "new IN orders in the projected move zone, limiting position growth "
                    "and worst-case drawdown"
                ),
                effect=(
                    f"Max position capped vs unconstrained growth. "
                    f"Max DD reduced ~20-35% vs do-nothing (per GA backtest patterns)"
                ),
                confidence=_confidence_label(conf_strength, n_ep, True),
                urgency="urgent" if new_liq_dist < 15 else "normal",
                params={"boundary_lower_target": boundary_target},
            )

        if side == "SHORT" and bias > 0:
            return Recommendation(
                bot_id=bot.bot_id,
                alias=bot.alias,
                risk_class=risk,
                action_type=ActionType.PAUSE_IN,
                trigger=trigger,
                impact=(
                    f"Bullish move to ~{projected_price:,.0f} projected. "
                    f"SHORT bot will open IN orders above — adverse accumulation risk. "
                    f"Unrealized: ~{delta_usd:+.0f} USD"
                ),
                action=(
                    "Pause new IN orders temporarily. "
                    "Re-enable when 4h projection invalidated or price reverses"
                ),
                reason=(
                    "Pausing IN prevents the bot from adding to a losing short "
                    "in an adverse move; reduces risk of position snowballing"
                ),
                effect=(
                    "Position size frozen at current level — "
                    "max loss is bounded at current size, not growing"
                ),
                confidence=_confidence_label(conf_strength, n_ep, True),
                urgency="normal",
            )

        # Generic ORANGE
        return Recommendation(
            bot_id=bot.bot_id,
            alias=bot.alias,
            risk_class=risk,
            action_type=ActionType.COMPOSITE,
            trigger=trigger,
            impact=f"Adverse move projected. Delta: ~{delta_usd:+.0f} USD, liq dist: {new_liq_dist:.1f}%",
            action="Consider boundary adjustment or pause IN — review position manually",
            reason="Multiple adverse signals detected",
            effect="Risk reduction — specific magnitude depends on chosen action",
            confidence=_confidence_label(conf_strength, n_ep, False),
            urgency="normal",
        )

    # RED
    return Recommendation(
        bot_id=bot.bot_id,
        alias=bot.alias,
        risk_class=risk,
        action_type=ActionType.MANUAL_STOP,
        trigger=trigger,
        impact=(
            f"CRITICAL: liq distance {bot.distance_to_liq_pct:.1f}% current, "
            f"projected {new_liq_dist:.1f}% after 4h move to {projected_price:,.0f}"
        ),
        action="URGENT: Consider manual stop or emergency boundary tighten immediately",
        reason="Liquidation proximity is critical. Adverse move may trigger forced liquidation",
        effect="Avoid forced liquidation vs staying passive",
        confidence="HIGH",   # mechanical certainty even if projection uncertain
        urgency="urgent",
    )


def generate_recommendations(impact: PortfolioBotImpact) -> list[Recommendation]:
    """Generate recommendations for all bots in portfolio impact."""
    recs: list[Recommendation] = []
    for bot in impact.bot_projections:
        rec = _build_recommendation(bot, impact.projection)
        recs.append(rec)
    return recs
