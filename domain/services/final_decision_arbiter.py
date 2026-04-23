from __future__ import annotations

from domain.contracts.final_decision import FinalDecision
from domain.contracts.market_context import MarketContext
from domain.contracts.strategy_evaluation import StrategyEvaluation
from domain.policies.ranking_policy import RankingPolicy
from domain.policies.veto_policy import VetoPolicy


class FinalDecisionArbiter:
    def __init__(self) -> None:
        self.ranking_policy = RankingPolicy()
        self.veto_policy = VetoPolicy()

    def run(self, context: MarketContext, evaluations: list[StrategyEvaluation]) -> FinalDecision:
        directional = [e for e in evaluations if e.family == 'directional' and not self.veto_policy.is_blocked(e)]
        grid = [e for e in evaluations if e.family == 'grid' and not self.veto_policy.is_blocked(e)]
        directional_winner = self.ranking_policy.pick_best(directional)
        grid_winner = self.ranking_policy.pick_best(grid)
        why = []
        not_now = []
        warnings = []
        if directional_winner:
            why.extend(directional_winner.why or [directional_winner.summary])
            warnings.extend(directional_winner.warnings)
        else:
            not_now.append('Нет подтверждённого directional-кандидата.')
        if grid_winner:
            warnings.extend(grid_winner.warnings)
        market_id = context.market_identity
        return FinalDecision(
            symbol=market_id.get('symbol', 'BTCUSDT'),
            timeframe=market_id.get('timeframe', '15m'),
            timestamp=market_id.get('timestamp', ''),
            directional_state=directional_winner.state if directional_winner else 'NO_SETUP',
            directional_side=directional_winner.side if directional_winner else 'NEUTRAL',
            directional_strategy_id=directional_winner.strategy_id if directional_winner else 'none',
            directional_score=directional_winner.score if directional_winner else 0.0,
            directional_confidence=directional_winner.confidence if directional_winner else 0.0,
            grid_state=grid_winner.state if grid_winner else 'GRID_HOLD',
            grid_side=grid_winner.side if grid_winner else 'NEUTRAL',
            grid_strategy_id=grid_winner.strategy_id if grid_winner else 'none',
            grid_score=grid_winner.score if grid_winner else 0.0,
            grid_confidence=grid_winner.confidence if grid_winner else 0.0,
            market_bias=directional_winner.side if directional_winner else 'NEUTRAL',
            primary_action=directional_winner.state if directional_winner else (grid_winner.state if grid_winner else 'WATCH'),
            primary_mode='CORE_V1',
            risk_level=context.risk_context.get('risk_level', 'HIGH'),
            why=why,
            not_now=not_now,
            where_to_watch=context.watch_context.get('where_to_watch', ''),
            next_trigger_long=context.watch_context.get('next_trigger_long', ''),
            next_trigger_short=context.watch_context.get('next_trigger_short', ''),
            invalidation_zone=context.watch_context.get('invalidation_zone_if_any', ''),
            warnings=warnings,
        )
