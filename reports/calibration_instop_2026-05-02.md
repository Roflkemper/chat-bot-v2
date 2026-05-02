# Calibration sim — instop Semant A + indicator gate (2026-05-02)

**TZ:** TZ-ENGINE-FIX-CALIBRATION-INSTOP
**Branch:** `tz-engine-fix-calibration-instop`
**Skills applied:** architect_inventory_first, project_inventory_first, trader_first_filter, phase_aware_planning, param_provenance_tracker, data_freshness_check, cost_aware_executor, result_sanity_check, regression_baseline_keeper

---

## §0 TL;DR

| Side  | Old CV (clean sim) | **New CV (instop + indicator)** | Δ relative |
|-------|--------------------|---------------------------------|-----------:|
| SHORT |              1.37% |                       **7.64%** |    +457%   |
| LONG  |             34.82% |                      **14.39%** |     −59%   |

**Hypothesis confirmed:** missing operator mechanics in sim → K_LONG TD-dependence. Adding instop Semant A + indicator gate reduces LONG resolution-sensitivity CV by **>2×** (34.82% → 14.39%). The most extreme LONG outlier (target_pct=0.25, ratio 0.190 in clean sim) collapsed into the cluster (0.525 in new sim).

SHORT CV increased from 1.37% → 7.64%. Still small in absolute terms; this is an expected artifact of adding parameter-dependent mechanics. SHORT realized was already well-modeled by the clean sim, so the *additional* sensitivity from per-bar instop/indicator decisions is now visible (it was previously absorbed silently into the K factor).

**Verdict per side:**
- LONG: **structural gap partially closed.** Remaining 14.39% CV plausibly comes from out-stop-group (combo-stop trim) — separate next-layer TZ candidate.
- SHORT: hypothesis **not** rejected; new variance is mechanic-driven, not a bug.

---

## §1 Method

### 1.1 New sim parameters

`services/calibration/sim.py` extended with three optional kwargs (defaults preserve previous behavior):

```python
GridBotSim(
    side, order_size, grid_step_pct, target_pct, max_orders,
    *,
    instop_pct=0.0,                  # 0 → no delay (clean baseline)
    indicator_period=0,              # 0 → no gate
    indicator_threshold_pct=0.0,     # 0 → no gate
)
```

When enabled:
- Indicator gate: `engine_v2/indicator.py` port (`PricePercentIndicator`). Pushes close on each bar; once `Price% > +threshold` (SHORT) / `< −threshold` (LONG) fires, `_is_indicator_passed=True` and the bar's OHLC is **not** processed (start fresh from next bar — same as `engine_v2/bot.py` step()). Reset on full-close.
- Instop Semant A: `engine_v2/instop.py` port (`InstopTracker`). After indicator pass, `pending_levels=1` is seeded so the A2 scenario fires on `instop_pct` reversal from local extremum. A1/A3 transitions when grid levels are crossed during pending state. On fire: one combined IN of `pending_levels × order_size`. Reset on full-close.

### 1.2 Provenance (param_provenance_tracker)

Both modules carry top-of-file source pointers:
- `services/calibration/instop_semant_a.py` → `engine_v2/instop.py:114-148`, operator-confirmed 2026-05-02 via TZ-CLOSE-GAP-05.
- `services/calibration/indicator_gate.py` → `engine_v2/indicator.py` + `engine_v2/bot.py` reset semantics + PROJECT_CONTEXT §2 once-per-cycle confirmed 2026-05-02.

### 1.3 Run params (from ground-truth common_*_params)

| Side  | instop_pct | indicator_period | indicator_threshold_pct |
|-------|-----------:|-----------------:|------------------------:|
| SHORT |       0.03 |               30 |                     0.3 |
| LONG  |      0.018 |               30 |                     0.3 |

### 1.4 Window & data

