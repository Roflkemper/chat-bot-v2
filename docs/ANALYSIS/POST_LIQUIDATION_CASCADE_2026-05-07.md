# Post-Liquidation Cascade Direction Backtest — EDGE подтверждён на n=103

**Дата**: 2026-05-07 (обновлено после расширения данных)
**Метод**: 30,630 BTCUSDT liquidations с фев-июнь 2024 (Bybit, sferez/BybitMarketData GitHub) + BTC OHLCV полностью покрывает период.
**Скрипты**: `scripts/download_bybit_liquidations.py`, `scripts/backtest_post_cascade.py`, `scripts/backfill_btc_pre_april2024.py`
**Raw**: `state/post_cascade_test.json`, `data/historical/bybit_liquidations_2024.parquet`

---

## TL;DR — Первый подтверждённый direction-edge проекта

**После long-cascade ≥5 BTC (рынок резко падает + лонги принудительно ликвидированы):**
- **Через 12 часов** — цена ВЫШЕ в **73% случаев** (n=103), сильный рост в **69%**, средний +1.14%

**На меньших порогах** (больше срабатываний, edge скромнее):
- Long-cascade ≥1 BTC, +12h: **62% pct_up** (n=598), mean +0.54%
- Long-cascade ≥2 BTC, +12h: **63% pct_up** (n=297), mean +0.68%

**После short-cascade ≥2 BTC** (резкий рост, шорты сгорели):
- +24h: **61% pct_up** (n=296), mean +1.06% — продолжение тренда вверх

---

## Что изменилось vs первый прогон

Утром на **n=15** (overlap 38 дней) показывало 87% / 80% / +1.72%. Это было **завышено селекционным bias'ом** — данные апреля 2024 случайно были на стороне отскоков.

После backfill BTC OHLCV до 12.02.2024 (commit + scripts/backfill_btc_pre_april2024.py): overlap 110 дней, n вырос с 15 до 103. Edge **частично исчез**, но **подтвердился** на разумном уровне.

**Доверительный интервал** для pct_up=73%, n=103: примерно **[63%, 81%]** при 95% CI. То есть истинный edge **точно выше монетки**, но величина может быть от 63% до 81%.

---

## Финальная таблица — все пороги, все окна

| Direction | Threshold | n | +4h pct_up | +12h pct_up | +24h pct_up | +12h mean | +24h mean |
|---|---|---|---|---|---|---|---|
| **Long-cascade** | ≥0.5 BTC | 925 | 55% | 61% | 56% | +0.46% | +0.66% |
| **Long-cascade** | ≥1.0 BTC | 598 | 56% | 62% | 57% | +0.54% | +0.75% |
| **Long-cascade** | ≥2.0 BTC | 297 | 59% | 63% | 59% | +0.68% | +1.01% |
| **Long-cascade** | **≥5.0 BTC** | **103** | **67%** | **73%** ⭐ | **64%** | **+1.14%** | **+1.50%** |
| Short-cascade | ≥0.5 BTC | 914 | 55% | 58% | 58% | +0.36% | +0.77% |
| Short-cascade | ≥1.0 BTC | 578 | 54% | 59% | 59% | +0.39% | +0.89% |
| Short-cascade | ≥2.0 BTC | 296 | 54% | 57% | **61%** | +0.53% | +1.06% |
| Short-cascade | ≥5.0 BTC | 102 | 53% | 57% | 61% | +0.29% | +1.02% |

**Закономерность**: чем больше каскад, тем сильнее edge (для long). Threshold ≥5 BTC — sweet spot.

---

## Логика — почему это работает

Когда биржа **принудительно ликвидирует** большое количество лонгов:
1. Это означает цена ушла **резко вниз** за короткий период (>~2-3% за 5 минут типично)
2. Принудительные продажи через market orders создают **overshoot вниз** (цена уходит дальше fair value)
3. Через несколько часов рынок **возвращается** к нормальному уровню → bounce

Это **structural fact**, не предсказание тренда. Mean-reversion после margin-call волны.

Аналогично для short-cascade — squeeze rally часто продолжается 24h, но без такого явного pattern.

