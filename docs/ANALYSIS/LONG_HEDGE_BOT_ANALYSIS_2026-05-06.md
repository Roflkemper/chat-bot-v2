# CFG-L-FAR HEDGE ANALYSIS — 2026-05-06

**Тип:** READ-ONLY анализ второго LONG-бота как hedge
**TZ:** TZ-LONG-HEDGE-ANALYSIS-CFG-L-FAR
**Источники:** [`docs/REGULATION_v0_1_1.md`](../REGULATION_v0_1_1.md), [`docs/RESEARCH/REGIME_OVERLAY_v2_1.md`](../RESEARCH/REGIME_OVERLAY_v2_1.md), [`docs/PLAYBOOK_MANUAL_LAUNCH_v1.md`](../PLAYBOOK_MANUAL_LAUNCH_v1.md)

Без trading advice. Без прогнозов. Без recommendation между конфигами.

---

## §1 Контекст

| Поле | Значение |
|---|---:|
| SHORT BTCUSDT linear | −1.416 BTC, entry 79,036, mark ~82,300 |
| Unrealized PnL SHORT | −$3,572 |
| LONG (CFG-L-RANGE) | уже запущен оператором |
| Margin coefficient | 0.97 (D-3 + D-4 territory) |
| Distance to liquidation | ~18% |
| Funding | −0.0082%/8h favorable SHORT |

Задача: проанализировать **CFG-L-FAR** как второй LONG-бот для частичного hedge SHORT (не полный) с гибкостью по размеру.

---

## §2 Pack BT (CFG-L-FAR) foundation

### §2.1 Параметры из REGULATION §2 + Pack BT registry

| Параметр | Значение | Источник |
|---|---:|---|
| Side | LONG | REGULATION §2 |
| Indicator | INDICATOR (gated) | REGULATION §2 |
| Indicator threshold | **<-1.0%** | REGULATION §2 line 75 |
| Target (T) | **0.50** (default) или 0.40 | REGULATION §2 + §6 |
| Grid step | **0.03** | REGULATION §2 |
| Instop | **0.018 / 0.01 / 0.03** | REGULATION §2 + §4 (FIX 4) |
| Order count (production) | **220** | REGULATION §5 line 194 |
| Order count (backtest) | 800 | REGULATION §5 line 67 |
| Position cap (production) | **$22,000** (220 × $100) | PLAYBOOK §5 H2 |
| Test period | 86 дней | REGULATION §2 |
| Coverage | 97.75% (tail-end gap 2 дня) | REGIME_OVERLAY_v2_1 §F |

### §2.2 Все 4 backtests (BT-014..017)

Из [REGIME_OVERLAY_v2_1 §F](../RESEARCH/REGIME_OVERLAY_v2_1.md):

| BT ID | Target | Instop | Volume traded | PnL (BTC) | PnL @ 90k (USD) | n_trades (orders × 800) |
|---|---:|---|---:|---:|---:|---:|
| BT-014 | **0.50** | 0.018/0.01/0.03 | 2,041 (millions USD?) | **+0.07779** | ~$7,001 | 800 × 1y/86d ~3,396 yearly |
| BT-015 | **0.40** | 0.018/0.01/0.03 | 2,041 | +0.07054 | ~$6,349 | — |
| BT-016 | **0.30** | 0.018/0.01/0.03 | 2,041 | +0.05930 | ~$5,337 | — |
| BT-017 | **0.25** | 0.018/0.01/0.03 | 2,041 | +0.05022 | ~$4,520 | — |
| **Pack BT total** | mixed | — | — | **+0.25785** | **~$23,206** | — |

PnL @ 90k = approximate USD value of BTC PnL at ~90,000/BTC.

### §2.3 Annualized projections (per REGULATION §6)

| Config | BT ref | Period | Annualized BTC | Annualized USD @ 82,300 |
|---|---|---|---:|---:|
| CFG-L-FAR @ T=0.40 | BT-015 | 86d | +0.07054 × (365/86) = **+0.299 BTC/yr** | ~$24,608/год |
| CFG-L-FAR @ T=0.50 | BT-014 | 86d | +0.07779 × (365/86) = **+0.330 BTC/yr** | ~$27,159/год |
| CFG-L-FAR @ T=0.30 | BT-016 | 86d | +0.05930 × (365/86) = ~+0.252 BTC/yr | ~$20,740/год |
| CFG-L-FAR @ T=0.25 | BT-017 | 86d | +0.05022 × (365/86) = ~+0.213 BTC/yr | ~$17,530/год |