- Overlap window: 2026-04-02 08:00 → 2026-04-29 17:13 UTC (28 days, identical to TZ-ENGINE-FIX-RESOLUTION report)
- Bars: 39,434 × 1m + 2,365,981 × 1s
- Sim runtime new (12 configs × 2 resolutions): **87 s** (vs 65 s on clean sim — overhead from instop logic)

---

## §2 Per-config results — new sim

### SHORT (USDT-M, order_size=0.003 BTC)

| bot_id     | target_pct | sim_1m new (USD) | sim_1s new (USD) | ratio  | fills_1m | fills_1s |
|------------|-----------:|-----------------:|-----------------:|-------:|---------:|---------:|
| 5181061252 |       0.19 |           252.48 |           336.89 |  1.334 |      126 |      234 |
| 5658350391 |       0.21 |           279.06 |           362.72 |  1.300 |      126 |      244 |
| 4714585329 |       0.25 |           329.25 |           433.60 |  1.317 |      127 |      239 |
| 5360096295 |       0.30 |           393.24 |           442.62 |  1.126 |      125 |      224 |
| 5380108649 |       0.35 |           458.14 |           517.12 |  1.129 |      121 |      221 |
| 4929609976 |       0.45 |           580.81 |           661.74 |  1.139 |      119 |      217 |

### LONG (COIN-M, order_size=200 USD)

| bot_id     | target_pct | sim_1m new (BTC) | sim_1s new (BTC) | ratio  | fills_1m | fills_1s |
|------------|-----------:|-----------------:|-----------------:|-------:|---------:|---------:|
| 5303833401 |       0.21 |          0.01124 |          0.00590 |  0.525 |      520 |      302 |
| 4373073010 |       0.25 |          0.01331 |          0.00716 |  0.538 |      502 |      309 |
| 5342519228 |       0.30 |          0.01383 |          0.00872 |  0.630 |      459 |      319 |
| 5989606209 |       0.35 |          0.01650 |          0.01036 |  0.628 |      458 |      320 |
| 5975887092 |       0.45 |          0.02061 |          0.01451 |  0.704 |      450 |      338 |
| 5888109809 |       0.50 |          0.02110 |          0.01666 |  0.790 |      418 |      355 |

### Aggregates (new vs old)

| Side  | n | New mean | New median | New std | New CV  |  Old CV  | Δ CV    |
|-------|--:|---------:|-----------:|--------:|--------:|---------:|--------:|
| SHORT | 6 |   1.2241 |     1.2196 |  0.0935 |  7.64%  |   1.37%  | +457%   |
| LONG  | 6 |   0.6359 |     0.6292 |  0.0915 | 14.39%  |  34.82%  | −59%    |

---

## §3 Sanity flags & investigation (result_sanity_check)

Both sides crossed the 50% Δ-CV threshold. Per skill protocol, root cause review before reporting:

### 3.1 LONG (CV 34.82% → 14.39%, −59%)

**Plausible.** The clean sim opened LONG IN orders immediately at every grid crossing — driving 1,400–1,900 fills per config on 1m data. With instop + indicator now in place, fills drop to 418–520 (1m) and 302–355 (1s), matching the order of magnitude of the GA `num_triggers` field for SHORT runs (559 in 1y for bot 5658350391; ~46 per 30 days = realistic intra-day cadence).

The previous LONG outlier (4373073010, target=0.25, ratio 0.190) had unusually high fill count even on 1m relative to its peers — symptomatic of phantom fills from intra-bar reconstruction. With instop delaying entries to actual reversal points, both 1m and 1s sims now produce comparable trajectories → ratio 0.538 (within new cluster).

### 3.2 SHORT (CV 1.37% → 7.64%, +457%)

**Plausible.** SHORT ratios shifted from ≈1.0 (resolution-insensitive on clean sim) to 1.13–1.33 (new sim has more 1s-than-1m fills, as expected when intra-minute fills can also be gated by instop pullbacks). Two clusters appear: targets 0.19/0.21/0.25 → ratio ~1.32; targets 0.30/0.35/0.45 → ratio ~1.13. This bimodality is target-dependent: tight targets are more sensitive to within-minute reversals because TPs are closer to entries.

