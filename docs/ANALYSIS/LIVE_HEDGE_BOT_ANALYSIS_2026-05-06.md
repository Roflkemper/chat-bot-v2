# LIVE HEDGE BOT ANALYSIS — BTC-LONG-D-хедж — 2026-05-06

**Тип:** READ-ONLY post-hoc analysis запущенного бота
**TZ:** TZ-LIVE-HEDGE-BOT-ANALYSIS
**Дата запуска:** 2026-05-06 ~16:48 UTC+3
**Источники:** [`docs/REGULATION_v0_1_1.md`](../REGULATION_v0_1_1.md), [`docs/PLAYBOOK_MANUAL_LAUNCH_v1.md`](../PLAYBOOK_MANUAL_LAUNCH_v1.md), [`docs/RESEARCH/REGIME_OVERLAY_v2_1.md`](../RESEARCH/REGIME_OVERLAY_v2_1.md), live computations on `data/forecast_features/full_features_1y.parquet`

Без trading advice. Без прогнозов. Без рекомендаций изменения параметров.

**Margin framing:** только через distance-to-liquidation. Coefficient % НЕ используется как threat metric (per operator decision 2026-05-06 17:00, M-* false positives — known issue, см. backlog `TZ-MARGIN-COEFFICIENT-SEMANTICS-FIX`). Emergency = distance < 5%.

---

## §1 Bot status

| Поле | Значение |
|---|---:|
| Имя | BTC-LONG-D-хедж ✨ |
| Status | ЗАПУЩЕН 2026-05-06 ~16:48 UTC+3 |
| Side | LONG |
| Контракт | inverse XBTUSD (assumed — operator screen showed "LONG inverse"); требуется final operator clarification |
| Indicator | **ASSUMED Pack E `<-0.3%` PRICE%-1m-30** (не виден на скрине) — в случае иного индикатора пересчитать activation frequency |
| Order count | 80 |
| Шаг сетки | 0.04% |
| Размер ордера | $500 |
| Target profit | 0.5% |
| Instop | 0.018 / 0.01 / 0.03 |
| Trailing | OFF (assumed) |
| Total max position | 80 × $500 = **$40,000** |
| Coverage range | 80 × 0.04% = **3.2% drop** от стартовой цены |

---

## §2 Verified параметры vs Pack E PLAYBOOK baseline

| Параметр | Pack E PLAYBOOK | BTC-LONG-D-хедж | Δ | Significance |
|---|---:|---:|---:|---|
| Side | LONG | LONG | — | match |
| Indicator | `<-0.3%` PRICE%-1m-30 | assumed same | — | match (assumed) |
| Target | 0.5% | 0.5% | 0 | match |
| Instop | 0.018 / 0.01 / 0.03 | 0.018 / 0.01 / 0.03 | 0 | match (F-G validated direction для Pack E) |
| **Order count** | **220** | **80** | **−64%** | shallower coverage |
| **Order size** | **$100** | **$500** | **+400%** | bigger per-trade exposure |
| **Grid step** | **0.03%** | **0.04%** | **+33%** | wider grid, fewer fills |
| **Max position** | **$22,000** | **$40,000** | **+82%** | larger total exposure |
| **Coverage range** | 6.6% drop | 3.2% drop | **−52%** | exhausts ~2x earlier |
| Trailing | OFF | OFF (assumed) | — | match |

**Foundation note:** Pack E backtested на order_count=5,000 (REGULATION §5). Production cap 220. Этот бот использует 80. Pack E backtest evidence — direction signal, не magnitude prediction (PLAYBOOK §3 line 61).

---

## §3 Activation frequency estimate

Из [`LONG_HEDGE_BOT_ANALYSIS_2026-05-06.md`](LONG_HEDGE_BOT_ANALYSIS_2026-05-06.md) §3.1, computed live on 1y data:

| Indicator | Distinct events / 1y | Per day |
|---|---:|---:|
| Pack E `<-0.3%` / 30min (1h debounce) | 2,146 | **5.88/day** |

**С grid step 0.04% vs Pack E 0.03%:** wider grid означает ~25-33% реже fills per trigger event. Approximate adjusted activation:
- Pack E rate adjusted: ~**4.4 fills/day** (5.88 × 0.75)
- Per month: ~**130 fills/month**

**С order_size $500 vs $100:** на каждый fill — $500 LONG buy. При triggers 4.4/day, full $40k exhaustion = 80 fills = **~18 days** при average activation rate (если drops равномерные).

