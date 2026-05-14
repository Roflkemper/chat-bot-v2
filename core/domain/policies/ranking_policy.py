from __future__ import annotations

from domain.contracts.strategy_evaluation import StrategyEvaluation


class RankingPolicy:
    def pick_best(self, evaluations: list[StrategyEvaluation]) -> StrategyEvaluation | None:
        if not evaluations:
            return None
        return sorted(evaluations, key=lambda e: (e.score, e.confidence), reverse=True)[0]
