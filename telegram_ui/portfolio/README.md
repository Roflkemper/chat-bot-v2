# /portfolio — GinArea bot portfolio command

Shows a live snapshot of all GinArea bots: balance, PnL, volume, positions, and alert conditions.

## Data source

**Primary:** `ginarea_tracker/ginarea_live/snapshots.csv` — written every 60 seconds by the tracker. The command reads the latest row per bot and the row closest to 24h ago to compute deltas.

**Fallback:** GinArea API via `ginarea_tracker/ginarea_client.py` — used only if the CSV is missing or the last row is older than 5 minutes. No 24h deltas available in fallback mode.

## Example output

```
📊 ПОРТФЕЛЬ GINAREA | 24.04 12:34 UTC

СУММАРНО
  Balance:    $116,522 (+$84 / +0.6% 24ч)
  Balance BTC: 0.02857
  Unrealized: -$425.49
  Volume 24ч: $145,678
  Активных:   5 / 15

ПО БОТАМ (сортировка: volume 24ч, desc)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ TEST_1  · SHORT · active
   PnL: +$24.15 (24ч) | Vol: $82,340
   Pos: -0.1800 · entry: $75,822
   Liq: 23.8% до ликвидации 🚨

⏸ КЛОД_ИМПУЛЬС  · LONG · paused
   PnL: +$0.00 (24ч) | Vol: $5,400
   Pos: 0 · нет позиции

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ ВНИМАНИЕ
  • Без сработок >6ч: BTC-LONG-B, BTC-LONG-C
  • DD >3.5%: TEST_2 (4.1%)
  • Близко к ликвидации (<25%): TEST_1 (23.8%)
```

## Alerts

Defined in `alerts.py`. Active rules:

| Rule | Condition |
|------|-----------|
| Без сработок >6ч | `inFilledCount` unchanged between 6h-ago and latest snapshot |
| DD >3.5% | `abs(current_profit) / balance > 3.5%` |
| Близко к ликвидации | `|liq_price - avg_price| / avg_price < 25%` |
| Статус Failed | `status in ("failed", "error")` |

Thresholds are in `config.py` (`DD_ALERT_PCT`, `LIQ_ALERT_PCT`).

## Structure

```
telegram_ui/portfolio/
├── command.py       # handle_portfolio_command() — main entry
├── data_source.py   # BotData, CSV + API loading
├── formatter.py     # message text formatting
├── alerts.py        # rule-based alert detection
├── config.py        # paths and thresholds
└── tests/
    ├── test_alerts.py
    ├── test_portfolio_formatter.py
    └── test_portfolio_command_integration.py
```

## Running tests

```bash
pytest telegram_ui/portfolio/tests/ -v
```
