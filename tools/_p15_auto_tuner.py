"""Stage D3 — P-15 auto-tuner.

Re-tunes (R%, K%, dd_cap%) on the most recent N days of BTC 1h+15m bars
and emits a recommendation if the new best is materially better than the
production parameters.

Production params (from services/setup_detector/p15_rolling.py):
  R_PCT       = 0.3
  K_PCT       = 1.0
  DD_CAP_PCT  = 3.0
  TF          = 15m

Algorithm:
  1. Load last `--days` days of BTCUSDT 15m + 1h klines (frozen 2y CSV).
  2. For each (R, K, dd_cap) in sweep grid → simulate harvest mode.
  3. Rank by Sharpe-per-trade × log(1+N), pick top.
  4. If top != production params AND PnL improvement ≥ 30% AND PF≥1.5 →
     emit a TG-style recommendation. Otherwise: 'no change'.

Run weekly via cron-style task. Pure read-only — does not modify code or
production state.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_15M = ROOT / "backtests" / "frozen" / "BTCUSDT_15m_2y.csv"
DATA_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"

PROD_R = 0.3
PROD_K = 1.0
PROD_DD = 3.0

FEE_BPS = 5.0


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _trend_gate(e50: float, e200: float, c: float, direction: str) -> bool:
    if direction == "short":
        return e50 > e200 and c > e50
    return e50 < e200 and c < e50


def simulate_harvest(df: pd.DataFrame, R_pct: float, K_pct: float, dd_cap_pct: float,
                     direction: str = "short", base: float = 1000.0,
                     max_reentries: int = 10) -> dict:
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    e50 = ema(df["close"], 50).values
    e200 = ema(df["close"], 200).values
    fee = FEE_BPS / 10000

    pnls: list[float] = []
    in_pos = False
    total = 0.0
    weighted = 0.0
    extreme = 0.0
    cum_dd = 0.0
    n_re = 0

    for i in range(200, len(close)):
        gate = _trend_gate(e50[i], e200[i], close[i], direction)
        c = close[i]
        if not in_pos and gate:
            in_pos = True
            total = base
            weighted = c * base
            extreme = c
            cum_dd = 0.0
            n_re = 0
            continue
        if in_pos:
            avg = weighted / total
            if direction == "short":
                extreme = max(extreme, high[i])
                adverse = (extreme - avg) / avg * 100.0
                retrace = (extreme - low[i]) / extreme * 100.0
                exit_p = extreme * (1 - R_pct / 100.0)
                reenter = exit_p * (1 + K_pct / 100.0)
            else:
                extreme = min(extreme, low[i])
                adverse = (avg - extreme) / avg * 100.0
                retrace = (high[i] - extreme) / extreme * 100.0
                exit_p = extreme * (1 + R_pct / 100.0)
                reenter = exit_p * (1 - K_pct / 100.0)
            cum_dd = max(cum_dd, adverse)
            if cum_dd >= dd_cap_pct:
                pnl_pct = (avg - c) / avg if direction == "short" else (c - avg) / avg
                pnls.append(total * (pnl_pct - 2 * fee))
                in_pos = False
                continue
            if not gate:
                pnl_pct = (avg - c) / avg if direction == "short" else (c - avg) / avg
                pnls.append(total * (pnl_pct - 2 * fee))
                in_pos = False
                continue
            if retrace >= R_pct and n_re < max_reentries:
                harvest = total * 0.5
                pnl_pct = (avg - exit_p) / avg if direction == "short" else (exit_p - avg) / avg
                pnls.append(harvest * (pnl_pct - fee))
                total -= harvest
                weighted -= avg * harvest
                weighted += reenter * base
                total += base
                n_re += 1
                extreme = reenter

    if in_pos:
        c = close[-1]
        avg = weighted / total
        pnl_pct = (avg - c) / avg if direction == "short" else (c - avg) / avg
        pnls.append(total * (pnl_pct - 2 * fee))

    arr = np.array(pnls) if pnls else np.array([0.0])
    n = len(pnls)
    pnl = float(arr.sum())
    wr = (arr > 0).sum() / max(n, 1) * 100
    sum_w = arr[arr > 0].sum()
    sum_l = -arr[arr < 0].sum()
    pf = float(sum_w / sum_l) if sum_l > 0 else (999.0 if sum_w > 0 else 0.0)
    std = arr.std(ddof=1) if n > 1 else 1.0
    sharpe = float(arr.mean() / std) if std > 0 else 0.0
    return {"R": R_pct, "K": K_pct, "dd": dd_cap_pct, "direction": direction,
            "N": n, "WR": round(wr, 1), "PF": round(pf, 2),
            "pnl": round(pnl, 2), "sharpe": round(sharpe, 3),
            "score": round(sharpe * np.log(1 + n), 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--direction", choices=("short", "long", "both"), default="both")
    args = ap.parse_args()

    df = pd.read_csv(DATA_15M).reset_index(drop=True)
    bars_per_day = 24 * 4   # 15m bars
    n_bars = args.days * bars_per_day + 300  # warmup
    if n_bars > len(df):
        print(f"WARN: requested {args.days}d but only {len(df)//bars_per_day}d available")
        n_bars = len(df)
    sl = df.iloc[-n_bars:].reset_index(drop=True)

    # Sweep
    R_grid = (0.2, 0.3, 0.4, 0.5)
    K_grid = (0.5, 1.0, 1.5)
    DD_grid = (2.0, 3.0, 5.0)
    directions = ("short", "long") if args.direction == "both" else (args.direction,)

    rows: list[dict] = []
    for direction in directions:
        for R in R_grid:
            for K in K_grid:
                for dd in DD_grid:
                    rows.append(simulate_harvest(sl, R, K, dd, direction))

    # Score-rank
    rows.sort(key=lambda r: -r["score"])

    print(f"[p15_auto_tuner] last {args.days}d window, {n_bars} bars (incl warmup)")
    print(f"  {'dir':<5} {'R':>4} {'K':>4} {'dd':>4} {'N':>4} {'WR':>5} {'PF':>6} "
          f"{'PnL$':>8} {'Sharpe':>6} {'score':>6}")
    print("  " + "-" * 65)
    for r in rows[:8]:
        print(f"  {r['direction']:<5} {r['R']:>4.1f} {r['K']:>4.1f} {r['dd']:>4.1f} "
              f"{r['N']:>4} {r['WR']:>5.1f} {r['PF']:>6.2f} {r['pnl']:>+8.1f} "
              f"{r['sharpe']:>+6.3f} {r['score']:>+6.3f}")

    # Find prod baseline for comparison
    def _prod(direction: str) -> dict | None:
        return next((r for r in rows if r["direction"] == direction
                     and abs(r["R"] - PROD_R) < 0.01
                     and abs(r["K"] - PROD_K) < 0.01
                     and abs(r["dd"] - PROD_DD) < 0.01), None)

    print()
    print("[p15_auto_tuner] PROD baseline vs best:")
    for direction in directions:
        prod = _prod(direction)
        best = next((r for r in rows if r["direction"] == direction), None)
        if prod is None or best is None:
            continue
        improvement = (best["pnl"] - prod["pnl"]) / max(abs(prod["pnl"]), 1.0) * 100
        same = (best["R"] == prod["R"] and best["K"] == prod["K"]
                and best["dd"] == prod["dd"])
        verdict = ("KEEP PROD" if same
                   else f"PROPOSE NEW (improvement {improvement:+.0f}% vs prod)"
                   if (improvement >= 30 and best["PF"] >= 1.5)
                   else "no clear winner")
        print(f"  {direction}: prod R={prod['R']:.1f} K={prod['K']:.1f} dd={prod['dd']:.1f} "
              f"-> PnL={prod['pnl']:+.1f}, PF={prod['PF']:.2f}")
        print(f"  {direction}: best R={best['R']:.1f} K={best['K']:.1f} dd={best['dd']:.1f} "
              f"-> PnL={best['pnl']:+.1f}, PF={best['PF']:.2f} | VERDICT: {verdict}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
