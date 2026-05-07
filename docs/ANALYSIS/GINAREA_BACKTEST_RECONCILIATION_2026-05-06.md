# GINAREA BACKTEST RECONCILIATION — 2026-05-06

**Источник:** 6 screenshot'ов GinArea backtest UI от оператора (2026-05-06)
**Контракт:** BTCUSD inverse, BitMEX, COIN_FUTURES
**Что делается:** сопоставление чисел backtest'ов друг с другом + с текущим запущенным ботом + с моей parquet-foundation. Без ре-расчётов, без новых reconciled версий.

Без trading advice. Без рекомендаций config.

---

## §1 6 backtests в одной таблице

| # | ID | Период | Strategy | Step | Count × Size | Trail | Profit BTC | Trades | Avg price |
|---|---|---|---|---:|---|---|---:|---|---:|
| 1 | 4886978820 | 05.02–05.05.2026 (3M) | DEFAULT GRID | 0.03 | 80 × $500 | OFF | **+0.0913** | 15 / $7,500 | 80,946 |
| 2 | 6330583675 | 05.02–05.05.2026 (3M) | DEFAULT GRID | 0.03 | 80 × $500 | ON (start=3, %=30) | **+0.0913** | 15 / $7,500 | 80,946 |
| 3 | 5079319343 | 05.02–05.05.2026 (3M) | DEFAULT GRID | 0.04 | 80 × $500 | ON | **+0.0954** | 14 / $7,000 | 80,969 |
| 4 | 4441190828 | 05.02–06.05.2026 (3M+1d) | INDICATOR `<-0.7%` | 0.04 | 80 × $500 | ON | **+0.1023** | 34 / $17,000 | 82,096 |
| 5 | 5852654037 | 05.05.2025–05.05.2026 (1Y) | DEFAULT GRID | 0.04 | 5400 × $100 | OFF | **−0.0503** | 925 / $92,500 | 101,628 |
| 6 | 6370367889 | 05.05.2025–05.05.2026 (1Y) | DEFAULT GRID | 0.03 | 5400 × $100 | OFF | **−0.0641** | 1182 / $118,200 | 101,500 |

Все LONG, all BTCUSD inverse, все одна биржа.

---

## §2 Расхождение знака между 3M и 1Y — почему

### §2.1 Что показывают графики прибыли

| Период | Profit shape (графика прибыли BTC) |
|---|---|
| 3M (5,6,7) | start ~0, провал в начале до −0.06..−0.10, восстановление, к концу +0.09..+0.10 BTC |
| 1Y (5) | flat на 0 до Feb 2026, **резкий провал к −0.7 BTC в феврале**, восстановление, к концу −0.05 BTC |
| 1Y (6) | то же что 5, провал к **−1.0 BTC в феврале**, к концу −0.06 BTC |

### §2.2 Цены в backtest'ах

| Период | Avg price в тестах | Что это значит |
|---|---:|---|
| 3M (5,6,7) | ~80,950 | период торговался около $80k |
| 3M (8) | 82,096 | INDICATOR fewer fills, средняя ближе к спот'у |
| 1Y (5,6) | ~101,500 | средняя за год — **bot набирал большие позиции на хаях ~$120k** |

### §2.3 Структурный вывод

| Утверждение | Evidence |
|---|---|
| 3M window — bullish recovery после провала | net change за период положительный, profit shape растёт к концу |
| 1Y window — содержит февральский крах | provals в графиках прибыли совпадают с моим parquet (BTC: max $126k Oct'25 → min $63k Feb'26) |
| Grid LONG **застревает на хаях** в долгом периоде | average position $100k+ в 1Y vs $80k в 3M; реализованный + нереализованный = net negative |
| Realized vs unrealized gap | 1Y test 5: realized +0.185 BTC / unrealized **−0.236 BTC** → net −0.050. Бот закрывал прибыльные циклы, но висит позиция на $126k купленной |

**Простая фраза:** в долгом окне с большим провалом grid LONG копит просадку быстрее чем зарабатывает на восстановлении. Знак PnL зависит от того, **закончился период провалом или восстановлением**.

---

## §3 INDICATOR `<-0.7%` vs DEFAULT GRID — реальная разница

Сравнение в 3M окне (одинаковые период / step / count / size / trail):

