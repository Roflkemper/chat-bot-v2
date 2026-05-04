# Backtest Audit — Calibration Numbers Trust Map

**Status:** AUDIT (TZ-BACKTEST-AUDIT, Block 14)
**Date:** 2026-05-05
**Method:** Read-only trace from `STATE_CURRENT.md §3` + `MASTER §6` baseline. No rerun, no code changes.

---

## §0 Reference: production live config (the gold standard)

From `docs/GINAREA_MECHANICS.md §6 "Живые параметры ботов (24.04)"`:

**SHORT (linear BTCUSDT)** — TEST_1 / TEST_2 / TEST_3:
- `order_size = 0.001 BTC`
- `order_count = 200`
- `grid_step_pct = 0.03`
- `target_profit_pct = 0.25`
- `instop_pct ∈ {0, 0.018, 0.03}`
- `boundaries = [68000, 78600]`
- `indicator = Price%, TF=1min, Period=30, > 0.3%`

**LONG (inverse XBTUSD)** — BTC-LONG-C:
- `order_size = 100 USD`
- `order_count = 220`
- `grid_step_pct = 0.03`
- `boundaries.upper = 76800`

Trust labels below are graded against this gold standard.

---

## §1 Audit table (D54)

| # | Metric | Value | Source | Params used | Match production? | Trust |
|---|--------|-------|--------|-------------|--------------------|-------|
| 1 | K_SHORT (direct 1s) median | 8.87, CV 31.8%, n=6 | `data/calibration/reconcile_direct_k_20260504T083655Z.json` ← `scripts/reconcile_direct_k.py` ← `data/calibration/ginarea_ground_truth_v1.json` | gs=0.03 ✓, target_pct sweep 0.19–0.45 (incl. 0.25 ✓), **size=0.003 BTC ✗** (live 0.001), **max_orders=800 ✗** (live 200), no instop, no indicator | gs ✓ / TP one of six matches ✓ / size ×3 / order_count ×4 / **no instop, no indicator** | ⚠️ Partial |
| 2 | K_LONG (direct 1s) median | 4.13, CV 43.1%, n=6 | same artifact as #1 | gs=0.03 ✓, **size=$200 ✗** (live $100), **max_orders=800 ✗** (live 220), no instop, no indicator | gs ✓ / TP varies / size ×2 / order_count ×3.6 | ⚠️ Partial |
| 3 | K_LONG (calibration extend) | 4.275, CV 24.9% | `reports/calibration_long_extended_2026-05-02.md` ← TZ-CALIBRATION-LONG-EXTEND | gs=0.03 ✓, **size=$200 ✗**, **max_orders=800 ✗**, sim raw mode "no instop/combo_stop" | gs ✓ / size ×2 / order_count ×3.6 / **no instop** | ⚠️ Partial |
| 4 | K_SHORT (historical) | 9.637, CV 3.0% | Same `ginarea_ground_truth_v1.json` (referenced in `docs/CONTEXT/DEPRECATED_PATHS.md:20`) | gs=0.03 ✓, **size=0.003 BTC ✗**, **max_orders=800 ✗**, no instop, no indicator | gs ✓ / size ×3 / order_count ×4 | ⚠️ Partial |
| 5 | K_LONG (historical) | 4.275, CV 24.9% | Same as #3 (single artifact, two STATE rows refer to it) | same as #3 | gs ✓ / size ×2 / order_count ×3.6 | ⚠️ Partial |
| 6 | Coordinated grid best | $37,769/year, 20 configs | `reports/coordinated_grid_research_2026-05-02.md:3` | "Bot params fixed: TD=0.25%, GS=0.03%, **SHORT 0.003 BTC, LONG 200 USD**" — explicitly research config | gs ✓ / TP ✓ / size ×3 (SHORT) and ×2 (LONG) / no instop, no indicator | ⚠️ Partial |
| 7 | Setup detector WR (strength=9) | 43.1% WR, +$16,163 / 1y BTCUSDT | `docs/HANDOFF_2026-04-30_evening_final.md` (table) ← `services/setup_backtest/outcome_simulator.py` ← `services/setup_detector/outcomes.py:_calc_pnl_usd` ← `services/setup_detector/setup_types.py:89,132` | `recommended_size_btc = 0.05` (×50 vs live 0.001 BTC); execution = hypothetical TP/SL hits, not GridBotSim cycles | grid params N/A (signal detector, not bot) / **size ×50 vs live** | ❌ Default |
| 8 | LONG ground truth | −0.5 BTC/year over 6 GinArea backtests | `data/calibration/ginarea_ground_truth_v1.json` (`common_long_params`: size=$200, max_trigger=800) | research configs as above | size ×2 / order_count ×3.6 | ⚠️ Partial |
| 9 | SHORT ground truth | +$31k..+$50k/year over 6 GinArea backtests | same JSON (`common_short_params`: size=0.003 BTC, max_trigger=800) | research configs | size ×3 / order_count ×4 | ⚠️ Partial |
| 10 | Unified Brier ceiling | 0.257 on 105k bars × 44 features | `docs/CONTEXT/DEPRECATED_PATHS.md:45` (DP-002) ← `data/forecast_features/full_features_1y.parquet` (pre-Tier-1) | feature pipeline 5m × 1y, 44 cols pre-expansion. No GinArea bot params involved (signal-side, not bot-side) | N/A — feature-based forecast | ✅ for what it claims |
| 11 | Forecast pipeline regime models | MARKUP 1h qual / 4h 0.259 / 1d 0.235 — MARKDOWN 0.204 / 0.228 / qual — RANGE 0.247/0.248/0.250 | `data/calibration/oos_validation_20260503T222446Z.json` ← `scripts/_oos_cv.py` ← `services/market_forward_analysis/regime_models/{markup,markdown,range}.py` | seed=42, 400 trials, 5-window CV; 5m features × per-regime parquet; 84 cols (Tier-1 + Tier-2). No GinArea params. | N/A — signal-side, not bot PnL | ✅ for what it claims |

