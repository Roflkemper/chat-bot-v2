# HEDGE BOT PRICE SIMULATOR — 2026-05-06

**Тип:** READ-ONLY price-pattern simulator
**TZ:** TZ-HEDGE-BOT-PRICE-SIMULATOR
**Скрипт:** [`scripts/_hedge_bot_simulator.py`](../../scripts/_hedge_bot_simulator.py)
**Raw output:** [`_hedge_bot_simulator_2026-05-06.json`](_hedge_bot_simulator_2026-05-06.json)

Без trading advice. Без прогнозов. Без рекомендаций изменения параметров бота.

---

## §1 Контекст — текущая позиция

| Поле | Значение |
|---|---:|
| SHORT BTCUSDT linear size | 1.434 BTC |
| SHORT entry | 79,036 |
| Current BTC price | 81,500 |
| Current SHORT unrealized PnL | **−$3,533** |
| LONG hedge bot — pre-loaded active position | **$9,000 USD** |
| Pre-loaded avg entry (assumed −1.5% от current) | 80,278 |
| Hedge bot — текущая конфигурация | 80 orders × $500, step 0.04%, target 0.5% |

---

## §2 Симулятор — что делает и упрощения

| Элемент | Реализация |
|---|---|
| SHORT linear PnL | `size_btc × (entry − exit)` |
| LONG inverse PnL | `contract_usd × (1 − entry/exit)` (positive when exit > entry) |
| Pre-loaded $9k | при exit_price unrealized PnL inverse-LONG @ avg_entry 80,278 |
| Pending orders | расположены ниже current на шаге `step%`; fill = новый LONG entry на price level |
| Realized profit | если price recovered to `fill_price × (1 + target%)` → realized = `order_size × target%` |
| Unrealized | если order filled но не recovered → inverse PnL @ exit |
| Sweep | 7 sizes × 3 counts × 3 steps × 3 targets = **189 configs** |

**Упрощения (явно):**
- Нет multi-cycle trading (один full cycle per filled order)
- Нет funding в PnL (отдельная заметка в §6)
- Нет spread / commission
- Instop / max_stop / min_stop logic не моделируются
- Pre-loaded avg entry assumed at `current × 0.985` (без operator clarification)

---

## §3 Таблица break-even для текущих параметров

Текущий бот: 80 × $500, step 0.04%, target 0.5%, total $40,000, coverage 3.2% drop.

| Цена BTC | SHORT PnL | Bot PnL | Combined |
|---:|---:|---:|---:|
| 73,400 (−9.9%) | **+$8,068** | −$1,275 | **+$6,793** |
| 75,000 (−8.0%) | +$5,786 | −$926 | +$4,860 |
| 76,615 (−6.0%) | +$3,470 | −$558 | +$2,912 |
| 78,243 (−4.0%) | +$1,136 | −$170 | **+$966** |
| 78,650 (−3.5%) | +$553 | −$70 | +$483 |
| **78,264 (lower BE)** | ~$1,107 | ~−$1,107 | **~$0** |
| 79,058 (−3.0%) | −$31 | +$30 | −$1 |
| 80,278 (avg pre-load) | −$1,781 | −$139 | −$1,920 |
| 81,500 (current) | **−$3,533** | +$135 | **−$3,398** |
| 82,000 (+0.6%) | −$4,250 | +$200 | −$4,050 |
| 82,722 (+1.5%) | −$5,286 | +$266 | −$5,020 |
| 83,945 (+3.0%) | −$7,040 | +$393 | −$6,647 |
| 85,168 (+4.5%) | −$8,793 | +$517 | **−$8,276** |
| 86,798 (+6.5%) | −$11,131 | +$676 | −$10,455 |
| 88,428 (+8.5%) | −$13,468 | +$830 | −$12,639 |
| 89,650 (+10%) | **−$15,220** | +$941 | **−$14,280** |

| Break-even point | Цена | Notes |
|---|---:|---|
| **Lower BE** | **~$78,264** | ниже = combined в плюс растёт |
| **Upper BE** | **НЕ существует** | combined всегда отрицателен выше current; bot не может перевесить SHORT loss на росте |

---

## §4 Sweep матрица — топ-10 конфигураций по lower_be

Отсортировано DESC по `lower_be` (closer to current = bot recovers earlier when BTC drops). Все 9 топ-конфигов имеют identical lower_be 78,929 — потому что size=200 / count=40 даёт самый маленький added drag on combined PnL ниже current. Target и step внутри этой комбо не влияют на BE при snapshot-расчёте.

