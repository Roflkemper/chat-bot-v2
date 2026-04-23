from __future__ import annotations

from dataclasses import dataclass, field
from domain.contracts.market_context import MarketContext
from domain.contracts.strategy_evaluation import StrategyEvaluation
from strategies.directional.liquidity_trap import LiquidityTrapStrategy
from strategies.directional.range_reentry import RangeReentryStrategy
from strategies.grid.grid_preactivation import GridPreactivationStrategy


@dataclass(slots=True)
class StrategyRegistry:
    strategies: list = field(default_factory=lambda: [
        LiquidityTrapStrategy(),
        RangeReentryStrategy(),
        GridPreactivationStrategy(),
    ])

    def run_all(self, context: MarketContext) -> list[StrategyEvaluation]:
        evaluations: list[StrategyEvaluation] = []
        for strategy in self.strategies:
            result = strategy.evaluate(context)
            if result is not None:
                evaluations.append(result)
        return evaluations
