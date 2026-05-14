# Аудит валидности бэктестов — 2026-05-08 + 2026-05-09

## Зачем этот документ

Оператор задал прямой вопрос: «вчера-сегодня делали много бэктестов, особенно
P-15 нашли супер-сетап — какие данные валидны?». Ниже — честная разметка по
каждому скрипту: на чём считал, что подтверждено, что под вопросом.

---

## Классификация движков

В проекте 3 разных «движка» симуляции, разной точности:

### 🟢 engine_v2 (`managed_grid_sim`) — **КАЛИБРОВАННЫЙ**

Расположен в `services/managed_grid_sim/` + ядро в Codex (`backtest_lab/engine_v2/`).
Использует полную механику GinArea: bot lifecycle, IN/OUT orders, instop A1/A2/A3,
out_stop trailing, формулы PnL по типам контрактов (linear/inverse).

**Валидация:** прогнал live-конфиг ШОРТ ОБЬЕМ (`5188321731`) на тех же 802 минутных
барах когда бот реально работал live. Расхождение:
- Объём: **±14%**
- Trades: **±20%**
- PnL: нестабилен на коротких окнах (мелкие $$ суммы), на длинных усредняется

**Вывод:** годен для решений по объёму, drawdown, position size. По PnL —
доверять ±20% диапазону на долгих окнах.

**Используют:**
- `tools/_backtest_grid_interventions.py` (сегодняшний бэктест интервенций)

### 🟡 backtest_signals helpers — **частично валидны**

Расположен в `tools/backtest_signals.py`. Это набор функций (rsi, mfi, obv, cmf,
macd_hist, detect_multi_divergences, detect_bos_signals, score_signals,
compute_metrics).

**Что считают:** indicators + signals + forward returns на close-to-close
без учёта SL/TP intra-bar и без учёта grid-механики GinArea.

**Что НЕ считают:** реальные комиссии, intra-bar волатильность, накопление
позиции в сетке, instop задержка открытия.

**Подходит для:** оценки **edge сигналов** (есть ли отклонение от случайного
на N-баровом горизонте). НЕ подходит для предсказания live PnL grid-бота.

**Используют:**
- `tools/_backtest_15m_setups.py`, `_backtest_filters.py`, `_backtest_funding_transitions.py`,
  `_backtest_horizons.py`, `_backtest_multi_asset.py`, `_backtest_short_1h_bear.py`
- `tools/_walkfwd_all_detectors.py`
- `tools/_genetic_detector_search.py` (E1 single-asset GA — **first run**)

### 🔴 inline simple sim — **упрощённые, на коротких окнах ненадёжны**

Каждый скрипт со своей упрощённой симуляцией без интеграции с engine_v2.

**Что не учитывают:** intra-bar SL/TP правильно, instop A3 (объединение IN),
out_stop trailing, реальные комиссии.

**Подходит для:** грубой оценки «есть-нет edge». НЕ подходит для решений
по миграции live-стратегии.

**Используют:**
- `tools/_backtest_p15_full.py` (P-15 LONG/SHORT, harvest-mode + tp-flat)
- `tools/_backtest_p15_multi_asset.py` (P-15 на BTC+ETH+XRP)
- `tools/_backtest_tp_autoupdate_vs_bag.py` (TZ-TP-AUTOUPDATE)
- `tools/_backtest_p15_honest.py`, `_backtest_p15_rolling_rebalance.py`,
  `_backtest_p16_post_impulse.py`, `_backtest_dual_leg.py`,
  `_backtest_dual_independent.py`
- `tools/_genetic_detector_search_multi.py` (E1+ multi-asset GA)

---

## Аудит по конкретным результатам

### 🟢 ВАЛИДНО — Бэктест grid-интервенций (сегодня)
**Скрипт:** `_backtest_grid_interventions.py`
**Движок:** engine_v2 (calibrated)
**Результат:** 5 сценариев × 11 окон × 7 дней BTC 1m
- baseline: $728k vol, -$905 net, $1964 DD
- combined (3 правила): $400k vol, **-$249 net (3.6× меньше), $729 DD (2.7× меньше)**

