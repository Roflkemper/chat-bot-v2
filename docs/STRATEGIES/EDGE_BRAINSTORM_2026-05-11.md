# Edge Brainstorm — что мы упустили, что можно добавить

**Дата:** 2026-05-11
**Метод:** 3 параллельных Explore-агента + ручная верификация
**Контекст:** оператор просит "медленно и тщательно" найти упущенные edge-категории
для дополнения текущего стека (P-15, GinArea cascade, setup_detector, cascade_alert).

---

## Реальность текущего стека (live PnL)

Прежде чем добавлять новое — что **реально работает** и что **бьёт по карману**:

### Работает (positive expectancy live)
| Детектор | N | PnL | WR | Заметка |
|---|---:|---:|---:|---|
| **long_multi_divergence** | 47 | **+$4,386** | 100% | RSI+OBV дивергенция 1h — топ |
| **long_pdl_bounce** | 18 | +$1,570 | 100% | отбой от PDL |
| **long_double_bottom** | 6 | +$586 | 100% | редко но точно |
| **Cascade Alert** (n=103/102) | — | — | 61-73% | +0.46-1.14% за 12ч |
| **GinArea SHORT-каскад** TD 0.20/0.35/0.60 | 5,324 | +$10,156/yr | 67% | свежий V3-результат |

### Деградировало (live хуже backtest)
| Детектор | N | PnL | Проблема |
|---|---:|---:|---|
| **short_pdh_rejection** | 67 | −0.17%/trade | CI95 [-0.28, -0.05] весь в минусе. DISABLED |
| **short_rally_fade** | 58 | +0.19%/trade | На грани, недавние сделки −$286 |
| **short_mfi_multi_ga** | 9 | −0.32%/trade | overfit, 7/9 TIMEOUT |
| **P-15 LONG/SHORT** live | 282 | **−$926** | dd_cap 3% слишком жёстко в range |

### Мертвый код (никогда не fires)
- `long_rsi_momentum_ga` — 29 fires, 0 emit (combo_block 100%)
- `long_dump_reversal` — 1,463 fires, 0.2% emit (strength threshold 9 слишком высокий)

**Главный вывод:** P-15 в paper-trade убыточен (−$926), несмотря на backtest-PF 4.32.
Backtest предполагал нулевые slippage и идеальный timing reentry — live это не даёт.
**Не катить P-15 на реальные деньги ещё 1-2 недели**, пока не разберёмся с dd_cap.

---

## Какие данные у нас уже есть (свежие)

| Источник | Cadence | Свежесть | Используется? |
|---|---|---|---|
| OHLCV 1m/15m/1h BTC/ETH/XRP | 1m/15m/1h | live | да, везде |
| Liquidations 5 бирж | 100ms WS | live | cascade_alert (только Binance/Bybit активно) |
| OI per exchange (Binance+Bybit) | 5m | live | OIDeltaSignal |
| Funding rate 8h | 5m | live | FundingSignal |
| L/S ratios (global + top traders + Bybit) | 5m | live | feature pipeline, но **нет real-time детекторов** |
| Taker buy/sell % | 5m | live | computed, **no triggers** |
| Premium index (mark − index) | 5m | live | **не используется** |
| BTC.D + total mcap | 5m | live | **не используется вообще** |
| Cross-exchange OI (binance vs bybit) | 5m | live | данные есть, **edge нет** |
| **Orderbook L2 depth20** | 100ms WS | **STALE с 2026-05-03!** | сборщик не работает, edge невозможен пока не починим |
| **Trade ticks** | — | **не собирается** (A2 ошибся) | edge невозможен без сбора |
| ICT levels (PDH/PDL/PWH/PWL/Asia/London/NY) | precomputed | static | dist_to_* фичи + LEVEL_BREAK |
| RSI div / Pin bar 15m | precomputed | static | детекторы |

**Главное:** orderbook + ticks **не доступны** (сборщик стоит). Любой edge на их базе требует
сначала починить/написать collector. Funding/OI/LS/premium/BTC.D — всё свежее, готовое.

---

## 14 кандидатов на новый edge (ранжированы)

Критерии оценки:
- **Edge** — насколько ожидаемо принесёт деньги (subjective, на основе общих знаний рынка + что уже работает у нас)
- **Сложность** — H/M/L (high/medium/low, времени на реализацию)
- **Данные готовы?** — есть ли уже всё для бэктеста
- **Корреляция с текущим стеком** — не дублирует ли существующее

### 🟢 TIER A — высокий edge, данные есть, низкая сложность

#### #1. Funding rate extremes (+/− 0.05% / 8h)
- **Идея:** когда funding > +0.05% (лонги переплачивают шортам) или < −0.05% → mean revert в 12-24ч.
- **Edge:** известный, документированный академически. На BTC исторически WR 60-65%, EV ~0.5-1% / trade.
- **Данные:** `state/deriv_live_history.jsonl` — funding_rate_8h, history с глубиной. Готово.
- **Сложность:** L. Простой detector + бэктест на 1y.
- **Корреляция:** дополняет cascade_alert (одна сторона crowded + funding extreme = сильнее edge).
- **Почему упустили:** есть `FundingSignal` в feature pipeline, но **никто не fires на абсолютных экстремумах** — только в составе ML-фич.