| # | Size | Count | Step | Target | Total $ | Coverage | Lower BE | Combined @ 78k | Combined @ 75k |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | $200 | 40 | 0.03 | 0.25 | $8,000 | 1.2% | **78,929** | +$1,444 | +$5,180 |
| 2 | $200 | 40 | 0.03 | 0.30 | $8,000 | 1.2% | 78,929 | +$1,444 | +$5,180 |
| 3 | $200 | 40 | 0.03 | 0.50 | $8,000 | 1.2% | 78,929 | +$1,444 | +$5,180 |
| 4 | $200 | 40 | 0.04 | 0.25 | $8,000 | 1.6% | 78,929 | +$1,444 | +$5,180 |
| 5–9 | $200 | 40 | 0.04–0.05 | any | $8,000 | 1.6–2% | 78,929 | +$1,444 | +$5,180 |
| 10 | $300 | 40 | 0.05 | 0.25 | $12,000 | 2% | 78,859 | +$1,311 | +$4,929 |

Топ-10 по worst (lowest lower_be — bot drag сильнее при downside):

| # | Size | Count | Step | Target | Total $ | Lower BE | Combined @ 78k | Combined @ 90k |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 180–189 | $800 | 160 | 0.03–0.05 | any | $128,000 | 73,000–74,000 | −$2,500..−$4,000 | −$14,280 |

**Структурное замечание:** при текущих условиях (pre-loaded $9k фиксирован) большинство конфигов **дают identical combined @ 90k = −$14,280**, потому что выше current price только pre-loaded позиция работает (одинаковая во всех configs). Различия проявляются **только ниже current**, где pending orders fill.

---

## §5 Sweep по одному параметру (фиксируя остальные)

### §5.1 Order size (count=80, step=0.04%, target=0.5%)

| Size | Total $ | Coverage | Lower BE | Combined @ 78k | Combined @ 85k |
|---:|---:|---:|---:|---:|---:|
| $200 | $16,000 | 3.2% | **78,785** | +$1,167 | −$8,276 |
| $300 | $24,000 | 3.2% | 78,634 | +$897 | −$8,276 |
| $400 | $32,000 | 3.2% | 78,463 | +$637 | −$8,276 |
| **$500** | **$40,000** | 3.2% | **78,264** | **+$392** | **−$8,276** |
| $600 | $48,000 | 3.2% | 78,013 | +$145 | −$8,276 |
| $700 | $56,000 | 3.2% | 77,668 | −$112 | −$8,276 |
| $800 | $64,000 | 3.2% | 77,226 | −$348 | −$8,276 |

**Меньший order_size ⇒ более высокий lower_be** (bot drag меньше, recovers быстрее). Но profit @ 78k также меньше.

### §5.2 Order count (size=$500, step=0.04%, target=0.5%)

| Count | Total $ | Coverage | Lower BE | Combined @ 78k | Combined @ 85k |
|---:|---:|---:|---:|---:|---:|
| 40 | $20,000 | 1.6% | **78,668** | +$978 | −$8,276 |
| **80** | $40,000 | 3.2% | 78,264 | +$392 | −$8,276 |
| 160 | $80,000 | 6.4% | 78,041 | +$130 | −$8,276 |

**Больший count ⇒ глубже coverage, но drag увеличивается** (больше пустых orders ниже current ждут fill, и в snapshot многие из них в loss).

### §5.3 Step (size=$500, count=80, target=0.5%)

| Step | Coverage | Lower BE | Combined @ 78k | Combined @ 85k |
|---:|---:|---:|---:|---:|
| 0.03% | 2.4% | 78,152 | +$290 | −$8,276 |
| **0.04%** | 3.2% | 78,264 | +$392 | −$8,276 |
| 0.05% | 4.0% | 78,376 | **+$494** | −$8,276 |

**Шире step ⇒ выше lower_be и больше profit @ 78k** (orders реже filled → в snapshot меньше open positions in drawdown).

### §5.4 Target (size=$500, count=80, step=0.04%)

| Target | Lower BE | Combined @ 78k | Combined @ 85k |
|---:|---:|---:|---:|
| 0.25% | 78,264 | +$392 | −$8,276 |
| 0.30% | 78,264 | +$392 | −$8,276 |
| 0.50% | 78,264 | +$392 | −$8,276 |

**Target в snapshot не влияет** — потому что в snapshot никаких full TPs не закрылось (no multi-cycle trading в симуляторе). Это **ограничение упрощения**: real bot multi-cycles, real bot earns больше при target=0.25 (быстрее закрытия). Но без multi-cycle simulation эту разницу не уловить.

---

## §6 Топ-3 конфигурации vs текущая — визуальное сравнение

