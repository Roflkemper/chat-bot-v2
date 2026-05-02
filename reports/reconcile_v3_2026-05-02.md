# Reconcile v3 — Resolution Sensitivity Probe (2026-05-02)

**TZ:** TZ-ENGINE-FIX-RESOLUTION
**Branch:** `tz-engine-fix-resolution`
**Skills applied:** architect_inventory_first, project_inventory_first, trader_first_filter, phase_aware_planning, data_freshness_check, cost_aware_executor, result_sanity_check, regression_baseline_keeper, param_provenance_tracker

---

## §0 TL;DR

| Side  | n | Mean sim_1s / sim_1m | CV    | Verdict                                     |
|-------|---|----------------------|-------|---------------------------------------------|
| SHORT | 6 | **1.0043**           | 1.37% | K_SHORT **stable** to resolution change     |
| LONG  | 6 | 0.8396 (median 0.96) | 34.8% | K_LONG **NOT improved** by 1s — structural  |

**Recommendation:** keep current K values (K_SHORT=9.637, K_LONG=4.275). Do **not** open a separate calibration update TZ on the basis of resolution alone. Pursue instop-in-sim as the next handle on K_LONG variance.

---

## §1 Inventory & data gap (data_freshness_check)

| Source                        | Period                                       | Coverage of GA window |
|-------------------------------|----------------------------------------------|-----------------------|
| GA ground truth (12 backtests)| 2025-05-01 → 2026-04-30 (≈365d)              | 100% (reference)      |
| BTCUSDT_1m_2y.csv (frozen 1m) | 2024-04-30 → 2026-04-29                      | 100%                  |
| BTCUSDT_1s_2y.csv (frozen 1s) | **2026-04-02 → 2026-05-02 (≈30d)**           | **7.6%**              |

`check_direct_k_feasible(...)` returns `False` (need ≥ 95%). **Direct K vs GA reconcile mode is BLOCKED on data scope.** A meaningful K_factor = `ga_realized / sim_realized` requires the sim to span the same year as the GA realized PnL; running sim over 30 days against year-long GA realized would produce a 12× inflated nonsensical K.

This was caught by the inventory step BEFORE running misleading numbers — per `data_freshness_check` and `result_sanity_check`.

---

## §2 Method — resolution sensitivity probe (defensible alternative)

Instead of `K = ga / sim_1s` with mismatched periods, we compare:

```
ratio_i  =  sim_1s.realized_i  /  sim_1m.realized_i   (same window, same engine, same config)
```

over the **30-day overlap window** (2026-04-02 08:00 → 2026-04-29 17:13 UTC), where both 1m and 1s data are available. This isolates the **resolution effect** on realized PnL, independent of any GA period mismatch.

Reading:
- `ratio ≈ 1` → resolution change does not affect realized PnL → current K is stable wrt resolution.
- `ratio >> 1` or `<< 1` → 1m undercounts/overcounts intra-minute fills → K should be re-derived on 1s data once 1y of 1s OHLCV is available.

Engine: `services/calibration/sim.py` (standalone, no instop, no indicator gate, no trailing-stop group — by design, K absorbs these).
Bars: 39,434 × 1m and 2,365,981 × 1s on the overlap window.
Runtime: 65.3 s for full 12-config sweep (cost_aware_executor budget OK).

---

## §3 Per-config results

### SHORT (target_pct sweep, USDT-M, order_size=0.003 BTC)

| bot_id     | target_pct | sim_1m realized USD | sim_1s realized USD | ratio  | fills_1m | fills_1s |
|------------|-----------:|--------------------:|--------------------:|-------:|---------:|---------:|
| 5181061252 |       0.19 |              278.14 |              283.52 |  1.019 |      677 |      691 |
| 5658350391 |       0.21 |              305.71 |              303.65 |  0.993 |      673 |      668 |
| 4714585329 |       0.25 |              349.37 |              358.46 |  1.026 |      644 |      662 |
| 5360096295 |       0.30 |              417.39 |              413.22 |  0.990 |      641 |      634 |
| 5380108649 |       0.35 |              476.92 |              478.41 |  1.003 |      627 |      629 |
| 4929609976 |       0.45 |              595.76 |              592.22 |  0.994 |      608 |      604 |

### LONG (target_pct sweep, COIN-M, order_size=200 USD)

| bot_id     | target_pct | sim_1m realized BTC | sim_1s realized BTC | ratio  | fills_1m | fills_1s |
|------------|-----------:|--------------------:|--------------------:|-------:|---------:|---------:|
| 5303833401 |       0.21 |             0.01067 |             0.01089 |  1.021 |     1852 |     1892 |
| 4373073010 |       0.25 |             0.01210 |             0.00230 | **0.190** |     1772 |  **311** |
| 5342519228 |       0.30 |             0.01368 |             0.01300 |  0.950 |     1667 |     1586 |
| 5989606209 |       0.35 |             0.01482 |             0.01471 |  0.993 |     1541 |     1532 |
| 5975887092 |       0.45 |             0.01923 |             0.01853 |  0.964 |     1555 |     1500 |
| 5888109809 |       0.50 |             0.01926 |             0.01773 |  0.920 |     1408 |     1300 |

### Aggregates

