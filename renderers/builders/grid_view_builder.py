from __future__ import annotations

from domain.contracts.execution_plan import ExecutionPlan
from domain.contracts.final_decision import FinalDecision
from renderers.view_models.grid_view_model import GridViewModel


class GridViewBuilder:
    def build(self, decision: FinalDecision, execution: ExecutionPlan) -> GridViewModel:
        long_state = execution.grid_execution.state if execution.grid_execution.side == 'LONG' else 'GRID_HOLD'
        short_state = execution.grid_execution.state if execution.grid_execution.side == 'SHORT' else 'GRID_HOLD'
        return GridViewModel(
            decision_bias=decision.grid_side,
            current_grid_action=decision.grid_state,
            long_grid_state=long_state,
            short_grid_state=short_state,
            grid_reason='; '.join(decision.why) if decision.why else '-',
            zones_summary=decision.where_to_watch,
            grid_note=execution.grid_execution.grid_note,
        )