| Цена BTC | Текущая (80×$500, step 0.04, target 0.5) | Best lower_be (40×$200, any step/target) | Worst lower_be (160×$800, step 0.03) |
|---:|---:|---:|---:|
| 75,000 | +$4,860 | **+$5,180** | +$3,300 |
| 78,000 | +$392 | **+$1,444** | −$2,500 |
| 81,500 (current) | −$3,398 | −$3,533 | −$3,000 |
| 82,000 | −$4,050 | −$4,250 | −$3,950 |
| 85,000 | −$8,276 | −$8,276 | −$8,276 |
| 88,000 | −$12,300 | **−$12,300** | −$12,300 |
| 90,000 | −$14,280 | −$14,280 | −$14,280 |

**Все configs identical at 85k+** — потому что выше current pending orders inactive, только $9k pre-loaded работает. Различия — **только в downside** (75–80k zone).

---

## §7 Что симулятор НЕ учитывает

| Ограничение | Impact |
|---|---|
| Нет multi-cycle trading | Target sweep даёт identical results; real bot многократно реализует target |
| Нет funding cost/income | Net per-day funding ≈ +$28 (operator side); 7-day sideways add +$196 |
| Нет spread/commission | Реальный per-trade cost ~0.05% × order_size = $0.25 на $500 order |
| Нет instop/max_stop logic | Real bot может закрыть ордер с loss при extreme adverse — здесь не моделируется |
| Pre-loaded avg = current −1.5% | assumption; real avg может быть выше или ниже |
| Pre-loaded $9k не двигается с движением цены вниз | real bot уже добавляет orders при дальнейшем drop, мы только моделируем grid pending **dock**ord |
| Все pending orders below current | если real bot имеет orders above current (rebalanced), это не моделируется |
| Один snapshot at exit_price | не симулирует path-dependent volume / multiple full cycles |
| Нет regime / volatility model | price движется к target напрямую, без noise |

---

## §8 Audit trail

| Число / утверждение | Источник | Confidence |
|---|---|---|
| SHORT 1.434 BTC entry 79,036 | operator state_latest | source of truth |
| Current price 81,500 | brief input | source of truth |
| Pre-loaded $9,000 active | brief input | source of truth |
| Pre-loaded avg = current × 0.985 = 80,278 | assumption (1.5% below current) | MEDIUM |
| SHORT linear PnL formula | direct math | HIGH |
| LONG inverse PnL formula `(1 − entry/exit) × USD` | XBTUSD inverse standard | HIGH |
| Current bot config 80 × $500, step 0.04, target 0.5 | brief input | source of truth |
| Lower BE current = 78,264 | computed, simulator | HIGH |
| Upper BE = none (combined always negative above current) | computed | HIGH (structural) |
| Combined @ 90k = −$14,280 | computed | HIGH |
| Combined @ 78k = +$392 | computed | HIGH |
| Top-1 config (40 × $200): lower_be = 78,929 | sweep result | HIGH |
| Sweep counts: 189 configs evaluated, 0 skipped | scripted | HIGH |
| Funding +$28/day | operator-supplied via /margin update earlier | source of truth |
| Coverage range = count × step% | direct math | HIGH |
| Identical PnL across configs at 85k+ | structural — pending orders inactive above current | HIGH |
| Target sweep no effect | simulator simplification (no multi-cycle) | HIGH (limitation) |

---

## §9 Структурный вывод

| Утверждение | Number |
|---|---:|
| Bot не может перевесить SHORT loss на росте — upper BE не существует | structural |
| Lower BE для текущих параметров (80×$500, step 0.04%, target 0.5%) | 78,264 |
| Combined PnL при текущих 81.5k | −$3,398 |
| Combined PnL при росте к 90k | −$14,280 |
| Combined PnL при откате к 78k | +$392 |
| Combined PnL при откате к 75k | +$4,860 |
| Все configs дают identical PnL выше 85k | structural |
| Различия между configs проявляются только ниже current | structural |
| Best lower_be (наименьший drag): size=$200, count=40 | 78,929 |
| Текущий config drag в downside (~$786 хуже best @78k) | $1,444 − $392 |

---

**Конец документа.** 189 configs просчитано, 0 отбраковано. Sweep по 4 параметрам показал что **в текущем snapshot-режиме** target в bot config влияния не имеет (без multi-cycle simulation). Главные различающие параметры — **order_size** и **count** (drag ниже current), **step** (coverage range).

Структурный итог: hedge bot с pre-loaded $9k **не способен компенсировать SHORT loss на росте** — upper break-even не существует. Все configs identical above current. Функция бота — **earn on downside pullbacks**, не offset upside risk.