**Score: 0 ✅-production-aligned for K/grid figures, 7 ⚠️ partial, 1 ❌ default, 2 ✅-but-orthogonal (signal models that don't claim to mirror bot PnL).**

---

## §2 Per-number narrative (D55)

### #1 — K_SHORT (direct 1s) = 8.87 median

**What it is:** the multiplicative gap between simulated SHORT realized PnL and GinArea-actual realized PnL across 6 SHORT backtest points, computed today after the full year of 1s OHLCV data was loaded.

**Code path:** `scripts/reconcile_direct_k.py` reads `data/calibration/ginarea_ground_truth_v1.json`, runs `services.calibration.sim.GridBotSim` per point, divides GA realized by sim realized → K factor.

**Params:** `common_short_params` from the GT JSON: `grid_step_pct=0.03` ✓, `order_size_btc=0.003` ✗ (live is 0.001), `max_trigger_number=800` ✗ (live is 200). Indicator gate and instop both **off** in sim (raw mode). Target_pct varied 0.19–0.45 across 6 points; one (0.25) matches live target.

**Verdict:** PARTIAL. Grid step matches. Order size is 3× larger, order count 4× larger. Critical: live SHORT bots have `indicator = Price% > 0.3%` AND nonzero `instop_pct` on TEST_2/TEST_3, neither of which the K-factor sim uses. K=8.87 is a **research-config K**, not a production-replica K.

### #2 — K_LONG (direct 1s) = 4.13 median

Same artifact as #1, LONG side. `common_long_params`: gs=0.03 ✓, `order_size_usd=200` ✗ (live $100), `max_trigger_number=800` ✗ (live 220). Same partial verdict.

### #3 — K_LONG (calibration extend) = 4.275

`reports/calibration_long_extended_2026-05-02.md`. Generated 2026-05-01 from the same GT JSON LONG points using the same `GridBotSim`. Header explicitly: "Engine: standalone sim raw mode (no instop/combo_stop)". Same research configs.

### #4–#5 — Historical K_SHORT=9.637 / K_LONG=4.275

Both come from earlier runs of the same calibration code on the same GT JSON. K_SHORT=9.637 is referenced in DP-001 (`docs/CONTEXT/DEPRECATED_PATHS.md:20`) without a separate report file; K_LONG=4.275 is the same number as #3. Same partial-match verdict.

### #6 — Coordinated grid best $37,769/year

`reports/coordinated_grid_research_2026-05-02.md` line 3: "Bot params fixed: TD=0.25%, GS=0.03%, **SHORT 0.003 BTC, LONG 200 USD**". The report itself flags in §240: "Synthetic sim: no instop, no indicator gate, no trailing stop group — sim fills ~10× more than real GinArea for SHORT (K=9.637). Combined_realized_usd values are NOT real-money equivalents."

### #7 — Setup detector WR (strength=9) = 43.1% / +$16,163

From a year backtest of `services/setup_detector/`. The PnL assumes each detected setup is taken with `recommended_size_btc=0.05` (set in `services/setup_detector/setup_types.py:89,132`) — **50× larger than live GinArea bots' 0.001 BTC**. Not a grid bot calibration; a discrete-setup hypothetical PnL with synthetic sizing. Grid mechanics (instop / indicator / boundaries) don't apply.

### #8–#9 — GA ground truth (LONG / SHORT)

The 6+6 GinArea backtest results in `data/calibration/ginarea_ground_truth_v1.json`. Real GinArea PnL — but produced with operator-defined research configs (size=$200 LONG / 0.003 BTC SHORT, max_orders=800), **not** live TEST_1/2/3 or BTC-LONG-C. Numbers themselves are factually correct "what happened in those backtests" but extrapolating to "live bot expected PnL" requires accepting the same 2-3× scaling assumption as the K factors.

### #10 — Unified Brier 0.257

DP-002 result. Pre-Tier-1 44-col feature pipeline. No bot params — signal-side prediction Brier. ✅ for what it claims.

### #11 — Regime model forecasts

`oos_validation_20260503T222446Z.json` — 5-window CV across 3 regimes × 3 horizons = 45 Brier points. Same signal-side concern as #10: forecast probability metrics, not bot PnL. ✅ for what they claim.

---

## §3 Downstream impact analysis (D56)

### Sizing v0.1 base values (1.4 / 1.0 / 0.6)

`docs/DESIGN/SIZING_MULTIPLIER_v0_1.md §"Decisions"`: these multipliers are calibrated to today's CV-mean Brier ranking — i.e., to **#11 (regime forecast Brier)**, NOT to any K factor or PnL number. **Sizing v0.1 is NOT directly compromised** by the partial-match issues in #1–#9.

### DP-001 (K-factor deprecation)

Cites K_LONG CV=24.9% as evidence K is structurally TD-dependent. Today's direct_k run (#2) gave CV=43.1% on a clean year of 1s data — **strengthens** DP-001. The deprecation conclusion holds even though absolute K values are research-conditioned, because TD-dependence is a property of the K-factor *function* over target_pct, not of any specific param tuple. ✅ DP-001 is robust.

### DP-002 (whatif-v3 unified rebuild kill)

Cited Brier 0.257 ceiling (#10). Independent of GinArea params. ✅ robust.

### Phase-aware sizing TODO

Conceptually depends on regime classifier reliability (#11) and K-factor *structure* (DP-001) — not on absolute K values. ✅ robust.

### Coordinated grid $37,769/year — actual money?

This is the highest-risk inference. The headline reads like a "we make this much" claim but the underlying sim used 3× live size. Real-money equivalent ≈ $37,769 / K_SHORT_blended ≈ $4k/yr (rough; the report's own caveat says sim PnL is ~10× real). Any operator decision treating $37k as a forecast of live-bot earnings is **likely off by an order of magnitude**. ⚠️ This is the one downstream number where the partial-match issue actually matters in operator framing.

### Setup detector strength=9 → +$16,163

Fed into the Year-Ahead Opportunity Map. The +$16k/yr figure assumes 0.05 BTC sizing — no live bot uses this size. Treating this as a real-money expectation is misleading by ~50× (recompute at 0.001 BTC ≈ $323/yr). ❌ Affects opportunity-map credibility but not the existence of the WR signal itself.

### Chain-of-trust summary

```
GinArea ground truth JSON (research configs)
    │
    ├──► K_SHORT/LONG factors (#1-#5) — partial match to production
    │       │
    │       └──► DP-001 deprecation (uses CV/structure, not values) — ✅ robust
    │
    ├──► Coordinated grid $37k figure (#6) — same research scaling
    │       │
    │       └──► Operator decisions about ensemble PnL expectations — ⚠️ off by ~10×
    │
    └──► GA ground truth references (#8, #9) — research configs

Setup detector +$16k (#7) — synthetic 0.05 BTC sizing — ❌ default
    └──► Opportunity map credibility — overstated by ~50×

Forecast pipeline Brier (#10, #11) — signal-side only, no bot params
    │
    └──► Sizing v0.1 base multipliers — derived from forecast Brier, not K factors
            │
            └──► Phase-aware sizing TODO — ✅ robust per chain
```

The chain isn't fully compromised. **K-related numbers are research-grade** — fine for *structural* conclusions (DP-001, K is TD-dependent), but **not** for absolute-PnL claims (coordinated grid $37k, setup detector +$16k). Forecast pipeline numbers are independent and trustworthy for what they measure.

---

## §4 Recommendations per row (D57)

| # | Metric | Recommendation | Rationale |
|---|--------|----------------|-----------|
| 1 | K_SHORT direct 1s 8.87 | **Recalibrate** with live SHORT config (size=0.001 BTC, order_count=200, indicator Period=30 > 0.3%, instop=0.018% as TEST_2 typical). Time: ~1 min compute. | Production-aligned K is the actually-useful K for live sizing. |
| 2 | K_LONG direct 1s 4.13 | **Recalibrate** with live LONG config (size=$100, order_count=220, no indicator, dsblin=OFF). Time: ~1 min. | Same. |
| 3 | K_LONG calib extend 4.275 | **Mark legacy** — supersede with row 2 recalibration. | Same artifact as #2 with prior data. |
| 4 | K_SHORT historical 9.637 | **Mark legacy** — supersede with row 1 recalibration. | Single-source artifact. |
| 5 | K_LONG historical 4.275 | **Mark legacy** — duplicate of #3. | Same as #3. |
| 6 | Coord grid $37,769/yr | **Re-derive** post-recalibration with production K factors. Add explicit caveat in any briefing material that current $37k is research-config-grade. | Operator framing risk (~10× overstatement on absolute PnL). |
| 7 | Setup WR/PnL +$16k | **Accept as-is with caveat** — the WR (43.1%) is the meaningful signal; the +$16k is sizing-dependent rendering. Mark `recommended_size_btc=0.05` explicit wherever this number appears. | Recalibrating "what would $16k be at 0.001 BTC?" gives ~$323 — still positive signal but not a headline number. |
| 8 | LONG GT −0.5 BTC/yr | **Accept as-is** — these are real GinArea backtest results at the configs they were run with. Add note: "research configs, not live BTC-LONG-C." | Numbers factually correct in their own context. |
| 9 | SHORT GT +$31..50k/yr | **Accept as-is** with same note. | Same. |
| 10 | Unified Brier 0.257 | **Keep** — DP-002 evidence, doesn't need params. | Signal-side, no bot config involved. |
| 11 | Regime model Brier matrix | **Keep** — CV-validated, signal-side. | Same. |

**Top-of-stack recommendation:** rows 1–6 should all be re-anchored to live configs in a single follow-up TZ (`TZ-K-RECALIBRATE-PRODUCTION-CONFIGS`). Compute is sub-minute per K factor; minutes for coordinated grid. Rows #8–11 are fine as-is with documentation. Row #7 is documentation-only fix.

---

## §5 What this audit does NOT cover (out of scope per anti-drift)

- No backtest re-runs.
- No code changes (sizing, dashboard, forecast).
- No judgment on whether *decisions* (DP-001 deprecation, sizing v0.1 base values) were correct given the chain — only whether the numbers feeding them are production-aligned.
- No commit-history archeology beyond locating source files.
- No claims about XRP, multi-asset, or anything not in `STATE_CURRENT §3`.

---

## §6 Summary

**11 numbers audited.** The partial-match pattern is dominated by **size and order-count mismatches** between research configs (size 0.003 BTC / $200, max_orders 800) and live configs (0.001 BTC / $100, max_orders 200/220). Grid step matches everywhere. Indicator/instop are absent from sim everywhere — this is a **structural** absence, not a parameter mismatch.

**Robust without recalibration:** DP-001 (uses K *structure* not *value*), DP-002 (signal-side), forecast pipeline (signal-side), sizing v0.1 (built on forecast Brier, not K).

**Needs recalibration to be load-bearing:** K factors (rows 1–5), coordinated grid headline (row 6).

**Framing-risk only (no recompute needed):** setup detector PnL (row 7), GT PnL labels (rows 8–9).

Compute cost of full recalibration: under 30 minutes total wall-clock for rows 1–6 if done as one batch. Decision on whether to schedule that recalibration is for operator + MAIN.
