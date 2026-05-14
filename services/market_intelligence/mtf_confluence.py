"""Multi-timeframe confluence scorer.

Aggregates signals from multiple timeframes (15m, 1h, 4h) and pattern types
to produce a directional bias score and confidence level.

Score range: -100 (strong bearish) to +100 (strong bullish)
Confluence threshold for alert: abs(score) >= 40
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .order_blocks import OrderBlock, OBType
from .msb_detector import MSBEvent, MSBType
from .premium_discount import FVG, PremiumDiscountLevel, PriceZone
from .ict_killzones import KillzoneState, Session
from .event_detectors import (
    FundingSignal, FundingBias,
    OIDeltaSignal, OIBias,
    TakerSignal, TakerBias,
    RSIDivSignal, DivType,
    PinBarSignal, PinBarType,
)


class ConfluenceBias(str, Enum):
    STRONG_BULL = "strong_bull"
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"
    STRONG_BEAR = "strong_bear"


@dataclass
class ConfluenceScore:
    score: float                   # -100 to +100
    bias: ConfluenceBias
    contributing_signals: list[str] = field(default_factory=list)
    alert_worthy: bool = False     # True if abs(score) >= threshold
    timeframes_agree: bool = False # True if 15m + 1h + 4h all point same direction


def _bias(score: float) -> ConfluenceBias:
    if score >= 60:
        return ConfluenceBias.STRONG_BULL
    if score >= 30:
        return ConfluenceBias.BULL
    if score <= -60:
        return ConfluenceBias.STRONG_BEAR
    if score <= -30:
        return ConfluenceBias.BEAR
    return ConfluenceBias.NEUTRAL


def compute_confluence(
    killzone: Optional[KillzoneState] = None,
    pd_level: Optional[PremiumDiscountLevel] = None,
    obs: Optional[list[OrderBlock]] = None,
    fvgs: Optional[list[FVG]] = None,
    msb_events: Optional[list[MSBEvent]] = None,
    funding: Optional[FundingSignal] = None,
    oi: Optional[OIDeltaSignal] = None,
    taker: Optional[TakerSignal] = None,
    rsi_div: Optional[RSIDivSignal] = None,
    pin_bar: Optional[PinBarSignal] = None,
    alert_threshold: float = 40.0,
) -> ConfluenceScore:
    """Compute directional confluence from all available signals."""
    score = 0.0
    signals: list[str] = []

    # Premium/Discount: price in discount = bullish bias, premium = bearish
    if pd_level is not None:
        if pd_level.current_zone == PriceZone.DISCOUNT:
            score += 20
            signals.append("price_in_discount(+20)")
        elif pd_level.current_zone == PriceZone.PREMIUM:
            score -= 20
            signals.append("price_in_premium(-20)")

    # FVG: unmitigated bullish FVG below = support; bearish above = resistance
    if fvgs:
        cp = (pd_level.current_price if pd_level else 0)
        for fvg in fvgs[:3]:
            if not fvg.filled:
                if fvg.bullish and fvg.high < cp:
                    score += 10
                    signals.append(f"bull_fvg_below(+10)")
                    break
                if not fvg.bullish and fvg.low > cp:
                    score -= 10
                    signals.append(f"bear_fvg_above(-10)")
                    break

    # Order blocks
    if obs:
        cp = (pd_level.current_price if pd_level else 0)
        for ob in obs[:3]:
            if not ob.mitigated:
                if ob.ob_type == OBType.BULLISH and ob.high < cp:
                    score += 15
                    signals.append("bull_ob_below(+15)")
                    break
                if ob.ob_type == OBType.BEARISH and ob.low > cp:
                    score -= 15
                    signals.append("bear_ob_above(-15)")
                    break

    # MSB events — most recent
    if msb_events:
        latest = msb_events[0]
        if latest.msb_type in (MSBType.BOS_UP, MSBType.CHOCH_UP):
            pts = 20 if latest.msb_type == MSBType.CHOCH_UP else 10
            score += pts
            signals.append(f"{latest.msb_type.value}(+{pts})")
        elif latest.msb_type in (MSBType.BOS_DN, MSBType.CHOCH_DN):
            pts = 20 if latest.msb_type == MSBType.CHOCH_DN else 10
            score -= pts
            signals.append(f"{latest.msb_type.value}(-{pts})")

    # Funding extremes
    if funding:
        if funding.bias == FundingBias.EXTREME_LONG:
            score -= 10
            signals.append("funding_extreme_long(-10)")
        elif funding.bias == FundingBias.EXTREME_SHORT:
            score += 10
            signals.append("funding_extreme_short(+10)")

    # OI extremes
    if oi:
        if oi.bias == OIBias.SPIKE_UP:
            score += 5
            signals.append("oi_spike_up(+5)")
        elif oi.bias == OIBias.SPIKE_DN:
            score -= 5
            signals.append("oi_spike_dn(-5)")

    # Taker bias
    if taker:
        if taker.bias == TakerBias.HEAVY_BUY:
            score += 10
            signals.append("taker_heavy_buy(+10)")
        elif taker.bias == TakerBias.HEAVY_SELL:
            score -= 10
            signals.append("taker_heavy_sell(-10)")

    # RSI divergence
    if rsi_div:
        if rsi_div.div_type == DivType.BULLISH:
            score += 15
            signals.append("rsi_div_bull(+15)")
        elif rsi_div.div_type == DivType.BEARISH:
            score -= 15
            signals.append("rsi_div_bear(-15)")

    # Pin bar
    if pin_bar:
        if pin_bar.pin_type == PinBarType.HAMMER:
            score += 10
            signals.append("pin_bar_hammer(+10)")
        elif pin_bar.pin_type == PinBarType.SHOOTING_STAR:
            score -= 10
            signals.append("pin_bar_shooting_star(-10)")

    # Clamp score to [-100, 100]
    score = max(-100.0, min(100.0, score))

    return ConfluenceScore(
        score=round(score, 1),
        bias=_bias(score),
        contributing_signals=signals,
        alert_worthy=abs(score) >= alert_threshold,
        timeframes_agree=len(signals) >= 3 and all(
            (s.startswith("bull") or "(+" in s) == (score > 0) for s in signals
        ),
    )
