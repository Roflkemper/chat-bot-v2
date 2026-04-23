from __future__ import annotations

from renderers.view_models.analysis_view_model import AnalysisViewModel


class AnalysisRenderer:
    def render(self, vm: AnalysisViewModel) -> str:
        return (
            f"📊 {vm.title} [{vm.timeframe}]\n\n"
            f"• режим: {vm.regime}\n"
            f"• локация: {vm.location}\n"
            f"• движение: {vm.movement_state} / {vm.movement_quality}\n"
            f"• реакция: {vm.reaction_status}\n"
            f"• смотреть: {vm.where_to_watch}\n"
            f"• заметка: {vm.analysis_note}"
        )
