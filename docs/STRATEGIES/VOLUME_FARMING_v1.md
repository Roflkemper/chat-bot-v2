# Volume Farming Strategies — V1 (Tight) + V2 (Combo-trailing)

**Status:** READY (operator approved 2026-05-09).
**Цель:** $500k оборота/сутки на BitMEX, прибыль ≈ 0 или маленький плюс.
**Контекст:** до $10M/мес (VIP уровень) тейкер-режим оправдан. Maker-only усложняет логику и не даёт значимой экономии на этом объёме.

**Источники механики:** [`docs/GINAREA_MECHANICS.md`](../GINAREA_MECHANICS.md) §1-7.

---

## Расчётная база (общая для V1/V2)

| Метрика | Значение |
|---|---|
| Цель оборота/сутки | $500,000 |
| Цель оборота/месяц | ~$15M |
| Комиссия taker BitMEX | 0.035% × 2 = 0.07% round-trip |
| Profit/IN формула | `target_profit_pct − min_stop_pct` |
| Net edge/IN | `(target − min_stop) − 0.07%` |
| BTC volatility ~ | 1-2%/сутки = 33-66× grid_step (0.03%) |

---

## V1 — Tight Volume Farming (базовая, безопасная)

### Концепция
Узкие параметры, частый набор IN, минимальный profit per cycle. Net edge per IN ≈ 0 → объём максимальный, риск минимальный.

### Параметры

**SHORT linear BTCUSDT:**
```yaml
side: SHORT
contract: linear BTCUSDT
order_size: 0.05 BTC          # ~$4,000 notional на IN
order_count: 100
grid_step_pct: 0.03
target_profit_pct: 0.08
min_stop_pct: 0.01
max_stop_pct: 0.02
instop_pct: 0                 # нормальный набор без задержки
boundaries:
  lower: текущая_цена * 0.95
  upper: текущая_цена * 1.05
dsblin: false
indicator:
  type: Price%
  tf: 1min
  period: 30
  condition: "> 0.2%"
разовая_проверка: ON
```

**LONG inverse XBTUSD:**
```yaml
side: LONG
contract: inverse XBTUSD
order_size: 5000              # $5,000 = 5000 контрактов
order_count: 100
grid_step_pct: 0.03
target_profit_pct: 0.08
min_stop_pct: 0.01
max_stop_pct: 0.02
instop_pct: 0
boundaries:
  lower: текущая_цена * 0.95
  upper: текущая_цена * 1.05
dsblin: false
indicator:
  type: Price%
  tf: 1min
  period: 30
  condition: "< -0.2%"
разовая_проверка: ON
```

### Математика V1

| Параметр | Значение |
|---|---|
| Profit/IN gross | 0.08% − 0.01% = 0.07% |
| Net per IN после комиссии | 0.07% − 0.07% = **0.0%** |
| Объём 1 round-trip SHORT | $4,000 × 2 = $8,000 |
| Объём 1 round-trip LONG | $5,000 × 2 = $10,000 |
| Round-trips/сутки на BTC vol 1.5% | ~30-40 на ноге |
| Объём/сутки (обе ноги) | (30 × $8k) + (30 × $10k) = **$540k** ✓ |
| Прибыль/сутки net | ~$0 ± $50 |

### Когда не работает
- **Низкая волатильность** (<0.5%/сутки) → boundaries не достигаются, IN не набираются → объём падает до $100-150k
- **Сильный one-way тренд** > 5% → boundaries пробиваются, dsblin=false продолжает но close далеко от entry → возможны убыточные Out Stop
- **Funding rate spike** (>0.05% за 8h) → накопленные позиции платят/получают funding, может перебить профит

### Риск-профиль
- Max drawdown за день при 5% spike против: ~$300-500 (зависит от того сколько IN накопил бот к моменту разворота)
- Equity at risk: ~$15-20k (margin requirement при 100 IN × $4k notional / leverage 5x)

---

## V2 — Combo-trailing Exploit (агрессивная, выходные)

### Концепция
Эксплуатирует **Out Stop trailing** механизм GinArea (§3 GINAREA_MECHANICS):
- IN-ордера, достигшие target, объединяются в комбо-стоп
- Комбо-стоп trailing'ует за ценой с отклонением `max_stop_pct`
- На trending market дальние IN дают возрастающий профит

Шире параметры → больше profit per IN, но реже срабатывания. На выходных хорошо: BTC чаще даёт чистые движения 1-2% без шума.

### Параметры

