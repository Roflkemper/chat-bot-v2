# A1 — Final verdict on detectors honest backtest

**Дата:** 2026-05-10
**Engine:** intra-bar SL/TP simulator (1m data, calibrated)
**Fees:** maker -0.0125% IN + taker 0.075% OUT + 0.02% slippage = ~0.165% round-trip
**Period:** 815 days, 1,174,306 bars (2024-02 → 2026-05)
**Folds:** 4 walk-forward × ~204 days

## Сводка: 0 из 14 рабочих

| # | Detector | Trades | Avg PF | Pos folds | Total PnL | Verdict |
|---|---|---:|---:|:---:|---:|:---:|
| 1 | `long_rsi_momentum_ga` | 872 | 1.03 | 0/4 | +$128 | ❌ OVERFIT (random luck) |
| 2 | `long_pdl_bounce` | 1,178 | 1.05 | 0/4 | +$12 | ❌ OVERFIT |
| 3 | `long_div_bos_confirmed` | 204 | 1.05 | 1/4 | -$3 | ❌ OVERFIT |
| 4 | `short_mfi_multi_ga` | 52 | 1.35 | 0/4 | -$62 | ❌ OVERFIT |
| 5 | `long_div_bos_15m` | 223 | 0.86 | 1/4 | -$175 | ❌ OVERFIT |
| 6 | `short_div_bos_15m` | 167 | 0.70 | 1/4 | -$250 | ❌ OVERFIT |
| 7 | `long_oversold_reclaim` | 99 | 0.30 | 0/4 | -$326 | ❌ OVERFIT |
| 8 | `short_overbought_fade` | 216 | 0.47 | 0/4 | -$410 | ❌ OVERFIT |
| 9 | `short_pdh_rejection` | 1,687 | 0.90 | 0/4 | -$648 | ❌ OVERFIT |
| 10 | `double_top_setup` | 6,244 | 0.74 | 0/4 | -$5,034 | ❌ OVERFIT |
| 11 | `long_dump_reversal` | 6,704 | 0.70 | 0/4 | -$6,392 | ❌ OVERFIT |
| 12 | `double_bottom_setup` | 6,976 | 0.66 | 0/4 | -$7,321 | ❌ OVERFIT |
| 13 | `short_rally_fade` | 8,469 | 0.64 | 0/4 | -$8,431 | ❌ OVERFIT |
| 14 | `long_multi_divergence` | 11,372 | 0.68 | 0/4 | -$12,371 | ❌ OVERFIT |

**Cumulative PnL:** −$41,283 на 815 днях (−$50.6/день).

## Что это значит

Все 14 детекторов **заточены под historical patterns которых больше нет**, либо
изначально были random fits на in-sample. Walk-forward режет любую "удачу" на
части данных где фит не пересекается с реальным распределением.

### Структурные баги (вероятно те же что в grid_coordinator)

1. **Пороги 2021-эры** — RSI 75/25, funding 0.04%/8h. Реальные 2026 значения в
   2-8× ниже. Сегодня нашли это в grid_coordinator (commit 495b7ab) — после
   калибровки 2 → 78 сигналов/28д с precision 70%+.

2. **Логика "no confirm volume"** — на разворотах объём растёт, не падает.
   Тоже сегодня починили в grid_coordinator (`volume_no_confirm` →
   `volume_spike_at_extreme`).

3. **OI/funding профиль перевёрнут** — `oi_rising + funding_high`
   описывает open positions, не exhaustion. Аналогичные грабли и в детекторах.

## Рекомендация

**НЕ деплоить ни один из этих детекторов в paper/live**. Текущая библиотека
неприменима как есть.

Два пути:

**Путь A (быстрый, 1-2 недели):** Применить найденные сегодня калибровочные
правила (snizit thresholds 2-3×, починить inverted volume/OI logic) к 3-4
самым многообещающим детекторам (`long_rsi_momentum_ga`, `long_pdl_bounce`,
`short_pdh_rejection` — самые активные с PF около 1.0). Прогнать walk-forward
заново.

**Путь B (долгий, 1+ месяц):** Списать эту библиотеку как unsalvageable,
сосредоточиться на grid_coordinator-подобных индикаторах с откалиброванной
логикой. Использовать GA для оптимизации новых сигналов с защитой от overfit
через 4-fold WF.

## Связанная работа

- Калибровка grid_coordinator: commit `495b7ab` (RSI 75→65, OI 1.0→0.3, structural fix)
- Источник детекторов: `src/strategy/detectors/` (14 файлов)
- Raw runs: `state/detectors_honest_runs.csv`
- Backtest engine: `tools/_backtest_detectors_honest.py`
