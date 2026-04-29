from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from services.advise_v2.schemas import CurrentExposure, MarketContext
from services.advise_v2.session_intelligence import is_session_open_window


class SetupMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str = Field(..., pattern=r"^P-\d+$")
    pattern_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    direction: Literal["long", "short", "neutral"]
    matched_conditions: list[str] = Field(default_factory=list)
    missing_conditions: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _PatternSpec:
    pattern_id: str
    pattern_name: str
    direction: Literal["long", "short", "neutral"]
    base_confidence: float
    evaluator: Callable[[MarketContext], tuple[list[str], list[str], float]]


def match_setups(
    market_context: MarketContext,
    current_exposure: CurrentExposure,
) -> list[SetupMatch]:
    """
    Return diagnostic SetupMatch rows for all 12 patterns, sorted by confidence DESC.

    Long patterns are dampened by 50% when net_btc > 0.5.
    Short patterns are dampened by 50% when net_btc < -0.5.
    """
    matches: list[SetupMatch] = []
    for spec in _PATTERNS:
        matched_conditions, missing_conditions, confidence = spec.evaluator(market_context)
        confidence = _apply_exposure_dampening(
            confidence=confidence,
            direction=spec.direction,
            net_btc=current_exposure.net_btc,
        )
        confidence = _apply_session_adjustments(
            pattern_id=spec.pattern_id,
            confidence=confidence,
            market_context=market_context,
            matched_conditions=matched_conditions,
            missing_conditions=missing_conditions,
        )
        matches.append(
            SetupMatch(
                pattern_id=spec.pattern_id,
                pattern_name=spec.pattern_name,
                confidence=max(0.0, min(1.0, confidence)),
                direction=spec.direction,
                matched_conditions=matched_conditions,
                missing_conditions=missing_conditions,
            )
        )
    return sorted(matches, key=lambda match: (-match.confidence, match.pattern_id))


def _apply_exposure_dampening(confidence: float, direction: str, net_btc: float) -> float:
    if direction == "long" and net_btc > 0.5:
        return confidence * 0.5
    if direction == "short" and net_btc < -0.5:
        return confidence * 0.5
    return confidence


def _apply_session_adjustments(
    pattern_id: str,
    confidence: float,
    market_context: MarketContext,
    matched_conditions: list[str],
    missing_conditions: list[str],
) -> float:
    session = market_context.session

    if session.is_weekend:
        matched_conditions.append("weekend_low_liquidity")
        confidence *= 0.5
    else:
        missing_conditions.append("weekend_low_liquidity")

    in_open_window = is_session_open_window(session, 30)

    if pattern_id in {"P-2", "P-6"}:
        if in_open_window and session.kz_active in {"LONDON", "NY_AM"}:
            matched_conditions.append(f"{session.kz_active.lower()}_open_window_boost")
            confidence += 0.10
        else:
            missing_conditions.append("london_or_ny_am_open_window")

    if pattern_id in {"P-1", "P-7"}:
        if session.kz_active == "ASIA":
            matched_conditions.append("asia_session_range_boost")
            confidence += 0.05
        else:
            missing_conditions.append("asia_session_range_boost")

    if pattern_id == "P-9":
        if in_open_window and session.kz_active == "NY_AM":
            matched_conditions.append("ny_am_open_window_boost")
            confidence += 0.10
        else:
            missing_conditions.append("ny_am_open_window_boost")

    if pattern_id in {"P-3", "P-4"}:
        if session.is_friday_close:
            matched_conditions.append("friday_close_dampened")
            confidence -= 0.10
        else:
            missing_conditions.append("friday_close_dampened")

    return confidence


def _score_pattern(
    matched_conditions: list[str],
    missing_conditions: list[str],
    base_confidence: float,
    modifier_bonus: float = 0.0,
) -> float:
    total_conditions = len(matched_conditions) + len(missing_conditions)
    if base_confidence == 0.0 or total_conditions == 0:
        return 0.0
    return (base_confidence * (len(matched_conditions) / total_conditions)) + modifier_bonus


