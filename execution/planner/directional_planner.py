from __future__ import annotations

from domain.contracts.directional_execution import DirectionalExecution
from domain.contracts.final_decision import FinalDecision


class DirectionalPlanner:
    def run(self, decision: FinalDecision) -> DirectionalExecution:
        enabled = decision.directional_state not in {'NO_SETUP', 'WATCH'}
        return DirectionalExecution(
            enabled=enabled,
            side=decision.directional_side,
            state=decision.directional_state,
            entry_model='rejection_probe' if 'SHORT' in decision.directional_state or 'LONG' in decision.directional_state else 'no_entry',
            entry_zone=decision.where_to_watch,
            trigger=decision.next_trigger_short if decision.directional_side == 'SHORT' else decision.next_trigger_long,
            invalidation_zone=decision.invalidation_zone,
            stop_logic='beyond invalidation zone',
            tp1='first mean reversion target',
            tp2='range mid / secondary target',
            be_rule='move BE after first clean reaction',
            partial_exit_rule='partial on first target or impulse fade',
            chase_allowed=False,
            preferred_mode='probe' if 'PROBE' in decision.directional_state or 'ARM' in decision.directional_state else 'watch',
            size_hint='small' if enabled else 'none',
            execution_note='Execution follows FinalDecision only.',
        )
