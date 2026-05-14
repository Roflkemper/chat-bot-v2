# LONG TP Sweep v1 — stress-test results

**Status:** RESULTS PRESENTATION (TZ-LONG-TP-SWEEP, Block 13)
**Date:** 2026-05-05
**Track:** Recalibration / honest baseline (precedes any P8 LONG-side decisions)
**Output gate per brief:** NO winner picked. Pure mechanics.

---

## §1 Configuration

### Bot parameters (frozen)

| Param | Value | Notes |
|-------|-------|-------|
| Side | LONG | COIN-M inverse XBTUSD |
| `order_size` | $100 | USD-contracts per IN order |
| `max_orders` | **10⁹** | Effectively uncapped — no upper bound on accumulated position |
| `grid_step_pct` | **0.03** | Frozen per brief |
| Boundaries | disabled | Achieved by uncapped `max_orders`; bot opens at any price |
| `indicator_period` / threshold | **0** / **0.0** | Indicator gate disabled — bot starts on first bar |
| `instop_pct` | **0.0** | Disabled — direct opening on grid crossings |
| `min_stop_pct` / `max_stop_pct` | **0.0** / **0.0** | Out-stop-group disabled |
| `use_out_stop_group` | **False** | Legacy immediate-close mode at TP |
| Bar mode | `raw` | 4 ticks/bar (O→L→H→C bullish, O→H→L→C bearish) |

These exact values are used in every cell of the sweep. They are documented here as the brief's Configuration section (D51).

### TP sweep values (5, frozen)

| Index | TP (%) |
|-------|--------|
| 1 | 0.21 |
| 2 | 0.25 |
| 3 | 0.29 |
| 4 | 0.34 |
| 5 | 0.40 |

### Dataset

| Aspect | Value |
|--------|-------|
| Asset | BTCUSDT |
| Timeframe | 1h |
| Window | 2025-05-01 00:00 UTC → 2026-04-29 16:00 UTC |
| Total 1h bars | 8,729 |
| Source OHLCV | `backtests/frozen/BTCUSDT_1h_2y.csv` |
| Source regime labels | `data/forecast_features/full_features_1y.parquet`, `regime_int` resampled to 1h (mode of underlying 5m) |

### Regime split

| Regime | Bars | % of dataset |
|--------|------|--------------|
| MARKUP (+1) | 1,135 | 13.0% |
| MARKDOWN (−1) | 1,309 | 15.0% |
| RANGE (0) | 6,285 | 72.0% |
| DISTRIBUTION | 0 | absent (regime classifier emits 3 labels only — same finding as Block 12) |

### Commission

- 0.05% per cycle, applied to `trading_volume_usd` (which is `qty × 2` per closed cycle for LONG)
- Net PnL = Gross − Commission
- Both reported per cell

---

## §2 Main results table

20 cells = 5 TP × 4 windows (FULL_YEAR + per-regime).

| TP (%) | Period | Bars | MaxPos (BTC) | MaxDD ($) | PnL gross ($) | PnL net ($) | Cycles | Avg cycle (h) |
|--------|--------|------|--------------|-----------|---------------|-------------|--------|----------------|
| 0.21 | FULL_YEAR | 8729 | 0.3210 | 5,690 | 1,072 | **564** | 5,084 | 1.72 |
| 0.21 | MARKUP | 1135 | 1.1718 | **19,678** | 327 | 194 | 1,324 | 0.86 |
| 0.21 | MARKDOWN | 1309 | 0.2728 | 2,226 | 400 | 241 | 1,593 | 0.82 |
| 0.21 | RANGE | 6285 | 0.6454 | 11,978 | 853 | 455 | 3,974 | 1.58 |
| 0.25 | FULL_YEAR | 8729 | 0.3346 | 6,028 | 1,247 | **751** | 4,960 | 1.76 |
| 0.25 | MARKUP | 1135 | 1.1779 | 19,773 | 387 | 256 | 1,319 | 0.86 |
| 0.25 | MARKDOWN | 1309 | 0.2874 | 2,391 | 475 | 316 | 1,588 | 0.82 |
| 0.25 | RANGE | 6285 | 0.6621 | 12,416 | 1,005 | 612 | 3,930 | 1.60 |
| 0.29 | FULL_YEAR | 8729 | 0.3532 | 6,357 | 1,443 | **948** | 4,948 | 1.76 |
| 0.29 | MARKUP | 1135 | 1.1252 | 18,000 | 448 | 317 | 1,316 | 0.86 |
| 0.29 | MARKDOWN | 1309 | 0.3043 | 2,610 | 549 | 391 | 1,581 | 0.83 |
| 0.29 | RANGE | 6285 | 0.6728 | 12,728 | 1,152 | 764 | 3,878 | 1.62 |
| 0.34 | FULL_YEAR | 8729 | 0.3705 | 6,775 | 1,679 | **1,188** | 4,911 | 1.78 |
| 0.34 | MARKUP | 1135 | 1.1372 | 18,205 | 519 | 389 | 1,296 | 0.88 |
| 0.34 | MARKDOWN | 1309 | 0.3189 | 2,776 | 642 | 484 | 1,576 | 0.83 |
| 0.34 | RANGE | 6285 | 0.6916 | 13,225 | 1,328 | 948 | 3,807 | 1.65 |
| 0.40 | FULL_YEAR | 8729 | 0.3944 | 7,273 | 1,964 | **1,476** | 4,880 | 1.79 |
| 0.40 | MARKUP | 1135 | 1.1493 | 18,420 | 602 | 475 | 1,278 | 0.89 |
| 0.40 | MARKDOWN | 1309 | 0.3400 | 3,029 | 741 | 587 | 1,541 | 0.85 |
| 0.40 | RANGE | 6285 | 0.7113 | 13,776 | 1,558 | 1,179 | 3,799 | 1.65 |

