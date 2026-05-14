from __future__ import annotations

from domain.contracts.final_decision import FinalDecision
from domain.contracts.grid_execution import GridExecution


class GridPlanner:
    def run(self, decision: FinalDecision) -> GridExecution:
        state = decision.grid_state
        side = decision.grid_side
        return GridExecution(
            enabled=state != 'GRID_DISABLED',
            side=side,
            state=state,
            grid_mode='prearm' if 'PREARM' in state or 'ARM' in state else 'watch',
            arm_status=state,
            add_allowed=False,
            reduce_allowed='HOLD' in state,
            exit_required='CANCEL' in state,
            aggression_mode='safe',
            size_mode='small',
            reactivation_rule='re-evaluate on next edge reaction',
            kill_switch_reason='' if 'CANCEL' not in state else 'scenario invalidated',
            grid_note='Grid planner follows FinalDecision.grid_state only.',
        )