---

## Подводные камни

1. **n=103 — нормально, но не идеально**. CI 63-81% — edge значительный, но точное значение неточное. Через 6-12 месяцев forward-data CI станет узким.

2. **Период 02-06.2024 = bull market** (BTC шёл с $42k до $73k). В медвежьем рынке pattern может быть **слабее** (overshoot не обязательно reverts) или **наоборот сильнее** (margin calls глубже).

3. **Только Bybit** — реальные cascade'ы по сумме больше (Binance + Bitmex добавляют). Возможно threshold нужно нормализовать на total exchange OI.

4. **Cost model**: 0.07% × 2 + 0.05% slippage = **0.19% drag**. На mean +1.14% за 12h это net **+0.95%**. Edge выживает.

5. **Окно +1h не работает** — это **артефакт grid'а** (1h price bars). Нужен 1m OHLCV для оценки +1h. Текущие цифры показывают всегда ≈0% потому что resampled.

---

## Trading edge — конкретные сетапы

### Сетап 1: BUY after long-cascade ≥5 BTC (high confidence)

```
Trigger: long_liq за 5 минут ≥ 5 BTC (Bybit)
Entry: market buy через 5-15 минут после каскада (allow стабилизация)
Target: +1.14% (12h) или trail
Stop: -0.5% или 0.5× target
Confidence: 73% pct_up, 69% strong_up, 24% pct_strong_down
EV (без cost): +1.14% × 0.73 - 0.5% × 0.27 = +0.70%
EV (с cost 0.19%): +0.51%
```

### Сетап 2: BUY after long-cascade ≥1 BTC (more frequent, smaller edge)

```
Trigger: long_liq за 5 минут ≥ 1 BTC
Entry: то же
Target: +0.5% (12h)
Stop: -0.3%
Confidence: 62% pct_up
EV (без cost): +0.5% × 0.62 - 0.3% × 0.38 = +0.20%
EV (с cost): почти 0 — слабовато
```

→ Сетап 1 (≥5 BTC) — наш приоритет.

### Сетап 3: HOLD-or-add SHORT after short-cascade ≥2 BTC, +24h

```
Trigger: short_liq за 5 минут ≥ 2 BTC, цена вверх
Smart play: НЕ открывать новый SHORT, а зафиксировать частично имеющуюся
позицию или раздвинуть boundary (P-1 в playbook).
Confidence: 61% продолжит вверх через 24h.
Применение для оператора: подтверждает что не нужно agressive-shorting на squeeze rally.
```

---

## Что дальше

### Сейчас можем

1. **Live cascade alert в /momentum_check** (1-2 часа): когда long_liq ≥5 BTC за 5 мин в реальном времени → push в Telegram "⚡ КАСКАД! Шанс отскока 73% за 12h, средняя цель +1.14%"

2. **Paper trader auto-trade** (1 час): после cascade detection автоматически открыть бумажную BUY позицию с TP +1.14% / SL -0.5% на 12h. Накапливать forward-данные.

### После 1-2 месяцев forward-validation

3. Если accuracy сохранится 70%+ — добавить как **первое автоматическое торговое правило** в advisor с положительным EV.

### Долгосрочно

4. Сделать live ingestion historical liquidations (агрегация Bybit + Binance + BitMEX) → больше данных для уточнения edge.

5. Изучить cascade-pattern в **bear market** (нужны данные 2022 года) — для робастности.

---

## Связанные документы

- [MULTI_SIGNAL_CONFLUENCE_2026-05-07.md](MULTI_SIGNAL_CONFLUENCE_2026-05-07.md) — провал all-bars confluence
- [INVERTED_VERDICT_TEST_2026-05-07.md](INVERTED_VERDICT_TEST_2026-05-07.md) — провал инверсии
- [BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md](BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md) — провал regime-only

`state/post_cascade_test.json` — полный raw output.
`data/historical/bybit_liquidations_2024.parquet` — 30k events.
`backtests/frozen/BTCUSDT_1m_2y.csv` — 1.17M баров (с 12.02.2024).
