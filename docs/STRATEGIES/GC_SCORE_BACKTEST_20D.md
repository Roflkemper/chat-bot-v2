# GC score backtest — 20-day window

**Window:** 2026-04-19 02:00:00+00:00 -> 2026-05-09 22:00:00+00:00  (20.8d)
**Samples:** 501

**Caveat:** only 20 days of deriv data available. To validate
on 2y, backfill `data/historical/binance_combined_*.parquet`
from Binance Futures public archive.

## UPside score

| score | n | WR% (60min) | PF | exp% | n (240min) | WR% | PF | exp% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 153 | 20.3 | 0.122 | -0.203 | 153 | 24.2 | 0.257 | -0.321 |
| 2 | 38 | 26.3 | 0.187 | -0.209 | 38 | 42.1 | 0.474 | -0.152 |
| 3 | 14 | 14.3 | 0.09 | -0.448 | 14 | 50.0 | 0.479 | -0.293 |
| 4 | 20 | 5.0 | 0.008 | -0.365 | 20 | 30.0 | 0.41 | -0.313 |
| 5 | 4 | 0.0 | 0.0 | -0.817 | 4 | 0.0 | 0.0 | -0.514 |

## DOWNside score

| score | n | WR% (60min) | PF | exp% | n (240min) | WR% | PF | exp% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 243 | 24.3 | 0.291 | -0.144 | 243 | 36.2 | 0.631 | -0.113 |
| 2 | 77 | 13.0 | 0.114 | -0.181 | 77 | 22.1 | 0.296 | -0.166 |
| 3 | 20 | 10.0 | 0.069 | -0.252 | 20 | 40.0 | 0.428 | -0.216 |
| 4 | 4 | 25.0 | 0.021 | -0.214 | 4 | 75.0 | 1.991 | +0.104 |
| 5 | 7 | 0.0 | 0.0 | -0.553 | 7 | 14.3 | 0.135 | -0.334 |

## Per-signal contribution (signal-only fires, 240min)

Forward 240min mean-revert return when this single signal fires (score>=1 with this signal contributing).

| direction | signal | n_fires | avg_ret_% | wr_% | pf |
|---|---|---:|---:|---:|---:|
| up | rsi_high | 66 | -0.2459 | 39.4 | 0.446 |
| up | mfi_high | 96 | -0.2955 | 27.1 | 0.311 |
| up | volume_spike_at_high | 20 | -0.5916 | 25.0 | 0.134 |
| up | deleverage_or_funding_top | 119 | -0.2726 | 29.4 | 0.323 |
| up | eth_sync_high | 26 | -0.4087 | 23.1 | 0.33 |
| up | xrp_mfi_high | 44 | -0.2014 | 36.4 | 0.464 |
| down | rsi_low | 29 | -0.2769 | 37.9 | 0.335 |
| down | mfi_low | 87 | -0.1552 | 10.3 | 0.173 |
| down | volume_spike_at_low | 6 | -0.3659 | 16.7 | 0.184 |
| down | deleverage_or_funding_bottom | 312 | -0.1349 | 35.3 | 0.56 |
| down | eth_sync_low | 20 | -0.3863 | 30.0 | 0.284 |
| down | xrp_mfi_low | 54 | -0.0454 | 48.1 | 0.776 |

## Verdict

Best 240min threshold (>=10 fires): **down>=1** with expectancy -0.132%, n=351, PF=0.55, WR=33.3%.

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