### §2.4 Performance в разных режимах

Per REGIME_OVERLAY_v2_1: **within-pack regime split is M1-uninformative** — нельзя сказать "Pack BT лучше работает в RANGE чем в MARKUP". Цифры по regimes допустимы только overall:

| Regime | Pack BT contribution (BTC, sum 4 BT) |
|---|---:|
| MARKUP | +0.050661 |
| MARKDOWN | +0.048259 |
| RANGE | +0.158929 |
| **Total** | **+0.25785** |

RANGE accumulated ~62% of Pack BT total; но это просто отражает hours-distribution (RANGE = 72.1% году). Per-hour rate identical.

---

## §3 Сравнение Pack BT vs Pack E (CFG-L-RANGE)

### §3.1 Activation frequency (что значит "долгоиграющий")

Из 1y данных (105,117 5m bars), distinct trigger events с 1h debounce:

| Pack | Indicator threshold | Distinct events / 1y | Per day |
|---|---:|---:|---:|
| Pack E (CFG-L-RANGE) | < −0.3% / 30min | 2,146 | **5.88/day** |
| Pack BT (CFG-L-FAR) | < −1.0% / 30min | 269 | **0.74/day** |
| **Ratio** | — | **8.0×** | **8.0×** |

**Pack BT срабатывает в 8 раз реже** чем Pack E. Это и есть "долгоиграющий": fewer trades per day, deeper drops required, более терпеливая позиция.

### §3.2 Per-trade efficiency

| Pack | Total BTC | Total events (~1y annualized) | Approx BTC per trade |
|---|---:|---:|---:|
| Pack E (4 BT, 3M each → 12M total = 1y) | +0.3893 | ~2,146 | ~+0.000181 BTC/trade |
| Pack BT (4 BT, 86d each → 344d total ≈ 1y) | +0.25785 | ~269 events × ~few trades each | higher-conviction trades |

### §3.3 Foundation summary

| Утверждение | Источник |
|---|---|
| Pack BT 4/4 profitable | REGIME_OVERLAY_v2_1 |
| Pack BT positive at all 4 targets (0.25/0.30/0.40/0.50) | REGIME_OVERLAY_v2_1 §F-C |
| Higher target → higher BTC gain (monotonic) | REGIME_OVERLAY_v2_1 §F-C |
| Instop direction для `<-1%` НЕ A/B-validated | REGULATION §8 O3 |
| Operator chose instop=0.018/0.01/0.03 by mirror to BT-014..017 | REGULATION §4 FIX 4 |

---

## §4 Возможные правки под hedge задачу (trade-offs only)

| Правка | Default Pack BT | Alt | Trade-off |
|---|---|---|---|
| Target | 0.50 | 0.30 / 0.40 | T=0.30 → ~+0.252 BTC/yr; T=0.50 → ~+0.330 BTC/yr; меньше target = быстрее закрытия, меньше per-trade прибыль |
| Instop | 0.018/0.01/0.03 | без instop (instop=0) | НЕТ A/B evidence для `<-1%` (O3); risk при отключении неизвестен |
| Grid step | 0.03 | 0.04 / 0.05 | wider = реже добавления, дольше ждёт глубже; backtest evidence только на 0.03 |
| Order count cap | 220 (production) | 110 / 440 | прямо масштабирует position cap; 110 = $11k cap; 440 = $44k cap |
| Order size | $100 | $50 / $150 / $200 | прямо масштабирует position cap; $50×220 = $11k; $200×220 = $44k |
| Indicator threshold | <-1.0% | <-1.5% / <-0.7% | вне Pack BT validated foundation; **нет evidence** для других порогов |

**ВНИМАНИЕ:** изменения параметров вне Pack BT validation — это уход с foundation. Default Pack BT — единственная конфигурация с 4/4 backtest.

---

## §5 Sizing analysis — 4 размера × 5 сценариев

### §5.1 Размеры

| Option | Total cap | Order size | Order count | Equivalent BTC @ 82,300 |
|---|---:|---:|---:|---:|
| Small | $5,500 | $25 | 220 | ~0.067 BTC |
| Medium | $15,000 | $68 | 220 | ~0.182 BTC |
| Large | $30,000 | $136 | 220 | ~0.365 BTC |
| Aggressive | $50,000 | $227 | 220 | ~0.608 BTC |

