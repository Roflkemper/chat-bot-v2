# GA-найденные detector-кандидаты — 2026-05-14

**Источник:** `state/ga_full_2026-05-14.jsonl` (50 popul × 100 gen = 5000 evaluations,
после dedup → 828 уникальных genome).

**Конфигурация GA:** `tools/_genetic_detector_search.py --population 50 --generations 100 --seed 42`  
**Данные:** `backtests/frozen/BTCUSDT_1h_2y.csv` (17,520 свечей, скачаны с Binance API 2026-05-14)  
**Walk-forward:** 4 fold по 6 мес каждый  
**Compute:** ~15 минут на M1, nice -n 10 в фоне (live-сервисы не пострадали)

## Distribution

| Verdict | Count | Доля | Смысл |
|---------|-------|------|-------|
| OVERFIT | 570 | 69% | 0-1 positive folds — отбраковано |
| MARGINAL | 186 | 22% | 2/4 positive — на грани |
| **STABLE** | **72** | **9%** | **3/4 positive — кандидат на wire** |

72 STABLE — это варианты **одного** champion-геном (GA сошёлся к локальному оптимуму).
Незначительные различия в `confluence_min`, `ema_fast`, `div_window_bars`.

## 🏆 Champion candidate

**Технический ID:** `long_macd_momentum_breakout`  
**Русское имя (для TG):** **«Пробой вверх на пике MACD-импульса (LONG)»**

### Условия срабатывания простыми словами

> Бот ловит **сильное продолжение восходящего тренда**:
> 1. Долгий бычий тренд уже идёт — быстрая EMA выше медленной (EMA-93 над EMA-251)
> 2. MACD-гистограмма достигла **пиковых положительных значений** (>75) — буллы доминируют
> 3. На последней свече **аномально высокий объём** (z-score >2.76, такое бывает реже чем раз в 100 баров)
> 4. Минимум **4 индикатора согласны**, что движение вверх не случайно
>
> Если все четыре условия совпали → **открываем LONG** со стопом на 0.83% ниже входа,
> цель прибыли = 2.24× размера стопа (≈ +1.85% от входа), время удержания — до 24 часов.
>
> **Контр-тренд НЕ ловит** (это не buy-the-dip). **Ловит trend-following** — поздний вход
> в тренд, который уже подтверждён всеми индикаторами, с большой целью.

### Параметры

| Параметр | Значение |
|----------|----------|
| direction | LONG |
| primary_ind | MACD (histogram) |
| primary_threshold | 75.4 |
| primary_direction | above |
| use_ema_gate | True |
| ema_fast / ema_slow | 93 / 251 |
| use_volume_filter | True |
| vol_z_min | 2.76 |
| pivot_lookback | 12 |
| div_window_bars | 30 |
| confluence_min | 4 |
| sl_pct | 0.83 |
| tp1_rr | 2.24 |
| hold_horizon_h | 24 |

### Метрики (walk-forward 2y BTC 1h)

- **all_period_pf:** 2.53
- **all_period_n:** 105 сделок
- **all_period_wr:** ~50%
- **positive_folds:** 3/4
- **avg_mean_pct/trade:** ≈ +0.4-0.6% (по best fold)

### Семантика

Ловит **explosive long-breakouts**:
1. MACD histogram уже > 75 — strong bullish momentum
2. Объём аномальный (z>2.76, ~раз в 100 баров)
3. Долгосрочный uptrend подтверждён (EMA 93 > EMA 251)
4. Confluence ≥ 4 индикаторов

**Не контр-тренд** (не buy-the-dip), а **trend-continuation с поздним entry + большим target (RR 2.24)**.

Сетап редкий: 105 за 2 года = ~1 в неделю.

### Чем отличается от существующих 17 detector'ов

Ни один из текущих не использует комбинацию `MACD-hist threshold + volume z-score` как primary trigger. Существующие используют RSI/MFI/CMF дивергенции (контр-тренд) или PDL/PDH bounce. Champion — **новый класс** trend-following.

## Дальнейшие шаги (отдельный TZ)

1. **TZ-070-GA-CANDIDATE-WIRE:** добавить `long_macd_momentum_breakout` в
   `services/setup_detector/setup_types.py` как новый тип. Реализация
   через стандартный setup_type интерфейс.

2. **TZ-071-GA-CANDIDATE-SHADOW:** прогнать 2 недели в shadow-mode (не
   эмитить в TG, писать в `state/shadow_emissions.jsonl`). Сравнить
   реальный forward-PnL с walk-forward predicted PF=2.53.

3. **Multi-asset валидация:** прогнать champion-genome backtest на ETH 1h
   и XRP 1h — работает ли семантика на других парах? Если PF≥1.5 на
   обоих — wire как universal, иначе BTC-only.

4. **GA на других direction'ах:** champion — LONG. Запустить отдельный
   GA с `--seed 43` и фильтром по `direction=short` (через изменение
   randomization weights в скрипте) — найти SHORT кандидата.

5. **GA на ETH/XRP данных:** скачать ETH 1h 2y и XRP 1h 2y, прогнать
   GA отдельно. Возможно найдёт пар-специфичные edges.

## Воспроизводимость

```bash
# Скачать данные
python scripts/fetch_btc_1h_2y.py

# Запустить GA (--seed 42 для детерминизма)
nice -n 10 python tools/_genetic_detector_search.py \
    --population 50 --generations 100 --seed 42 \
    --output state/ga_full_2026-05-14.jsonl
```
