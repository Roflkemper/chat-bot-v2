from __future__ import annotations

from app.runtime_flags import RuntimeFlags
from interfaces.telegram.bot_app import TelegramBotApp


def main() -> None:
    flags = RuntimeFlags()
    app = TelegramBotApp(runtime_flags=flags)
    app.run()


if __name__ == "__main__":
    main()