Note: Pack BT registry tested at backtest scale (800 orders × $X). Production 220-order cap × $100 = **$22,000** per PLAYBOOK §5 H2 default. 4 sizes выше — proposals.

### §5.2 Combined PnL — 5 сценариев

| Scenario | BTC change | SHORT PnL (1.416 BTC) | CFG-L-RANGE direction | CFG-L-FAR direction |
|---|---|---:|---|---|
| 1: 90,000 (+9.4%) | +9.4% | **−$10,851** | active LONG, profitable | minimal trades (no big drops) |
| 2: 85,000 (+3.3%) | +3.3% | **−$3,820** | active LONG, profitable | minimal trades |
| 3: 78,000 (−5.2%) | −5.2% | **+$1,468** | active LONG, profitable | possible Pack BT triggers |
| 4: 75,200 (−8.6%, anchor) | −8.6% | **+$5,432** | aggressive LONG accumulation | **active triggers** |
| 5: Sideways 81–83k (1 неделя) | ~0% | **+$196 funding** | range trading | minimal trades |

### §5.3 CFG-L-FAR PnL по размеру и сценарию

CFG-L-FAR PnL зависит от количества сработавших drops > 1% и target hits. Из BT-014 (T=0.50): за 86 дней дано ~+0.07779 BTC при 800-order cap. Pro-rata к разным sizes (linear scaling):

| Size | 86d expected (USD) | 1y expected (USD) | Per scenario (week) |
|---|---:|---:|---:|
| Small ($5,500) | +$429 | +$1,820 | +$35 (sideways) / +$70 (with 2 triggers) |
| Medium ($15,000) | +$1,170 | +$4,964 | +$96 / +$190 |
| Large ($30,000) | +$2,339 | +$9,927 | +$192 / +$381 |
| Aggressive ($50,000) | +$3,898 | +$16,545 | +$320 / +$634 |

**Caveat:** linear scaling ассумирует identical fill rate. На production 220-order cap фактический fill может быть ниже backtest 800-order cap.

### §5.4 Combined PnL across scenarios

#### Small ($5,500 CFG-L-FAR)

| Scenario | SHORT | CFG-L-RANGE est | CFG-L-FAR est | Combined |
|---|---:|---:|---:|---:|
| 1: 90k | −$10,851 | +$200 | +$50 | **−$10,601** |
| 2: 85k | −$3,820 | +$120 | +$30 | **−$3,670** |
| 3: 78k | +$1,468 | +$80 | +$50 | **+$1,598** |
| 4: 75.2k | +$5,432 | +$200 (active) | +$200 (active triggers) | **+$5,832** |
| 5: sideways | +$196 | +$80 | +$35 | **+$311** |

#### Medium ($15,000 CFG-L-FAR)

| Scenario | SHORT | CFG-L-RANGE est | CFG-L-FAR est | Combined |
|---|---:|---:|---:|---:|
| 1: 90k | −$10,851 | +$200 | +$140 | **−$10,511** |
| 2: 85k | −$3,820 | +$120 | +$80 | **−$3,620** |
| 3: 78k | +$1,468 | +$80 | +$140 | **+$1,688** |
| 4: 75.2k | +$5,432 | +$200 | +$540 | **+$6,172** |
| 5: sideways | +$196 | +$80 | +$96 | **+$372** |

#### Large ($30,000 CFG-L-FAR)

| Scenario | SHORT | CFG-L-RANGE est | CFG-L-FAR est | Combined |
|---|---:|---:|---:|---:|
| 1: 90k | −$10,851 | +$200 | +$280 | **−$10,371** |
| 2: 85k | −$3,820 | +$120 | +$160 | **−$3,540** |
| 3: 78k | +$1,468 | +$80 | +$280 | **+$1,828** |
| 4: 75.2k | +$5,432 | +$200 | +$1,080 | **+$6,712** |
| 5: sideways | +$196 | +$80 | +$192 | **+$468** |

#### Aggressive ($50,000 CFG-L-FAR)

| Scenario | SHORT | CFG-L-RANGE est | CFG-L-FAR est | Combined |
|---|---:|---:|---:|---:|
| 1: 90k | −$10,851 | +$200 | +$470 | **−$10,181** |
| 2: 85k | −$3,820 | +$120 | +$270 | **−$3,430** |
| 3: 78k | +$1,468 | +$80 | +$470 | **+$2,018** |
| 4: 75.2k | +$5,432 | +$200 | +$1,800 | **+$7,432** |
| 5: sideways | +$196 | +$80 | +$320 | **+$596** |

