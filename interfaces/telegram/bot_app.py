from __future__ import annotations

from app.runtime_flags import RuntimeFlags


class TelegramBotApp:
    def __init__(self, runtime_flags: RuntimeFlags) -> None:
        self.runtime_flags = runtime_flags

    def run(self) -> None:
        print("CORE V1 bootstrap ready. Telegram wiring should be connected here.")
