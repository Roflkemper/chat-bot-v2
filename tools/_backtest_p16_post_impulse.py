"""P-16 post-impulse-booster backtest — TZ-P16-BACKTEST.

Hypothesis from docs/CANON/HYPOTHESES_BACKLOG.md §P-16:
  After an impulse stops at resistance, open a SHORT booster bot with hard
  border.top above recent high. Take profit on pullback or break-even on
  border hit.

Strategy under test:
  1. Detect impulse: 4h-window return >= X% (X sweep: 3/5/8).
  2. Detect exhaustion: next bar makes lower high (no follow-through).
  3. Open SHORT at exhaustion bar close.
  4. border.top = impulse_high * (1 + offset%); if hit → forced close (loss).
  5. Take profit at entry * (1 - tp%).
  6. Time stop: 24h or 48h (sweep).

Sweep:
  X (impulse %)  ∈ {3, 5, 8}
  border offset  ∈ {0.3, 0.5, 0.8, 1.0} %
  tp             ∈ {0.5, 1.0, 1.5, 2.0} %
  time stop      = 48h (fixed)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))


def simulate(df: pd.DataFrame, X_pct: float, border_pct: float, tp_pct: float,
             time_stop_bars: int = 48, notional: float = 1000.0) -> dict:
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    trades: list[float] = []
    forced = 0
    timeouts = 0

    i = 4
    while i < len(close) - time_stop_bars:
        # Impulse window = last 4 bars
        w_low = low[i - 4]
        w_high = max(high[i - 3:i + 1])
        impulse = (w_high - w_low) / w_low * 100.0
        if impulse < X_pct:
            i += 1
            continue
        # Exhaustion: current bar high < previous bar high
        if not (high[i] < high[i - 1]):
            i += 1
            continue

        entry = close[i]
        border = w_high * (1 + border_pct / 100.0)
        tp_price = entry * (1 - tp_pct / 100.0)

        # Walk forward
        outcome = None
        for j in range(i + 1, min(i + 1 + time_stop_bars, len(close))):
            if high[j] >= border:
                pnl = (entry - border) / entry * notional
                trades.append(pnl)
                forced += 1
                outcome = "border"
                break
            if low[j] <= tp_price:
                pnl = (entry - tp_price) / entry * notional
                trades.append(pnl)
                outcome = "tp"
                break
        if outcome is None:
            pnl = (entry - close[min(i + time_stop_bars, len(close) - 1)]) / entry * notional
            trades.append(pnl)
            timeouts += 1

        # Skip ahead past this trade
        i += time_stop_bars

    if not trades:
        return {"X": X_pct, "border": border_pct, "tp": tp_pct, "N": 0,
                "WR": 0.0, "PF": 0.0, "total": 0.0, "forced": 0, "timeout": 0}

    arr = np.array(trades)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {
        "X": X_pct, "border": border_pct, "tp": tp_pct,
        "N": len(arr), "WR": float(len(wins) / len(arr) * 100),
        "PF": pf, "total": float(arr.sum()),
        "forced": forced, "timeout": timeouts,
    }


def main() -> int:
    print("=" * 90)
    print("P-16 POST-IMPULSE-BOOSTER BACKTEST (BTCUSDT 1h, 2y)")
    print("=" * 90)
    df = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    print(f"  bars: {len(df)}")

    X_grid = [3.0, 5.0, 8.0]
    B_grid = [0.3, 0.5, 0.8, 1.0]
    TP_grid = [0.5, 1.0, 1.5, 2.0]

    print(f"\n  {'X%':>3} | {'B%':>4} | {'TP%':>4} | {'N':>3} | {'WR%':>5} | {'PF':>6} | {'PnL$':>7} | forced/timeout")
    print("  " + "-" * 70)
    rows = []
    for X in X_grid:
        for B in B_grid:
            for TP in TP_grid:
                m = simulate(df, X, B, TP)
                if m["N"] == 0:
                    continue
                pf_str = f"{m['PF']:.2f}" if m['PF'] != float('inf') else " inf"
                print(f"  {m['X']:>3.0f} | {m['border']:>4.1f} | {m['tp']:>4.1f} | "
                      f"{m['N']:>3} | {m['WR']:>5.1f} | {pf_str:>6} | "
                      f"{m['total']:>+7.0f} | {m['forced']}/{m['timeout']}")
                rows.append(m)

    if rows:
        best = max(rows, key=lambda r: r["total"])
        print("\n  BEST PnL:")
        print(f"    X={best['X']}% border={best['border']}% TP={best['tp']}% "
              f"-> {best['total']:+.0f}$ (N={best['N']}, WR={best['WR']:.1f}%, "
              f"PF={best['PF']:.2f})")
        if best["total"] <= 0:
            print("\n  WARN: No positive-edge config in sweep.")
        else:
            print("\n  Positive edge found. Manual activation by operator (per design).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
