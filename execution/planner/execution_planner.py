from __future__ import annotations

from domain.contracts.execution_plan import ExecutionPlan
from domain.contracts.final_decision import FinalDecision
from execution.planner.directional_planner import DirectionalPlanner
from execution.planner.grid_planner import GridPlanner


class ExecutionPlanner:
    def __init__(self) -> None:
        self.directional_planner = DirectionalPlanner()
        self.grid_planner = GridPlanner()

    def run(self, decision: FinalDecision) -> ExecutionPlan:
        directional = self.directional_planner.run(decision)
        grid = self.grid_planner.run(decision)
        return ExecutionPlan(
            symbol=decision.symbol,
            timeframe=decision.timeframe,
            timestamp=decision.timestamp,
            primary_action=decision.primary_action,
            primary_mode=decision.primary_mode,
            directional_execution=directional,
            grid_execution=grid,
            operator_message=decision.why[0] if decision.why else 'Смотреть реакцию.',
            warnings=decision.warnings,
        )
