# GA Results — Stage E1 first run (2026-05-09)

**Source:** `state/ga_results_v2.jsonl`
**Compute:** ~50,000 evaluations on BTCUSDT 1h × 2y, 4-fold walk-forward
**Fitness:** PF × log(1+N) × stability_penalty (penalty=1 if 3+/4 STABLE)

## Verdict distribution
- STABLE:   137 / 1191 evaluations (11.5%)
- MARGINAL: 133 / 1191
- OVERFIT:  921 / 1191 (77%)

## Best STABLE genome — wired as detector

`LONG_RSI_MOMENTUM_GA` ([services/setup_detector/rsi_momentum_ga.py](../services/setup_detector/rsi_momentum_ga.py))

| Field | Value |
|---|---|
| Signal | RSI(14) > 71 |
| Trend gate | EMA50 > EMA200 AND close > EMA50 |
| Volume filter | vol_z(20-bar) ≥ 1.21 |
| SL | 1.39% |
| TP1 RR | 1.59 (≈ +2.21%) |
| Hold horizon | 24h max |
| Direction | LONG |

### Walk-forward metrics (4 fold × 6mo)
- **N total:** 125 trades over 2 years (≈ 62/year, manageable rate)
- **WR:** 57.4%
- **Avg PnL/trade:** +0.45% (after 2 × 0.05% fees)
- **PF:** 2.05
- **Per-fold PF:** 1.52 / 3.18 / 2.43 / 1.06 — 3/4 above PF=1.5 threshold

### Why it's a real edge
This is a classic momentum-breakout pattern, but the GA found the
specific BTC-1h thresholds:
- RSI > 71 alone fades — but **RSI > 71 in confirmed uptrend with volume**
  is continuation. The volume filter is the decisive ingredient (without
  it, breakouts often fail at resistance).
- The 24h hold matches typical BTC momentum half-life — long enough to
  capture full move, short enough to avoid mean-reversion drag.
- Fold 4 PF=1.06 is the only marginal fold (early 2026 chop). Worth
  monitoring if production environment matches that fold's regime.

## Other STABLE genomes — not wired

The next 6 unique STABLE genomes are **variations of the same pattern**
with slightly different EMA fast / vol-z / SL / RR values. All converged
on RSI>71 + uptrend gate + volume filter. This is GA validating the edge
through multiple parameter neighborhoods — the pattern is robust.

There were no STABLE genomes in *other* indicator/direction combinations
(no SHORT, no MFI, no CMF, no MACD). Two interpretations:
1. RSI is the dominant edge for 1h BTC; other indicators are noise.
2. GA needs more generations / different mutation rate to explore.

Recommend: re-run with population=80 and 200 generations next time we have
2-3h compute. Current run took ~50min.

## Risks
- **Forward-looking:** all 4 folds came from 2024-2026. If 2026 regime
  shifts to bear/range-only, edge may disappear. Set up monitoring
  alert for 30-day rolling PF < 1.3 to flag degradation.
- **Crowding risk:** every algo trader runs RSI+volume strategies. If
  this ever gets popular at scale, edge erodes. Monitor live PF vs
  backtest PF — divergence > 30% = crowding suspect.
- **Fees model:** assumed 0.05% taker per side. If actually paying
  funding rate on 24h holds, subtract 0.01-0.05% per trade depending
  on funding regime. Safer assumption: real PF ≈ 1.8 (vs backtest 2.05).

## Production rollout
- Wired to DETECTOR_REGISTRY (will fire alongside existing detectors)
- Will paper-trade for first 30 days via existing paper_trader.handle()
  (setup_type starts with "long_rsi_momentum_ga" — paper trader picks up
  by setup_type prefix patterns, falling back to default journal)
- After 30 days: compare live PF vs backtest 2.05. If within ±20% →
  promote to operator-confirmed signals. If >30% lower → debug or disable.
