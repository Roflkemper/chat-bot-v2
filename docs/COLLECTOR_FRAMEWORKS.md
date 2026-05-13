# Two collector frameworks — наглядная таблица

В проекте два независимых процесса по сбору рыночных данных. Они не дубликаты —
разделены по назначению. Документирую чтобы будущая Claude/оператор не путались.

## market_collector/  (sync, alert-feeding)

**Запуск:** `python -m market_collector.collector` (через watchdog → `collectors` component)

**Что пишет (single-file CSV):**
- `market_live/market_1m.csv` — OHLCV 1m BTCUSDT (Bybit klines REST)
- `market_live/market_15m.csv` — OHLCV 15m
- `market_live/market_1h.csv` — OHLCV 1h
- `market_live/liquidations.csv` — bybit + binance + okx (объединено в один файл, single symbol)
- `market_live/signals.csv` — trigger fires (LEVEL_BREAK, RSI_EXTREME, LIQ_CASCADE)

**Кто читает:**
- `services/cascade_alert/loop.py` — `market_live/liquidations.csv`
- `services/setup_detector/` через OHLCV CSV's
- `services/precision_tracker/`
- `signal_alert_worker` через `signals.csv`

**Threads:** sync `websocket-client` per exchange.

## collectors/  (async, archive for analytics)

**Запуск:** `python -m collectors.main` (через watchdog → `collectors_supervisor` component)

**Что пишет (per-symbol parquet, partitioned by day):**
- `market_live/liquidations/<exchange>/<symbol>/<date>.parquet`
  - Биржи: binance, bybit, okx, bitmex, hyperliquid (все 5)
  - Hyperliquid через `trades` channel с `liquidation` flag filter
- `market_live/orderbook/<exchange>/<symbol>/<date>.parquet`
  - Binance @depth20@100ms, 3 symbols (BTC, ETH, XRP)
- `market_live/trades/<exchange>/<symbol>/<date>.parquet`
  - Binance aggTrade, 3 symbols

**Кто читает:**
- Будущие backtest скрипты для Volume Profile, orderbook imbalance, multi-exchange OI div.
- Сейчас нет live consumers — это archive.

**Threads:** asyncio + `websockets` (async lib).

## Почему два

Исторически:
1. `market_collector/` старее, написан под нужды live alert pipeline.
2. `collectors/` добавлен позже — изначально умер 2026-05-03 (видимо crash / not autostarted).
3. Восстановлен 2026-05-12 (Phase 3.1/3.2 cleanup); добавлен в watchdog как `collectors_supervisor`.

Технически их можно было бы слить, но:
- Они пишут **разные форматы** (CSV vs parquet)
- Имеют **разные SLA** (alert latency vs archive throughput)
- Сливание = неделя refactor + риск регрессий

**Правильный путь** — оставить раздельно, поддерживать оба, документировать назначение.

## Watchdog компоненты

```
COMPONENTS = {
    "collectors": market_collector.collector,        # alert feeding
    "collectors_supervisor": collectors.main,        # archive
    ...
}
```

Оба автоматически поднимаются при падении (с правкой 2026-05-12 PID-lock cmdline verification, иначе старый рестартил каждые 2-4 мин).
