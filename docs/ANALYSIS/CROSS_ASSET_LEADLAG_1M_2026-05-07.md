# Cross-asset lead-lag on 1m bars (BTC / ETH / XRP) — 2026-05-07

**Question:** does ETH or XRP lead BTC (or vice versa) by 1-5 minutes on 1m frame?
On 1h frame lead-lag was already 0; this is the 1m follow-up.

**Method:** inner-join 1m closes for BTC/ETH/XRP, last 90 days
(2026-02-06 → 2026-05-07, 129,601 aligned bars). Log returns. Pearson cross-correlation
at lags `±10` minutes for each pair. Plus rolling 30-day windows for stability check.

**Source:** `scripts/cross_asset_leadlag_1m.py`
**Raw output:** `state/cross_asset_leadlag_1m.json`, `state/cross_asset_leadlag_1m.md`

## Global peak lag (90d, ±10 min)

| Pair | Peak lag (min) | Peak corr | Corr@lag=0 |
|---|---|---|---|
| BTC ↔ ETH | **0** | **0.8735** | 0.8735 |
| BTC ↔ XRP | **0** | **0.7869** | 0.7869 |
| ETH ↔ XRP | **0** | **0.7821** | 0.7821 |

For every pair the peak is exactly at lag = 0. Correlation collapses by ~50–100×
as soon as we move 1 minute either way. Highest non-zero-lag value is `BTC↔ETH @ lag=-1`
with corr `0.0202` — nothing actionable.

Off-zero corr distribution (all 60 non-zero lags across 3 pairs): all values within
`[-0.0093, +0.0202]`. Pure noise band; no second peak.

## Rolling 30d stability

Two non-overlapping 30d windows (Mar 8 → Apr 7, Apr 7 → May 7):

| Pair | W1 peak lag | W1 peak corr | W2 peak lag | W2 peak corr |
|---|---|---|---|---|
| BTC ↔ ETH | 0 | 0.874 | 0 | 0.869 |
| BTC ↔ XRP | 0 | 0.790 | 0 | 0.767 |
| ETH ↔ XRP | 0 | 0.788 | 0 | 0.770 |

100% of windows agree: peak at lag = 0. No regime in the last 90d shows a non-zero
lead-lag peak.

## Trader interpretation

- Confirms the 1h finding at finer resolution: **BTC/ETH/XRP are synchronous on 1m
  within Binance USDT-perp**. There is no exploitable 1–5 minute "alt leads BTC"
  (or vice versa) signal at this granularity.
- Off-zero correlations are in the `±0.01` noise band — too small to overcome
  spread + fees + execution latency. Even if you regressed BTC[t] on ETH[t-1m]
  the slope coefficient would explain `0.02² ≈ 0.04%` of variance.
- Implication for the bot: do **not** spend effort on cross-asset advance-warning
  features (e.g. "ETH spiked 1m ago → BTC about to move"). Whatever lead exists
  lives below the 1m bar — you would need tick / sub-second data and direct
  exchange feeds to even attempt to capture it, and that is well outside our
  current architecture.
- The *contemporaneous* correlation (`0.78–0.87`) is high — useful for hedging /
  beta neutralisation, **not** for prediction.

## Caveats

- 1m close-to-close contains microstructure noise; a true 30s or 10s lead would
  be averaged out. We cannot rule out sub-minute lead from this data.
- 90-day window covers a single broad market regime; an extreme news event might
  briefly create a lead-lag (e.g. ETF-flow shocks hitting BTC first). Not visible
  in aggregate stats.
- Pearson is linear. A non-linear lead (e.g. only large moves propagate with
  delay) would not show up here. Out of scope for this study.

## Verdict

**No edge.** Across 90 days of 1m data, every BTC/ETH/XRP pair peaks at lag = 0
with corr 0.78–0.87, and every off-zero lag (±1…±10 min) sits within the
`±0.02` noise band. Both rolling 30d windows confirm the same. There is no
1–5 minute cross-asset lead-lag tradable at 1m resolution on these instruments.
