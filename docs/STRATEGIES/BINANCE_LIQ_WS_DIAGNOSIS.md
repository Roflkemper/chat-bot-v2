# Binance liquidation WS — диагноз и план

## Что обнаружено

В `state/market_live/liquidations.csv` за recent 2195 строк — **только bybit**.
Binance не пишет ни одной записи.

В коде `market_collector/liquidations.py` есть обе функции (`_run_bybit_ws`,
`_run_binance_ws`), и `start_liquidation_streams()` запускает оба thread.

В логах `app.log*` (4 файла за ~24 часа) **ноль упоминаний** `binance_ws.connected`,
`binance_ws.connect_failed`, `binance_ws.parse_error`. Это значит:
- Либо thread не стартует вообще
- Либо thread стартует но логирование подавлено (вряд ли — bybit логируется ок)
- Либо collector-процесс работает в отдельном log-файле которого я не нашёл

## Что проверить

1. **Где живой stdout/stderr процесса `market_collector.collector`?**
   - watchdog запускает его как `pythonw -m market_collector.collector`
   - stdout/stderr возможно идёт в null или в отдельный файл
   - Найти этот файл и посмотреть `binance_ws.*` события

2. **Если thread не стартует:**
   - Проверить `start_liquidation_streams()` в `market_collector/liquidations.py`
   - Возможно условный pass для binance (флаг отключён?)

3. **Если thread стартует но WS не получает данных:**
   - URL: `wss://fstream.binance.com/ws/btcusdt@forceOrder`
   - Тест из CLI: `wsdump wss://fstream.binance.com/ws/btcusdt@forceOrder`
   - Binance в декабре 2024 изменил политику публичных streams для отдельных пар
   - Возможно нужно использовать `@!forceOrder@arr` (вся биржа) вместо одной пары

4. **IP/гео блокировка:**
   - Binance геоблокирует ряд IP диапазонов
   - Проверить через curl: `curl -I https://fstream.binance.com`

## Что предлагаю сделать сейчас

**НЕ чинить вслепую.** Это потенциально многочасовая задача (websocket debugging без live trial-and-error на dev машине).

Лучший action plan:
1. Изолировать collector log путь — найти где он пишет stdout/stderr
2. Запустить test-script `tools/_test_binance_liq_ws.py` (один thread, 5 мин записи в test file)
3. Если test-script тоже молчит — проблема в WS endpoint
4. Если test-script пишет — проблема в start_liquidation_streams() или logging

Альтернатива: **не чинить Binance**, а **добавить Bybit USDT-Perp** ETH/XRP к
текущему BTCUSDT. Сейчас trackится только BTCUSDT на bybit. ETH/XRP добавление
даст больше liquidation data и работает гарантированно.

## Связь с Phase 1.1

A2-агент написал "5 бирж работают (Bybit, Binance, BitMEX, OKX, Hyperliquid)".
**Это неверно — реально работает только Bybit BTCUSDT.**

Phase 1.1 разбита на:
- 1.1a: диагноз Binance (этот документ)
- 1.1b: написать OKX collector с нуля
- 1.1c: написать Hyperliquid collector с нуля

Каждая подзадача — 0.5-2 дня. Phase 1.1 в total ~3-5 дней работы.

## Action

Жду решения оператора:
- A) Тратить время на Binance WS debugging (1-2 дня)
- B) Скипнуть Binance, идти на Phase 1.2 (funding extremes) — данные точно есть
- C) Расширить Bybit на ETH/XRP вместо чинить Binance (1 день, гарантированный результат)
