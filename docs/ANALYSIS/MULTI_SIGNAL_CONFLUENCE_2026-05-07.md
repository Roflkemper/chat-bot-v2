# Multi-Signal Confluence Backtest — гипотеза не подтверждена

**Дата**: 2026-05-07
**Метод**: 8761 1h-точек (год: 2025-05-01 → 2026-05-01), 6 сигналов, проверка outcome 4h forward.
**Скрипт**: `scripts/backtest_multi_signal_confluence.py`
**Raw**: `state/multi_signal_confluence_test.json`

---

## Гипотеза

Утренние backtest'ы показали что одиночные сигналы (regime, OI, funding отдельно) дают **30-35% accuracy** — хуже монетки. Гипотеза была: **комбинация 3+ согласованных сигналов** должна дать **60%+** edge — это и был бы наш реальный direction-edge.

## Сигналы (каждый голосует long/short/neutral)

1. **regime_4h**: BULL (STRONG/SLOW/DRIFT_UP) → long, BEAR → short
2. **OI direction**: oi_delta_1h > +0.5% → long, < -0.5% → short
3. **Funding extreme**: z > 1.5 → short (crowd long), z < -1.5 → long (squeeze potential)
4. **OI/price divergence**: oi_div_z < -1.5 → long (squeeze), > 1.5 → short (distribution)
5. **Taker imbalance 1h**: > 0.55 → long, < 0.45 → short
6. **PDH/PDL break**: dist < 0.1% → long (PDH) / short (PDL)

`confluence_score = long_votes - short_votes` (диапазон -6..+6)

## Результат

| Score | Direction | n | mean move 4h | pct_up | strong_up (>0.3%) | strong_down (<-0.3%) |
|---|---|---|---|---|---|---|
| -4 | strong SHORT | 51 | -0.14% | 43% | 41% | **41%** |
| -3 | SHORT | 547 | -0.01% | 51% | 33% | 33% |
| -2 | weak SHORT | 2278 | -0.05% | 50% | 30% | 32% |
| -1 | weak SHORT | 2447 | +0.02% | 52% | 32% | 28% |
| **0** | **NEUTRAL** | **2401** | **0.00%** | 48% | 28% | 28% |
| +1 | weak LONG | 753 | +0.05% | 50% | 29% | 24% |
| +2 | LONG | 236 | -0.03% | 49% | 22% | 24% |
| +3 | strong LONG | 42 | +0.04% | **38%** | 24% | 24% |

## Ключевые выводы

### 1. Confluence НЕ улучшает direction-edge

Все confluence_scores дают примерно **30-33% accuracy** на strong move (>0.3% за 4h). Это **baseline случайности**: ~30% случаев цена делает >+0.3%, ~30% < -0.3%, ~40% болтается в боковике 0.3%.

### 2. Score +3 (strong LONG signal) даёт 38% pct_up — ХУЖЕ нейтрального

Это самое поразительное открытие: когда **5-6 сигналов** говорят LONG, цена в 62% случаев **не идёт вверх** на 4h. Это **anti-edge**, но n=42 малая выборка — возможно случайность.

### 3. Score -4 даёт 41/41% strong_up vs strong_down — паритет

Когда сильное SHORT-confluence — мощность вверх и вниз **одинаковая**. Цена movement становится более **волатильной**, но не направленной.

### 4. Distribution heavily centred around score 0

Подавляющее большинство (5828 из 8761 = **66%**) имеют `confluence_score ∈ [-1, +1]` — то есть signals **противоречат друг другу**, чистый signal редок.

## Интерпретация — почему confluence не работает

1. **Сигналы НЕ независимы**: regime_4h и OI часто коррелируют. Получаем "ghost confluence" — кажется что 3 сигнала, но это один общий market state.

2. **4h форвард слишком короткий**: возможно эти сигналы предсказывают direction на **24h+** окне. Текущий backtest дал inverted_verdict 24h тоже без edge — это вероятно тоже не сработает.

3. **Mean reversion + trend mix**: рынок 2025-2026 (наш период) был mostly bull market с короткими резкими откатами. На таком ландшафте signals "fader" и "trender" часто противоречат и в среднем cancel.

4. **Cost model**: даже если бы edge был 35% strong_up vs 30% baseline = 5% advantage, после комиссии 0.07% × 2 = 0.14% и slippage 0.05% — это **0.19%** заберёт значимую часть expected value.

## Что это значит для проекта

- **Direction-prediction edge не найден** ни одним путём за сегодня (regime, inverted, cross-asset, multi-signal confluence)
- **Не строить advisor v3 как "predict direction"** — фундаментально не работает
- **Реальный edge — non-directional**: RANGE/RANGE 57%, currency hedge ratio (Edge #1 в MASTER §16.8), active management поверх grid
- **Continuation hypothesis**: возможно edge есть на **сильно нестандартных** конфигурациях (после major liquidation cascade, крайнее funding, после макро-events) — но это требует **selection** не "all bars"

## Что попробовать вместо

### Hypothesis: post-liquidation-cascade pattern

Гипотеза: после **крупного liquidation event** (>0.5 BTC long-liq за 5 мин) рынок имеет direction-bias на 4-12h. Это **selection** на рідкі моменты, а не all-bars.

n будет **маленький** (~50-100 событий за год), но если accuracy 60%+ — это **edge**.

Я могу прогнать этот backtest за ~30 мин когда будет команда. Скрипт легко адаптируется.

### Hypothesis: extreme funding flip

После того как funding flip от extreme positive к extreme negative (или наоборот) **в течение 8h** — direction может быть предсказуем.

n тоже малый, но **selection logic правильная** для edge discovery.

---

## Связанные документы

- [BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md](BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md)
- [INVERTED_VERDICT_TEST_2026-05-07.md](INVERTED_VERDICT_TEST_2026-05-07.md)
- [CROSS_ASSET_FINDINGS_2026-05-07.md](CROSS_ASSET_FINDINGS_2026-05-07.md)
