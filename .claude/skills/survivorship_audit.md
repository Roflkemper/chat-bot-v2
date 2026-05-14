---
# Skill: survivorship audit

## For whom
Этот skill применяется ARCHITECT'ом и Code-исполнителем ПЕРЕД
публикацией любого результата вида "best config", "winning
parameter set", "X% improvement vs baseline", "$Y/year edge"
основанного на backtest sweep.

## Trigger
TZ или output содержит фразы:
- "best config", "winning combination", "top params"
- "$X/year", "+Y% vs baseline", "Z% win rate"
- "оптимальные параметры", "лучшая комбинация"
- Grid search / sweep результат с ranking by PnL
- Любой "champion" config выбранный среди ≥10 вариантов

И этот результат предлагается:
- В operator-facing report (МАСTER, OPPORTUNITY_MAP, PLAYBOOK)
- В live deployment recommendation (Phase 2/3)
- В обновлении калибровочных констант MASTER §10

## Rule
**"Champion" config из sweep MUST пройти out-of-sample (OOS)
validation на ≥ 30% длины in-sample window прежде чем
publishable как actual edge:**

```
in_sample_window: backtest period used for sweep
oos_window:      separate, non-overlapping period ≥ 30% of in_sample length
oos_pnl:         champion config performance on oos window
oos_pass:        oos_pnl > 0 AND oos_sharpe ≥ 0.5 × in_sample_sharpe
```

Если `oos_pass=False` → champion config = "in-sample artifact",
не publishable, отчёт MUST явно отметить survivorship risk.

## Mandatory steps BEFORE публикации champion result

1. Identify in-sample window (period of backtest sweep).

2. Allocate OOS window: BEFORE in-sample (preferred — no future
   leak risk) OR AFTER in-sample (acceptable если последовательно
   соблюдается). Length ≥ 30% of in-sample.

3. Re-run champion config (and TOP-3 alternatives) on OOS window
   without re-tuning.

4. Compare:
   - OOS PnL > 0?
   - OOS Sharpe ≥ 50% in-sample Sharpe?
   - OOS rank в TOP-3 sweep сохраняется?

5. Document в report (or refuse to publish):
   - "OOS validation: PASS — champion robust"
   - "OOS validation: FAIL — config likely overfitted, not 
     publishable as edge"
   - "OOS skipped — operator override (reason: ...)"

## Forbidden
- Публиковать "best config" без OOS validation в operator-facing
  document.
- Использовать full available data для sweep AND для validation
  (что эквивалентно отсутствию OOS).
- Пере-тюнить config после OOS fail и заявить "ну вот теперь робастный".
  Это p-hacking. После OOS fail — ROLL BACK к honest reporting.
- Sweep с >100 combinations без bonferroni / multiple-testing
  adjustment.

## Allowed
- Skip OOS для:
  - Pure exploratory research где результат явно помечен "EXPLORATORY,
    not for deployment".
  - Reproducing existing published result (operator уже видел OOS).
  - Single-config validation (без sweep — нечему overfit).

## Recovery
Если champion config FAIL OOS validation:
- НЕ публиковать как edge.
- Записать в INCIDENTS.md если уже было передано operator'у.
- Открыть TZ-RESEARCH-EXPLAIN-OOS-DRIFT для понимания почему
  in-sample дал false signal (regime mismatch? overfitted?).
- Не запускать в Phase 2/3 deployment.

## Why
Coordinated grid search дал $37,769/year (2025-04..2026-04 in-sample,
20 configs). Это TOP-1 из 20 вариантов на ОДНОМ годе данных. По
multiple-testing статистике, при 20 configs шанс что top-1 = pure
luck = ~1 - (1-α)^20 для null hypothesis "no edge". Без OOS не
отличить edge от шума.

PROJECT_CONTEXT §9 trader-first filter (б): "тестирование hypothesis
на real data". Hypothesis "$37k/year edge" не tested на real data
если на ней же и был tuned.

Без OOS дисциплины:
- Phase 2 рекомендации основаны на overfit.
- Operator теряет реальные деньги когда in-sample regime ends.
- /advise сигналы доверяются ложно.

Related skills: trader_first_filter (б), result_sanity_check,
multi_year_validator.
