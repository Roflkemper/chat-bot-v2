# Корреляции сигналов детекторов — 2026-05-14

_Сгенерирован `scripts/audit_signal_correlations.py`. Источник: `state/pipeline_metrics.jsonl`._

- Всего событий в pipeline: **19462**
- Из них emitted (отправлены в TG): **344**
- Уникальных детекторов (по setup_type@pair): **50**
- Окно агрегации: **5 мин**
- Минимум срабатываний детектора для попадания в матрицу: **5**

## Что значат метрики

- **N(A∧B)** — в скольких 5-мин окнах сработали оба детектора
- **P(B|A)** — вероятность что B сработает если уже сработал A
- **Jaccard** = N(A∧B) / (N(A) + N(B) − N(A∧B)) — симметричная мера пересечения, от 0 до 1

## Интерпретация Jaccard

- **>0.5** — сигналы фактически дублируют друг друга, использовать как 1 источник
- **0.2–0.5** — сильно скоррелированы, в confluence-score веса должны быть снижены
- **0.05–0.2** — частичная корреляция, норма для родственных сетапов
- **<0.05** — независимы, можно складывать confluence напрямую

## Топ-30 пар по Jaccard (по убыванию схожести)

| # | Детектор A | Детектор B | N(A) | N(B) | N(A∧B) | P(B\|A) | P(A\|B) | Jaccard |
|---|------------|------------|------|------|--------|---------|---------|---------|
| 1 | `long_dump_reversal@TESTUSDT` | `long_pdl_bounce@TESTUSDT` | 6 | 6 | 6 | 1.00 | 1.00 | 1.000 |
| 2 | `grid_booster@XRPUSDT` | `long_dump_reversal@XRPUSDT` | 6 | 6 | 5 | 0.83 | 0.83 | 0.714 |
| 3 | `grid_booster@XRPUSDT` | `long_pdl_bounce@XRPUSDT` | 6 | 6 | 4 | 0.67 | 0.67 | 0.500 |
| 4 | `long_dump_reversal@XRPUSDT` | `long_pdl_bounce@XRPUSDT` | 6 | 6 | 4 | 0.67 | 0.67 | 0.500 |
| 5 | `long_dump_reversal@ETHUSDT` | `long_pdl_bounce@ETHUSDT` | 8 | 13 | 6 | 0.75 | 0.46 | 0.400 |
| 6 | `long_pdl_bounce@ETHUSDT` | `long_pdl_bounce@XRPUSDT` | 13 | 6 | 5 | 0.38 | 0.83 | 0.357 |
| 7 | `long_dump_reversal@XRPUSDT` | `long_pdl_bounce@BTCUSDT` | 6 | 10 | 4 | 0.67 | 0.40 | 0.333 |
| 8 | `long_pdl_bounce@BTCUSDT` | `long_pdl_bounce@XRPUSDT` | 10 | 6 | 4 | 0.40 | 0.67 | 0.333 |
| 9 | `grid_booster@XRPUSDT` | `long_dump_reversal@ETHUSDT` | 6 | 8 | 3 | 0.50 | 0.38 | 0.273 |
| 10 | `long_dump_reversal@ETHUSDT` | `long_dump_reversal@XRPUSDT` | 8 | 6 | 3 | 0.38 | 0.50 | 0.273 |
| 11 | `long_dump_reversal@ETHUSDT` | `long_pdl_bounce@XRPUSDT` | 8 | 6 | 3 | 0.38 | 0.50 | 0.273 |
| 12 | `grid_booster@XRPUSDT` | `long_pdl_bounce@ETHUSDT` | 6 | 13 | 4 | 0.67 | 0.31 | 0.267 |
| 13 | `long_dump_reversal@XRPUSDT` | `long_pdl_bounce@ETHUSDT` | 6 | 13 | 4 | 0.67 | 0.31 | 0.267 |
| 14 | `grid_booster@BTCUSDT` | `long_pdl_bounce@BTCUSDT` | 9 | 10 | 4 | 0.44 | 0.40 | 0.267 |
| 15 | `p15_long_harvest@BTCUSDT` | `p15_long_reentry@BTCUSDT` | 16 | 15 | 6 | 0.38 | 0.40 | 0.240 |
| 16 | `grid_booster@XRPUSDT` | `long_pdl_bounce@BTCUSDT` | 6 | 10 | 3 | 0.50 | 0.30 | 0.231 |
| 17 | `long_pdl_bounce@BTCUSDT` | `long_pdl_bounce@ETHUSDT` | 10 | 13 | 4 | 0.40 | 0.31 | 0.211 |
| 18 | `long_dump_reversal@ETHUSDT` | `long_pdl_bounce@BTCUSDT` | 8 | 10 | 3 | 0.38 | 0.30 | 0.200 |
| 19 | `p15_long_harvest@XRPUSDT` | `p15_long_reentry@XRPUSDT` | 23 | 23 | 7 | 0.30 | 0.30 | 0.179 |
| 20 | `long_dump_reversal@BTCUSDT` | `long_pdl_bounce@BTCUSDT` | 6 | 10 | 2 | 0.33 | 0.20 | 0.143 |
| 21 | `long_pdl_bounce@BTCUSDT` | `p15_short_harvest@ETHUSDT` | 10 | 8 | 2 | 0.20 | 0.25 | 0.125 |
| 22 | `p15_short_harvest@ETHUSDT` | `p15_short_open@ETHUSDT` | 8 | 15 | 2 | 0.25 | 0.13 | 0.095 |
| 23 | `long_dump_reversal@BTCUSDT` | `long_dump_reversal@XRPUSDT` | 6 | 6 | 1 | 0.17 | 0.17 | 0.091 |
| 24 | `long_multi_divergence@BTCUSDT` | `p15_long_close@XRPUSDT` | 9 | 17 | 2 | 0.22 | 0.12 | 0.083 |
| 25 | `long_dump_reversal@BTCUSDT` | `p15_short_reentry@ETHUSDT` | 6 | 7 | 1 | 0.17 | 0.14 | 0.083 |
| 26 | `grid_booster@ETHUSDT` | `long_dump_reversal@ETHUSDT` | 5 | 8 | 1 | 0.20 | 0.12 | 0.083 |
| 27 | `long_dump_reversal@ETHUSDT` | `short_double_top@BTCUSDT` | 8 | 5 | 1 | 0.12 | 0.20 | 0.083 |
| 28 | `long_dump_reversal@TESTUSDT` | `long_multi_divergence@XRPUSDT` | 6 | 7 | 1 | 0.17 | 0.14 | 0.083 |
| 29 | `long_multi_divergence@XRPUSDT` | `long_pdl_bounce@TESTUSDT` | 7 | 6 | 1 | 0.14 | 0.17 | 0.083 |
| 30 | `p15_short_harvest@ETHUSDT` | `short_mfi_multi_ga@BTCUSDT` | 8 | 6 | 1 | 0.12 | 0.17 | 0.077 |