#### #2. Long/Short ratio extreme reversal
- **Идея:** `global_ls_ratio > 1.5` (толпа в лонг) или `< 0.5` (толпа в шорт) → fade.
  Дополнительно: divergence `top_trader_ls_ratio` vs `global_ls_ratio` (умные деньги против толпы).
- **Edge:** классика sentiment. У нас есть редкий доступ к **top traders** отдельно — это редкий edge.
- **Данные:** есть в `deriv_live.json`, история в jsonl.
- **Сложность:** L.
- **Корреляция:** независим от технических детекторов.
- **Почему упустили:** A1 пишет "computed but no triggers" — фича посчитана, в детекторах не используется.

#### #3. Premium index mean-reversion (BitMEX vs spot)
- **Идея:** когда `premium_pct` (mark − index) уходит больше ±0.3% → mean revert в часы.
- **Edge:** структурный (арбитражный), статистически устойчив на топ-pairs.
- **Данные:** есть в `deriv_live.json` (premium_pct, текущее значение −0.0417%).
- **Сложность:** L.
- **Корреляция:** независим.
- **Почему упустили:** данные собираются, никем не читаются.

#### #4. Funding flip detector (smoking gun)
- **Идея:** переход funding с + на − (или наоборот) исторически предшествует разворотам.
- **Edge:** редкое событие, но точное. На BTC ~5-15 раз/год значимых flip-ов.
- **Данные:** `deriv_live_history.jsonl` глубина 8h funding rate.
- **Сложность:** L.
- **Корреляция:** ортогонален всему.
- **Почему упустили:** ни один из существующих advisor'ов не считает flip-events.

---

### 🟡 TIER B — средний edge, данные есть, средняя сложность

#### #5. Cross-exchange OI divergence
- **Идея:** OI на Binance растёт, на Bybit падает (или наоборот) → расхождение позиционирования.
- **Edge:** хедж-фонды/whales часто хеджируют между биржами — расхождение = signal.
- **Данные:** есть `total_oi_native`, отдельно Binance и Bybit.
- **Сложность:** M (нужны историч данные обеих бирж синхронно).
- **Корреляция:** низкая с текущим.
- **Почему упустили:** A2 says "computed in feature pipeline but not actively used".

#### #6. Multi-asset relative strength (XRP/ETH lead BTC)
- **Идея:** когда XRP/ETH движутся раньше BTC на X% → BTC последует. Уже частично — у нас есть `xrp_lead` сигнал в GC. Расширить: cross-asset spread > 2σ → catch-up trade на отстающем активе.
- **Edge:** документирован в крипте, особенно ETH lead.
- **Данные:** OHLCV всех трёх есть.
- **Сложность:** M.
- **Корреляция:** дополняет GC.
- **Почему упустили:** есть `xrp_lead` (один сигнал из 6), но НЕ как самостоятельный detector с трейд-логикой.

#### #7. Liquidation imbalance per exchange
- **Идея:** OKX/Hyperliquid ликвидации сейчас игнорируются (только Binance/Bybit). Дополнить cascade_alert этими 2-3 биржами — больше данных = меньше false negatives.
- **Edge:** улучшение существующего работающего edge.
- **Данные:** `liquidations.csv` уже содержит все 5 бирж.
- **Сложность:** L (просто включить в текущий код).
- **Корреляция:** усиливает cascade_alert.
- **Почему упустили:** код cascade_alert фильтрует по exchange, забыли расширить.

#### #8. Session breakouts (Asia/London/NY)
- **Идея:** пробой Asia high/low в первый час London = trade в направлении пробоя.
- **Edge:** один из самых документированных в FX, работает и в крипте.
- **Данные:** ICT levels уже содержат `asia_high`, `london_high`, `ny_am_high`, `session_active`. Готово.
- **Сложность:** M.
- **Корреляция:** ортогонален setup'ам.
- **Почему упустили:** ICT levels есть как **features**, но **нет setup-детектора** который бы триггерил на session-breakout.

#### #9. Volume z-score climax detector
- **Идея:** свеча с volume_z > 3σ + закрытие против движения = climax (capitulation/blow-off). Похоже на double_bottom, но проще и более универсально.
- **Edge:** mean-revert после vol-climax статистически устойчив.
- **Данные:** OHLCV volume у нас есть, z-score уже считается в feature pipeline.
- **Сложность:** L.
- **Корреляция:** перекликается с long_multi_divergence (часто совпадают), но не дубль.
- **Почему упустили:** есть `vol_z` фича, никто не триггерит.

---

### 🟠 TIER C — потенциально высокий edge, но требует инфраструктуры

