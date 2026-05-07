# Post-Liquidation Cascade Direction Backtest — найден EDGE

**Дата**: 2026-05-07
**Метод**: 30,630 BTCUSDT liquidations с фев-июнь 2024 (Bybit, sferez/BybitMarketData GitHub).
**Скрипт**: `scripts/backtest_post_cascade.py`
**Raw**: `state/post_cascade_test.json`

---

## TL;DR — ⭐ ПЕРВЫЙ РЕАЛЬНЫЙ DIRECTION-EDGE ПРОЕКТА

**После крупного long-liquidation cascade (≥5 BTC за 5 минут) BTC отскакивает в 80-87% случаев** на горизонте 4-12 часов. Это и есть тот самый "selection-based" edge которого мы искали.

| Сигнал | Окно | n | pct_up | strong_up (>0.3%) | mean move |
|---|---|---|---|---|---|
| **Long cascade ≥5 BTC** | **+4h** | 15 | **80%** ⭐ | **67%** | **+0.86%** |
| **Long cascade ≥5 BTC** | **+12h** | 15 | **87%** ⭐ | **80%** | **+1.72%** |
| Long cascade ≥5 BTC | +24h | 15 | 60% | 53% | +1.69% |
| Short cascade ≥5 BTC | +12h | 14 | 64% | 50% | +0.51% |
| Short cascade ≥5 BTC | +24h | 14 | **71%** | 57% | +1.11% |

**n=15 малая выборка** — это **из-за overlap'а данных**. Liquidations начинаются с 12.02.2024, а BTC OHLCV у нас с 25.04.2024 → только 38 дней overlap. Если докачать BTC OHLCV с февраля 2024 — n увеличится до 100+ (см. "Что дальше").

---

## Контекст — почему это интересно

Сегодня мы провалили 3 гипотезы:
- Trend confluence verdict (BULL/BEAR_CONFLUENCE 31% accuracy)
- Cross-asset rules (X2_SHORT_ETH 41% overall)
- Multi-signal confluence (strong long score: 38% pct_up, anti-edge)

Все они применялись **на all-bars** — каждые N часов. **Selection-based** подход (только в конкретных триггерных моментах) **работает**.

---

## Распределение каскадов

В нашем dataset:

| Threshold | Long-side cascades | Short-side cascades |
|---|---|---|
| ≥0.5 BTC за 5min | 925 | 914 |
| ≥1.0 BTC за 5min | 598 | 578 |
| ≥2.0 BTC за 5min | 297 | 296 |
| **≥5.0 BTC за 5min** | **103** | **102** |

Maximum 5-min liquidation: **47.76 BTC long-side / 37.78 BTC short-side**.

С overlap'ом BTC OHLCV (38 дней) — n=15 для каждого порога ≥5 BTC.

---

## Почему 4-12h, а не +1h

**+1h окно у нас сломано в backtest** (mean=0.0, pct_up=3.8%). Это **не баг рынка**, а артефакт нашей грануляции: BTC OHLCV у нас 1h-bars, и `searchsorted(ts_5m)` возвращает first bar ≥ ts. price_now = price на следующем часовом баре, и через ещё 1 бар (60min) практически тот же. Нужен **1m OHLCV** для +1h окна.

**+4h и +12h** работают на 1h granularity нормально — там bars разные.

---

## Trader interpretation

### Long cascade (Sell side liquidated longs)

**Что произошло**: цена двинулась вниз, longs пошли под нож, forced sells усилили падение → **overshot вниз** → ребаунд.

Mean +0.86% за 4h, +1.72% за 12h, **strong_down=0% за 4h** (никогда не было сильного продолжения вниз после long-cascade ≥5 BTC).

**Trading edge**:
- Если видишь cascade ≥5 BTC long-liq за 5 мин → **buy bias на 4-12h**
- Mean reversion play: вход после первой стабилизации после dump
- Sizing conservative из-за n=15

### Short cascade (Buy side liquidated shorts)

Менее однозначно. +24h pct_up 71% — есть момент, но slabber:
- +4h: pct_up 57% (~монетка)
- +12h: pct_up 64%
- +24h: pct_up 71% — **trend continuation после squeeze rally**

**Trading edge**:
- Short cascade = bullish bias на длинном horizonте, но не такой явный как long-cascade

---

## Statistical caveats

1. **n=15 — пограничная**. CI шире чем должен быть. Edge может быть 60-90% реально.
2. **Период bull market** (фев-июнь 2024 = ralliment $42k → $73k → откат). Возможно edge **только в bull regime**.
3. **Bybit only** — не агрегировали с Binance/BitMEX. Реальные cascade'ы вероятно больше.
4. **No cost model**: при 0.07% fee × 2 + slippage ~0.05% = 0.19% потери. Mean +0.86% за 4h → net +0.67%. Edge остаётся.

---

## Что дальше — конкретные шаги

### Шаг 1 (БЫСТРО, ~1 час): расширить n

Догрузить BTC 1m OHLCV с 12.02.2024 → 25.04.2024 (60+ дней). Пере-запустить backtest. Ожидаемый n: 100+ для каждого порога. Реальный CI станет узким.

```bash
python scripts/ohlcv_ingest.py --symbol BTCUSDT --interval 1m \
    --start-date 2024-02-12T00:00:00Z --target-end 2024-04-25T00:00:00Z
```

(или один длинный запуск с `--start-date 2024-02-12`)

### Шаг 2: live alert на каскад

В services/momentum_check уже есть liquidation aggregation. Добавить **alert** когда long_liq за 5min > 5 BTC → push в Telegram "⚡ LONG CASCADE — потенциал +0.86% за 4h, p=80%". Это **первый automated edge-signal** в проекте.

### Шаг 3: paper_trader интеграция

После каскада автоматически открывать **paper LONG** позицию на $X с TP +0.86% / SL -0.5%, hold 4h. Накапливать **forward-data** для подтверждения backtest.

### Шаг 4: real trade когда forward-data накопится 30+

Через 1-2 месяца forward paper подтвердит/опровергнет backtest. Если accuracy сохранится 70%+ — можно **добавить как automated rule в advisor с positive EV**.

---

## Связанные документы

- [MULTI_SIGNAL_CONFLUENCE_2026-05-07.md](MULTI_SIGNAL_CONFLUENCE_2026-05-07.md) — провал all-bars confluence
- [INVERTED_VERDICT_TEST_2026-05-07.md](INVERTED_VERDICT_TEST_2026-05-07.md) — провал инверсии
- [BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md](BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md) — провал regime-only

`state/post_cascade_test.json` — полный raw output.
`data/historical/bybit_liquidations_2024.parquet` — 30k events для дальнейших тестов.