| Тест | Strategy | Profit BTC | Trades | Avg price |
|---|---|---:|---:|---:|
| 5079319343 | DEFAULT GRID | +0.0954 | 14 | 80,969 |
| 4441190828 | INDICATOR `<-0.7%` | **+0.1023** | **34** | 82,096 |
| Δ | INDICATOR vs DEFAULT | **+0.0069 BTC** (+7.2%) | **+20 trades** (×2.4) | +1,127 |

**Что показывает:**
- INDICATOR за тот же период сделал **в 2.4 раза больше сделок** при том же конфиге сетки
- INDICATOR заработал +0.0069 BTC больше (~$560 при цене $80k) — небольшая разница
- INDICATOR начинал входить **выше по цене** (avg 82,096 vs 80,969) — значит он не ждал боковика, он брал просадки `<-0.7%` где они были
- Соответствует foundation Pack E (INDICATOR 4/4 profitable) и Pack BT, но threshold у тебя `-0.7%` не `-0.3%` (Pack E) и не `-1.0%` (Pack BT). Это **третий вариант** — между ними

**Caveat:** один тест против одного — n=1 vs n=1, не статистически валидное сравнение. Это **одно наблюдение**, не утверждение «INDICATOR всегда лучше».

---

## §4 Trail ON / OFF — есть ли разница

Compare 4886978820 (trail OFF) vs 6330583675 (trail ON, start=3, %=30):

| Тест | Trail | Profit BTC | Trades | Avg price |
|---|---|---:|---:|---:|
| 4886978820 | OFF | +0.0913 | 15 / $7,500 | 80,946 |
| 6330583675 | ON | +0.0913 | 15 / $7,500 | 80,946 |
| Δ | | **0.0000** | 0 | 0 |

**Никакой разницы.** Profit идентичный, trades идентичные, avg идентичный.

**Структурное чтение:** в этом backtest period trail логика не сработала ни разу (не было движений достаточных чтобы trailing point активировался). Trail = `start=3% / %=30` означает: после +3% прибыли активируется trailing exit с шагом 30% от пика. На этом периоде такие движения не достигались на большинстве позиций.

**Вывод:** Trail ON в данном конкретном backtest не дал ни плюс ни минус. Foundation (моя сторона) trail vs no-trail comparison не делала на этих параметрах — gap.

---

## §5 Step 0.03 vs 0.04 — есть ли разница

Compare 4886978820 (step 0.03, trail OFF) vs 5079319343 (step 0.04, trail ON):

| Тест | Step | Trail | Profit BTC | Trades | Avg price |
|---|---:|---|---:|---:|---:|
| 4886978820 | 0.03 | OFF | +0.0913 | 15 / $7,500 | 80,946 |
| 5079319343 | 0.04 | ON | +0.0954 | 14 / $7,000 | 80,969 |
| Δ | +33% | n/a | **+0.0041** (+4.5%) | −1 | +23 |

⚠️ Это **нечистое сравнение** (trail отличается тоже). Но из §4 мы знаем что trail в этом окне = 0 effect. Значит вся разница — от step.

**Что говорит:**
- Step 0.04 дал чуть больше прибыли (+0.0041 BTC ≈ $330) при **меньшем** числе trades (14 vs 15)
- Шире сетка → реже fills → бот меньше входил → но конкретная конфигурация $500 × 80 × 0.04 поймала движения лучше

**Важная оговорка:** разница 0.0041 BTC на single-test basis — почти неотличимо от шума. Foundation на этих 2 точках ничего не утверждает.

---

## §6 Текущий запущенный бот → ближайший backtest

Твой live bot **BTC-LONG-D-хедж**:
- 80 orders × $500
- Step 0.04
- Trail ON (предполагаю)
- Strategy: оператор не уточнил — DEFAULT GRID или INDICATOR

**Ближайшие backtests:**

| Если live = DEFAULT GRID | → matches 5079319343 |
| Если live = INDICATOR `<-0.7%` | → matches 4441190828 |

| Backtest | Profit за 3M | Annualized projection (×4) | Если 1Y bear-included | 
|---|---:|---:|---|
| 5079319343 (DEFAULT) | +0.0954 BTC | +0.38 BTC/yr (если bull repeated) | НО 1Y тест показал **−0.05** в реальном году |
| 4441190828 (INDICATOR) | +0.1023 BTC | +0.41 BTC/yr (если bull repeated) | INDICATOR на 1Y у тебя нет → unknown |

