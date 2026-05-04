# P8-RGE — Expansion Variants Backtest Results v0.1

**Status:** RESULTS PRESENTATION (TZ-RGE-RESEARCH-EXPANSION, P8)
**Date:** 2026-05-05
**Track:** P8 — Idea 1 research, foundation for ensemble design
**Output gate per brief:** NO recommendations / NO winner-picking. Pure mechanics.

---

## §1 Methodology

### Variants tested (5, frozen)

| Variant | Semantics | Mechanics in this harness |
|---------|-----------|---------------------------|
| A | New grid levels added in trend direction | `max_orders` + 5 in directional regimes |
| B | Size × multiplier per existing level in trend direction | `order_size` × 2.0 in directional regimes |
| C | Range shift around current price + ATR offset | `grid_step_pct` + 0.1 × ATR_pct shift |
| D | Recompute boundaries with ATR + regime offset (Block 7 D-aligned) | `grid_step_pct` + 0.05 × ATR_pct, `max_orders` + 10 |
| E | Hybrid: A's extra levels + modest 1.2× size | `max_orders` + 5 AND `order_size` × 1.2 |

Direction-conditional parameters apply only when `regime ≠ RANGE` (RANGE preserves baseline grid). Per anti-drift, no hyperparameter sweep — single sensible defaults per variant.

### Regime split source

`data/forecast_features/full_features_1y.parquet` column `regime_int`:
- **+1 = MARKUP** (uptrend, `regime_24h == "uptrend"` in whatif_v3)
- **−1 = MARKDOWN** (downtrend)
- **0 = RANGE / sideways**

**DISTRIBUTION cells skipped** — the regime classifier in this dataset emits only 3 labels (`uptrend`/`downtrend`/`sideways`); no DISTRIBUTION code path. Per anti-drift "if data thin, flag and skip", DISTRIBUTION column is omitted (not synthesized). Resulting matrix: **5 variants × 3 regimes = 15 cells**.

### Dataset

| Aspect | Value |
|--------|-------|
| Asset | BTCUSDT |
| Timeframe | 4h (resampled from 1h source) |
| Window | 2025-05-01 → 2026-05-01 (365 days) |
| Total 4h bars | 2,183 |
| Source OHLCV | `backtests/frozen/BTCUSDT_1h_2y.csv` |
| Source regime labels | 4h mode of underlying 1h `regime_int` |
| Bar simulation engine | `services.calibration.sim.GridBotSim` (existing, unchanged) |

### Episode handling

Contiguous runs of bars in the same regime form an "episode". Episodes < 3 bars are dropped (noise). Each variant runs **per episode** with its own fresh `GridBotSim` state — episodes are not joined into one continuous stream. Cell PnL = sum of per-episode realized PnL.

### Grid base parameters (constant across variants)

| Param | Value | Notes |
|-------|-------|-------|
| `grid_step_pct` | 0.5 | Typical 4h-timeframe grid step |
| `target_pct` | 1.0 | 1% TP per cycle |
| `max_orders` | 100 | Baseline ceiling |
| `order_size` | 0.005 BTC | SHORT-side notional |
| Side mapping | MARKUP→LONG, others→SHORT | LONG PnL converted to USD via mean episode close for cross-cell comparison |

---

## §2 Comparison matrix — PnL ($USD)

| Variant | MARKUP | MARKDOWN | RANGE |
|---------|--------|----------|-------|
| A | 0.00 | **522.41** | 1698.72 |
| B | 0.00 | **1044.81** | 1698.72 |
| C | 0.00 | 344.73 | 1698.72 |
| D | 0.00 | 344.73 | 1531.62 |
| E | 0.00 | 626.89 | 1698.72 |

## §3 Comparison matrix — max drawdown (%)

| Variant | MARKUP | MARKDOWN | RANGE |
|---------|--------|----------|-------|
| A | 0.00 | 9.81 | 7.73 |
| B | 0.00 | **17.86** | 7.73 |
| C | 0.00 | 6.37 | 7.73 |
| D | 0.00 | 6.37 | 6.59 |
| E | 0.00 | 11.54 | 7.73 |

## §4 Per-cell metrics (full)

