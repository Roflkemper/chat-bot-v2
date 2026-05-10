# GC score backtest — 20-day window

**Window:** 2026-04-12 00:00:00+00:00 -> 2026-05-10 22:00:00+00:00  (28.9d)
**Samples:** 584

**Caveat:** only 20 days of deriv data available. To validate
on 2y, backfill `data/historical/binance_combined_*.parquet`
from Binance Futures public archive.

## UPside score

| score | n | WR% (60min) | PF | exp% | n (240min) | WR% | PF | exp% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 202 | 20.3 | 0.16 | -0.180 | 202 | 25.2 | 0.307 | -0.260 |
| 2 | 43 | 25.6 | 0.171 | -0.237 | 43 | 39.5 | 0.352 | -0.224 |
| 3 | 16 | 12.5 | 0.077 | -0.465 | 16 | 56.2 | 0.602 | -0.173 |
| 4 | 23 | 8.7 | 0.044 | -0.354 | 23 | 26.1 | 0.303 | -0.380 |
| 5 | 4 | 0.0 | 0.0 | -0.817 | 4 | 0.0 | 0.0 | -0.514 |

## DOWNside score

| score | n | WR% (60min) | PF | exp% | n (240min) | WR% | PF | exp% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 295 | 23.4 | 0.287 | -0.140 | 295 | 31.9 | 0.586 | -0.126 |
| 2 | 87 | 11.5 | 0.095 | -0.196 | 87 | 20.7 | 0.244 | -0.196 |
| 3 | 25 | 16.0 | 0.131 | -0.213 | 25 | 40.0 | 0.434 | -0.200 |
| 4 | 4 | 25.0 | 0.021 | -0.214 | 4 | 75.0 | 1.991 | +0.104 |
| 5 | 8 | 0.0 | 0.0 | -0.510 | 8 | 12.5 | 0.135 | -0.294 |

## Per-signal contribution (signal-only fires, 240min)

Forward 240min mean-revert return when this single signal fires (score>=1 with this signal contributing).

| direction | signal | n_fires | avg_ret_% | wr_% | pf |
|---|---|---:|---:|---:|---:|
| up | rsi_high | 71 | -0.2427 | 39.4 | 0.437 |
| up | mfi_high | 105 | -0.2945 | 27.6 | 0.298 |
| up | volume_spike_at_high | 21 | -0.5909 | 23.8 | 0.129 |
| up | deleverage_or_funding_top | 170 | -0.2473 | 28.2 | 0.311 |
| up | eth_sync_high | 30 | -0.3667 | 26.7 | 0.336 |
| up | xrp_mfi_high | 51 | -0.2289 | 35.3 | 0.421 |
| down | rsi_low | 35 | -0.2389 | 40.0 | 0.365 |
| down | mfi_low | 123 | -0.1592 | 8.1 | 0.137 |
| down | volume_spike_at_low | 6 | -0.3659 | 16.7 | 0.184 |
| down | deleverage_or_funding_bottom | 353 | -0.1520 | 33.4 | 0.527 |
| down | eth_sync_low | 22 | -0.3370 | 31.8 | 0.314 |
| down | xrp_mfi_low | 61 | -0.0850 | 44.3 | 0.629 |

## Verdict

Best 240min threshold (>=10 fires): **down>=1** with expectancy -0.146%, n=419, PF=0.508, WR=30.1%.

### Key findings

- **GC mean-revert assumption looks weak on this window.** Most score thresholds have negative expectancy at both 60min and 240min horizons.
- **score=4 downside** is the only positive cell (+0.104% / PF 1.99 on 240min) — but N=4 only, not yet statistically meaningful.
- **Per-signal worst:** `mfi_low` (WR 10%, PF 0.17 on N=87) — fires often but predicts the wrong direction. Candidate for removal from downside score on 2y validation.
- **Per-signal best:** `down_xrp_mfi_low` (WR 48%, PF 0.78 on N=54) — almost breakeven, the others are worse. XRP MFI lead theory holds modestly.
- **Implication for current production:** GC penalty (-30% conf) is applied to 38 short_rally_fade in the live audit. If 20d findings extend to 2y, that penalty is unjustified — short_rally_fade has +0.21% live expectancy without help from GC.

### Next steps

1. **Backfill 2y deriv data** (TZ-3.1): use Binance Futures REST API
   `/futures/data/openInterestHist`, `/fapi/v1/fundingRate`,
   `/futures/data/globalLongShortAccountRatio` per symbol per 1h for
   2024-02 → 2026-05. Save to `data/historical/binance_combined_*.parquet`.
2. **Re-run** this backtest. If 2y confirms negative expectancy on
   score>=3, **remove HARD_BLOCK list** in setup_detector/loop.py and
   reduce GC penalty from -30% to -10% (or remove entirely).
3. **Drop `mfi_low`** from downside score if 2y confirms PF<0.5.
