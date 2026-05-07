# K Recalibrate Production v1

Status: PARTIAL recalibration artifact  
Date: 2026-05-05  
Window: 2025-05-01 -> 2026-04-30 (annual 1s direct-k sim window)  
OHLCV: `backtests/frozen/BTCUSDT_1s_2y.csv` (31,536,000 bars loaded in-window)  
Raw output: `docs/RESEARCH/_k_recalibrate_production_raw.json`

## §1 Configs used

| Bot | Side | Contract | size | count | gs % | target % | min_stop % | max_stop % | instop % | indicator | once-check | boundaries | dsblin | Source |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|
| TEST_1 | SHORT | linear BTCUSDT | 0.001 BTC | 200 | 0.03 | 0.25 | 0.006 | 0.015 | 0 | Price% 1m / 30 / >0.3% | ON | 68000-78600 | OFF | docs/GINAREA_MECHANICS.md §6; ginarea_live/params.csv |
| TEST_2 | SHORT | linear BTCUSDT | 0.001 BTC | 200 | 0.03 | 0.25 | 0.008 | 0.025 | 0.018 | Price% 1m / 30 / >0.3% | ON | 68000-78600 | OFF | docs/GINAREA_MECHANICS.md §6; ginarea_live/params.csv |
| TEST_3 | SHORT | linear BTCUSDT | 0.001 BTC | 200 | 0.03 | 0.25 | 0.01 | 0.04 | 0.03 | Price% 1m / 30 / >0.3% | ON | 68000-78600 | OFF | docs/GINAREA_MECHANICS.md §6; ginarea_live/params.csv |
| BTC-LONG-C | LONG | inverse XBTUSD | $100 | 220 | 0.03 | 0.29 | 0.01 | 0.035 | 0.025 | Price% 1m / 30 / <-1.2% | ON | 75000-80000 | OFF / outside OFF | ginarea_live/params.csv; docs/GINAREA_MECHANICS.md §6 partial |

LONG note: the mechanics doc exposes only a partial LONG row. The missing fields above were filled from live-state snapshots in `ginarea_live/params.csv` for bot `5312167170` (`BTC-LONG-C`).

## §2 K_SHORT per TEST_1, TEST_2, TEST_3

Anchor used for all three SHORT K values: annual GT SHORT point `4714585329` (`target=0.25%`, realized `38909.93 USD`). This matches target but the GinArea denominator is still the research-config annual run, not annual TEST_1/2/3 live-bot output.

| Bot | K | sim realized USD | median | mean | CV % | range | n |
|---|---:|---:|---:|---:|---:|---|---:|
| TEST_1 | 814.5212 | 47.7703 | 814.5212 | 814.5212 | 0.00 | [814.5212, 814.5212] | 1 |
| TEST_2 | 223.9044 | 173.7792 | 223.9044 | 223.9044 | 0.00 | [223.9044, 223.9044] | 1 |
| TEST_3 | 209.6004 | 185.6386 | 209.6004 | 209.6004 | 0.00 | [209.6004, 209.6004] | 1 |

Family aggregate across the three SHORT production configs: median 223.9044, mean 416.0087, CV 67.75%, range [209.6004, 814.5212], n=3.

## §3 K_LONG for BTC-LONG-C

No exact annual GinArea backtest result for live `BTC-LONG-C` is present locally. Proxy anchor used: linear interpolation between annual LONG GT `target=0.25%` (`4373073010`, `0.12486136 BTC`) and annual LONG GT `target=0.30%` (`5342519228`, `0.1329 BTC`) to approximate a `target=0.29%` denominator.

| Bot | K | sim realized BTC | median | mean | CV % | range | n |
|---|---:|---:|---:|---:|---:|---|---:|
| BTC-LONG-C | 15.8672 | 0.0083 | 15.8672 | 15.8672 | 0.00 | [15.8672, 15.8672] | 1 |

This LONG value is an inferred proxy, not an exact annual direct-k point.

## §4 Comparison vs research-config K

Material = absolute difference >20% vs research baseline.

| Bot | Production K | Research baseline | Δ % vs research | Material? |
|---|---:|---:|---:|---|
| TEST_1 | 814.5212 | 8.8700 | 9082.88% | YES |
| TEST_2 | 223.9044 | 8.8700 | 2424.29% | YES |
| TEST_3 | 209.6004 | 8.8700 | 2263.03% | YES |
| BTC-LONG-C | 15.8672 | 4.1300 | 284.19% | YES |

