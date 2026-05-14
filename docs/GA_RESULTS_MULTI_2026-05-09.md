# GA Multi-Asset Results — Stage E1+ (2026-05-09)

**Source:** `state/ga_multi_results.jsonl`
**Compute:** ~819 evaluations × 4-fold walk-forward × (BTC + ETH + XRP)
**Fitness:** PF × log(1+N) × stability_penalty (penalty=1 if 3+/4 STABLE)

## Verdict distribution
- STABLE:   28 / 819 evaluations (3.4%)
- MARGINAL: 264 / 819
- OVERFIT:  527 / 819

## Best STABLE genome — wired as detector

`SHORT_MFI_MULTI_GA` ([services/setup_detector/mfi_multi_ga.py](../services/setup_detector/mfi_multi_ga.py))

| Field | Value |
|---|---|
| Signal | MFI(14) < 71.3 on BTC 1h |
| Trend gate | disabled (replaced by multi-asset gates) |
| Volume filter | vol_z(20) ≥ 1.0 |
| **ETH correlation gate** | **BTC↔ETH 30h Pearson ≥ 0.76** |
| **XRP lead** | **XRP MFI < 71.3 in last 4 bars** |
| SL | 1.43% (above entry — SHORT) |
| TP1 RR | 3.9 (≈ +5.58%) |
| Hold horizon | 1h max |
| Direction | SHORT |

### Walk-forward metrics
- **N total:** 406 trades over 2 years (≈ 200/year — high frequency)
- **WR:** 59.2%
- **PF:** 2.78
- **Per-fold PF:** 5.62 / 1.90 / 2.84 / 0.75 — 3/4 above 1.5

### Why multi-asset is meaningful here
Pure single-asset MFI fades (MFI<71 + vol spike) have N too high but PF
mediocre — too many false tops. Adding two cross-asset filters drastically
raises edge:

1. **ETH correlation** — ensures the move isn't BTC-isolated. When ETH is
   moving in sync, an MFI fade on BTC is a *broad-distribution* event, not a
   single-asset hiccup quickly bought back.

2. **XRP lead** — XRP is more volatile and tends to lead BTC by 1-4 hours
   on similar moves. Confirming XRP already started fading raises the
   probability that BTC will follow.

The 1h hold horizon matches the typical fade duration: this is a *quick
fade*, not a trend trade. If the drop doesn't come within an hour, exit
small.

## Cross-comparison vs single-asset GA (Stage E1)

| Metric | LONG_RSI_MOMENTUM_GA (single) | SHORT_MFI_MULTI_GA (multi) |
|---|---:|---:|
| Direction | LONG | SHORT |
| PF (2y) | 2.05 | **2.78** |
| WR | 57.4% | **59.2%** |
| N (2y) | 125 | **406** |
| Hold horizon | 24h | 1h |
| Folds positive | 3/4 | 3/4 |

The multi-asset variant generates **3.2× more signals** at higher PF —
a clearly better risk-adjusted edge. They are also **complementary** by
direction: LONG_RSI_MOMENTUM (uptrend continuation) + SHORT_MFI_MULTI
(top fade) — together cover both market sides.

## Other STABLE multi-asset genomes
The next 9 unique STABLE genomes are MFI variations (threshold 67-71)
with ETH correlation gate consistently. **All 10 best converge on the
same family.** This is GA validating the edge through neighborhood —
the pattern is robust.

## Risks
- **Companion data dependency** — needs ETH and XRP klines fetched live.
  Implementation reads via `core.data_loader.load_klines` (cached). If
  Binance API down for one of them, detector silently skips (returns None).
- **Forward-looking** — fold 4 PF=0.75 is the only marginal fold (early
  2026). If 2026 regime keeps trending, multi-asset fades may underperform.
  Set up monitoring on 30-day rolling PF < 1.3.
- **Correlation regime change** — if BTC and ETH decouple in future
  (e.g. ETH-specific catalyst), the corr gate disables almost all fires.
  Acceptable: detector should fire less but not generate bad trades.

## Production rollout
- Wired to DETECTOR_REGISTRY (will fire alongside existing detectors)
- Will paper-trade for first 30 days via existing paper_trader
- After 30 days: compare live PF vs backtest 2.78. Operator decision on
  promotion to confirmed signals.