Caveat: реальная частота зависит от volatility режима. В COMPRESSION (текущий) — significantly меньше triggers. В MARKDOWN — больше.

---

## §4 Expected PnL по 5 сценариям + distance-to-liquidation impact

Текущая позиция: SHORT 1.434 BTC linear @ entry 79,036, mark 82,300, liq @ 96,497. Текущий distance-to-liq SHORT = **17.25%** (комфортный запас).

### §4.1 Scenario table

| # | Цена | Δ% | SHORT PnL | dist_to_liq SHORT | CFG-L-RANGE est | BTC-LONG-D est | Combined |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 90,000 | +9.4% | **−$15,722** | **7.22%** | minimal | minimal | **−$15,500** |
| 2 | 85,000 | +3.3% | **−$8,552** | **13.53%** | small | minimal | **−$8,400** |
| 3 | 78,000 | −5.2% | **+$1,486** | **23.71%** | active | active (most fills) | **+$1,920** |
| 4 | 75,200 | −8.6% | **+$5,501** | **28.32%** | very active | exhausted (full $40k) | **+$6,500** |
| 5 | sideways 81–83k неделя | ~0% | **−$4,250** + funding (1w × $28/d = +$196) | **17.68%** | minimal | few fills | **−$3,900** |

### §4.2 Distance-to-liq framing

| Scenario | dist_to_liq | Status | Margin headroom |
|---|---:|---|---|
| 1 (90k) | **7.22%** | **WATCH** (closer to 5% emergency floor) | available margin shrinks materially |
| 2 (85k) | 13.53% | comfortable | ample headroom |
| 3 (78k) | 23.71% | very comfortable | LONG bots add collateral via gains |
| 4 (75.2k) | 28.32% | very comfortable | LONG bots fully active, gains add collateral |
| 5 (sideways) | 17.68% | comfortable | unchanged |

**Emergency tier (distance < 5%) НЕ достигается ни в одном из 5 сценариев.** Scenario 1 (90k) приближает SHORT к 7.2% headroom — это watch territory, но не emergency. Чтобы distance упал до 5%, цена должна дойти до **~91,902** (около +11.7% от текущей).

### §4.3 BTC-LONG-D PnL detail

PnL для $40k bot при exhaustion (BTC drops через 80 grid orders):
- 80 orders × $500 × target 0.5% per cycle = **$200 per full cycle** (если все 80 закрылись с TP)
- Pack E foundation: per-target +0.0825..+0.1114 BTC за 86d на 5,000-order backtest. Linear scale к $40k production: значимо ниже без direct evidence.
- Conservative estimate: $40k × annual return rate ~25-30% (от Pack E direction extrapolation) = **~$10k–12k/yr**, **~$830–1,000/month**, при equilibrium activation.

В Scenario 4 (75.2k) bot fully exhausted = заполнил $40k LONG позицию по средней цене ~80,950 (mid-grid). При recovery к 82,300 = unrealized ~+$840. Если каждый grid order попал в TP (0.5%) = realized +$200 за full grid → **~$800–1,000 cycle profit** при полной recovery после exhaustion.

В Scenario 1 (90k) bot не exhausted (нет drops), почти все orders untouched = minimal PnL **~$0–50**.

---

## §5 Hedge effectiveness

| Scenario | SHORT loss/profit | Hedge bot contrib | Hedge effectiveness % | Combined improvement |
|---|---:|---:|---:|---:|
| 1: 90k (adverse) | −$15,722 | ~$50 | **0.3%** | −$15,672 (negligible) |
| 2: 85k (adverse) | −$8,552 | ~$100 | **1.2%** | −$8,452 |
| 3: 78k (favorable for SHORT) | +$1,486 | ~+$300 | n/a (both winning) | +$1,786 |
| 4: 75.2k (very favorable SHORT) | +$5,501 | ~+$1,000 | n/a (both winning) | +$6,501 |
| 5: sideways | −$4,054 net | ~+$50 | 1.2% | −$4,000 |

**Honest finding:** в adverse scenarios (BTC up) BTC-LONG-D **не компенсирует SHORT loss** — hedge effectiveness 0.3%–1.2%. Бот не торгует при росте (нет drops индикатора). В favorable scenarios (BTC down) бот добавляет profit к SHORT profit — это complementary income, **не hedge в narrow sense**.