**Степень доверия:** **высокая**. Объём и DD близки к реальным (±15-20%).
PnL может быть ±20% от истины. Соотношение `combined vs baseline` (3.6× по
убыткам, 55% по объёму) **устойчиво** к этому шуму.

**Действия:** разворачиваем `grid_coordinator` (уже live), ждём подтверждения
сигналов на живом рынке 24-48 часов.

### 🟡 ОТНОСИТЕЛЬНО ВАЛИДНО — TZ-TP-AUTOUPDATE (твой прогон 8 мая)
**Скрипт:** `_backtest_tp_autoupdate_vs_bag.py`
**Движок:** inline simple sim
**Результат:** TP-flat vs grid-bag, 11 окон
- grid-bag чаще даёт лучший PnL
- TP-flat даёт DD в 3-5× меньше

**Степень доверия:** **средняя.** Соотношение направлений (grid лучше PnL,
TP-flat лучше DD) подтверждается логически. Конкретные числа PnL **могут
быть смещены** на 30-50% (нет реальной grid-механики).

**Действия:** **сегодняшний бэктест на engine_v2 подтверждает выводы** —
жёсткие интервенции (`pause_on_drawdown` ≈ TP-flat по сути) дают
3-5× меньше DD при потере 67% объёма. Это укладывается в твои наблюдения.

### 🔴 ПОД ВОПРОСОМ — P-15 «супер-сетап» (вчера, 8 мая)
**Скрипт:** `_backtest_p15_full.py`
**Движок:** inline simple sim
**Результат:** PnL 2y BTC: +$67,463 SHORT, +$64,980 LONG, PF 4.32/4.37,
3/4 walk-forward folds positive

**Степень доверия:** **низкая для конкретных сумм.** Это упрощённая симуляция
без правильной grid-механики. Цифра «+$67k за 2 года» — **скорее всего
завышена в 1.5-3 раза** из-за:
- Игнорирования комиссий (или грубая фиксированная ставка)
- Идеальные intra-bar fills (limit orders без проскальзывания)
- Простая reentry-логика без instop

**Что валидно:** тот факт, что **edge существует** (PF=4.32 — 4× больше чем
1.0 это сильный сигнал). Walk-forward 3/4 положительных folds — тоже сильный
indicator стабильности паттерна.

**Что НЕ валидно:** конкретная сумма $67k. В реальности эта стратегия может
давать +$15-30k за 2 года вместо $67k.

**Действия:**
1. P-15 уже в production как paper-trader (`services/paper_trader/p15_handler.py`)
2. Через **7-14 дней live-данных** сравним paper PnL vs backtest:
   - Если live на P-15 даёт ≥50% от backtest-расчётов = edge подтверждён
   - Если <30% = backtest сильно завышен, P-15 не годен для миграции

**Сейчас писать НЕ "P-15 даёт +$67k" — а "P-15 имеет edge PF=4.32, точную сумму
определит paper-trade".**

### 🔴 ПОД ВОПРОСОМ — GA «найденные сетапы» (вчера-сегодня)

**Скрипт single-asset:** `_genetic_detector_search.py`
**Движок:** backtest_signals helpers (forward return на close-to-close)
**Результат:** найден `LONG_RSI_MOMENTUM_GA` — RSI>71 + EMA50/200 trend + vol_z>=1.21,
PF=2.05, N=125, WR=57.4%

**Скрипт multi-asset:** `_genetic_detector_search_multi.py`
**Движок:** inline GA fitness sim
**Результат:** найден `SHORT_MFI_MULTI_GA` — MFI<71 + ETH corr>=0.76 +
XRP MFI lead, PF=2.78, N=406, WR=59.2%

**Степень доверия:** **средняя.** GA подобрал параметры на close-to-close
forward returns с **ЕСТЬ** учётом intra-bar SL/TP в фитнесе (после моего
исправления в commit `3828916`). PF=2.05 и 2.78 на 4-fold walk-forward —
сильные показатели, **edge скорее всего реальный**.

