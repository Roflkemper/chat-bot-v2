from __future__ import annotations

from domain.contracts.market_context import MarketContext
from domain.contracts.strategy_evaluation import StrategyEvaluation
from strategies.base import StrategyBase


class LiquidityTrapStrategy(StrategyBase):
    strategy_id = 'liquidity_trap'
    family = 'directional'

    def evaluate(self, context: MarketContext) -> StrategyEvaluation | None:
        location = context.location_context.get('price_location', 'UNKNOWN')
        reaction = context.liquidity_context.get('acceptance_vs_rejection', 'NONE')
        if location == 'UPPER' and 'REJECT' in str(reaction).upper():
            return StrategyEvaluation(
                strategy_id=self.strategy_id,
                family=self.family,
                side='SHORT',
                state='ARM_SHORT',
                action_type='trap',
                score=70.0,
                confidence=0.62,
                summary='Ловушка ликвидности сверху, short-подготовка.',
                why=['rejected_above', 'upper_edge_context'],
                trigger='retake below rejection zone',
                invalidation='acceptance above upper block',
                entry_model='rejection_probe',
            )
        if location == 'LOWER' and 'REJECT' in str(reaction).upper():
            return StrategyEvaluation(
                strategy_id=self.strategy_id,
                family=self.family,
                side='LONG',
                state='ARM_LONG',
                action_type='trap',
                score=70.0,
                confidence=0.62,
                summary='Ловушка ликвидности снизу, long-подготовка.',
                why=['rejected_below', 'lower_edge_context'],
                trigger='retake above rejection zone',
                invalidation='acceptance below lower block',
                entry_model='rejection_probe',
            )
        return None
