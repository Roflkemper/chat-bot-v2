# INVENTORY WEEKLY COMPARISON REPORT 2026-04-29T230727Z

## 0. Sources прочитаны

| # | Path | Status |
|---|---|---|
| 1 | `_recovery/restored/src/whatif/aggregator.py` | read |
| 2 | `src/whatif/reports.py` (active) | read |
| 3 | `_recovery/restored/src/advisor/v2/telemetry.py` | read |
| 4 | `services/telegram_runtime.py` lines 695–738 | read |

---

## 1. Per-implementation summary

### 1.1 aggregator.py (restored src/whatif/)

**Purpose:** Aggregate multiple What-If play simulation results into one markdown summary.

**Data source:** `whatif_results/P-*_YYYY-MM-DD.parquet` — backtest output parquets from grid search.

**Key functions:**
- `aggregate_results(output_dir, date_str)` → `(markdown_str, summary_df)`
- `categorize_result(mean_pnl, mean_dd_vs_base)` → "profitable" / "harmful" / "defensive" / "neutral"

**Output:** `whatif_results/SUMMARY_YYYY-MM-DD.md` — table with play_id, status, n_eps, best_combo, best_mean_pnl_vs_baseline_usd, win_rate, DD.

**Groups by:** play_id from `run_config` (backtest plays P-1..P-12).

**Relationship to reports.py:** imports `_PLAY_NAMES` from `src.whatif.reports`.

**Tests:** yes (restored `_recovery/restored/src/whatif/tests/`).

**Verdict:** Backtest aggregation tool. Читает parquet, не JSONL. Не связан с оператором или бумажным журналом.

---

### 1.2 reports.py (active src/whatif/)

**Purpose:** Per-play markdown report from backtest parquet files (TZ-022 §12).

**Data source:** `whatif_results/P-*_YYYY-MM-DD.parquet` и `*_raw.parquet`.

**Key functions:**
- `generate_report(play_id, results_df, manifest, raw_df)` → markdown string
- `write_report(play_id, output_dir, date_str)` → Path

**Output:** Markdown с param grid, summary table (combo → PnL vs baseline, win rate, DD), best combo, top-5/worst-5 episodes.

**Groups by:** param_combo_id внутри одного play.

**Verdict:** Backtest reporting tool. Читает parquet, не JSONL. Ни operator actions, ни followup, ни edge calculation.

---

### 1.3 telemetry.py (restored src/advisor/v2/)

**Purpose:** Log recommendations + reconcile outcomes at 1h/4h/24h horizons.

**Data source:** 
- Writes to: `logs/advisor_log.jsonl`, `logs/advisor_outcomes.jsonl`
- Reads: same files
- Schema: старый `Recommendation` (from cascade.py), НЕ `SignalEnvelope`

**Key functions:**
- `log_recommendation(rec, portfolio_balance)` — append to advisor_log.jsonl
- `schedule_outcome_check(rec, price_at_rec)` — pending entry in advisor_outcomes.jsonl
- `reconcile_pending(current_price)` — compute PnL proxy at elapsed horizons
- `get_stats(days)` → dict с `total`, `by_play_count`, `by_play_outcomes` (hit_rate, mean_actual_pnl, mean_expected_pnl at 4h horizon)
- `get_recent_log(n)` → last N entries from advisor_log.jsonl

**Verdict:** Closest in spirit (per-play stats, hit rate, PnL). Но:
- Schema несовместима с `SignalEnvelope` (старый `Recommendation` объект)
- Data paths: `logs/advisor_log.jsonl` vs нужные `state/advise_signals.jsonl` / `state/advise_action_match.jsonl` / `state/advise_followup.jsonl`
- Нет operator action breakdown (yes/no/partial/opposite)
- Нет period-bound [start, end)
- Нет blind spots / hits logic
- PnL proxy — синтетический price diff, не реальный operator outcome

**Useful patterns** (для вдохновения, не переиспользования): `_read_all()`, `get_stats()` structure, reconcile loop idea.

---

### 1.4 telegram_runtime.py line 705 — /advisor stats

**Purpose:** Telegram UI consumer of `advisor_telemetry.get_stats()`.

**What it shows:** per-play recommendation count, hit rate (n), actual vs expected PnL at 4h horizon.

**Data source:** delegates entirely to `advisor_telemetry.get_stats()` from old advisor v2.

**Verdict:** View layer. Сам данные не генерирует. Импортирует `src.advisor.v2.telemetry` (restored path).

---

## 2. Requirements comparison matrix

