from __future__ import annotations

from renderers.view_models.final_decision_view_model import FinalDecisionViewModel


class FinalDecisionRenderer:
    def render(self, vm: FinalDecisionViewModel) -> str:
        return (
            f"🧠 FINAL DECISION\n\n"
            f"• решение: {vm.decision_label}\n"
            f"• перевес: {vm.market_bias}\n"
            f"• действие: {vm.primary_action}\n"
            f"• режим: {vm.mode}\n"
            f"• почему: {vm.why}\n"
            f"• не сейчас: {vm.not_now}\n"
            f"• warning: {vm.warning}"
        )
