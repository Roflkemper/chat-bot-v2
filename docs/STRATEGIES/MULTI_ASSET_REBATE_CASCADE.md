# Multi-asset rebate cascade — ETH+XRP scaling

**Цель:** $1M+/день оборота при $15k депо, peak USD < $100k per asset.

## Текущее состояние (BTC only)

| Конфиг | Vol/3мес | Vol/день | Peak USD | Profit/3мес |
|---|---:|---:|---:|---:|
| BTC SH-T1 | 13.5M | 150k | **120k ⚠** | +2 315$ |
| BTC SH-T2 | 6.0M | 66k | 80k | +4 699$ |
| BTC SH-T3 | 2.2M | 24k | 48k | +3 247$ |
| BTC LONG-T2-mild | 4.5M | 50k | 88k | +22 100$ |
| **Total** | **26.2M** | **290k** | (per asset) | **+32 361$/3мес** |

**Гэп до $1M/день:** ×3.5

## Стратегия — клонировать на ETH + XRP

Те же параметры (gs, thresh, mult, TP), но **size в native валюте**.

### Принцип расчёта size

Заходим в позицию того же **USD-объёма** на всех парах, чтобы peak USD был ~ одинаковый.

Текущие цены (примерные, для расчёта):
- BTC: $79 000
- ETH: $2 250 (BTC/ETH ratio ≈ **35**)
- XRP: $1.40 (BTC/XRP ratio ≈ **56 000**)

## ETH configs (4 тира)

### ETH SH-T1 (пачка #23 wide stops)

```
Биржа:              BITMEX
Тип:                USDT_FUTURES
Пара:               ETHUSDT
Стратегия:          INDICATOR GRID
Условие входа:      PRICE%-1m-30-0.7 > 0.7%
Направление:        Short

Шаг сетки:          0.02
Количество ордеров: 5000
Размер ордера:      0.035 ETH    ← BTC 0.001 × 35
Макс. размер:       0.07 ETH     ← BTC 0.002 × 35 (REDUCED, было бы 0.105)
Мультипликатор:     1.3

Инстоп:             0.018
Целевой уровень:    0.21
Мин. Стоп:          0.012
Макс. Стоп:         0.035
Тейк-Профит:        12

Ожидание (vs BTC):
  Profit:    ~$1 600 / 3 мес  (BTC дал $2 315)
  Vol:       ~9.5M / 3 мес    (~105k/день)
  Peak USD:  ~75-85k
```

### ETH SH-T2 (TP=175)

```
Шаг сетки:          0.03
Количество ордеров: 5000
Размер ордера:      0.07 ETH     ← BTC 0.002 × 35
Макс. размер:       0.14 ETH     ← BTC 0.004 × 35
Мультипликатор:     1.3

Инстоп:             0.018
Целевой уровень:    0.35
Мин. Стоп:          0.006
Макс. Стоп:         0.020
Тейк-Профит:        175

Ожидание: profit ~$3 200/3мес, vol ~4M, peak ~75k
```

### ETH SH-T3 (TP=270)

```
Шаг сетки:          0.05
Количество ордеров: 5000
Размер ордера:      0.088 ETH    ← BTC 0.0025 × 35
Макс. размер:       0.176 ETH    ← BTC 0.005 × 35
Мультипликатор:     1.2

Инстоп:             0.018
Целевой уровень:    0.6
Мин. Стоп:          0.012
Макс. Стоп:         0.045
Тейк-Профит:        270

Ожидание: profit ~$2 200/3мес, vol ~1.5M, peak ~45k
```

### ETH LONG-T2-mild (COIN_FUTURES если есть, иначе linear)

ETH inverse contracts BitMEX (`ETHUSD`) — есть, можно через GinArea как COIN_FUTURES.

```
Биржа:              BITMEX
Тип:                COIN_FUTURES (ETHUSD)
Пара:               ETHUSD
Стратегия:          INDICATOR GRID
Условие входа:      PRICE%-1m-30--1.5 < -1.5%
Направление:        Long

Шаг сетки:          0.04
Количество ордеров: 5000
Размер ордера:      70 USD       ← BTC 100 × (1/1.43)
Макс. размер:       210 USD      ← BTC 300 × (1/1.43)
Мультипликатор:     1.2

Инстоп:             0.018
Целевой уровень:    0.85
Мин. Стоп:          0.005
Макс. Стоп:         0.025
Тейк-Профит:        0 (off)

Ожидание: profit ~$15k/3мес, vol ~3M, peak ~60k
```

## XRP configs (4 тира)

### XRP SH-T1

```
Биржа:              BITMEX
Тип:                USDT_FUTURES
Пара:               XRPUSDT
Стратегия:          INDICATOR GRID
Условие входа:      PRICE%-1m-30-0.7 > 0.7%
Направление:        Short

Шаг сетки:          0.02
Количество ордеров: 5000
Размер ордера:      56 XRP       ← BTC 0.001 × 56000
Макс. размер:       112 XRP      ← BTC 0.002 × 56000 (REDUCED)
Мультипликатор:     1.3

Инстоп:             0.018
Целевой уровень:    0.21
Мин. Стоп:          0.012
Макс. Стоп:         0.035
Тейк-Профит:        12

Ожидание: profit ~$1 400/3мес, vol ~8M, peak ~60k
```