| Requirement | aggregator | reports.py | telemetry | telegram_runtime |
|---|---|---|---|---|
| Read `advise_signals.jsonl` | ❌ | ❌ | ❌ | ❌ |
| Read `advise_action_match.jsonl` | ❌ | ❌ | ❌ | ❌ |
| Read `advise_followup.jsonl` | ❌ | ❌ | ❌ | ❌ |
| Group by setup_id (P-2, P-7, …) | ❌ parquet plays | ❌ parquet plays | ✅ by play_id (old schema) | ❌ delegates |
| Action breakdown (yes/no/partial/opposite) | ❌ | ❌ | ❌ | ❌ |
| Edge: followed PnL avg vs ignored PnL avg | ❌ | ❌ | partial (hit rate proxy) | ❌ |
| Blind spots (ignored profitable signals) | ❌ | ❌ | ❌ | ❌ |
| Hits (followed profitable signals) | ❌ | ❌ | partial (hit bool at 4h) | ❌ |
| Period-bound [start, end) | ❌ | ❌ | partial (days=N from now) | ❌ |
| WeeklyReport pydantic model | ❌ | ❌ | ❌ | ❌ |
| Markdown render | ✅ | ✅ | ❌ raw dict | ❌ Telegram text |

**Summary:** Ни один источник не покрывает ни одного ключевого требования по advise_v2 JSONL. Telemetry.py — ближайший по духу, но полностью несовместим по схеме и data paths.

---

## 3. Recommendation

**parallel_minimal** — отдельный модуль `services/advise_v2/weekly_report.py`.

**Rationale:**

1. **Другой data domain.** Все 4 existing implementations работают с backtest parquet или old advisor JSONL. `advise_v2` paper journal — genuinely novel: operator action tracking + signal outcome correlation. Нет базы для extend.

2. **Schema mismatch.** `SignalEnvelope` vs `Recommendation` — разные pydantic модели с несовместимыми полями. Reuse невозможен без conversion layer, который стоит дороже нового модуля.

3. **Data paths разные.** `state/advise_signals.jsonl` vs `logs/advisor_log.jsonl` vs `whatif_results/*.parquet`. Три изолированных data pipeline.

4. **telemetry.py useful patterns available.** `_read_all()` pattern, `get_stats()` структура, period-bound cutoff через `datetime.now() - timedelta(days=N)` — можно вдохновиться. Но это inspiration, не reuse.

5. **Minimal scope.** Weekly report это один файл ~150 строк: readers для 3 JSONL + group by setup_id + action breakdown + edge calc + pydantic WeeklyReport + markdown renderer.

**Rejected alternatives:**
- `reactivate_as_is`: нечего реактивировать — ни один не покрывает требования
- `extend_existing reports.py`: reports.py читает parquet, не JSONL; extension cost выше нового модуля
- `hybrid`: нет совместимых компонентов для комбинации

---

## 4. Implementation plan (parallel_minimal)

```
services/advise_v2/weekly_report.py   (NEW, ~150 lines)
tests/services/advise_v2/test_weekly_report.py  (NEW, ~20 tests)
```

**WeeklyReport pydantic model:**
```python
class SetupStats(StrictModel):
    setup_id: str              # "P-2"
    n_signals: int
    action_breakdown: dict[str, int]  # {"yes": 3, "no": 2, "partial": 1, "opposite": 0}
    followed_pnl_avg: float | None
    ignored_pnl_avg: float | None
    edge: float | None         # followed_pnl_avg - ignored_pnl_avg
    blind_spots: int           # ignored signals with positive followup PnL
    hits: int                  # followed signals with positive followup PnL

class WeeklyReport(StrictModel):
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    n_total_signals: int
    n_null_signals: int
    setups: list[SetupStats]
```

**Reader functions:**
- `load_signals(path, start, end)` → `list[SignalEnvelope]` (period-bound)
- `load_action_matches(path, start, end)` → `list[dict]`
- `load_followups(path, start, end)` → `list[dict]`

**Core function:**
- `build_weekly_report(start, end, signals_path, action_path, followup_path)` → `WeeklyReport`

**Renderer:**
- `render_markdown(report: WeeklyReport)` → str
- `render_telegram(report: WeeklyReport)` → str (≤4096 chars)

**Patterns borrowed from telemetry.py:**
- `_read_all()` JSONL reader pattern
- Per-play grouping structure
- Period cutoff via datetime comparison

---

## 5. Skills applied

- `state_first_protocol`: read existing implementations before recommendation
- `project_inventory_first`: this TZ IS the inventory step
- `encoding_safety`: markdown output via UTF-8
- `regression_baseline_keeper`: read-only, no code changes, no regression risk
- `operator_role_boundary`: recommendation only, no implementation issued
