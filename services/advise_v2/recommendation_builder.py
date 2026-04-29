from __future__ import annotations

from services.advise_v2.schemas import (
    CurrentExposure,
    MarketContext,
    Recommendation,
    RecommendationInvalidation,
    RecommendationTarget,
    TrendHandling,
)
from services.advise_v2.setup_matcher import SetupMatch

_SHORT_PATTERNS = {"P-1", "P-3", "P-6", "P-12"}
_LONG_PATTERNS = {"P-2", "P-4", "P-7", "P-9", "P-11"}


def build_recommendation(
    top_match: SetupMatch,
    market_context: MarketContext,
    current_exposure: CurrentExposure,
    trend_handling: TrendHandling,
) -> Recommendation:
    """
    Pure function. Build Recommendation from top matched setup and context.
    """
    del trend_handling
    if top_match.confidence == 0:
        raise ValueError("top_match.confidence must be > 0")

    primary_action = _primary_action(top_match.pattern_id)
    is_long = primary_action == "increase_long_manual"

    base_size, base_label = _base_size(current_exposure.free_margin_pct, top_match.confidence)
    size_btc = _round_2(base_size * top_match.confidence)
    size_usd_inverse = _round_2(size_btc * market_context.price_btc) if is_long else None
    entry_zone = _entry_zone(is_long, market_context)
    invalidation = _invalidation(is_long, market_context.price_btc)
    targets = _targets(is_long, market_context.price_btc)
    max_hold_hours = _max_hold_hours(top_match.pattern_id)
    size_rationale = (
        f"{base_label} — confidence {top_match.confidence:.2f}, "
        f"free margin {current_exposure.free_margin_pct:.0f}%"
    )

    return Recommendation(
        primary_action=primary_action,
        size_btc_equivalent=size_btc,
        size_usd_inverse=size_usd_inverse,
        size_rationale=size_rationale,
        entry_zone=entry_zone,
        invalidation=invalidation,
        targets=targets,
        max_hold_hours=max_hold_hours,
    )


def _primary_action(pattern_id: str) -> str:
    if pattern_id in _SHORT_PATTERNS:
        return "increase_short_manual"
    if pattern_id in _LONG_PATTERNS:
        return "increase_long_manual"
    raise ValueError(f"Unsupported pattern_id for recommendation: {pattern_id}")


def _base_size(free_margin_pct: float, confidence: float) -> tuple[float, str]:
    if confidence < 0.3:
        return 0.10, "conservative"
    if free_margin_pct < 30:
        return 0.05, "conservative"
    if free_margin_pct > 60:
        return 0.18, "aggressive"
    return 0.10, "normal"


def _entry_zone(is_long: bool, market_context: MarketContext) -> tuple[float, float]:
    price = market_context.price_btc
    if is_long:
        low = price * (1 - 0.005)
        high = price * (1 + 0.001)
        if market_context.nearest_liq_below is not None:
            low = market_context.nearest_liq_below.price
        return (_round_price(low), _round_price(high))
    low = price * (1 - 0.001)
    high = price * (1 + 0.005)
    if market_context.nearest_liq_above is not None:
        high = market_context.nearest_liq_above.price
    return (_round_price(low), _round_price(high))


def _invalidation(is_long: bool, price: float) -> RecommendationInvalidation:
    if is_long:
        return RecommendationInvalidation(
            rule=f"5m close below {_round_price(price * (1 - 0.007)):.0f}",
            reason="next major level breach, V failed",
        )
    return RecommendationInvalidation(
        rule=f"5m close above {_round_price(price * (1 + 0.007)):.0f}",
        reason="rejection failed, momentum continues up",
    )


def _targets(is_long: bool, price: float) -> list[RecommendationTarget]:
    multipliers = (1.006, 1.01, 1.015) if is_long else (0.994, 0.99, 0.985)
    rationales = (
        ("first resistance", "session VWAP", "rally extension")
        if is_long
        else ("first support", "session VWAP", "decline extension")
    )
    sizes = (30, 30, 40)
    return [
        RecommendationTarget(
            price=_round_price(price * multiplier),
            size_pct=size_pct,
            rationale=rationale,
        )
        for multiplier, size_pct, rationale in zip(multipliers, sizes, rationales)
    ]


def _max_hold_hours(pattern_id: str) -> int:
    if pattern_id in {"P-2", "P-6"}:
        return 4
    if pattern_id in {"P-1", "P-7", "P-11", "P-12"}:
        return 6
    return 8


def _round_2(value: float) -> float:
    return round(value * 100) / 100


def _round_price(value: float) -> float:
    return float(round(value))