Research baselines from `docs/RESEARCH/BACKTEST_AUDIT.md`: `K_SHORT=8.87 (CV 31.8%)`, `K_LONG=4.13 (CV 43.1%)`.

DP-001 status under production configs: **STILL CONFIRMED**. The absolute values move materially, especially because the SHORT family splits and the LONG proxy is not close to the historical research K. That keeps the "K is not a stable universal scalar" claim alive rather than weakening it.

## §5 Audit row closure

| Row | Audit item | Status | Reason |
|---|---|---|---|
| 1 | K_SHORT direct 1s 8.87 | partial | Sim rerun now uses live SHORT params, but denominator remains annual research-config GT realized PnL for the 0.25% target point, not annual TEST_1/2/3 GinArea actuals. |
| 2 | K_LONG direct 1s 4.13 | partial | Sim rerun uses live LONG_C params, but exact annual LONG_C GinArea actual is absent locally; K uses interpolated annual GT proxy between target 0.25 and 0.30 LONG points. |
| 3 | K_LONG calibration extend 4.275 | partial | Superseded directionally by live-param rerun, but still not fully closed because exact annual LONG_C denominator is missing and structural sim mismatch persists. |
| 4 | K_SHORT historical 9.637 | partial | Live-param SHORT rerun addresses the size/order-count mismatch on the sim side, but not the missing annual live-bot GinArea denominator. |
| 5 | K_LONG historical 4.275 | partial | Same reason as row 3 and row 2. |
| 6 | Coordinated grid best | still-open | This TZ recalibrated only direct-K proxies for the four live configs. Coordinated-grid recomputation with production-aligned K was explicitly out of scope and was not rerun. |

Closed count in this artifact: **0 fully closed**, **5 partial**, **1 still-open**.

## §6 Structural caveat

**Prominent caveat:** parameter-aligned rerun in this TZ does **not** make K production-grade. Per CP19, K remains research-grade because the calibration sim still does not reproduce the full GinArea platform behavior.

### (a) Params the sim actually consumed vs ignored

| Bot | Consumed by `services.calibration.sim` | Ignored / unmodeled by `services.calibration.sim` |
|---|---|---|
| TEST_1 | side, order_size, grid_step_pct, target_pct, max_orders, indicator_period=30, indicator_threshold=0.3, out_stop_group ON, min_stop=0.006, max_stop=0.015 | boundaries 68000-78600, contract label, once-check UI flag (sim hardcodes once-per-cycle), dsblin |
| TEST_2 | side, order_size, grid_step_pct, target_pct, max_orders, instop=0.018, indicator_period=30, indicator_threshold=0.3, out_stop_group ON, min_stop=0.008, max_stop=0.025 | boundaries 68000-78600, contract label, once-check UI flag, dsblin |
| TEST_3 | side, order_size, grid_step_pct, target_pct, max_orders, instop=0.03, indicator_period=30, indicator_threshold=0.3, out_stop_group ON, min_stop=0.01, max_stop=0.04 | boundaries 68000-78600, contract label, once-check UI flag, dsblin |
| BTC-LONG-C | side, order_size, grid_step_pct, target_pct, max_orders, instop=0.025 under sim's Semantics A implementation, indicator_period=30, indicator_threshold=1.2, out_stop_group OFF, min_stop=0.01, max_stop=0.035 | boundaries 75000-80000, dsblin OFF, dsblin_outside_boundaries OFF, contract label |

Important nuance: this repo's current `services/calibration/sim.py` **does** consume indicator gating and an `instop` path. That contradicts older docs that described the sim as raw-only. However, the modeled `instop` path is specifically `Instop Semantics A` (`services/calibration/instop_semant_a.py`), while LONG bot semantics for production were previously flagged as unclear in `scripts/reconcile_production.py`.

### (b) Implication for K trust

- SHORT: this TZ is better than the old research-config K because size/order-count and the live indicator/instop/out-stop settings were aligned on the sim side. But the denominator still comes from research-config annual GT results, not annual TEST_1/2/3 GinArea actuals.
- LONG: the trust level is lower than SHORT. The exact annual `BTC-LONG-C` GinArea denominator is absent locally, so the reported K is proxy-based. In addition, LONG_C `instop` was previously documented as a semantic risk area.
- Boundaries and `dsblin` remain outside the sim. Any live-bot behavior driven by "don't open outside range / don't resume" is invisible here.
- Therefore the produced K values are still **research-grade**, not production-grade. This TZ addresses parameter mismatch more honestly than the old 8.87 / 4.13 figures, but structural absence still dominates load-bearing trust.

No recommendation is made here; this is a flag for operator + MAIN review.
