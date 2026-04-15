from __future__ import annotations

from abc import ABC, abstractmethod
from domain.contracts.market_context import MarketContext
from domain.contracts.strategy_evaluation import StrategyEvaluation


class StrategyBase(ABC):
    strategy_id: str
    family: str
    priority: int = 100

    @abstractmethod
    def evaluate(self, context: MarketContext) -> StrategyEvaluation | None:
        raise NotImplementedError