**SHORT linear BTCUSDT:**
```yaml
side: SHORT
contract: linear BTCUSDT
order_size: 0.05 BTC          # тот же notional
order_count: 100
grid_step_pct: 0.03
target_profit_pct: 0.12       # шире для trailing
min_stop_pct: 0.015
max_stop_pct: 0.04            # БОЛЬШОЙ trailing — ловит тренды
instop_pct: 0.02              # сглаживание входов (Семантика A)
boundaries:
  lower: текущая_цена * 0.93
  upper: текущая_цена * 1.07
dsblin: false
indicator:
  type: Price%
  tf: 1min
  period: 30
  condition: "> 0.3%"          # повышенный порог — реже стартует
разовая_проверка: ON
```

**LONG inverse XBTUSD:**
```yaml
side: LONG
contract: inverse XBTUSD
order_size: 5000
order_count: 100
grid_step_pct: 0.03
target_profit_pct: 0.12
min_stop_pct: 0.015
max_stop_pct: 0.04
instop_pct: 0.02
boundaries:
  lower: текущая_цена * 0.93
  upper: текущая_цена * 1.07
dsblin: false
indicator:
  type: Price%
  tf: 1min
  period: 30
  condition: "< -0.3%"
разовая_проверка: ON
```

### Математика V2

| Параметр | Значение |
|---|---|
| Profit/IN gross (без trailing) | 0.12% − 0.015% = 0.105% |
| Net per IN после комиссии | 0.105% − 0.07% = **+0.035%** |
| Net per IN с trailing на trending (10 IN объединились) | до **+0.15%** на крайних IN |
| Объём 1 round-trip SHORT | $4,000 × 2 = $8,000 |
| Round-trips/сутки на BTC vol 2% | ~15-25 на ноге |
| Объём/сутки (обе ноги) | (20 × $8k) + (20 × $10k) = **$360k** |
| Прибыль/сутки net (typical) | +$50-150 |
| Прибыль/сутки на trending day | +$200-400 |

**Объём ниже V1**, но **прибыль выше**. На выходных при 1-2% движениях V2 даёт реальный edge от Out Stop trailing.

### Когда работает лучше V1
- Trending market (направленное движение 1-3% за день)
- Низкий шум (выходные, азиатская сессия)
- Funding rate близкий к нулю

### Когда хуже V1
- Choppy market (много мелких движений 0.05-0.1%) → не достигает target=0.12% → IN не закрываются
- Высокая волатильность спайками → инстоп=0.02% задерживает входы → пропускаешь движения

### Риск-профиль
- Max drawdown при 7% one-way spike: ~$800-1500
- Equity at risk: ~$20-25k

---

## Сравнение V1 vs V2

| Критерий | V1 Tight | V2 Combo-trailing |
|---|---|---|
| Цель оборота | $500k/сутки ✓ | $300-400k/сутки |
| Net прибыль/сутки | ~$0 | +$100-200 |
| Round-trips/сутки | 60-80 | 30-50 |
| Сложность мониторинга | низкая | средняя |
| Чувствительность к funding | низкая | средняя |
| Лучший рынок | volatile chop | trending |
| Worst-case DD/сутки | -$500 | -$1500 |
| Когда запускать | будни (high vol) | выходные (trending) |

---

## Запуск (operator workflow)

### V1 (повседневная)
1. Открыть GinArea, создать SHORT-бота с параметрами выше
2. Создать LONG-бота с параметрами выше (на inverse XBTUSD)
3. Запустить оба, мониторить через `/audit` в TG
4. Каждые 4-6 часов проверять `state/setups.jsonl` на алерты
5. Если volume цель не достигается за 6 часов → понизить indicator threshold с 0.2% до 0.15%

### V2 (выходные)
1. В пятницу вечером остановить V1
2. Перенастроить параметры на V2 (или создать новых ботов)
3. Запустить в субботу утром (00:00 UTC)
4. Не трогать до воскресенья 23:00 UTC
5. Снять статистику, вернуть V1 на понедельник

---

## Health-checks (что добавить в bot7 — pending)

- [ ] **Volume tracker**: hourly TG-сводка `[V-FARM] objem 4h: $87k / $500k target (17%)`
- [ ] **Idle alert**: если bot >6h без новых IN → TG WARN
- [ ] **Boundary breach alert**: цена вышла за boundaries → TG WARN
- [ ] **Funding warn**: funding > 0.03%/8h → TG WARN, режим может стать убыточным
- [ ] **Daily P&L summary**: 23:00 UTC → суммарная статистика V1/V2 с разбивкой по ногам

---

## Changelog

```
2026-05-09 v1.0 | V1 + V2 параметры зафиксированы оператором.
                  Источники: GINAREA_MECHANICS.md §1-7, скрин UI 2026-05-09.
                  Operator launches V2 on weekends, V1 on weekdays.
```