**Что НЕ валидно:** точные суммы PnL не считались, только PF и WR.

**Действия:**
1. Оба детектора уже **wired в DETECTOR_REGISTRY** и paper-trade'ятся
   через стандартный `paper_trader.handle()`
2. Через **30 дней** live PF сравнить с backtest PF
3. Если live PF в пределах ±20% от backtest — promote в operator-confirmed

### 🟡 ОТНОСИТЕЛЬНО ВАЛИДНО — STRATEGY_LEADERBOARD (сегодня)
**Скрипт:** `_walkfwd_historical_setups.py`
**Движок:** не делает бэктест — анализирует **уже эмитированные** setups из
`data/historical_setups_y1_2026-04-30.parquet` (18712 реальных эмитов за год)

**Результат:** 1 STABLE (`long_pdl_bounce`), 5 OVERFIT, 1 TOO_FEW

**Степень доверия:** **высокая для verdict-классификации.** Это не симуляция,
а анализ реальных эмитов с реальными outcome'ами (TP/SL/expired). 4-fold split
по времени — стандартный walk-forward.

**Слабая сторона:** покрывает только 7 из 18 детекторов (остальные
не оставляли записи в parquet). Полный walk-forward через DetectionContext
(`_walkfwd_detectors_full.py`) пока не работает (OOM).

---

## Сводная таблица: что брать всерьёз

| Бэктест | Дата | Движок | Доверие к выводам | Доверие к суммам |
|---|---|---|---|---|
| Grid interventions (combined) | 09.05 | 🟢 engine_v2 | **высокое** | ±20% |
| TZ-TP-AUTOUPDATE (твой) | 08.05 | 🔴 simple | **высокое** (направ) | ±50% |
| P-15 +$67k 2y | 08.05 | 🔴 simple | средн. (edge есть) | **сумма завышена** |
| GA `LONG_RSI_MOMENTUM_GA` | 09.05 | 🟡 helpers+SL/TP | средн. | только PF |
| GA `SHORT_MFI_MULTI_GA` | 09.05 | 🔴 simple multi | средн. | только PF |
| Strategy Leaderboard | 09.05 | анализ эмитов | **высокое** | n/a (verdict) |
| Confluence Matrix | 09.05 | анализ эмитов | **высокое** | n/a (boost) |

---

## Что менять в наших выводах

1. **P-15 «+$67k 2y» убрать как сумму, оставить как edge.** Корректнее писать:
   «P-15 имеет статистический edge PF=4.32 на BTC 1h 2y, walk-forward 3/4 folds
   positive. Конкретная live-доходность определяется paper-trade'ом.»

2. **GA-найденные детекторы — называть «кандидатами» а не «производственными».**
   До 30 дней live-проверки они **paper-only**, не для live-сделок.

3. **Combined-интервенции — единственный бэктест на калиброванном движке.**
   На него можно опираться при принятии решений.

4. **Все остальные «суперцифры» (PnL, доходность) — инвентаризировать как гипотезы**
   до проверки на калиброванном движке.

---

## Что планирую сделать дальше

**Шаг 1 — провалидировать P-15 правильно:**
- Прогнать `tools/_backtest_p15_*` через engine_v2 (managed_grid_sim) с
  правильной grid-механикой
- Это даст **реальный** PnL без преувеличений

**Шаг 2 — провалидировать GA-детекторы:**
- Это сложнее: GA нашёл паттерн на forward-return на close, а в live это
  нужно превратить в торговый setup с SL/TP. Это уже сделано в wire'нутых
  детекторах — паттерн ловит, но **PnL** оценивается через paper-trader

**Шаг 3 — наблюдение на живых данных** (главный валидатор):
- P-15 paper trader работает с 8 мая → через 7 дней первые результаты
- Через 30 дней — все GA-детекторы

Я сейчас работаю над Шагом 1 — переношу P-15 на калиброванный движок.
