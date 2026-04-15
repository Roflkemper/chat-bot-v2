from __future__ import annotations

from renderers.view_models.action_view_model import ActionViewModel


class ActionRenderer:
    def render(self, vm: ActionViewModel) -> str:
        return (
            f"⚡ ЧТО ДЕЛАТЬ\n\n"
            f"• сейчас: {vm.current_action}\n"
            f"• действие: {vm.what_now}\n"
            f"• trigger: {vm.trigger or '-'}\n"
            f"• invalidation: {vm.invalidation or '-'}\n"
            f"• запрет: {vm.ban_list}\n"
            f"• note: {vm.action_note}"
        )
