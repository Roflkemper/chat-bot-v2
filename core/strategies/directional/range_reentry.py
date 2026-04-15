from __future__ import annotations

from domain.contracts.market_context import MarketContext
from domain.contracts.strategy_evaluation import StrategyEvaluation
from strategies.base import StrategyBase


class RangeReentryStrategy(StrategyBase):
    strategy_id = 'range_reentry'
    family = 'directional'

    def evaluate(self, context: MarketContext) -> StrategyEvaluation | None:
        if not context.regime_context.get('range_friendly', False):
            return None
        location = context.location_context.get('price_location', 'UNKNOWN')
        if location == 'UPPER':
            return StrategyEvaluation(
                strategy_id=self.strategy_id,
                family=self.family,
                side='SHORT',
                state='WATCH_SETUP',
                action_type='reentry',
                score=55.0,
                confidence=0.5,
                summary='Short reentry от верхней части диапазона.',
                why=['range_friendly', 'upper_zone'],
                trigger='return inside range',
                invalidation='acceptance above range high',
                entry_model='range_reentry',
            )
        if location == 'LOWER':
            return StrategyEvaluation(
                strategy_id=self.strategy_id,
                family=self.family,
                side='LONG',
                state='WATCH_SETUP',
                action_type='reentry',
                score=55.0,
                confidence=0.5,
                summary='Long reentry от нижней части диапазона.',
                why=['range_friendly', 'lower_zone'],
                trigger='return inside range',
                invalidation='acceptance below range low',
                entry_model='range_reentry',
            )
        return None