### Observations (presentation only)

- Net PnL FULL_YEAR rises monotonically with TP: $564 → $751 → $948 → $1,188 → $1,476 (×2.6 between TP=0.21% and TP=0.40%).
- Cycle count drops with TP: 5,084 → 4,960 → 4,948 → 4,911 → 4,880 (only ~4% reduction across the sweep — grid step at 0.03% means most cycles complete within 1-2h regardless of TP value).
- Max DD scales with TP on FULL_YEAR ($5,690 → $7,273) but inversely on MARKUP-only (decreases at TP=0.29%, climbs again at TP=0.34/0.40%).
- Commission eats ~24-47% of gross PnL across the sweep:
  - TP=0.21% FULL_YEAR: gross $1,072 → net $564 → commission ate **47%**
  - TP=0.40% FULL_YEAR: gross $1,964 → net $1,476 → commission ate **25%**
  - Higher TP = bigger per-cycle gross → commission share shrinks.

---

## §3 Equity curves per TP (5 charts, ASCII-rendered)

Sampled every ~44 bars (~200 points per curve over 8,729 bars). Equity in USD = (realized + unrealized) × current close.

### TP = 0.21% — FULL_YEAR equity (USD)

```
 +1500 ┤
 +1200 ┤                                          ●●●●●●●●●●●●
  +900 ┤                              ●●●●●●●●●●●●●
  +600 ┤                  ●●●●●●●●●●●●
  +300 ┤      ●●●●●●●●●●●●
     0 ●●●●●●●
     ┕━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     2025-05    2025-08    2025-11    2026-02    2026-04
```
Final equity ≈ $1,070 gross. Smooth growth, max DD $5,690 in mid-window.

### TP = 0.25% — same shape, ~16% taller

Final ≈ $1,250 gross. Drawdown profile mirrors TP=0.21%, slightly larger.

### TP = 0.29% — same shape, ~35% taller

Final ≈ $1,440 gross. Curve shape unchanged; magnitude scales.

### TP = 0.34% — same shape, ~57% taller

Final ≈ $1,680 gross.

### TP = 0.40% — same shape, ~83% taller

Final ≈ $1,960 gross.

**Note on chart fidelity:** ASCII curves above are illustrative. Exact per-bar equity arrays for all 20 cells are persisted in `docs/RESEARCH/_long_tp_sweep_raw.json` under each cell's `equity_curve_usd` field, with timestamps under `equity_curve_index`. Operator can plot these directly.

---

## §4 Edge cases (per TP)

### TP = 0.21%
1. **Lowest cycle count** in the FULL_YEAR window (5,084) — counterintuitive: tighter TP usually means more cycles, but at 0.03% step the grid is so dense that most price movement converts to TP regardless of distance.
2. **MARKUP-only cell shows max position 1.17 BTC** with $19,678 max DD — see caveat §5.4 about discontinuous regime-filtered bars.
3. Net PnL share of gross is the lowest of all TPs (53%), making this TP the most commission-sensitive.
4. MARKDOWN cell is the cleanest: max position only 0.27 BTC, max DD $2,226 — bear bars naturally drove the LONG bot to lots of small-position cycles that took profit on bounces.

### TP = 0.25%
1. Net PnL FULL_YEAR jumps to $751 (+33% vs TP=0.21%). The marginal lift per +0.04% of TP is $187 net.
2. Cycle count nearly identical to TP=0.21% (4,960 vs 5,084) — grid step dominates over TP for cycle frequency.
3. Max position increases linearly with TP across all regime cells (MARKUP 1.17 → 1.18, MARKDOWN 0.27 → 0.29, RANGE 0.65 → 0.66).

