"""P-15 rolling-trend-rebalance backtest — TZ-P15-BACKTEST.

Hypothesis from docs/CANON/HYPOTHESES_BACKLOG.md §P-15:
  On confirmed uptrend, SHORT bot rolls: takes profit on retracement, then
  reenters higher. Tested under 3 market types (volatile / smooth / cascade).

Strategy under test (simplified to backtestable form):
  1. Trend onset gate: EMA50 > EMA200 AND last close > EMA50 (uptrend confirmed).
  2. Open SHORT at gate trigger, size = $1000 notional.
  3. Wait for retracement of R% from running high.
  4. Close SHORT at retracement (PnL = (entry - retrace_price) / entry * size).
  5. Reentry SHORT at retrace_price + K% (higher).
  6. Repeat until trend gate flips down (EMA50 < EMA200) → exit.
  7. Per-cycle drawdown cap: if SHORT goes -5% from entry → forced close (loss).

Sweep:
  R ∈ {0.3, 0.5, 0.8, 1.0, 1.5} %
  K ∈ {0.0, 0.3, 0.5, 1.0} %  (reentry offset above retrace low)

Output: per-(R,K) PnL, win rate, cycles count, max DD, sharpe-ish.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def simulate(df: pd.DataFrame, R_pct: float, K_pct: float,
             notional: float = 1000.0, dd_cap_pct: float = 5.0) -> dict:
    """Simulate P-15 rolling-trend rebalance. Returns metrics dict."""
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    e50 = ema(df["close"], 50).values
    e200 = ema(df["close"], 200).values

    trades: list[float] = []   # per-cycle PnL in USD
    in_short = False
    entry = 0.0
    running_high = 0.0   # since SHORT opened, tracks high water mark
    cycles_in_trend = 0
    forced_closes = 0

    for i in range(200, len(close)):
        trend_up = e50[i] > e200[i] and close[i] > e50[i]
        c = close[i]

        if not in_short and trend_up:
            in_short = True
            entry = c
            running_high = c
            continue

        if in_short:
            # End trend → exit
            if not trend_up:
                pnl = (entry - c) / entry * notional
                trades.append(pnl)
                in_short = False
                cycles_in_trend = 0
                continue

            running_high = max(running_high, high[i])
            # DD cap (SHORT loses when price climbs)
            adverse = (c - entry) / entry * 100.0
            if adverse >= dd_cap_pct:
                pnl = (entry - c) / entry * notional
                trades.append(pnl)
                forced_closes += 1
                in_short = False
                cycles_in_trend = 0
                continue

            # Retracement check: low fell R% from running_high
            retrace = (running_high - low[i]) / running_high * 100.0
            if retrace >= R_pct:
                exit_price = running_high * (1 - R_pct / 100.0)
                pnl = (entry - exit_price) / entry * notional
                trades.append(pnl)
                # Reentry K% above the retrace exit price (only if trend still up)
                if trend_up and cycles_in_trend < 20:
                    entry = exit_price * (1 + K_pct / 100.0)
                    running_high = entry
                    cycles_in_trend += 1
                else:
                    in_short = False
                    cycles_in_trend = 0

    if not trades:
        return {"R": R_pct, "K": K_pct, "N": 0, "WR": 0.0, "PF": 0.0,
                "total": 0.0, "max_dd": 0.0, "forced": 0}

    arr = np.array(trades)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    total = float(arr.sum())
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    wr = float(len(wins) / len(arr) * 100)
    cum = arr.cumsum()
    peak = np.maximum.accumulate(cum)
    dd = float((peak - cum).max())

    return {
        "R": R_pct, "K": K_pct, "N": len(arr),
        "WR": wr, "PF": pf, "total": total, "max_dd": dd, "forced": forced_closes,
    }


def main() -> int:
    print("=" * 90)
    print("P-15 ROLLING-TREND REBALANCE BACKTEST (BTCUSDT 1h, 2y)")
    print("=" * 90)
    df = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    print(f"  bars: {len(df)}")

    R_grid = [0.3, 0.5, 0.8, 1.0, 1.5]
    K_grid = [0.0, 0.3, 0.5, 1.0]

    print(f"\n  {'R%':>4} | {'K%':>4} | {'N':>4} | {'WR%':>5} | {'PF':>6} | {'PnL$':>8} | {'maxDD$':>7} | forced")
    print("  " + "-" * 70)
    rows = []
    for R in R_grid:
        for K in K_grid:
            m = simulate(df, R, K)
            pf_str = f"{m['PF']:.2f}" if m['PF'] != float('inf') else " inf"
            print(f"  {m['R']:>4.1f} | {m['K']:>4.1f} | {m['N']:>4} | "
                  f"{m['WR']:>5.1f} | {pf_str:>6} | {m['total']:>+8.0f} | "
                  f"{m['max_dd']:>7.0f} | {m['forced']}")
            rows.append(m)

    # Best by PnL
    best = max(rows, key=lambda r: r["total"])
    print("\n  BEST PnL config:")
    print(f"    R={best['R']}% K={best['K']}% -> {best['total']:+.0f}$ "
          f"(N={best['N']}, WR={best['WR']:.1f}%, PF={best['PF']:.2f}, maxDD={best['max_dd']:.0f}$)")

    if best["total"] <= 0:
        print("\n  WARN: No positive-edge config. P-15 hypothesis NOT VALIDATED on 2y 1h BTC.")
    else:
        print(f"\n  Positive edge at R={best['R']}, K={best['K']}.")
        print("  CAVEAT: simulation assumes immediate reentry; real grid has slippage and fees.")
        print("  Recommend dry-run + slippage haircut (~0.05% per cycle) before live activation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
