# TZ-TP-AUTOUPDATE-BACKTEST — инструкция запуска

**Создано:** 2026-05-09
**Приоритет:** ⭐ (operator's starred task)
**Скрипт:** `tools/_backtest_tp_autoupdate_vs_bag.py`

## Вопрос исследования

> TP+autoupdate (закрыл всю позу на +$TP, переоткрыл) более живуч **на объём при той же drawdown** чем grid-with-bag (накопление SHORT-позиций при росте, надежда на mean-revert)?

Это решает выбор режима для GinArea bot: текущий V1/V2 (grid+bag) vs предлагаемый TP-flat.

## Что считается

**Mode A — TP-flat (autoupdate)**:
- Открыл при gate (EMA50/EMA200 + close)
- Закрыл всю позу при +$TP — переоткрыл сразу или после пуллбэка K%
- Force-close при cum drawdown ≥ dd_cap

**Mode B — Grid-with-bag (текущий стиль)**:
- Открыл при gate
- При каждом неблагоприятном движении на K% добавляет $base в bag (averaging)
- Закрыл весь bag при суммарной нереализованной ≥ +$TP
- Force-close при cum drawdown ≥ dd_cap

## Параметры sweep

| Параметр | Значения |
|---|---|
| TP$ | 1, 2, 5, 10 |
| dd_cap% | 3, 5 |
| direction | short, long (BTC) |
| reentry (TP-flat) | immediate, wait_K_pct (K=0.3%) |
| ladder_K (grid) | 0.5%, 1.0% |

Итого: **2 × 4 × 2 × 2 = 32** TP-flat конфига + **2 × 4 × 2 × 2 = 32** grid-bag = **64 прогона**.

## Данные

`backtests/frozen/BTCUSDT_1m_2y.csv` (1.17M баров, 2024-04-25 → ~2026-04). Скрипт берёт **последние 7 дней** + 300 баров warmup для EMA200.

## Запуск

```bash
# Последние 7 дней (default)
python tools/_backtest_tp_autoupdate_vs_bag.py

# Сдвиг назад: --start-day 1 = пред. 7 дней, 2 = 7 дней до этого, и т.д.
python tools/_backtest_tp_autoupdate_vs_bag.py --start-day 1
```

Прогон занимает ~10-30 сек (64 конфига × 10080 баров).

## Output

1. **Console** — таблица всех 64 прогонов отсортированная по PnL, плюс:
   - Verdict block: best PnL / best efficiency (PnL/$volume bps) / worst maxDD per mode
   - Head-to-head: TP-flat vs grid-bag при одинаковых параметрах

2. **CSV** — `backtests/frozen/tp_autoupdate_vs_bag_2026-05-09.csv`

## Метрики

| Колонка | Что значит |
|---|---|
| `pnl_total` | Сумма PnL за 7 дней ($) |
| `max_dd` | Max equity drawdown (peak-to-trough на equity curve, $) |
| `peak_notional` | Самая большая позиция в моменте ($) — для bag показывает risk |
| `volume` | Сумма всех |position changes| ($) — proxy GinArea volume KPI |
| `pnl_per_volume_bps` | Эффективность: bps от объёма (PnL/Volume × 10000) |
| `n_tp` | Сколько раз закрылись по TP |
| `n_forced` | Сколько раз закрылись по dd_cap (плохой случай) |

## Acceptance criteria для миграции

Если **TP-flat выигрывает**:
- На большинстве конфигов TP/dd `pnl_total(TP-flat) > pnl_total(grid-bag)`, **И**
- `max_dd(TP-flat)` существенно меньше (≤50% от grid-bag), **И**
- `peak_notional(TP-flat)` намного меньше (без накопления bag)

→ **Решение:** мигрировать одного бота TEST_3 → 7-дневный dry-run с TP-flat параметрами.

Если **grid-bag выигрывает**:
- Либо PnL заметно выше, либо bps-эффективность лучше при сопоставимом DD

→ **Решение:** оставить как есть, но протестировать на других слайсах (--start-day 1..10) на устойчивость.

## Ограничения

- **Симуляция упрощена** — нет funding rate, нет slippage на крупных позициях, fee=5 bps taker. Реальный bot платит meaning рядом.
- **Gate простой** (EMA50/EMA200) — реальный GinArea triggered indicator-based, не EMA. Но edge-сравнение между режимами относительное → должно сохраниться.
- **7d sample может быть biased** — оператор хотел именно «последние 7 дней» для матча с live стат. Если результат intersting, повторить на --start-day 1..10 для устойчивости.

## Что делать после прогона

1. Скинь мне output (console + CSV) → я проанализирую head-to-head.
2. Если TP-flat выигрывает → готовлю миграцию TEST_3 (config + dry-run скрипт).
3. Если grid-bag выигрывает → закрываем гипотезу, переходим к TZ-SPIKE-DEFENSIVE-DETECTOR.