### XRP SH-T2 (TP=175)

```
Шаг сетки:          0.03
Количество ордеров: 5000
Размер ордера:      113 XRP
Макс. размер:       226 XRP
Мультипликатор:     1.3
TP=175, остальное как ETH SH-T2

Ожидание: profit ~$2 800/3мес, vol ~3.5M, peak ~65k
```

### XRP SH-T3 (TP=270)

```
Шаг сетки:          0.05
Количество ордеров: 5000
Размер ордера:      141 XRP
Макс. размер:       282 XRP
Мультипликатор:     1.2
TP=270, остальное как ETH SH-T3

Ожидание: profit ~$2 000/3мес, vol ~1.2M, peak ~40k
```

### XRP LONG-T2-mild

XRP inverse на BitMEX (`XRPUSD`) — есть.

```
Тип:                COIN_FUTURES (XRPUSD)
Шаг сетки:          0.04
Размер ордера:      71 USD
Макс. размер:       214 USD
Мультипликатор:     1.2
Остальное как ETH LONG-T2-mild

Ожидание: profit ~$10k/3мес, vol ~2M, peak ~40k
```

## Сводный прогноз (после внедрения всех 12 тиров)

| Asset | Vol/3мес | Vol/день | Peak per asset |
|---|---:|---:|---:|
| BTC (4 тира) | 26.2M | 290k | до 120k ⚠ (fix max=0.002 → 80k) |
| ETH (4 тира) | ~18M | 200k | ~85k |
| XRP (4 тира) | ~14.5M | 160k | ~65k |
| **Total** | **~58M** | **~650k/день** | (per-asset) |

**Гэп до $1M/день:** ещё ×1.5. Можно добавить SOL/SUI если у тебя на GinArea, или поднять размеры на 30-50% после стабилизации.

**Чистый profit (rebate ~0.02%):**
- 58M × 3мес × 0.0002 = **+$11.6k от rebate alone**
- Плюс grid edge ~$30-50k/3мес
- **Итого ~$40-60k / 3мес = $13-20k/мес чистыми**

ROI депо $15k: **~100-130% годовых** (без учёта unrealized swings).

## Главный риск — correlated crash

В day типа 2024-08-05 (yen carry unwind):
- BTC −15% за 24h
- ETH −22%
- XRP −20%

Все 4 SHORT-тира на каждой паре одновременно растут unrealized:
- BTC sum peak ≈ 248k$ (T1+T2+T3 при максимуме)
- ETH sum peak ≈ 165k$
- XRP sum peak ≈ 105k$
- **Global peak ≈ 520k$** ⚠

При $15k маржи это **35× leverage** — близко к liquidation.

## Защита — расширение cliff_monitor

Сейчас `services/ginarea_api/cliff_monitor.py` имеет:
- `check_short_t2_bots` (per-bot)
- `check_short_bag_aggregate` (sum по всем SHORT)

Нужно добавить:
- **Per-asset bag**: отдельный bag для BTC/ETH/XRP — если BTC bag <-3k → DANGER
- **Global bag**: суммарный по всем парам — если <-10k → CRITICAL (план эвакуации)

## Roadmap внедрения

### Phase 1 (немедленно, до multi-asset)
- [x] BTC SH-T1 max=0.003 → 0.002 (вариант C из ROI_ANOMALY.md) — peak 120k → 80k
- [ ] **Прогнать в GinArea backtest для проверки**

### Phase 2 (после phase 1 success)
- [ ] ETH SH-T1: запустить с reduced max=0.07 ETH
- [ ] Наблюдать 1 неделю: peak USD, profit/день, нет ли блокировки от GinArea за multi-asset auth

### Phase 3 (после Phase 2 stable)
- [ ] ETH SH-T2, ETH SH-T3
- [ ] XRP SH-T1, XRP SH-T2
- [ ] ETH LONG-T2-mild

### Phase 4 (после Phase 3)
- [ ] XRP SH-T3, XRP LONG-T2
- [ ] cliff_monitor расширение (per-asset + global bag)
- [ ] Weekly report — добавить vol/день target tracking

### Phase 5 (опциональный buster)
- [ ] SOL multi-tier (если поддерживается на GinArea/BitMEX)
- [ ] Тюнинг promosjuточных T1.5 (gs=0.025) на BTC

## Backtest prompts

См. секции выше — 8 готовых GinArea конфигов (ETH×4 + XRP×4). Запускать **по одному**, скриншот результата → я обновляю прогноз profit/vol/peak.

Рекомендую начать с **ETH SH-T1** — самый предсказуемый (BTC SH-T1 уже валидирован).

## Связанные документы

- [[SHORT_T1_ROI_ANOMALY]] — ROI анализ всех тиров (вариант C → max=0.002)
- [[CASCADE_GINAREA_V5_SWEEP]] — base BTC параметры
- [[PRE_CASCADE_SIGNAL_R&D]] — раннее предупреждение каскадов