| Variant | Regime | Bars | Episodes | PnL ($) | Max DD % | Sortino | Trades | Mean ep len |
|---------|--------|------|----------|---------|----------|---------|--------|-------------|
| A | MARKUP | 240 | 45 | 0.00 | 0.00 | -0.0 | 47 | 5.3 |
| A | MARKDOWN | 269 | 45 | 522.41 | 9.81 | 0.0 | 126 | 6.0 |
| A | RANGE | 1547 | 122 | 1698.72 | 7.73 | 0.001 | 358 | 12.7 |
| B | MARKUP | 240 | 45 | 0.00 | 0.00 | -0.0 | 47 | 5.3 |
| B | MARKDOWN | 269 | 45 | 1044.81 | 17.86 | 0.0 | 126 | 6.0 |
| B | RANGE | 1547 | 122 | 1698.72 | 7.73 | 0.001 | 358 | 12.7 |
| C | MARKUP | 240 | 45 | 0.00 | 0.00 | 0.0 | 44 | 5.3 |
| C | MARKDOWN | 269 | 45 | 344.73 | 6.37 | 0.0 | 80 | 6.0 |
| C | RANGE | 1547 | 122 | 1698.72 | 7.73 | 0.001 | 358 | 12.7 |
| D | MARKUP | 240 | 45 | 0.00 | 0.00 | 0.0 | 44 | 5.3 |
| D | MARKDOWN | 269 | 45 | 344.73 | 6.37 | 0.0 | 80 | 6.0 |
| D | RANGE | 1547 | 122 | 1531.62 | 6.59 | 0.002 | 321 | 12.7 |
| E | MARKUP | 240 | 45 | 0.00 | 0.00 | 0.0 | 47 | 5.3 |
| E | MARKDOWN | 269 | 45 | 626.89 | 11.54 | -0.0 | 126 | 6.0 |
| E | RANGE | 1547 | 122 | 1698.72 | 7.73 | 0.001 | 358 | 12.7 |

---

## §5 Per-variant edge cases (3-5 each, observation only)

### Variant A — extra levels in trend direction
1. MARKUP cells return zero PnL across all 45 episodes — episodes are too short (mean 5.3 bars × 4h = ~21 hours) for the 1% TP cycle to complete in a regime classified as MARKUP.
2. MARKDOWN: 522 USD / 126 trades = $4.14 per trade average — clean baseline.
3. RANGE: 1547 bars × ~12.7 mean episode length means many episodes are long enough for multiple TP cycles. Fills (358) are 2.8× the MARKDOWN count despite only ~5.7× the bar count.
4. Max DD scales with bar count more than with variant choice in RANGE (9.8% MARKDOWN vs 7.7% RANGE — both come from the same baseline GridBotSim).

