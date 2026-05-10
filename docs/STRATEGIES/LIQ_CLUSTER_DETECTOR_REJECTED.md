# Liquidations cluster detector — REJECTED (2026-05-10)

**File deleted:** `services/setup_detector/liq_cluster_detector.py`
**Backtest tool kept:** `tools/_liq_cluster_backtest.py` (research artifact)

## Hypothesis

When $1M+ of LONG liquidations cluster in a 5-minute window AND SHORT
liquidations are <30% of that, the market has just absorbed the worst of
forced selling — bounce probability rises. Symmetric for SHORT.

## Why rejected

### 1. Backtest result on 12 days (2026-04-19 → 2026-05-02)

```
LONG  signals: ~few, total PnL  -1.95%
SHORT signals: ~few, total PnL -11.34%
```

Both directions unprofitable on the small window we have. SHORT side
particularly bad in a bullish/range-up market.

### 2. Historical data unavailability

`market_live/liquidations/` (per-exchange daily parquets): only **4 days**
of meaningful data — 2026-04-28 to 2026-05-02, ~17k rows total.

To validate this detector on 2y, we'd need:
- Binance Futures historical liquidations (no public archive endpoint —
  must collect live or use 3rd-party aggregator like Coinglass)
- ETH/XRP equivalents

Current data volume is **two orders of magnitude** below what's needed
for walk-forward validation. The 12d backtest is anecdotal at best.

### 3. The detector was never wired

The file was written 2026-05-10 morning batch, never added to
`DETECTOR_REGISTRY` in `setup_types.py`. So it was costing nothing
in production — just sitting as dead code on the disk.

## Decision

- **Delete** `services/setup_detector/liq_cluster_detector.py`. Avoids
  future confusion ("is this used? why not?").
- **Keep** `tools/_liq_cluster_backtest.py` as a research artifact —
  if a 30+ day liquidations dataset materializes, this tool runs the
  test in 30 seconds.
- **Re-evaluate** if/when:
  - We accumulate 90+ days of `market_live/liquidations/` data, OR
  - Coinglass / 3rd-party historical liquidations become available

## Related

- `tools/_liq_cluster_backtest.py` (kept)
- Original commit introducing the detector: see git log for
  `liq_cluster_detector.py`
- This rejection: commit `<this commit hash>`