**Расхождение:**
- 3M annualized projection (+0.38..+0.41 BTC) **противоречит** реальному 1Y результату DEFAULT (−0.05..−0.06 BTC)
- Различие = 0.40+ BTC ≈ $32,000+ при цене 80k
- Причина: 3M-период был bull-recovery. 1Y-период включает февральский крах
- **Нельзя умножать 3M result на 4 для прогноза годовой доходности** — это структурно неверно для grid LONG

---

## §7 Что эти числа НЕ говорят

| Вопрос | Ответ |
|---|---|
| Будет ли live bot прибыльным | Зависит от того, повторится ли паттерн февральского провала. 1Y бычий с провалом → DEFAULT минус. Чистый бычий 3M → плюс |
| Какой config "оптимальный" | Между 4 3M-тестами разница 0.011 BTC (+12%) — мало. Не достаточно для optimization claim |
| Будет ли trail помогать в bear-window | Foundation gap. На 3M trail = 0 effect (не активировался). На 1Y trail OFF в обоих негатив тестах → не A/B |
| Реальная разница INDICATOR vs DEFAULT в 1Y | Foundation gap. У тебя только 3M INDICATOR test |
| Bear-window standalone result | Foundation gap. **Нет ни одного backtest на чисто-bear period** (даже 1Y test mixed). Февраль 2026 единственное bear-эпизод в твоих данных |

**Bear-window — критическая дырка.** Все твои 6 тестов содержат либо bull-recovery (3M), либо bull+crash+recovery (1Y). Чистого нисходящего тренда (например июнь-октябрь 2022, $30k → $20k) — нет в backtest'ах. Поведение этих params в sustained downtrend — **unknown**.

---

## §8 Что это значит для текущей позиции

| Факт | Значение |
|---|---|
| Live bot live since ~2026-05-06 16:48 UTC+3 | active менее суток |
| 3M backtest closest match | DEFAULT @ +0.095 за 3M (~$0.50k income/mo если повторится) |
| 1Y backtest closest match | DEFAULT @ −0.05 за 1Y (если повторится — net loss) |
| Какой scenario повторится — unknown | foundation не предсказывает |
| Что делает bot в твоей текущей ситуации | hedges downside drift через DCA fills; на росте — pre-loaded position просто sit |

Это **honest reading** твоих собственных backtests + моей foundation.

---

## §9 Audit trail

| Утверждение | Источник | Confidence |
|---|---|---|
| 6 backtest values | operator screenshots (4886978820, 6330583675, 5079319343, 4441190828, 5852654037, 6370367889) | source of truth |
| 3M test all positive | direct screenshot read | HIGH |
| 1Y tests all negative | direct screenshot read | HIGH |
| Feb 2026 crash in parquet (max $126k → min $63k) | computed from `data/forecast_features/full_features_1y.parquet` | HIGH |
| 3M annualized projection NOT extrapolable to 1Y | derived from §2 evidence | HIGH (structural) |
| INDICATOR vs DEFAULT +0.0069 BTC delta | direct math from screenshots | HIGH (n=1 vs n=1) |
| Trail ON = 0 effect on this period | direct comparison 4886978820 vs 6330583675 | HIGH (in this period only) |
| Step 0.04 ≈ +0.004 BTC vs 0.03 | derived (with trail caveat) | LOW (n=1, trail confounded) |
| Bear-window foundation gap | absence of evidence | HIGH (verified gap) |
| GinArea uses BTCUSD inverse mark, my parquet uses BTCUSDT linear close | comparing avg prices ($80k vs $73k in 3M, $101k vs $95k in 1Y) | MEDIUM (data source difference confirmed empirically) |

---

**Конец документа.** Шесть твоих backtest'ов нормализованы в одну таблицу. Главные выводы: (1) 3M-projection ×4 НЕ равно 1Y-result (structural difference); (2) bear-window foundation gap — все тесты на bull-skewed периодах; (3) разница между конфигами в 3M-тестах мала (0.0913–0.1023 BTC, range ~12%), это в пределах шума одного backtest'а.