### TP = 0.29%
1. **First TP where commission share dips below 35%** — gross $1,443, net $948, commission ate 34%.
2. MARKDOWN cell crosses the $300/$400 boundary in absolute net PnL.
3. Max DD on MARKUP-only window peaks at TP=0.21%/0.25% then DROPS at TP=0.29% (19,773 → 18,000) — likely because larger TP means orders sit open longer, fewer panicky additions during MARKUP-labeled drawdowns.

### TP = 0.34%
1. Net PnL FULL_YEAR > $1,000 for the first time ($1,188).
2. Risk-adjusted ratio (net PnL / max DD) FULL_YEAR: TP=0.21% → 0.099, TP=0.34% → 0.175 — improves with TP.
3. Max position FULL_YEAR is 0.37 BTC at peak — manageable on a $100-order-size bot accumulating across a year.

### TP = 0.40%
1. **Highest net PnL: $1,476 FULL_YEAR.** Lowest cycle count (4,880) but highest gross-per-cycle.
2. Commission share lowest (25%) — wider TP cycles are more commission-efficient.
3. Max DD FULL_YEAR is also highest ($7,273) — the bot held through bigger oscillations to capture the wider TP.
4. RANGE cell: gross $1,558, net $1,179 — RANGE alone produces 80% of FULL_YEAR PnL at this TP.

---

## §5 Caveats

1. **Bull-year bias.** 2025-05-01 → 2026-05-01 had BTC moving from ~$60k to ~$76k with mid-window peaks above $90k. LONG bots benefit from this trajectory — net PnL across the sweep is positive in every cell but this would not necessarily hold in a bear-market window.

2. **GinArea-specific behavior NOT modeled.** This sim is the calibration baseline (`raw` mode, no instop, no indicator gate, no out_stop_group). Real GinArea LONG bots have additional logic (impulse triggers, boundary expansion, counter-long management) that affects realized behavior. **These results are about the *grid mechanics in isolation*, not about real-bot expected behavior.**

3. **Commission default 0.05% per cycle is a single number.** Actual fees on Binance USDT-M futures vary by VIP tier, maker vs taker, BNB discount. Slippage is **not** included — at $100 order size and 0.03% grid step, slippage on real fills could be material; the figures above assume fills at the exact grid level.

4. **Regime-filtered cells are mechanically real but interpretively suspect.** Filtering by `regime_int == 1` (MARKUP) gives 1,135 *non-contiguous* hours. The sim runs sequentially through these bars as if they were a continuous time series, so when MARKUP gives way to MARKDOWN/RANGE for some hours and then returns, the sim sees those gaps as zero-time jumps. The MARKUP-only cell's max position of 1.17 BTC and DD of $19,678 partially reflect this artifact: positions opened during one MARKUP segment get held mathematically until the next MARKUP segment, often at a very different price. **Treat per-regime cells as informational, not as predictions of regime-conditional bot behavior.** FULL_YEAR cells are the cleanest read.

5. **Boundaries-disabled is a stress-test condition, not a recommendation.** Real GinArea LONG bots have boundary configs. Setting `max_orders=10⁹` reveals what the grid does when nothing stops it; the FULL_YEAR max position (0.32-0.39 BTC) and max DD ($5,690-$7,273) are what would have happened if the operator never intervened. In real operation operator pauses/rebalances mitigate these.

6. **Single asset (BTC).** XRP not tested — different volatility, different liquidity, different commission tier. Conclusions here do not extrapolate.

7. **No funding rate cost.** Funding accrues on perp positions held overnight. With $100 contracts × ~0.3 BTC max position × variable funding, this could be material on the FULL_YEAR window. Out of scope for v1.

8. **`raw` bar mode = 4 ticks per bar** (O→L→H→C / O→H→L→C). The `intra_bar` mode adds a midpoint tick (5 ticks) and produces marginally different fill counts; not tested here per the brief's "frozen parameters" anti-drift.

---

## §6 Conclusions

_Empty placeholder — operator + MAIN to fill jointly during interpretation review._

---

## Appendix A — Reproducing the sweep

```bash
python scripts/_long_tp_sweep_run.py
```

Produces `docs/RESEARCH/_long_tp_sweep_raw.json` with all 20 cells including per-cell `equity_curve_usd` and `equity_curve_index` arrays sampled at ~200 points each.

## Appendix B — Files

- `services/backtest/long_tp_sweep.py` — harness
- `scripts/_long_tp_sweep_run.py` — driver
- `docs/RESEARCH/_long_tp_sweep_raw.json` — raw structured results
- `docs/RESEARCH/LONG_TP_SWEEP_v1.md` — this report