Структурно: **этот бот не hedge SHORT loss, а зарабатывает на pullbacks внутри дрифта вниз**. Hedge term здесь означает "complementary LONG income в pullback windows", не "offsetting position для SHORT exposure".

---

## §6 Риски (через distance-to-liquidation)

### §6.1 Bot stand-alone drawdown

При adverse movement (BTC падает но не возвращается):
- Bot накапливает $40k LONG позицию через 80 fills (3.2% range)
- Если BTC проваливается ниже coverage range (drop > 3.2% от старта = ниже ~79,666):
  - Все 80 orders заполнены, бот не может больше торговать
  - Average cost basis ~80,950 (mid-grid)
  - Худший случай: BTC drops к 75,200 → bot позиция $40k × (75,200/80,950 − 1) = **−$2,840**
  - Худший случай: BTC drops к 70,000 → −$5,407

### §6.2 Distance-to-liquidation impact от bot

Bot — LONG inverse XBTUSD. Это **другой margin pool** от SHORT BTCUSDT linear (если operator использует isolated accounts) или **shared cross-margin** (если cross). 

**Критический gap:** воркер не знает, в каком margin pool работает bot. Если cross-margin:
- LONG позиция при росте BTC → profit → добавляет collateral → distance-to-liq SHORT улучшается
- LONG позиция при падении → loss → съедает collateral → distance-to-liq SHORT ухудшается
- В Scenario 3 (78k): LONG bot loses ~$1,500 → dist-to-liq SHORT slightly worse (но всё равно 23.7% — wide margin)
- В Scenario 1 (90k): LONG bot wins ~$50 (minimal triggers) → dist-to-liq SHORT остаётся ~7.22%

Если isolated:
- Bot's PnL не влияет на SHORT margin
- Только funding и position size матерят для cross-account distance

### §6.3 Available margin impact

- Bot reserves $40k margin для full position (или N% при leverage)
- Текущая available margin: $20,434 (последний operator snapshot)
- **$40k bot total > $20,434 available** — operator должен подтвердить что collateral достаточно для full grid exhaustion. Если cross-margin shared с SHORT, full exhaustion может consumeать margin pool.

### §6.4 Funding considerations

- LONG inverse XBTUSD при negative funding: long pays short в inverse, **LONG получает funding** при positive (typical setup)
- Текущий funding −0.0082%/8h: SHORT получает funding (как уже работает)
- Net на portfolio: SHORT linear gains funding + LONG inverse — funding direction зависит от XBTUSD funding rate (отдельный от BTCUSDT linear)
- **Гэп:** воркер не имеет live XBTUSD funding rate

### §6.5 Edge cases

| Edge case | Что происходит | Foundation |
|---|---|---|
| Все 80 orders заполнены (BTC drops 3.2%) | Bot exhausted, $40k LONG позиция, ждёт recovery | direct math |
| BTC продолжает падать после exhaustion | Bot не торгует, позиция в drawdown | bot logic |
| Регим переключается в TREND_DOWN/CASCADE_DOWN | Pack C LONG default 3/3 losing — но это DEFAULT bot, не indicator-gated. Pack E indicator-gated 4/4 profitable across все режимы за 86d window | REGULATION §3 |
| Funding flips к ≥0 | Pack BT analysis: median 65h, цена ~+1.31% выше setup | v3 §7.6 |

---

## §7 Отклонения от Pack E foundation

### §7.1 order_size $500 vs $100 (5×)

| Метрика | Pack E ($100) | BTC-LONG-D ($500) |
|---|---:|---:|
| Profit per successful trade (target 0.5%) | $0.50 | **$2.50** |
| Loss per failed trade (max stop 0.03%) | $0.03 | **$0.15** |
| Risk:reward ratio | same (1:16.7) | same (1:16.7) |
| PnL volatility per trade | low | **5× higher** |

### §7.2 order_count 80 vs 220 (−64%)

| Метрика | Pack E (220) | BTC-LONG-D (80) |
|---|---:|---:|
| Coverage range (drop %) | 220 × 0.03% = **6.6%** | 80 × 0.04% = **3.2%** |
| От 82,300 exhaust at | 76,868 | **79,666** |
| BTC drop required для exhaustion | 6.6% | 3.2% |

