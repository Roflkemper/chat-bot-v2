# P-15 Live vs Backtest — диагноз 2026-05-11

## Проблема

Live paper P-15 за месяц: **−$926** в минусе.
Backtest HONEST V2 на 2y BTC 1m: **+$24,868** за SHORT, **+$22,130** за LONG (4/4 фолда позитивные).

Гипотеза изначально была: dd_cap=3% слишком агрессивен.
Sweep по dd_cap (2.0-6.0%) × slippage × gate (84 комбо) — **гипотеза опровергнута**:
все 84 комбо позитивные, dd_cap влияет на PnL менее чем на 5%.

## Реальный диагноз

Из live trades `state/p15_paper_trades.jsonl` за 2026-05-11:

```
17:18 BTCUSDT LONG layer 2 REENTRY @ $82,569 (avg $82,260)
…7 harvests + reentries…
19:44 BTCUSDT LONG layer 6 CLOSE @ $82,023 avg $84,464 — dd_cap → −$56
```

**Паттерн всех CLOSE-событий:**
1. Open layer 1 на текущей цене
2. Harvest по retrace +0.3% → reentry K=1% выше exit
3. Цена пошла вниз → следующий harvest → reentry **ещё выше** на 1%
4. К layer 6-7 avg_entry оказывается **+3-4% выше** entry layer 1
5. Любая просадка → cum_dd 3% → forced close с большим minus'ом

**Это не баг dd_cap. Это анти-edge reentry-логики:**
бот **догоняет** максимумы (для LONG) или минимумы (для SHORT), наращивая
позицию против тренда после первого harvest. После 6 reentries avg_entry
оказывается там где **никогда** не было до этого — на пике волатильности.

## Почему backtest этого не видит

Мой sweep использует `df.resample("1h")` — на 1h данных:
- Внутри-часовых retrace 0.3% (R) почти не видно (1h bar gross свинг 0.5-2%)
- Reentry K=1% поднимает порог следующего harvest на следующий час
- Условия редко совпадают → reentries практически не происходят
- Получается ОДИН большой trade на trend, а не grid-набор

Live: P-15 работает **на 15m данных** (см. setup_detector/p15_rolling.py),
ретрейсменты 0.3% случаются часто, reentries накапливаются.

## Что делать

Bekstest нужно гонять **на 15m или 1m данных**, чтобы воспроизвести live логику.
Только тогда увидим что `K=1.0%` слишком жёсткий offset reentry в среднем.

Гипотезы для следующего sweep:
1. Уменьшить **K** (например 0.5%) — reentry ближе к exit
2. Ограничить **n_reentries** (например 3 вместо 10)
3. Reentry **только при подтверждении trend continuation** (новый extreme)
4. Изменить **harvest size** (например 30% вместо 50%)
5. Отказаться от reentry вообще, использовать тренд как трэйлинг trail-stop

## Action

- Этот отчёт = root cause analysis. **dd_cap не виноват.**
- Нужен новый sweep на 15m данных с фокусом на K, n_reentries и harvest_size.
- **До этого момента** — НЕ катать P-15 на реальные деньги.
- В live можно временно повысить dd_cap до 5% — позиции будут жить дольше,
  но это **не вылечит проблему**, только отсрочит close.

## Файлы

- Sweep dd_cap: [P15_DD_CAP_SWEEP.md](./P15_DD_CAP_SWEEP.md)
- Roadmap: [EDGE_ROADMAP_2026-05-11.md](./EDGE_ROADMAP_2026-05-11.md)
- Live trades: `state/p15_paper_trades.jsonl`