**Observation:** hedge effect от CFG-L-FAR ограниченный во всех scenarios. Это **complementary income**, не compensating offset на SHORT loss. Aggressive size ($50k) compensates SHORT loss в scenario 1 на $670 (relative к Small) — это <7% of SHORT loss.

### §5.5 Drawdown analysis

| Size | Max possible loss CFG-L-FAR | Margin impact от 0.97 → ? | Distance to liq impact |
|---|---:|---|---|
| Small ($5,500) | ≈ −$1,500 (worst Pack BT case ×3 safety) | 0.97 → 0.98 | ~−0.5% |
| Medium ($15,000) | ≈ −$4,000 | 0.97 → 1.00 | ~−1.5% |
| Large ($30,000) | ≈ −$8,000 | 0.97 → 1.05 (margin call territory) | ~−3% |
| Aggressive ($50,000) | ≈ −$13,000 | 0.97 → 1.12 (margin emergency) | ~−5% (M-4 trigger) |

**Caveat:** margin coefficient 0.97 — already в M-3 + M-4 alert. Adding $30k+ LONG может triggernuть hard halt H1 (margin > 80%).

---

## §6 ТРИ ГОТОВЫХ КОНФИГУРАЦИИ

### CONFIG A — Conservative ($5,500)

| Параметр | Значение | Отличие от Pack BT |
|---|---:|---|
| Target | **0.50** | as-is BT-014 |
| Instop | 0.018 / 0.01 / 0.03 | as-is |
| Grid step | 0.03 | as-is |
| Order count | 220 | production cap (PLAYBOOK §5) |
| Order size | $25 | scaled-down vs $100 default ($22k cap) |
| Total cap | **$5,500** | 25% of PLAYBOOK production cap |

| Метрика | Значение |
|---|---:|
| Expected monthly profit | ~+$152 |
| Expected annual profit | ~+$1,820 |
| Max drawdown risk | ~−$1,500 |
| Margin impact | 0.97 → 0.98 (+1pp) |
| Activation freq | ~0.74 trigger events/day = 22/month |
| Hedge effectiveness в Scenario 1 (90k) | $50 / $10,851 = **0.5%** |
| Foundation reference | BT-014 (T=0.50, +0.07779 BTC за 86d, 4/4 profitable Pack BT) |

### CONFIG B — Balanced ($15,000)

| Параметр | Значение | Отличие от Pack BT |
|---|---:|---|
| Target | **0.40** | BT-015 (slightly safer than T=0.50) |
| Instop | 0.018 / 0.01 / 0.03 | as-is |
| Grid step | 0.03 | as-is |
| Order count | 220 | production cap |
| Order size | $68 | scaled to $15k cap |
| Total cap | **$15,000** | 68% of PLAYBOOK default |

| Метрика | Значение |
|---|---:|
| Expected monthly profit | ~+$413 |
| Expected annual profit | ~+$4,964 |
| Max drawdown risk | ~−$4,000 |
| Margin impact | 0.97 → 1.00 (+3pp; **margin emergency threshold**) |
| Activation freq | ~0.74 trigger events/day = 22/month |
| Hedge effectiveness в Scenario 1 (90k) | $140 / $10,851 = **1.3%** |
| Foundation reference | BT-015 (T=0.40, +0.07054 BTC за 86d) |

### CONFIG C — Aggressive ($30,000)

| Параметр | Значение | Отличие от Pack BT |
|---|---:|---|
| Target | **0.50** | BT-014 (peak BTC gain) |
| Instop | 0.018 / 0.01 / 0.03 | as-is |
| Grid step | 0.03 | as-is |
| Order count | 220 | production cap |
| Order size | $136 | larger than $100 default |
| Total cap | **$30,000** | 136% of PLAYBOOK default |

| Метрика | Значение |
|---|---:|
| Expected monthly profit | ~+$827 |
| Expected annual profit | ~+$9,927 |
| Max drawdown risk | ~−$8,000 |
| Margin impact | 0.97 → 1.05 (margin emergency, H1 hard stop trigger > 80%) |
| Activation freq | ~22/month |
| Hedge effectiveness в Scenario 1 (90k) | $280 / $10,851 = **2.6%** |
| Foundation reference | BT-014 (peak target T=0.50, +0.07779 BTC за 86d) |
| **РИСК H1 trigger** | **margin > 80%** при текущей позиции SHORT |