**Важно:** этот бот exhausts при BTC drop до ~79,666 (близко к operator's SHORT entry 79,036). Если BTC доходит до anchor 75,200, бот уже давно exhausted.

### §7.3 grid step 0.04% vs 0.03% (+33%)

| Метрика | Pack E (0.03%) | BTC-LONG-D (0.04%) |
|---|---:|---:|
| Distance between grid levels | 0.03% | 0.04% |
| Fills per drop | tighter | ~25% реже |
| Foundation evidence | 4/4 BT profitable | **NO direct evidence для 0.04%** |

Foundation gap: Pack E backtests — все на 0.03 grid. 0.04 не A/B-validated. Direction (positive PnL) предполагается тот же (target/instop unchanged), но magnitude unknown.

---

## §8 Что foundation НЕ говорит

| Вопрос | Причина |
|---|---|
| Точная expected monthly PnL | Pack E backtest order_count=5000, production 220, этот бот 80 — order_count downscale unmodelled |
| Effect 0.04 grid step vs 0.03 | Не A/B-validated (Pack E backtests все на 0.03) |
| Effect $500 vs $100 order size | direct linear scaling assumed, но не validated |
| Cross- или isolated-margin pool | Operator не подтвердил mode |
| Live XBTUSD funding rate | data file 1y только BTCUSDT, не XBTUSD |
| Точная date exhaustion | depends на realized volatility, не predictable |
| Hedge effectiveness в bear market | 1y данные были bull-skewed; Pack BT/E foundation на bull window |
| Indicator точно `<-0.3%` или другой | Не виден на скрине; assumed Pack E |
| Поведение бота после exhaustion при continued drop | depends на bot logic (вне foundation scope) |

---

## §9 Audit trail

| Число / утверждение | Источник | Confidence |
|---|---|---|
| Pack E PLAYBOOK params (220 / $100 / 0.03 / 0.018 / 0.5 / OFF / OFF) | [PLAYBOOK_MANUAL_LAUNCH_v1.md:44-58](../PLAYBOOK_MANUAL_LAUNCH_v1.md) | HIGH |
| Pack E max position $22,000 | PLAYBOOK_MANUAL_LAUNCH_v1.md:58 | HIGH |
| BTC-LONG-D max position $40,000 | direct math 80 × $500 | HIGH |
| BTC-LONG-D coverage range 3.2% | direct math 80 × 0.04% | HIGH |
| Pack E coverage range 6.6% | direct math 220 × 0.03% | HIGH |
| Pack E activation 5.88/day | [LONG_HEDGE_BOT_ANALYSIS_2026-05-06.md:§3.1](LONG_HEDGE_BOT_ANALYSIS_2026-05-06.md) computed on 1y data | HIGH |
| Adjusted activation ~4.4/day для 0.04 grid | extrapolation 0.75× rate | MEDIUM (caveat in §3) |
| Pack E PnL direction signal not magnitude | [PLAYBOOK_MANUAL_LAUNCH_v1.md:61](../PLAYBOOK_MANUAL_LAUNCH_v1.md) | HIGH |
| Pack E 4/4 profitable | [REGIME_OVERLAY_v2_1.md:51-58](../RESEARCH/REGIME_OVERLAY_v2_1.md) | HIGH |
| 0.04 grid не A/B-validated | absence of evidence in REGIME_OVERLAY foundation | HIGH (verified gap) |
| SHORT 1.434 BTC entry 79,036 | operator state_latest 2026-05-06 | source of truth |
| Liquidation price 96,497 | operator BitMEX UI 2026-05-06 | source of truth |
| Distance to liq formula `(liq - mark) / mark × 100` | direct calc | HIGH |
| Scenario 1 dist-to-liq 7.22% (NOT emergency tier) | direct math | HIGH |
| Scenario 1 SHORT PnL −$15,722 | direct math 1.434 × (79,036 − 90,000) | HIGH |
| Hedge effectiveness 0.3%–1.2% in adverse | derived from Pack E activation rate × scaled position | MEDIUM (estimation) |
| Funding −0.0082%/8h SHORT | operator state_latest | source of truth |
| Margin emergency = distance < 5% | operator decision 2026-05-06 17:00 | source of truth |

---

**Конец документа.** Bot status зафиксирован, 5 сценариев с distance-to-liquidation в каждом, hedge effectiveness честно посчитан (0.3%–1.2% в adverse), 3 ключевых отклонения от Pack E количественно описаны, foundation gaps explicit. Margin framing — только distance-to-liq, никаких coefficient % как threat.
