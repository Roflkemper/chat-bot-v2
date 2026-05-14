from __future__ import annotations

import sys
import traceback
import warnings


def _print_missing_dependency(exc: ModuleNotFoundError) -> int:
    missing = getattr(exc, "name", None) or "unknown"
    print("\n[BOOT ERROR] Не хватает Python-зависимости:", missing)
    print("Запусти: python -m pip install -r requirements.txt")
    print("Если запускаешь через RUN_BOT.bat — просто перезапусти после обновления requirements.txt.\n")
    return 1


def main() -> int:
    warnings.warn(
        "telegram_bot_runner.py is deprecated. "
        "Use app_runner.py (TZ-010) to run Telegram bot + Orchestrator in one process. "
        "This runner starts only the Telegram bot, without orchestrator alerts.",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        from services.telegram_runtime import TelegramBotApp
    except ModuleNotFoundError as exc:
        return _print_missing_dependency(exc)
    except Exception as exc:
        print("\n[BOOT ERROR] Не удалось инициализировать Telegram runtime.")
        print(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1

    try:
        app = TelegramBotApp()
        app.run()
        return 0
    except ModuleNotFoundError as exc:
        return _print_missing_dependency(exc)
    except Exception as exc:
        print("\n[BOOT ERROR] Бот остановлен с ошибкой.")
        print(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