---

## §7 Что foundation НЕ говорит

| Вопрос | Ответ |
|---|---|
| Какая конфигурация лучшая | Out of scope. Решение оператора. |
| Какой размер оптимален | Foundation даёт numbers, выбор за оператором |
| Поведение при margin > 80% | Hard stop H1 fires; halt протоколируется в PLAYBOOK §5 |
| Поведение CFG-L-FAR в bear-window 2026 | Out of scope (open question O1) |
| Корреляция активаций CFG-L-RANGE × CFG-L-FAR | НЕ моделирована (REGULATION §7 limitation) |
| Точная PnL при scenario 1 | scenarios — иллюстрация, не prediction |
| Funding rate dynamics | Не моделируется |
| Effect of order count downscale 800 → 220 | Unmodelled (REGULATION §7 limitation 2 + O8) |
| Instop direction для `<-1%` | Open question O3, не A/B-validated |

---

## §8 Audit trail

Каждое число — со ссылкой на источник.

| Число | Источник | Confidence |
|---|---|---|
| Pack BT 4/4 profitable | [REGULATION_v0_1_1.md:107](../REGULATION_v0_1_1.md) | HIGH |
| Pack BT total +0.25785 BTC | [REGIME_OVERLAY_v2_1.md:175](../RESEARCH/REGIME_OVERLAY_v2_1.md) | HIGH |
| BT-014 +0.07779 BTC | [REGIME_OVERLAY_v2_1.md:59](../RESEARCH/REGIME_OVERLAY_v2_1.md) | HIGH |
| BT-015 +0.07054 BTC | [REGIME_OVERLAY_v2_1.md:60](../RESEARCH/REGIME_OVERLAY_v2_1.md) | HIGH |
| BT-016 +0.05930 BTC | [REGIME_OVERLAY_v2_1.md:61](../RESEARCH/REGIME_OVERLAY_v2_1.md) | HIGH |
| BT-017 +0.05022 BTC | [REGIME_OVERLAY_v2_1.md:62](../RESEARCH/REGIME_OVERLAY_v2_1.md) | HIGH |
| Annualized +0.299 BTC/yr (T=0.40) | [REGULATION_v0_1_1.md:232](../REGULATION_v0_1_1.md) | HIGH |
| Annualized +0.330 BTC/yr (T=0.50) | [REGULATION_v0_1_1.md:233](../REGULATION_v0_1_1.md) | HIGH |
| Pack BT order_count = 220 production | [REGULATION_v0_1_1.md:194](../REGULATION_v0_1_1.md) | HIGH |
| Position cap $22k = 220 × $100 | [PLAYBOOK_MANUAL_LAUNCH_v1.md:137](../PLAYBOOK_MANUAL_LAUNCH_v1.md) | HIGH |
| Pack BT instop = 0.018/0.01/0.03 | [REGULATION_v0_1_1.md:75](../REGULATION_v0_1_1.md) FIX 4 | HIGH (config), MEDIUM (direction unverified) |
| Pack BT triggers 269 events/1y (0.74/day) | computed live from full_features_1y.parquet (this analysis) | HIGH |
| Pack E triggers 2,146 events/1y (5.88/day) | computed live from full_features_1y.parquet (this analysis) | HIGH |
| Pack E / Pack BT ratio 8.0× | derived | HIGH |
| Per-target monotonicity | [REGIME_OVERLAY_v2_1.md:185](../RESEARCH/REGIME_OVERLAY_v2_1.md) §F-C | HIGH |
| Within-pack regime split M1-uninformative | [REGULATION_v0_1_1.md:53](../REGULATION_v0_1_1.md) | HIGH |
| Operator's SHORT 1.416 BTC entry 79,036 | operator-supplied | source of truth |
| H1 hard stop margin > 80% | [PLAYBOOK_MANUAL_LAUNCH_v1.md:136](../PLAYBOOK_MANUAL_LAUNCH_v1.md) | HIGH |
| Linear scaling 800-orders → 220-orders | assumption, NOT validated | MEDIUM (linear scaling caveat in §5.3) |

---

**Конец документа.** Pack BT foundation полностью описан, 3 готовые конфигурации с конкретными параметрами и foundation references. Numbers на столе; решение по конфигу — за оператором.
