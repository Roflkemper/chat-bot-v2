# P-15 multi-asset projection (2026-05-11)

## 2y backtest results × pair-factor scaling

| Leg | PF | Raw PnL | Factor | Scaled PnL |
|---|---:|---:|---:|---:|
| BTCUSDT long | 3.84 | $+21,138 | 1.00 | $+21,138 |
| BTCUSDT short | 3.91 | $+19,133 | 1.00 | $+19,133 |
| ETHUSDT long | 3.36 | $+25,661 | 0.50 | $+12,830 |
| ETHUSDT short | 3.39 | $+18,196 | 0.50 | $+9,098 |
| XRPUSDT long | 3.48 | $+29,159 | 0.30 | $+8,748 |
| XRPUSDT short | 3.04 | $+21,965 | 0.30 | $+6,590 |
| **TOTAL** | — | **$+135,252** | — | **$+77,537** |

## Interpretation

Raw 2y PnL of $135k assumed equal $1000 base on all 6 legs — unrealistic
(BTC and XRP have very different market depth and slippage profiles).

Scaled allocation per `P15_PAIR_SIZE_FACTOR` (commit 0a7ac6b):
- **2y total: $+77,537** = **~$3,230/mo** target run-rate
- BTC contributes 52% of scaled PnL (40,271 of 77,537)
- ETH 28% (21,928)
- XRP 20% (15,338)

## What this assumes

1. All 6 legs run continuously, max 2 same-direction open at any time
   (cross-asset correlation cap enforced via `P15_MAX_SAME_DIRECTION_LEGS=2`).
2. ADVISOR_DEPO_TOTAL=$15,145 → P15_PCT_OF_DEPO=6.5% gives BTC base
   $984. ETH base $492. XRP base $295.
3. No slippage degradation beyond what was in the 2y backtest (~0.165% RT).
4. Trend regime distribution over next 2y matches last 2y.

## What this doesn't yet account for

- Margin coupling across legs when several open simultaneously
- Liquidity stress in XRP on $292 entries (acceptable; XRP futures avg
  depth at midprice is $50k+)
- Fee tier degradation if volume exceeds maker rebate band
- Funding rate accumulation on positions held >24h (typically negligible
  on P-15 cycle times)

## Action items

- [ ] Watch live P-15 equity over next 4 weeks for actual vs projected
      run-rate ($3,230/mo). Reports in daily KPI.
- [ ] If actual run-rate < 50% of projection by week 4, reconsider
      pair factors (maybe ETH should be 0.7 not 0.5).
- [ ] Track per-pair Sharpe in equity journal — large deviation
      between legs would suggest factor adjustment.