### Variant B — size × 2 in trend direction
1. MARKDOWN PnL doubles to $1044 vs A's $522 (expected — same trade count, double size).
2. **MARKDOWN max DD almost doubles too: 9.81% → 17.86%.** This is the DP-001 pattern made visible — uniform scalar scaling moves both PnL and DD proportionally with no risk-adjusted improvement.
3. RANGE cell identical to A — by design (B's size× only triggers on directional regimes).
4. MARKUP unchanged (0 PnL) — short episodes still don't complete cycles regardless of size.

### Variant C — range shift via ATR-augmented step
1. Wider grid step in MARKDOWN reduces trade count (126 → 80) and PnL (522 → 345).
2. But max DD also drops (9.81% → 6.37%) — fewer trades means fewer simultaneous open positions on adverse moves.
3. Risk-adjusted (PnL/DD) ratio MARKDOWN: A=53.3, B=58.5, C=54.1 — variant C trades less but at slightly worse efficiency than A on this metric.
4. RANGE behavior identical to A — direction=0 short-circuits the ATR-shift path.

### Variant D — ATR boundary recompute, applies always
1. The only variant whose RANGE cell *differs* from baseline (1531 vs 1698 — wider step reduces trade frequency by ~10%).
2. MARKDOWN identical to C (344.73 / 6.37%) — same ATR mechanics, just reached via a different code path.
3. RANGE max DD lowest of all variants in RANGE: 6.59% vs 7.73%. Wider grid → fewer concurrent positions.
4. Trade count reduction in RANGE: 358 → 321. Real but small.

### Variant E — hybrid (A's levels + 1.2× size)
1. MARKDOWN PnL 626 vs A's 522 → 20% lift exactly matches the 1.2× size scale.
2. Max DD: 11.54% vs A's 9.81% → also ~17% increase, near-linear with size.
3. **DP-001 risk diluted but not removed:** E shows the same risk-scales-with-PnL pattern as B, just at a smaller magnitude.
4. RANGE cell identical to A (direction=0 path bypasses both A's level addition and B's size scaling).

---

## §6 Data caveats

1. **Bull-year bias (factual, not corrected).** Window 2025-05-01 → 2026-05-01 spans BTC moving from ~$60k to ~$76k (mid-window peaks above $90k). Fewer MARKDOWN episodes (45 of ~212 total) and shorter MARKUP runs (45 episodes mean 5.3 bars each). RANGE dominates with 122 episodes / 1547 bars. **Cells should not be compared between regimes as if regimes had equal data.** Cross-regime aggregation is reference-only.

2. **MARKUP PnL = 0 across all variants.** Mean MARKUP episode = 5.3 bars × 4h = ~21 hours. With 1% TP and 0.5% grid step on LONG side, a TP cycle requires price to round-trip ≥1% in 21 hours — happens occasionally but not enough to register a complete cycle within episode boundaries (sim freshly starts each episode). This is a methodology artifact, not a finding about variants. Possible mitigation in v0.2: warm-start sim across consecutive bars, or use `unrealized_pnl` instead of `realized_pnl` for short episodes. Out of scope for v0.1.

3. **DISTRIBUTION column missing.** `regime_24h` classifier in `data/forecast_features/full_features_1y.parquet` emits only 3 labels. To get a real DISTRIBUTION column, either (a) wire a Wyckoff-aware classifier upstream, or (b) re-label the dataset with phase classifier output. Both are out of scope for this TZ.

4. **Sortino values are uninformative.** 4h bar resolution → most bars have ΔPnL=0; non-zero filter helps but Sortino still pegged near 0 because the few nonzero deltas are mostly positive (sim closes on TP, rarely on opposite). For meaningful Sortino, switch to per-trade returns or per-day equity sampling. Out of scope for v0.1.

5. **Side mapping is heuristic.** MARKUP → LONG, others → SHORT. RANGE could equally be a LONG-SHORT hedge pair (closer to Idea 2's range-bot ensemble); this single-side approximation undercounts RANGE PnL potential. Variants tested only the SHORT side in RANGE, which means RANGE PnL ≈ 1698 USD / 122 episodes = $13.9/episode — but a true range-pair would roughly double this. **For comparing variant *mechanics*, single-side is sufficient. For absolute PnL claims, this is a floor estimate.**

6. **No transaction costs.** Sim does not subtract fees / funding / slippage. The PnL numbers are gross. Realistic net PnL on RANGE cell would shave 30-40% per trade × 358 trades = significant. Variant ordering is preserved under uniform fee assumption, but absolute magnitudes are optimistic.

7. **Sim does not model GinArea-specific behavior.** No instop, no indicator gate, no boundary expansion. The GridBotSim used is the calibration baseline (raw mode). Production GinArea bots have additional logic that affects realized PnL — this backtest tests *expansion variants in isolation*, not real-bot behavior.

8. **Single-asset (BTC).** XRP not tested. P8 ensemble eventually targets multi-asset; expand once design is validated.

---

## §7 Conclusions

_Empty placeholder — operator + MAIN to fill jointly during interpretation review._

---

## Appendix A — Reproducing the matrix

```bash
python scripts/_p8_run_matrix.py
```

Writes `docs/RESEARCH/_p8_raw_results.json` with structured per-cell data including `edge_cases` lists.

## Appendix B — Files touched

- `services/backtest/__init__.py` (new)
- `services/backtest/expansion_research.py` (new — harness)
- `scripts/_p8_run_matrix.py` (new — driver)
- `docs/RESEARCH/_p8_raw_results.json` (new — raw results, not committed normally)
- `docs/RESEARCH/P8_RGE_EXPANSION_RESULTS_v0_1.md` (this file)
