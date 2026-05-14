from __future__ import annotations

from dataclasses import dataclass
from domain.services.market_pipeline import MarketPipeline
from domain.services.feature_pipeline import FeaturePipeline
from domain.services.context_pipeline import ContextPipeline
from strategies.registry import StrategyRegistry
from domain.services.final_decision_arbiter import FinalDecisionArbiter
from execution.planner.execution_planner import ExecutionPlanner
from renderers.builders.analysis_view_builder import AnalysisViewBuilder
from renderers.builders.final_decision_view_builder import FinalDecisionViewBuilder
from renderers.builders.action_view_builder import ActionViewBuilder
from renderers.builders.grid_view_builder import GridViewBuilder


@dataclass(slots=True)
class CommandRouter:
    market_pipeline: MarketPipeline
    feature_pipeline: FeaturePipeline
    context_pipeline: ContextPipeline
    strategy_registry: StrategyRegistry
    arbiter: FinalDecisionArbiter
    execution_planner: ExecutionPlanner

    def build_minimal_views(self, symbol: str, timeframe: str) -> dict[str, object]:
        raw = self.market_pipeline.run(symbol=symbol, timeframe=timeframe)
        features = self.feature_pipeline.run(raw)
        context = self.context_pipeline.run(raw, features)
        evaluations = self.strategy_registry.run_all(context)
        decision = self.arbiter.run(context, evaluations)
        execution = self.execution_planner.run(decision)
        return {
            'analysis': AnalysisViewBuilder().build(context),
            'final_decision': FinalDecisionViewBuilder().build(decision),
            'action': ActionViewBuilder().build(decision, execution),
            'grid': GridViewBuilder().build(decision, execution),
        }
