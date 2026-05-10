# P-15 + grid_coordinator confluence

**Period:** 365d BTC | **GC threshold:** score >= 3

## GC state distribution over period

- Total 1h ticks: 8711
- GC downside>=3 (oversold, LONG-aligned): 459 (5.3%)
- GC upside>=3 (overbought, SHORT-aligned): 392 (4.5%)
- GC neutral (both<3): 7860 (90.2%)

## P-15 baseline (no GC filter)

- LONG: N=1094, PnL=$7215, PF=3.49
- SHORT: N=1012, PnL=$7900, PF=3.99
- COMBINED: $15115

## Limitation

P15Result is summary-level (PnL totals, not per-trade list). To do true per-trade GC bucketing, we need to extend simulate_p15_harvest to return trade events with timestamps. This v1 only shows GC distribution as context.

## Next step

If operator wants to filter P-15 by GC: refactor simulate_p15_harvest to log trade-by-trade timestamps + entry/exit PnL, then compute PnL distribution by GC bucket.