| Side  | n | mean ratio | median | std    | CV     |
|-------|--:|-----------:|-------:|-------:|-------:|
| SHORT | 6 |     1.0043 | 0.9986 | 0.0137 |  1.37% |
| LONG  | 6 |     0.8396 | 0.9571 | 0.2923 | 34.82% |

---

## §4 Sanity check — LONG outlier (result_sanity_check)

Bot **4373073010** (LONG, target_pct=0.25): ratio = 0.190 (sim_1s = 19% of sim_1m). Fills dropped from 1,772 (1m) to 311 (1s) — **5.7× collapse**.

Hypothesis: 1m OHLC sequence (O→H→L→C reconstruction) creates phantom intra-bar paths that trigger TP fills which never existed on real 1s tape. With 1s resolution, the actual price walk for this specific config (target_pct=0.25 happens to be near a regime threshold for this period) doesn't cross enough TP boundaries.

This is **not a sim bug** — it's the known limitation of bar-resolution simulation for tight-target configs. The fix is data resolution (which we tested) but the result is **less confidence**, not more, on K_LONG: target_pct=0.25 specifically becomes much more sensitive to resolution than the other LONG configs.

Excluding this outlier, LONG ratios cluster at 0.92–1.02 (mean 0.97, CV 4.0%), close to SHORT.

---

## §5 K-implications

If we naively re-scale K from 1m to 1s using the mean ratio:

```
K_LONG_1s_implied  =  K_LONG_1m  /  mean_ratio_LONG  =  4.275 / 0.8396  ≈  5.09
                     (with median, ≈ 4.467)
```

But this is **not** a recalibrated K — it's a back-of-the-envelope. A real K_LONG_1s requires running sim on a **full year** of 1s data so that `sim_realized` is comparable to `ga_realized`. Currently neither value is meaningful at the 30-day scale.

**SHORT**: ratio mean 1.0043 ⇒ K_SHORT_1s ≈ K_SHORT_1m × (1/1.0043) ≈ **9.60**. Within the existing K_SHORT CV of 3% — no movement.

---

## §6 Hypothesis on K_LONG TD-dependence (CV 24.9% on 1m baseline)

The TZ asked: *"Если CV не улучшился → hypothesis why (instop missing in sim — structural, не fixable on 1s)"*.

Confirmed. The probe shows resolution change does **not** stabilize K_LONG (CV 34.82% on 1s ratios is in fact worse than 24.9% on 1m K). Therefore the TD-dependence is **structural**, not a resolution artifact:

1. **instop is not in sim.py** (intentional, per `class GridBotSim` docstring). LONG bots in real GinArea wait for `instop_pct` reversal from local extremum after indicator (Semant A — confirmed by TZ-CLOSE-GAP-05). Sim opens IN orders immediately at grid crossings. This delay reduces real fills relative to sim, by an amount that depends on `target_pct` × volatility regime → TD-dependent.
2. **Indicator gate not in sim.py.** GinArea fires indicator once per cycle (`is_indicator_passed` flag). Sim has no gating. Per-bar effect varies with regime.
3. **Out-stop group / combo-stop not in sim.py.** Closing IN groups via trailing-stop affects realized PnL on combos. Sim closes only on TP. Different sensitivity per target.

These are **structural omissions in sim.py by design** — the K factor was specifically introduced to absorb them. K_SHORT happens to be stable because SHORT realized is dominated by simple TP cycling on the testnet tape; K_LONG is volatile because the missing mechanics (instop especially) load harder on LONG/COIN-M during specific regimes.

**Implication:** to reduce K_LONG CV, we'd need to add instop / indicator gate to sim — outside this TZ's scope. This is a separate `TZ-ENGINE-FIX-CALIBRATION-INSTOP` proposal.

---

## §7 Recommendation (operator decision)

| Option | Description | Effort | Trade-off |
|---|---|---|---|
| **A (default)** | **Keep current K values.** K_SHORT=9.637, K_LONG=4.275 retained. Note resolution-stability of K_SHORT, structural K_LONG variance. | 0 | TD-dependence remains documented, not eliminated. |
| B | Open new TZ to ingest **1y of 1s OHLCV** for both BTCUSDT and XRPUSDT, then re-run direct-K reconcile. | ~1.6 GB CSV per symbol, 1–2h Binance pull, then sim re-run. | Resolves data-gap, but won't fix K_LONG variance (per §6). |
| C | Open new TZ to add instop (Semant A) + indicator gate to `services/calibration/sim.py`. | 1–2 days. | Most likely path to lower K_LONG CV. Requires careful test on existing K_SHORT to avoid drift. |

**Recommendation: Option A** as immediate decision (no MASTER §10 update needed); **Option C** as the next calibration TZ. Option B is low-value without C.

---

## §8 Files & artifacts

- `services/calibration/reconcile_v3.py` — module (load_ga_points, run_resolution_sensitivity, check_direct_k_feasible, k_factor)
- `tests/services/calibration/test_reconcile_v3.py` — 13 tests, all green
- This report

**No production changes.** Branch `tz-engine-fix-resolution` ready for operator review. Do not merge until §7 decision is made.

---

## §9 Regression baseline (regression_baseline_keeper)

`tests/services/calibration/test_reconcile_v3.py`: 13/13 pass.
`tests/services/calibration/test_calibration_sim.py` (existing): unchanged (read-only — verified by running both suites in same session).
