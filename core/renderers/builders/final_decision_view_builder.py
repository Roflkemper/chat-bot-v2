from __future__ import annotations

from domain.contracts.final_decision import FinalDecision
from renderers.view_models.final_decision_view_model import FinalDecisionViewModel


class FinalDecisionViewBuilder:
    def build(self, decision: FinalDecision) -> FinalDecisionViewModel:
        return FinalDecisionViewModel(
            price=0.0,
            decision_label=decision.directional_state,
            market_bias=decision.market_bias,
            primary_action=decision.primary_action,
            mode=decision.primary_mode,
            confidence_or_strength=f'{decision.directional_confidence:.2f}',
            why='; '.join(decision.why) if decision.why else '-',
            not_now='; '.join(decision.not_now) if decision.not_now else '-',
            warning='; '.join(decision.warnings) if decision.warnings else '-',
        )
