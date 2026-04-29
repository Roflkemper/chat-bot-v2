from __future__ import annotations

from services.advise_v2.schemas import CurrentExposure, MarketContext, TrendHandling

_REGIME_BASE_SCORES = {
    "trend_up": 0.8,
    "trend_down": 0.8,
    "impulse_up": 0.7,
    "impulse_down": 0.7,
    "impulse_up_exhausting": 0.5,
    "impulse_down_exhausting": 0.5,
    "range_wide": 0.3,
    "range_tight": 0.2,
    "consolidation": 0.2,
    "unknown": 0.0,
}
_UP_REGIMES = {"impulse_up", "impulse_up_exhausting", "trend_up"}
_DOWN_REGIMES = {"impulse_down", "impulse_down_exhausting", "trend_down"}
_ALIGNMENT_THRESHOLD = 0.3
_NEUTRAL_NET_THRESHOLD = 0.05


def compute_trend_handling(
    market_context: MarketContext,
    current_exposure: CurrentExposure,
) -> TrendHandling:
    """
    Return trend_handling block for the signal envelope.

    Computes:
    - current_trend_strength: 0..1 based on regime_label and price_change_1h_pct
    - if_trend_continues_aligned: behavior if trend continues with current net position
    - if_trend_reverses_against: behavior if trend reverses against current net position
    - de_risking_rule: adverse de-risking guidance for the current exposure
    """
    score = _trend_strength_score(market_context)
    trend_dir = _trend_direction(market_context)
    alignment = _position_alignment(current_exposure.net_btc, trend_dir)

    net = current_exposure.net_btc
    available_usd = current_exposure.available_usd

    if alignment == "against":
        de_risking_rule = (
            f"Position {abs(net):.3f} BTC against {trend_dir} trend. "
            f"Per +{1.0:.1f}% adverse move, close "
            f"{25}% of remaining net position. "
            f"Realized buffer: ${available_usd:.0f} "
            f"covers {25 * 4}% reduction lossless."
        )
        if_trend_continues_aligned = (
            f"Trend continues {trend_dir}: position deepens DD. "
            f"De-risking rule activates per +1% adverse step."
        )
        if_trend_reverses_against = (
            f"Reversal from {trend_dir}: existing adverse position "
            f"becomes aligned. Hold and tap profits as price returns "
            f"to entry zones."
        )
    elif alignment == "aligned":
        de_risking_rule = (
            f"Position {abs(net):.3f} BTC aligned with {trend_dir} trend. "
            f"Hold and tap partial profits at next liq cluster "
            f"or +{0.5}% from current. No de-risking trigger."
        )
        if_trend_continues_aligned = (
            f"Trend continues {trend_dir}: existing position generates "
            f"unrealized gains. Production bots farm trigger volume. "
            f"No action required from operator until liq cluster ahead."
        )
        if_trend_reverses_against = (
            f"Reversal from {trend_dir}: aligned position becomes "
            f"adverse. De-risking activates per +1% reversal step. "
            f"Watch nearest liq cluster as confirmation level."
        )
    else:
        de_risking_rule = (
            f"Net exposure |{net:.3f}| BTC near neutral or "
            f"trend direction unclear. No active de-risking rule. "
            f"Watch for regime confirmation before adding."
        )
        if_trend_continues_aligned = (
            "Trend direction unclear. No specific continuation behavior "
            "predicted; await next regime classification cycle."
        )
        if_trend_reverses_against = (
            "Reversal from neutral state ambiguous. Await confirmation "
            "candle close before initiating new position."
        )

    return TrendHandling(
        current_trend_strength=score,
        if_trend_continues_aligned=if_trend_continues_aligned,
        if_trend_reverses_against=if_trend_reverses_against,
        de_risking_rule=de_risking_rule,
    )


def _trend_strength_score(market_context: MarketContext) -> float:
    base = _REGIME_BASE_SCORES[market_context.regime_label]
    abs_change = abs(market_context.price_change_1h_pct)
    if abs_change > 2.5:
        modifier = 0.15
    elif abs_change > 1.5:
        modifier = 0.10
    elif abs_change > 0.8:
        modifier = 0.05
    else:
        modifier = 0.0
    return min(1.0, base + modifier)


def _trend_direction(market_context: MarketContext) -> str:
    if (
        market_context.regime_label in _UP_REGIMES
        or market_context.price_change_1h_pct > _ALIGNMENT_THRESHOLD
    ):
        return "up"
    if (
        market_context.regime_label in _DOWN_REGIMES
        or market_context.price_change_1h_pct < -_ALIGNMENT_THRESHOLD
    ):
        return "down"
    return "neutral"


def _position_alignment(net_btc: float, trend_dir: str) -> str:
    if abs(net_btc) <= _NEUTRAL_NET_THRESHOLD or trend_dir == "neutral":
        return "neutral"
    if (net_btc < -_NEUTRAL_NET_THRESHOLD and trend_dir == "down") or (
        net_btc > _NEUTRAL_NET_THRESHOLD and trend_dir == "up"
    ):
        return "aligned"
    if (net_btc < -_NEUTRAL_NET_THRESHOLD and trend_dir == "up") or (
        net_btc > _NEUTRAL_NET_THRESHOLD and trend_dir == "down"
    ):
        return "against"
    return "neutral"