def _within_pct(price: float, level: float, pct: float) -> bool:
    if level <= 0:
        return False
    return abs(price - level) / level <= pct


def _in_range(value: float, low: float, high: float) -> bool:
    return low <= value <= high


def _eval_p1(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label in {"range_tight", "range_wide"}:
        matched.append(f"regime_label={market_context.regime_label} matched")
    else:
        missing.append("regime_label in {range_tight, range_wide}")
    if market_context.rsi_1h > 65:
        matched.append(f"rsi_1h={market_context.rsi_1h} > 65")
    else:
        missing.append("rsi_1h > 65")
    if market_context.price_change_5m_30bars_pct > 0.5:
        matched.append(f"price_change_5m_30bars_pct={market_context.price_change_5m_30bars_pct} > 0.5")
    else:
        missing.append("price_change_5m_30bars_pct > 0.5")
    modifier_hits = {"upper_band_test", "volume_decline"} & set(market_context.regime_modifiers)
    confidence = _score_pattern(matched, missing, 0.6, modifier_bonus=0.1 * len(modifier_hits))
    return matched, missing, confidence


def _eval_p2(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label in {"impulse_down", "impulse_down_exhausting"}:
        matched.append(f"regime_label={market_context.regime_label} matched")
    else:
        missing.append("regime_label in {impulse_down, impulse_down_exhausting}")
    if market_context.rsi_1h < 35:
        matched.append(f"rsi_1h={market_context.rsi_1h} < 35")
    else:
        missing.append("rsi_1h < 35")
    if market_context.price_change_5m_30bars_pct < -1.0:
        matched.append(f"price_change_5m_30bars_pct={market_context.price_change_5m_30bars_pct} < -1.0")
    else:
        missing.append("price_change_5m_30bars_pct < -1.0")
    if market_context.nearest_liq_below is not None:
        matched.append("nearest_liq_below is present")
        if _within_pct(market_context.price_btc, market_context.nearest_liq_below.price, 0.003):
            matched.append("price within 0.3% of nearest_liq_below.price")
        else:
            missing.append("price within 0.3% of nearest_liq_below.price")
    else:
        missing.append("nearest_liq_below is not None")
        missing.append("price within 0.3% of nearest_liq_below.price")
    bonus = 0.1 if "volume_spike_5m" in market_context.regime_modifiers else 0.0
    bonus += 0.1 if "liq_cluster_breached_below" in market_context.regime_modifiers else 0.0
    confidence = _score_pattern(matched, missing, 0.7, modifier_bonus=bonus)
    return matched, missing, confidence


def _eval_p3(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label == "trend_down":
        matched.append("regime_label=trend_down matched")
    else:
        missing.append("regime_label == trend_down")
    if market_context.price_change_5m_30bars_pct > 0.4:
        matched.append(f"price_change_5m_30bars_pct={market_context.price_change_5m_30bars_pct} > 0.4")
    else:
        missing.append("price_change_5m_30bars_pct > 0.4")
    if _in_range(market_context.rsi_1h, 40, 55):
        matched.append(f"rsi_1h={market_context.rsi_1h} in range 40-55")
    else:
        missing.append("rsi_1h in range 40-55")
    bonus = 0.1 if "pullback_to_ema" in market_context.regime_modifiers else 0.0
    confidence = _score_pattern(matched, missing, 0.65, modifier_bonus=bonus)
    return matched, missing, confidence


def _eval_p4(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label == "trend_up":
        matched.append("regime_label=trend_up matched")
    else:
        missing.append("regime_label == trend_up")
    if market_context.price_change_5m_30bars_pct < -0.4:
        matched.append(f"price_change_5m_30bars_pct={market_context.price_change_5m_30bars_pct} < -0.4")
    else:
        missing.append("price_change_5m_30bars_pct < -0.4")
    if _in_range(market_context.rsi_1h, 45, 60):
        matched.append(f"rsi_1h={market_context.rsi_1h} in range 45-60")
    else:
        missing.append("rsi_1h in range 45-60")
    bonus = 0.1 if "pullback_to_ema" in market_context.regime_modifiers else 0.0
    confidence = _score_pattern(matched, missing, 0.65, modifier_bonus=bonus)
    return matched, missing, confidence


def _eval_p5(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label in {"impulse_down", "trend_down"}:
        matched.append(f"regime_label={market_context.regime_label} matched")
    else:
        missing.append("regime_label in {impulse_down, trend_down}")
    if market_context.rsi_1h > 30:
        matched.append(f"rsi_1h={market_context.rsi_1h} > 30")
    else:
        missing.append("rsi_1h > 30")
    if market_context.price_change_1h_pct < -1.5:
        matched.append(f"price_change_1h_pct={market_context.price_change_1h_pct} < -1.5")
    else:
        missing.append("price_change_1h_pct < -1.5")
    return matched, missing, 0.0


def _eval_p6(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label in {"impulse_up", "impulse_up_exhausting"}:
        matched.append(f"regime_label={market_context.regime_label} matched")
    else:
        missing.append("regime_label in {impulse_up, impulse_up_exhausting}")
    if market_context.rsi_1h > 65:
        matched.append(f"rsi_1h={market_context.rsi_1h} > 65")
    else:
        missing.append("rsi_1h > 65")
    if market_context.price_change_5m_30bars_pct > 1.0:
        matched.append(f"price_change_5m_30bars_pct={market_context.price_change_5m_30bars_pct} > 1.0")
    else:
        missing.append("price_change_5m_30bars_pct > 1.0")
    if market_context.nearest_liq_above is not None:
        matched.append("nearest_liq_above is present")
        if _within_pct(market_context.price_btc, market_context.nearest_liq_above.price, 0.003):
            matched.append("price within 0.3% of nearest_liq_above.price")
        else:
            missing.append("price within 0.3% of nearest_liq_above.price")
    else:
        missing.append("nearest_liq_above is not None")
        missing.append("price within 0.3% of nearest_liq_above.price")
    bonus = 0.1 if "volume_spike_5m" in market_context.regime_modifiers else 0.0
    bonus += 0.1 if "liq_cluster_breached_above" in market_context.regime_modifiers else 0.0
    confidence = _score_pattern(matched, missing, 0.7, modifier_bonus=bonus)
    return matched, missing, confidence


def _eval_p7(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label in {"range_tight", "range_wide"}:
        matched.append(f"regime_label={market_context.regime_label} matched")
    else:
        missing.append("regime_label in {range_tight, range_wide}")
    if market_context.rsi_1h < 35:
        matched.append(f"rsi_1h={market_context.rsi_1h} < 35")
    else:
        missing.append("rsi_1h < 35")
    if market_context.price_change_5m_30bars_pct < -0.5:
        matched.append(f"price_change_5m_30bars_pct={market_context.price_change_5m_30bars_pct} < -0.5")
    else:
        missing.append("price_change_5m_30bars_pct < -0.5")
    modifier_hits = {"lower_band_test", "volume_decline"} & set(market_context.regime_modifiers)
    confidence = _score_pattern(matched, missing, 0.6, modifier_bonus=0.1 * len(modifier_hits))
    return matched, missing, confidence


def _eval_p8(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label in {"impulse_up", "trend_up"}:
        matched.append(f"regime_label={market_context.regime_label} matched")
    else:
        missing.append("regime_label in {impulse_up, trend_up}")
    if market_context.rsi_1h < 70:
        matched.append(f"rsi_1h={market_context.rsi_1h} < 70")
    else:
        missing.append("rsi_1h < 70")
    if market_context.price_change_1h_pct > 1.5:
        matched.append(f"price_change_1h_pct={market_context.price_change_1h_pct} > 1.5")
    else:
        missing.append("price_change_1h_pct > 1.5")
    return matched, missing, 0.0


def _eval_p9(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label in {"impulse_up", "trend_up"}:
        matched.append(f"regime_label={market_context.regime_label} matched")
    else:
        missing.append("regime_label in {impulse_up, trend_up}")
    if _in_range(market_context.rsi_1h, 55, 70):
        matched.append(f"rsi_1h={market_context.rsi_1h} in range 55-70")
    else:
        missing.append("rsi_1h in range 55-70")
    if market_context.price_change_5m_30bars_pct > 0.8:
        matched.append(f"price_change_5m_30bars_pct={market_context.price_change_5m_30bars_pct} > 0.8")
    else:
        missing.append("price_change_5m_30bars_pct > 0.8")
    if market_context.nearest_liq_above is None or market_context.price_btc > market_context.nearest_liq_above.price:
        matched.append("nearest_liq_above is None or already broken")
    else:
        missing.append("nearest_liq_above is None or price > nearest_liq_above.price")
    bonus = 0.15 if "volume_spike_5m" in market_context.regime_modifiers else 0.0
    confidence = _score_pattern(matched, missing, 0.55, modifier_bonus=bonus)
    return matched, missing, confidence


def _eval_p10(_: MarketContext) -> tuple[list[str], list[str], float]:
    return [], ["session_history_required"], 0.0


def _eval_p11(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label == "consolidation":
        matched.append("regime_label=consolidation matched")
    else:
        missing.append("regime_label == consolidation")
    if _in_range(market_context.rsi_1h, 40, 50):
        matched.append(f"rsi_1h={market_context.rsi_1h} in range 40-50")
    else:
        missing.append("rsi_1h in range 40-50")
    if abs(market_context.price_change_1h_pct) < 0.5:
        matched.append(f"|price_change_1h_pct|={abs(market_context.price_change_1h_pct)} < 0.5")
    else:
        missing.append("abs(price_change_1h_pct) < 0.5")
    confidence = _score_pattern(matched, missing, 0.5)
    return matched, missing, confidence


def _eval_p12(market_context: MarketContext) -> tuple[list[str], list[str], float]:
    matched, missing = [], []
    if market_context.regime_label == "consolidation":
        matched.append("regime_label=consolidation matched")
    else:
        missing.append("regime_label == consolidation")
    if _in_range(market_context.rsi_1h, 50, 60):
        matched.append(f"rsi_1h={market_context.rsi_1h} in range 50-60")
    else:
        missing.append("rsi_1h in range 50-60")
    if abs(market_context.price_change_1h_pct) < 0.5:
        matched.append(f"|price_change_1h_pct|={abs(market_context.price_change_1h_pct)} < 0.5")
    else:
        missing.append("abs(price_change_1h_pct) < 0.5")
    confidence = _score_pattern(matched, missing, 0.5)
    return matched, missing, confidence


_PATTERNS: tuple[_PatternSpec, ...] = (
    _PatternSpec("P-1", "Range fade short", "short", 0.6, _eval_p1),
    _PatternSpec("P-2", "Reversal long after liq cascade", "long", 0.7, _eval_p2),
    _PatternSpec("P-3", "Trend continuation short after pullback", "short", 0.65, _eval_p3),
    _PatternSpec("P-4", "Trend continuation long after pullback", "long", 0.65, _eval_p4),
    _PatternSpec("P-5", "HARD_BAN counter-trend long in strong downtrend", "long", 0.0, _eval_p5),
    _PatternSpec("P-6", "Reversal short after liq cascade up", "short", 0.7, _eval_p6),
    _PatternSpec("P-7", "Range fade long", "long", 0.6, _eval_p7),
    _PatternSpec("P-8", "HARD_BAN counter-trend short in strong uptrend", "short", 0.0, _eval_p8),
    _PatternSpec("P-9", "Breakout long", "long", 0.55, _eval_p9),
    _PatternSpec("P-10", "HARD_BAN re-short after recent stop hit", "short", 0.0, _eval_p10),
    _PatternSpec("P-11", "Range continuation long", "long", 0.5, _eval_p11),
    _PatternSpec("P-12", "Range continuation short", "short", 0.5, _eval_p12),
)