## Топ-15 детекторов по числу срабатываний (за всю историю)

| Детектор | Срабатываний (emitted) |
|----------|------------------------|
| `p15_long_reentry@XRPUSDT` | 23 |
| `p15_long_harvest@XRPUSDT` | 23 |
| `p15_long_close@BTCUSDT` | 22 |
| `p15_long_open@BTCUSDT` | 19 |
| `p15_long_close@XRPUSDT` | 17 |
| `p15_long_harvest@BTCUSDT` | 16 |
| `p15_short_open@ETHUSDT` | 15 |
| `p15_long_reentry@BTCUSDT` | 15 |
| `long_pdl_bounce@ETHUSDT` | 13 |
| `p15_short_close@ETHUSDT` | 12 |
| `p15_long_open@XRPUSDT` | 11 |
| `short_double_top@ETHUSDT` | 11 |
| `long_pdl_bounce@BTCUSDT` | 10 |
| `long_double_bottom@XRPUSDT` | 9 |
| `long_multi_divergence@BTCUSDT` | 9 |

## Что делать с найденными корреляциями

1. **Пары с Jaccard >0.5** — задизайнить как один сигнал.
   - Либо явно слить в один setup_type
   - Либо в confluence_score не суммировать их веса (max() вместо +)

2. **Пары с Jaccard 0.2–0.5** — пересчитать веса в
   `services/setup_detector/confluence_score.py`. Сейчас, скорее всего,
   суммируются как независимые → завышенный confluence_pct.

3. **Пары между разными парами (BTC↔ETH↔XRP)** — это cross-asset
   confluence, обычно полезный сигнал. Не убирать.

## Перегенерация

```bash
python scripts/audit_signal_correlations.py
```