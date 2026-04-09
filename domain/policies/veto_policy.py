from __future__ import annotations

from domain.contracts.strategy_evaluation import StrategyEvaluation


class VetoPolicy:
    def is_blocked(self, evaluation: StrategyEvaluation) -> bool:
        return bool(evaluation.vetoes)
