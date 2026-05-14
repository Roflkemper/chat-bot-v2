---
# Skill: calibration drift monitor

## For whom
Этот skill применяется ARCHITECT'ом (Claude) и Code-исполнителем
ВО ВРЕМЯ работы с любыми решениями зависящими от опубликованных
K-факторов (K_SHORT, K_LONG из MASTER §10) или их производных
(/advise сигналы, paper journal expected PnL, weekly comparison).

## Trigger
Любое из:
- TZ или conversation использует K_SHORT, K_LONG, K_FACTOR из MASTER §10
- Code считает expected_pnl, predicted_realized, или другую метрику
  выведенную из калибровочных констант
- Operator показывает live realized PnL за период и спрашивает
  "соответствует ли калибровке"
- Запуск /advise который полагается на K в формуле sizing/edge
- TZ-WEEKLY-COMPARISON-REPORT или любой post-mortem отчёт
  comparing live vs expected

## Rule
**Перед использованием опубликованного K-фактора в production-decision
проверить что K_drift вычислен и в пределах envelope:**

```
K_drift_pct = |K_live_window - K_published| / K_published * 100
```

- `K_drift_pct < 15%` → use K as-is
- `K_drift_pct ∈ [15%, 30%]` → use K, but flag "drift warning" в outputs
- `K_drift_pct > 30%` → STOP, не использовать K, открыть TZ-RECALIBRATE

K_live_window вычисляется из последнего operator_journal или 
state_snapshot слайда длиной ≥ 7 дней (минимум для statistical
significance) ≤ 30 дней (чтобы не мешать с устаревшими режимами).

## Mandatory steps BEFORE применения K в decision

1. Прочитать docs/STATE/STATE_CURRENT.md §3 CALIBRATION NUMBERS
   (текущий published K).

2. Прочитать `state/operator_journal/decisions.parquet` или 
   эквивалент за последние 7-30 дней. Для каждого SHORT/LONG cycle:
   `K_observed = ga_realized_in_window / sim_realized_in_window`
   (sim запускается на тех же данных через
   `services.calibration.runner` или `reconcile_v3`).

3. Aggregate K_observed → K_live (mean) + CV.

4. Вычислить K_drift_pct по формуле выше.

5. Apply rule (use / warn / stop).

## Forbidden
- Использовать K из MASTER §10 без drift check, если decision
  затрагивает live trading или reporting (paper journal, weekly).
- "Я думаю K стабильный, проверять не буду" без явного operator
  override.
- Считать K_observed на окне < 7 дней (statistical noise).
- Считать K_observed на окне > 60 дней (regime mixing).

## Allowed
- Skip drift check для:
  - Pure backtest research где K не используется в outputs
    (например, raw simulate_probe runs).
  - Calibration TZs которые сами вычисляют K (они и есть
    источник истины).
  - Operator явно сказал "use published K, не проверяй drift".

## Recovery
Если drift > 30% обнаружен:
- НЕ молча использовать K.
- Записать INC-ENTRY в INCIDENTS.md с window, K_live, K_published, drift.
- Открыть TZ-RECALIBRATE-K-{SIDE}-{date}.
- Operator решает: переключиться на K_live или дождаться recalibration.

Если drift в [15%, 30%]:
- Output decision MUST содержать строку:
  `⚠ K drift warning: K_published={value} vs K_live={value} ({drift_pct}%)`
- Operator видит и осознанно decides.

## Why
Из проектной истории: K_LONG показал TD-dependence (CV 24.9% на 
1-year window). Это не баг — это структурное свойство калибровки.
Но если живая торговля идёт в режиме где K_LONG drift > 30% от 
published, то /advise sizing формула overshoots/undershoots, и 
оператор получает ошибочные рекомендации.

PROJECT_CONTEXT §3 P-1 принцип "Защита > возможность" — лучше 
flag drift и подождать чем выдать confident-wrong decision.

Related skills: param_provenance_tracker (источник K), 
trader_first_filter (защита капитала от bugs).
