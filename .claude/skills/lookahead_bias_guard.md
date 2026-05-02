---
# Skill: lookahead bias guard

## For whom
Этот skill применяется ARCHITECT'ом ПЕРЕД нарезанием любого
backtest/sim/reconcile TZ, и Code-исполнителем ПЕРЕД commit
backtest result, как self-review checklist.

## Trigger
Любое из:
- TZ упоминает "backtest", "sim", "reconcile", "replay", "simulate"
- Code пишет/изменяет любой файл из:
  - `services/calibration/sim.py`, `reconcile_v3.py`
  - `services/coordinated_grid/simulator.py`
  - `services/setup_backtest/replay_engine.py`, `outcome_simulator.py`
  - `services/h10_grid.py`, `scripts/backtest_h10.py`
  - `services/managed_grid_sim/managed_runner.py`, `sweep_engine.py`
  - `src/whatif/*` simulation modules
- Сам код использует timestamp как фильтр на DataFrame
- Computation expected_pnl использует данные за период

## Rule
**Backtest computation на момент времени T MUST использовать ТОЛЬКО
данные с timestamp ≤ T (или `< T` где applicable):**

```
LEAK = computation_at_T uses any data with ts > T
NO_LEAK_INVARIANT = ∀ T in backtest, ∀ row in input:
                    if row.ts > T: row NOT used in decision_at_T
```

## Mandatory checklist BEFORE commit

Для каждого нового/изменённого backtest module пройти 6 пунктов:

### 1. Slice operations
Проверить что слайсы dataframe ВСЕГДА bounded by current timestamp:
- ✅ `df.loc[:current_ts]`, `df[df.index < current_ts]`
- ✅ `df.loc[current_ts - lookback : current_ts]`
- ❌ `df.tail(N)` где N не привязан к current_ts (берёт хвост = future)
- ❌ `df.sort_values(...).head(N)` — risk if sort is not chronological
- ❌ `df["target_col"].max()` без фильтра по ts

### 2. Indicator / feature computation
- Rolling windows должны заканчиваться НА current_ts, не "centered around":
  - ✅ `df['close'].rolling(20).mean().iloc[ts_idx]`
  - ❌ `df['close'].rolling(20, center=True).mean()` (uses 10 bars after)
- Resample / aggregation с label="right" closed="right" если bar at T
  завершился ровно в T (knowable). label="left" если bar at T только
  STARTS в T (future close still unknown).

### 3. TP / SL / Exit calculation
- Exit price MUST be derived from bar boundaries that bot could observe
  in real time:
  - ✅ Bar high/low touched within bar duration → exit at TP/SL within
    bar (assuming bot reacts ≤ 1 tick latency).
  - ❌ Exit at "next bar's open" if next bar's data wasn't available
    at decision time.
  - ❌ Exit at bar's mid-price (operator can't reliably trade midpoint).

### 4. Setup / signal detection
- Detector MUST be called with cutoff `< current_ts`:
  - ✅ `detect_setup(ts, df.loc[df.index < ts])`
  - ❌ `detect_setup(ts, df)` — detector sees full history
- Pattern matching на closed bars only — current bar still forming
  if used in live, treat as `null` until close.

### 5. Calibration constants (K, threshold, params)
- Constants used in backtest at T MUST come from EARLIER calibration:
  - ✅ K_LONG calibrated 2025-04-01, applied to backtest 2025-04-01..2026
  - ❌ K_LONG calibrated 2026-04-30 on full year, then applied "to verify"
    on the same year — circular.

### 6. Test data isolation
- Test in tests/* MUST NOT touch live `state/*.json`.
- Frozen baselines в `state/baseline/*.json` MUST NOT be regenerated
  from current state (would inject future data).

## Forbidden
- "Я уверен что нет утечки" без прохождения 6-пункт checklist.
- Использовать pandas `.loc[]` без проверки что upper bound = current_ts.
- Заявлять "backtest показал X" без указания которое именно окно
  использовалось для калибровки vs которое для validation.
- Считать sim result "consistent with real" если sim was tuned on the
  same data (см. survivorship_audit).

## Allowed
- Skip checklist для:
  - Pure docs / report updates.
  - Unit tests с явно constructed synthetic data (нет реального leak risk).
  - Analytics post-mortem на полностью завершённый период (нет future).

## Recovery
Если leak обнаружен ПОСЛЕ commit:
- Записать в INCIDENTS.md с module + line + nature of leak.
- Открыть TZ-FIX-LEAK-{module}.
- Re-run all backtest results that depended on the leaky module —
  старые numbers invalidated.
- Notify operator: published K / edge / config based on leaky sim is
  null-and-void until re-run.

## Why
Lookahead bias — самый коварный bug в backtest research:
- Не падает в тестах (sim "работает", выдаёт "положительный edge").
- Производит false confidence: "у нас есть стратегия!".
- Невидим до live deployment, где реальный PnL расходится с backtest
  на порядки.

Из проектной истории:
- Reconcile_v3 sim_1y vs GA_1y — обе стороны считались на одном году.
  Без OOS validation это совмещение тренировки и теста.
- Calibration K вычисляется на same window where it then validated.
  Circular — справедливо только если operator явно понимает.

PROJECT_CONTEXT §9 P-2 принцип "Boundaries — анти-сквиз": та же логика
применяется к research — границы между training и validation = anti-squeeze
для accidental future leak.

Related skills: trader_first_filter (б — testing hypothesis), 
survivorship_audit, regression_baseline_keeper.
