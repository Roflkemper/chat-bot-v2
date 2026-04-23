from __future__ import annotations

from domain.contracts.market_context import MarketContext
from domain.contracts.strategy_evaluation import StrategyEvaluation
from strategies.base import StrategyBase


class GridPreactivationStrategy(StrategyBase):
    strategy_id = 'grid_preactivation'
    family = 'grid'

    def evaluate(self, context: MarketContext) -> StrategyEvaluation | None:
        allowances = context.strategy_allowance_context
        location = context.location_context.get('price_location', 'UNKNOWN')
        if allowances.get('allow_grid_short') and location == 'UPPER':
            return StrategyEvaluation(
                strategy_id=self.strategy_id,
                family=self.family,
                side='SHORT',
                state='GRID_PREARM_SHORT',
                action_type='grid',
                score=60.0,
                confidence=0.58,
                summary='Разрешён ранний prearm short-grid у верхнего блока.',
                why=['grid_short_allowed', 'upper_zone'],
                grid_bias='SHORT',
            )
        if allowances.get('allow_grid_long') and location == 'LOWER':
            return StrategyEvaluation(
                strategy_id=self.strategy_id,
                family=self.family,
                side='LONG',
                state='GRID_PREARM_LONG',
                action_type='grid',
                score=60.0,
                confidence=0.58,
                summary='Разрешён ранний prearm long-grid у нижнего блока.',
                why=['grid_long_allowed', 'lower_zone'],
                grid_bias='LONG',
            )
        return StrategyEvaluation(
            strategy_id=self.strategy_id,
            family=self.family,
            side='NEUTRAL',
            state='GRID_HOLD',
            action_type='grid',
            score=10.0,
            confidence=0.2,
            summary='Grid в hold до нормальной реакции.',
            why=['no_edge_for_grid'],
            grid_bias='NONE',
        )