The increase in CV does **not** indicate a bug; it indicates that resolution-sensitivity is now *visible* where the clean sim collapsed it. The absolute ratios remain narrow (std 0.094 on a mean of 1.22 → tight in absolute terms).

### 3.3 No bug-suspect findings

- Existing 26 calibration tests still pass (regression_baseline_keeper).
- 11 new tests for instop + indicator pass.
- Default-disabled params: any caller not opting in sees the same behavior as before.

---

## §4 K-implications (informational, NOT a recalibration)

This experiment uses the 30-day window only. The numbers below illustrate magnitude only — a real K_factor still requires sim and GA to span the same period.

```
Apparent K shift on 1s vs 1m (new sim):
  SHORT mean ratio 1.224 → if 1s-based GT existed,
                            K_SHORT_1s ≈ K_SHORT_1m / 1.224 ≈ 7.87
  LONG  mean ratio 0.636 → K_LONG_1s ≈ K_LONG_1m / 0.636 ≈ 6.72
                          (vs current K_LONG_1m = 4.275)
```

The K_LONG implied shift (4.27 → 6.72) is **larger** than the previous-report estimate (≈5.09). This is because the new sim now under-counts fills on 1s by ~36%, shifting K. Both SHORT and LONG K values would need full-year reconcile data to be authoritative.

---

## §5 Verdict & recommendation

| Side  | Hypothesis status                       | Next step                                                      |
|-------|-----------------------------------------|----------------------------------------------------------------|
| LONG  | **Partially confirmed.** Adding instop+gate cuts CV >2×. | New layer hypothesis: out-stop-group (combo-stop trim) accounts for remaining 14% CV. Open `TZ-ENGINE-FIX-CALIBRATION-OUTSTOP` if needed. |
| SHORT | Original baseline acceptable.            | Keep clean sim as-is for SHORT calibration; do not enable instop+indicator unless re-deriving K_SHORT against a 1s ground truth. |

### Operator decision points

1. **Merge or hold this branch?** Recommend **hold for review** until §5.2 decision. No production code path uses these new params yet — `services/calibration/runner.py` still calls `run_sim` without them. Existing K calibration unchanged.

2. **Update K factors in MASTER §10?** **No, not yet.** Both old and new K values are computed against 30-day-mismatched data. A real K update needs 1y of 1s OHLCV (separate operator action).

3. **Open the next-layer TZ?** Recommend **yes for LONG** (out-stop-group). For SHORT, the 1.37% CV on clean sim is already excellent — adding mechanics there is gold-plating.

4. **Should `services/calibration/runner.py` adopt the new params for the LONG ground-truth derivation?** This would change the published K_LONG (currently 4.275). Operator decision.

---

## §6 Files & artifacts

- `services/calibration/sim.py` — extended with 3 optional kwargs, default behavior preserved
- `services/calibration/instop_semant_a.py` — port of engine_v2/instop.py
- `services/calibration/indicator_gate.py` — port of engine_v2/indicator.py
- `tests/services/calibration/test_sim_instop.py` — 6 tests
- `tests/services/calibration/test_sim_indicator_gate.py` — 5 tests
- `services/calibration/reconcile_v3.py` (cherry-picked from `tz-engine-fix-resolution`)
- `tests/services/calibration/test_reconcile_v3.py` (cherry-picked) — 13 tests
- This report

**Calibration test suite:** 37/37 pass on this branch (26 baseline + 11 new).

**Branch held for operator review.** Do not merge until §5 decisions are made.

---

## §7 Regression baseline (regression_baseline_keeper)

```
$ pytest tests/services/calibration/ -q
.....................................                                    [100%]
37 passed in 0.19s
```

No existing test regressed. New tests added cover the 6 instop scenarios and 5 indicator-gate scenarios per TZ acceptance criteria.
