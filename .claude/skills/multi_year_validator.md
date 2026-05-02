---
# Skill: multi year validator

## For whom
Этот skill применяется ARCHITECT'ом и Code-исполнителем ПЕРЕД
выводом любого backtest-derived statement про expected edge,
expected PnL, or "stable performance".

## Trigger
Backtest result используется в operator-facing statement, и
один из истинно:
- backtest window < 2 years
- backtest covers только 1 market regime (e.g. only bull, only range)
- result published as "$X/year", "Y% APY", "stable across regimes"

## Rule
**Любое expected-PnL / edge claim MUST содержать явное regime
disclosure:**

```
window_years = (end - start).days / 365.25
n_regimes_covered = count of {bull, bear, range, high_vol, low_vol}
                    present in window per docs/regime classification

minimum_acceptable_for_publishable_edge:
  window_years ≥ 2.0 AND n_regimes_covered ≥ 3
```

Если backtest НЕ удовлетворяет:
- Result MUST быть помечен `EXPLORATORY — NOT FOR DEPLOYMENT`.
- Operator-facing report MUST включить блок "regime caveats" со
  списком регимов которые НЕ покрыты.

## Mandatory steps BEFORE публикации edge claim

1. Compute `window_years` из start/end timestamps backtest.

2. Classify regimes в window используя:
   - `services/regime_red_green/` если есть готовый classifier
   - Manual: rolling 30-day price change (bull >+15%, bear <-15%, range otherwise)
   - Plus volatility tier: realized vol percentile >75th = high_vol

3. Записать regime histogram (% времени в каждом).

4. Apply rule:
   - ≥ 2y AND ≥ 3 regimes → PUBLISHABLE
   - ≥ 1y AND 2 regimes → REVIEW NEEDED, mark "limited regime coverage"
   - < 1y OR 1 regime → EXPLORATORY only, никаких деплой recommendations

5. Document в report:
```
**Backtest scope:**
- Window: 2025-04-01..2026-04-30 (1.08 years)
- Regimes covered: bull (45%), range (40%), high_vol (10%), low_vol (5%)
- Bear regime: NOT in sample → result unreliable for bear conditions
```

## Forbidden
- Заявлять "$X/year" или "Y% APY" если backtest < 1 года, без
  EXPLORATORY tag.
- Использовать annualized return из < 6 месяцев данных в operator-facing
  output. Это шум.
- Publish "winning config" если backtest covered только текущий
  регим (например 2025 был mostly bull → strategy "wins" but не
  tested на 2022 bear).
- Игнорировать regime mix даже если total window ≥ 2y, если
  coverage skewed (95% bull, 5% range).

## Allowed
- Skip multi-year requirement для:
  - Pure mechanical validation (sim correctness check, не edge claim).
  - Live paper journal in Phase 1 (явно short-window by design).
  - Pre-existing K calibration на available frozen data (документировано
    как "1y baseline, multi-year extension pending").

## Recovery
Если published edge claim violates rule (обнаружено post-publish):
- Записать в INCIDENTS.md.
- Update report: добавить EXPLORATORY tag retroactively.
- Notify operator: "результат X отозван до multi-year re-run".
- Не блокировать research, но remove from MASTER §10 / OPPORTUNITY_MAP.

## Why
2025 was largely bull regime (BTC 60k → 78k+). Любой strategy
backtested ONLY на 2025 показывает "великолепный edge" просто
потому что longs выигрывают в bull. Это НЕ edge — это beta.

Из проектной истории:
- Coordinated grid: $37,769/year on 1-year sweep (2025-04..2026-04).
  Mostly bull regime. Не tested на 2022 bear (-65%) или 2018 bear
  (-80%). Если в Phase 2 deploy и наступит bear — стратегия может
  потерять годовые gains за месяц.
- K_LONG calibration: 6 GA backtests на одном году. Не известно
  как K себя ведёт когда BTC падает 6 месяцев подряд.

PROJECT_CONTEXT §3 "Цикл-смерти на затяжном тренде" — описывает
именно тот failure mode который multi-year validation вскрывает.

P-1 принцип "Защита > возможность" — лучше отметить EXPLORATORY
и подождать big-window data, чем deploy под bull regime overfit.

Related skills: trader_first_filter (а — risk-profile в реальной
торговле), survivorship_audit, lookahead_bias_guard.
