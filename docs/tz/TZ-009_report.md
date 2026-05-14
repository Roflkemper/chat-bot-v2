# TZ-009 Report

Date: 2026-04-18

## Что сделано
- Создан `services/telegram_alert_client.py`.
- Реализован `TelegramAlertClient` как singleton с lazy init.
- Подключена отправка через `pyTelegramBotAPI` (`telebot`) с использованием `config.BOT_TOKEN`, `config.CHAT_ID`, `config.ENABLE_TELEGRAM`.
- Добавлен fallback на логирование без crash, если Telegram выключен, токен отсутствует или отправка падает.
- Обновлён `services/telegram_alert_service.py`:
  - логирование alert/report всегда сохраняется
  - отправка выполняется через `asyncio.to_thread(...)`
  - длинные сообщения режутся на чанки до `3800` символов
- Добавлены и обновлены unit-тесты:
  - `tests/test_telegram_alert_client.py`
  - `tests/test_telegram_alert_service.py`

## Результаты автотестов
- Focused tests:
  - `python -m pytest tests/test_telegram_alert_client.py tests/test_telegram_alert_service.py -q`
  - Result: `14 passed`
- Full regression:
  - `RUN_TESTS.bat`
  - Result: `237 passed in 65.13s`

## Baseline проверка
- Команда:
  - `python run_backtest.py --lookback-days 180 --mode frozen --data-file backtests/frozen/BTCUSDT_1h_180d_frozen.json --output-dir backtests`
- Результат:
  - Trades: `22`
  - Winrate: `72.73%`
  - PnL: `10.9273%`
  - Max DD: `-2.1542%`
- Вывод: baseline не сдвинут.

## Smoke test
- Проверка конфига:
  - `python -c "import config; print('TOKEN set:', bool(config.BOT_TOKEN), '| CHAT_ID:', config.CHAT_ID)"`
  - Result: `TOKEN set: False | CHAT_ID:`
- Одиночная отправка:
  - `python -c "import asyncio; from services.telegram_alert_service import send_telegram_alert; asyncio.run(send_telegram_alert('TZ-009 smoke test - orchestrator alerts live'))"`
  - Result in logs: `[ALERT CLIENT] BOT_TOKEN not set, alerts will be logged only`
  - Received in Telegram: `NO`
  - Комментарий: реальная доставка в Telegram не подтверждена, потому что в этой workspace-копии нет реальных `BOT_TOKEN` и `CHAT_ID`. Fallback-поведение отработало корректно, без crash.
- Проверка импортов:
  - `python -c "import services.telegram_alert_service; print('Alert service import OK')"`
  - Result: `Alert service import OK`
  - `PYTHONPATH=.pytest_pkgs python -c "import services.telegram_runtime; print('Analytical bot import OK')"`
  - Result: `Analytical bot import OK`

## Изменённые файлы
- `services/telegram_alert_client.py`
- `services/telegram_alert_service.py`
- `tests/test_telegram_alert_client.py`
- `tests/test_telegram_alert_service.py`
- `TZ-009_report.md`

## Итог
- Реальная Telegram-интеграция для orchestrator alerts реализована.
- Аналитический бот не ломался и импортируется в тестовом окружении.
- При отсутствии токена система безопасно деградирует в логирование.
