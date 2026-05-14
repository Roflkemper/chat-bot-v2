from __future__ import annotations

from renderers.view_models.grid_view_model import GridViewModel


class GridRenderer:
    def render(self, vm: GridViewModel) -> str:
        return (
            f"🧩 GRID\n\n"
            f"• bias: {vm.decision_bias}\n"
            f"• action: {vm.current_grid_action}\n"
            f"• long grid: {vm.long_grid_state}\n"
            f"• short grid: {vm.short_grid_state}\n"
            f"• why: {vm.grid_reason}\n"
            f"• zones: {vm.zones_summary}\n"
            f"• note: {vm.grid_note}"
        )
