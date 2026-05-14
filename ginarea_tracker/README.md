# GinArea Bot Tracker v2

24/7 трекер всех ботов GinArea. Каждые N секунд пишет снимки статистики и журнал событий (срабатывание ордеров).

## Установка

```bash
cd ginarea_tracker
pip install -r requirements.txt
cp .env.example .env
```

## Получение TOTP_SECRET из GinArea

1. Зайдите в настройки безопасности своего аккаунта GinArea.
2. Включите двухфакторную аутентификацию (Google Authenticator / TOTP).
3. На экране QR-кода выберите **«Показать секрет»** или **«Enter key manually»**.
4. Скопируйте BASE32-строку (вид: `JBSWY3DPEHPK3PXP`) — это и есть `GINAREA_TOTP_SECRET`.
5. Проверьте: `python -c "import pyotp; print(pyotp.TOTP('ВАШ_СЕКРЕТ').now())"` должно выдать 6 цифр.

## Конфигурация `.env`

| Переменная | Описание |
|---|---|
| `GINAREA_API_URL` | Базовый URL API (напр. `https://api.ginarea.io`) |
| `GINAREA_EMAIL` | Email аккаунта |
| `GINAREA_PASSWORD` | Пароль |
| `GINAREA_TOTP_SECRET` | BASE32-секрет TOTP |
| `SNAPSHOT_INTERVAL_SEC` | Интервал снимков в секундах (default: 60) |
| `OUTPUT_DIR` | Директория вывода (default: `ginarea_live`) |
| `TRACK_ALL_BOTS` | `true` — все боты; `false` — фильтр по `BOT_FILTER` |
| `BOT_FILTER` | Comma-separated bot ID или name (если `TRACK_ALL_BOTS=false`) |

## Запуск

```bash
python tracker.py
```

Логи пишутся в `ginarea_live/tracker.log` (rotating, 10 МБ × 5 файлов) и в stdout.

## Формат файлов

### `ginarea_live/snapshots.csv` — снимок каждого бота каждые N сек

```
ts_utc, bot_id, bot_name, alias, status, position, profit, current_profit,
in_filled_count, in_filled_qty, out_filled_count, out_filled_qty,
trigger_count, trigger_qty, average_price, trade_volume,
balance, liquidation_price, stat_updated_at, schema_version
```

### `ginarea_live/events.csv` — только строки при срабатывании ордеров

```
ts_utc, bot_id, bot_name, event_type, delta_count, delta_qty,
price_last, position_after, profit_after, schema_version
```

`event_type` ∈ `{IN_FILLED, OUT_FILLED}`

### `ginarea_live/params.csv` — снимок параметров бота (при старте и при изменении)

```
ts_utc, bot_id, bot_name, strategy_id, side, grid_step, grid_step_ratio,
max_opened_orders, border_top, border_bottom, instop, minstop, maxstop,
target, total_sl, total_tp, raw_params_json, schema_version
```

`schema_version = 2`. При изменении схемы будет создан новый файл с суффиксом `_v{N}.csv`.

## Алиасы ботов

Файл `bot_aliases.json` — отображение `botId → читаемое имя`. Перечитывается раз в 10 минут (можно править на лету).

```json
{
  "5196832375": "TEST_1",
  "5017849873": "TEST_2"
}
```

## Тесты

```bash
pytest tests/ -v
```
