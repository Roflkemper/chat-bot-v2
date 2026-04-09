from __future__ import annotations

from domain.contracts.execution_plan import ExecutionPlan
from domain.contracts.final_decision import FinalDecision
from renderers.view_models.action_view_model import ActionViewModel


class ActionViewBuilder:
    def build(self, decision: FinalDecision, execution: ExecutionPlan) -> ActionViewModel:
        trigger = execution.directional_execution.trigger or decision.next_trigger_long or decision.next_trigger_short
        return ActionViewModel(
            price=0.0,
            current_action=decision.primary_action,
            what_now=execution.operator_message,
            trigger=trigger,
            invalidation=decision.invalidation_zone,
            ban_list='NO CHASE',
            action_note=execution.directional_execution.execution_note,
        )