#### #10. Volume Profile (POC/HVN/LVN) на 4h окне
- **Идея:** Point of Control / High-Volume Node / Low-Volume Node — один из самых мощных edge в институциональном трейдинге. Цена тянется к POC, отскакивает от HVN, проходит сквозь LVN.
- **Edge:** **очень высокий** на крипто-фьючерсах при наличии данных.
- **Данные:** нужны **тиковые сделки (trade ticks)**. **Сейчас НЕ собираются.**
- **Сложность:** **H** — надо написать WebSocket-collector trades с Binance, агрегатор volume per price level, состояние и backtest.
- **Корреляция:** ортогонален всему.
- **Почему упустили:** инфраструктурная сложность; без collector trades невозможно.
- **Action:** если решим заходить — сначала ТЗ на collector trades (2-3 дня), потом edge.

#### #11. Orderbook imbalance / large limit order detection
- **Идея:** bid/ask volume imbalance > 3:1 в top 5 levels = direction signal. Большие limit orders (whale walls) = support/resistance.
- **Edge:** работает в microframe (минуты).
- **Данные:** orderbook L2 **собирался до 2026-05-03 потом остановился**. Сборщик надо чинить.
- **Сложность:** H (починить collector + backtest).
- **Корреляция:** ортогонален.
- **Почему упустили:** collector умер 8 дней назад.

#### #12. BTC.D regime switcher
- **Идея:** когда BTC dominance растёт > X% за день → SHORT alts, LONG BTC (risk-off). И наоборот.
- **Edge:** макро-regime, медленнее но устойчивый.
- **Данные:** `btc_dominance_pct` есть в deriv_live, **но не используется**.
- **Сложность:** M (нужна история глубже текущего jsonl).
- **Корреляция:** влияет на portfolio allocation, не на одну сделку.
- **Почему упустили:** данные есть, никто не читает.

---

### 🔴 TIER D — низкий edge / сомнительный / overlap

#### #13. Open Interest delta + price divergence (Wyckoff-style)
- **Идея:** цена падает, OI растёт → накопление шортов → разворот вверх. Уже есть `OIDeltaSignal`.
- **Edge:** работает, но **уже частично используется**.
- **Action:** не новый edge, **доработка существующего**.

#### #14. Funding + OI confluence (уже у нас есть pre_cascade_alert)
- **Идея:** crowded + funding extreme = cascade incoming.
- **Status:** уже реализовано в `pre_cascade_alert/loop.py` (с 2026-05-10).
- **Action:** мониторим результаты, добавлять не нужно.

---

## Приоритизированный список действий

Если деньги/время ограничены, делал бы в таком порядке:

### Фаза 1 (1-2 недели, max edge per hour)
1. **#7 Liquidation imbalance per exchange** (1 день, усиливает рабочий edge)
2. **#1 Funding extremes detector** (1-2 дня, очевидный edge, простой code)
3. **#3 Premium index mean-reversion** (1 день, простой, ортогонален)
4. **#2 L/S ratio + top-trader divergence** (2-3 дня)
5. **#9 Volume z-score climax** (1-2 дня)

**Итого:** ~2 недели работы, 5 новых детекторов из готовых данных.

### Фаза 2 (1 месяц, средний effort)
6. **#4 Funding flip detector** (3-4 дня, нужна история глубокая)
7. **#8 Session breakouts** (3-5 дней, нужно ICT level update механизм)
8. **#6 Multi-asset relative strength** (1 неделя, корреляции + бэктест)
9. **#5 Cross-exchange OI divergence** (1 неделя)

### Фаза 3 (большая инфраструктура, делать только если фазы 1-2 принесут)
10. **#10 Volume Profile** — сначала trades collector (3-4 дня), потом POC/HVN (1 неделя), потом backtest
11. **#11 Orderbook imbalance** — сначала починить orderbook collector, потом edge
12. **#12 BTC.D regime** — требует архитектурного решения по portfolio allocation

---

## Что НЕ предлагаю и почему

**Не делаем (overlap / низкий edge):**
- ❌ Ещё одну вариацию RSI/MFI с разными порогами — overfit риск, у нас уже 21 детектор
- ❌ Новый divergence-detector в дополнение к long_multi_divergence — он и так лучший
- ❌ ML-модель для всех данных — слишком много параметров, риск переобучения
- ❌ Усложнение setup_detector pipeline новыми filter'ами — итак сложный

**Под вопросом:**
- ⚠️ P-16 post-impulse booster (в HYPOTHESES_BACKLOG) — может стоит протестить отдельно
- ⚠️ Восстановление orderbook collector — есть код, надо разобраться почему остановился

---

## Самое срочное — починить P-15

**Это не новый edge, но критическое.** P-15 paper-trade **−$926** за месяц, хотя backtest обещал
+$132k/2y. dd_cap 3% слишком агрессивен в range. Прежде чем катать в продакшен:
1. Бэктест с dd_cap 4-5% и менее агрессивным trend-gate
2. Сравнить layer-5+ harvest vs early-harvest
3. Учесть slippage явно

---

**Конец отчёта.**
