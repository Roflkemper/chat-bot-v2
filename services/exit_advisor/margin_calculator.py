"""Margin calculator: estimate margin requirement per exit recommendation.

For each RankedStrategy, computes the USD margin needed and whether
the operator can afford it given current free_margin.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .strategy_ranker import ExitFamily, RankedStrategy

# Approximate BTC leverage (conservative estimate: 10x cross margin)
_DEFAULT_LEVERAGE = 10.0
_COUNTER_HEDGE_LEVERAGE = 5.0   # counter-hedge is conservative sizing

# Size tiers
_SIZE_TIERS = {
    "conservative": 0.7,   # 70% of suggested size
    "balanced": 1.0,
    "aggressive": 1.3,
}


@dataclass
class MarginRequirement:
    strategy: RankedStrategy
    required_usd: float
    affordable: bool
    size_used_btc: Optional[float]
    size_used_pct: Optional[float]
    notes: str


class MarginCalculator:
    def __init__(
        self,
        leverage: float = _DEFAULT_LEVERAGE,
        size_tier: str = "balanced",
        max_margin_pct: float = 30.0,
    ) -> None:
        self._leverage = leverage
        self._tier_factor = _SIZE_TIERS.get(size_tier, 1.0)
        self._max_margin_pct = max_margin_pct

    def compute(
        self,
        strategy: RankedStrategy,
        current_price: float,
        free_margin_usd: float,
        total_balance_usd: float,
        short_position_btc: float = 0.0,
    ) -> MarginRequirement:
        """Compute margin requirement for a single strategy."""
        required_usd = 0.0
        size_btc = None
        size_pct = None
        notes = ""

        if strategy.family == ExitFamily.A:
            # partial_close: no new margin needed — reduces margin usage
            fraction = strategy.size_pct or 25.0
            released = abs(short_position_btc) * (fraction / 100) * current_price / self._leverage
            required_usd = 0.0
            size_pct = fraction
            notes = f"releases ~${released:.0f} margin (fraction={fraction:.0f}%)"

        elif strategy.family == ExitFamily.B:
            # counter_hedge: open long → requires margin
            raw_btc = (strategy.size_btc or 0.05) * self._tier_factor
            required_usd = raw_btc * current_price / _COUNTER_HEDGE_LEVERAGE
            size_btc = raw_btc
            notes = f"counter-long {raw_btc:.3f} BTC @ ~{_COUNTER_HEDGE_LEVERAGE:.0f}x"

        elif strategy.family == ExitFamily.C:
            # boundary_adjust: no margin needed
            required_usd = 0.0
            notes = f"boundary raise +{strategy.offset_pct or 0.5:.1f}% — no margin"

        elif strategy.family == ExitFamily.D:
            # grid_tighten: no margin needed
            required_usd = 0.0
            notes = f"param change (tf={strategy.target_factor}, gs={strategy.gs_factor}) — no margin"

        elif strategy.family == ExitFamily.F:
            # composite: boundary + short stack → margin for new short
            raw_btc = (strategy.size_btc or 0.05) * self._tier_factor
            required_usd = raw_btc * current_price / self._leverage
            size_btc = raw_btc
            notes = f"add short {raw_btc:.3f} BTC + raise boundary {strategy.offset_pct or 0.5:.1f}%"

        # Affordability check
        max_allowed = total_balance_usd * self._max_margin_pct / 100
        affordable = required_usd <= free_margin_usd and required_usd <= max_allowed

        if not affordable and required_usd > 0:
            notes += f" | INSUFFICIENT: need ${required_usd:.0f}, have ${free_margin_usd:.0f} free"

        return MarginRequirement(
            strategy=strategy,
            required_usd=required_usd,
            affordable=affordable,
            size_used_btc=size_btc,
            size_used_pct=size_pct,
            notes=notes,
        )

    def compute_all(
        self,
        strategies: list[RankedStrategy],
        current_price: float,
        free_margin_usd: float,
        total_balance_usd: float,
        short_position_btc: float = 0.0,
    ) -> list[MarginRequirement]:
        results = []
        for s in strategies:
            req = self.compute(s, current_price, free_margin_usd, total_balance_usd, short_position_btc)
            s.margin_required_usd = req.required_usd
            results.append(req)
        return results
