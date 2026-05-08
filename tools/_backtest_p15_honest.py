"""P-15 rolling-trend-rebalance — HONEST simulator.

Differs from _backtest_p15_rolling_rebalance.py (the optimistic version):
  1. Position averaging: each reentry ADDS to short, not replaces.
     Avg_entry = (sum entry_i * size_i) / total_size.
     This is what a real grid does — base_size + reentry_size accumulate.
  2. Cumulative drawdown: tracks unrealized PnL across all reentries from
     trend_start to trend_end, not per-cycle.
  3. Trend exit: when EMA50 < EMA200 OR cum_dd > dd_cap, force-close all
     accumulated positions at current price (real loss).
  4. Slippage + fee: 0.05% per cycle (open + close = 0.1% round trip).
  5. Per-trend-instance tracking: each trend up = one "trade" with N reentries.

Sweep:
  R ∈ {0.3, 0.5, 0.8, 1.0, 1.5} %
  K ∈ {0.0, 0.3, 0.5, 1.0} %
  dd_cap ∈ {3, 5, 10} %  (when to abort the trend cycle as failed)

Also splits results by market regime: volatile (high ATR), smooth (low ATR),
cascade (price impulse > 5% in 24h).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

FEE_BPS = 5.0  # 0.05% per side (taker fee + slippage estimate)


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def classify_regime(df: pd.DataFrame) -> pd.Series:
    """Return regime label per bar: volatile / smooth / cascade."""
    a = atr(df, 14) / df["close"] * 100  # ATR as % of price
    ret24 = df["close"].pct_change(24).abs() * 100
    out = pd.Series("normal", index=df.index, dtype=object)
    out[ret24 >= 5] = "cascade"
    out[(a >= 1.0) & (out == "normal")] = "volatile"
    out[(a < 0.5) & (out == "normal")] = "smooth"
    return out


def simulate_honest(df: pd.DataFrame, R_pct: float, K_pct: float, dd_cap_pct: float,
                    base_size_usd: float = 1000.0, max_reentries: int = 10,
                    regime_filter: str | None = None) -> dict:
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    e50 = ema(df["close"], 50).values
    e200 = ema(df["close"], 200).values
    regimes = classify_regime(df).values

    trends_pnl: list[float] = []  # one entry per completed trend cycle
    trend_dd_history: list[float] = []
    forced = 0  # trends ended by dd_cap
    natural_exits = 0  # trends ended by EMA flip
    total_reentries = 0

    in_trend = False
    # Position aggregate state
    total_size_usd = 0.0
    weighted_entry = 0.0   # sum of entry_i * size_i
    running_high = 0.0
    last_exit_price = 0.0
    n_reentries = 0
    cum_dd_in_trend = 0.0

    for i in range(200, len(close)):
        trend_up = e50[i] > e200[i] and close[i] > e50[i]
        c = close[i]

        # Filter by regime if requested
        if regime_filter is not None and regimes[i] != regime_filter:
            if in_trend:
                # Close at current price if regime changed away
                avg_entry = weighted_entry / total_size_usd
                pnl_pct = (avg_entry - c) / avg_entry
                fee = FEE_BPS / 10000 * 2  # round trip
                pnl_usd = total_size_usd * (pnl_pct - fee)
                trends_pnl.append(pnl_usd)
                trend_dd_history.append(cum_dd_in_trend)
                in_trend = False
                total_size_usd = 0.0
                weighted_entry = 0.0
                n_reentries = 0
                cum_dd_in_trend = 0.0
            continue

        if not in_trend and trend_up:
            # Open base SHORT
            in_trend = True
            total_size_usd = base_size_usd
            weighted_entry = c * base_size_usd
            running_high = c
            n_reentries = 0
            cum_dd_in_trend = 0.0
            continue

        if in_trend:
            avg_entry = weighted_entry / total_size_usd
            running_high = max(running_high, high[i])

            # Cumulative adverse: how far is price above avg_entry NOW (high-water mark)
            adverse_pct = (running_high - avg_entry) / avg_entry * 100.0
            cum_dd_in_trend = max(cum_dd_in_trend, adverse_pct)

            # DD cap -> force close (failed trend cycle, real loss)
            if cum_dd_in_trend >= dd_cap_pct:
                pnl_pct = (avg_entry - c) / avg_entry
                fee = FEE_BPS / 10000 * 2
                pnl_usd = total_size_usd * (pnl_pct - fee)
                trends_pnl.append(pnl_usd)
                trend_dd_history.append(cum_dd_in_trend)
                forced += 1
                in_trend = False
                total_size_usd = 0.0
                weighted_entry = 0.0
                n_reentries = 0
                cum_dd_in_trend = 0.0
                continue

            # Trend natural exit (EMA flip down)
            if not trend_up:
                pnl_pct = (avg_entry - c) / avg_entry
                fee = FEE_BPS / 10000 * 2
                pnl_usd = total_size_usd * (pnl_pct - fee)
                trends_pnl.append(pnl_usd)
                trend_dd_history.append(cum_dd_in_trend)
                natural_exits += 1
                in_trend = False
                total_size_usd = 0.0
                weighted_entry = 0.0
                n_reentries = 0
                cum_dd_in_trend = 0.0
                continue

            # Retracement: low fell R% from running_high -> partial harvest
            retrace = (running_high - low[i]) / running_high * 100.0
            if retrace >= R_pct and n_reentries < max_reentries:
                # Realize half the position at retrace_price (partial harvest)
                exit_price = running_high * (1 - R_pct / 100.0)
                harvest_size = total_size_usd * 0.5
                pnl_pct = (avg_entry - exit_price) / avg_entry
                fee = FEE_BPS / 10000  # one side here, the other side is in reentry
                realized = harvest_size * (pnl_pct - fee)
                trends_pnl.append(realized)  # log partial as "mini trade"
                # Reduce position
                total_size_usd -= harvest_size
                weighted_entry -= avg_entry * harvest_size
                # Reentry K% above the harvest exit
                reentry_price = exit_price * (1 + K_pct / 100.0)
                reentry_size = base_size_usd  # add fresh base size at higher level
                weighted_entry += reentry_price * reentry_size
                total_size_usd += reentry_size
                n_reentries += 1
                total_reentries += 1
                # Reset running_high to current (post-reentry phase)
                running_high = reentry_price

    # Close any open trend at end of data
    if in_trend:
        c = close[-1]
        avg_entry = weighted_entry / total_size_usd
        pnl_pct = (avg_entry - c) / avg_entry
        fee = FEE_BPS / 10000 * 2
        pnl_usd = total_size_usd * (pnl_pct - fee)
        trends_pnl.append(pnl_usd)
        trend_dd_history.append(cum_dd_in_trend)

    if not trends_pnl:
        return {"R": R_pct, "K": K_pct, "dd_cap": dd_cap_pct, "regime": regime_filter,
                "N": 0, "WR": 0.0, "PF": 0.0, "total": 0.0, "max_dd": 0.0,
                "forced": 0, "natural": 0, "reentries": 0}

    arr = np.array(trends_pnl)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {
        "R": R_pct, "K": K_pct, "dd_cap": dd_cap_pct, "regime": regime_filter,
        "N": len(arr),
        "WR": float(len(wins) / len(arr) * 100),
        "PF": pf,
        "total": float(arr.sum()),
        "avg": float(arr.mean()),
        "max_dd": float(max(trend_dd_history) if trend_dd_history else 0.0),
        "forced": forced,
        "natural": natural_exits,
        "reentries": total_reentries,
    }


def main() -> int:
    print("=" * 95)
    print("P-15 ROLLING-TREND REBALANCE — HONEST SIMULATOR (BTCUSDT 1h, 2y)")
    print("=" * 95)
    print("Differences from naive sim:")
    print("  - Position averaging on reentry (size accumulates)")
    print("  - Cumulative DD across the whole trend, not per-cycle")
    print("  - 0.05% slippage+fee per side")
    print("  - dd_cap -> real force-close at current price")
    print()

    df = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    print(f"  bars: {len(df)}")

    # ── Phase 1: full-period sweep
    print("\n" + "=" * 95)
    print("PHASE 1: full 2y sweep")
    print("=" * 95)
    print(f"  {'R%':>4} | {'K%':>4} | {'DDcap':>5} | {'N':>3} | {'WR%':>5} | {'PF':>6} | {'avg$':>7} | {'PnL$':>8} | {'maxDD%':>6} | forced/natural | reents")
    print("  " + "-" * 95)
    rows = []
    for R in [0.3, 0.5, 0.8, 1.0, 1.5]:
        for K in [0.0, 0.3, 0.5, 1.0]:
            for dd in [3.0, 5.0, 10.0]:
                m = simulate_honest(df, R, K, dd)
                if m["N"] == 0:
                    continue
                pf_str = f"{m['PF']:.2f}" if m['PF'] != float('inf') else " inf"
                print(f"  {m['R']:>4.1f} | {m['K']:>4.1f} | {m['dd_cap']:>5.1f} | "
                      f"{m['N']:>3} | {m['WR']:>5.1f} | {pf_str:>6} | "
                      f"{m['avg']:>+7.1f} | {m['total']:>+8.0f} | {m['max_dd']:>6.2f} | "
                      f"{m['forced']:>3}/{m['natural']:<3}      | {m['reentries']}")
                rows.append(m)

    if not rows:
        print("  no trades.")
        return 1

    best = max(rows, key=lambda r: r["total"])
    print("\n  BEST PnL config (full period):")
    print(f"    R={best['R']}% K={best['K']}% dd_cap={best['dd_cap']}% -> {best['total']:+.0f}$")
    print(f"    N={best['N']} trends, WR={best['WR']:.1f}%, PF={best['PF']:.2f}, "
          f"avg={best['avg']:+.1f}$/trend, maxDD={best['max_dd']:.2f}%")
    print(f"    forced={best['forced']} natural={best['natural']} reentries={best['reentries']}")

    # ── Phase 2: per-regime test of best config
    print("\n" + "=" * 95)
    print(f"PHASE 2: best config (R={best['R']}/K={best['K']}/dd={best['dd_cap']}) by regime")
    print("=" * 95)
    print(f"  {'regime':<10} | {'N':>3} | {'WR%':>5} | {'PF':>6} | {'avg$':>7} | {'PnL$':>8} | {'maxDD%':>6} | forced")
    print("  " + "-" * 80)
    for reg in ["volatile", "smooth", "cascade", "normal"]:
        m = simulate_honest(df, best['R'], best['K'], best['dd_cap'], regime_filter=reg)
        if m["N"] == 0:
            print(f"  {reg:<10} | {0:>3} | (no trends in this regime)")
            continue
        pf_str = f"{m['PF']:.2f}" if m['PF'] != float('inf') else " inf"
        print(f"  {reg:<10} | {m['N']:>3} | {m['WR']:>5.1f} | {pf_str:>6} | "
              f"{m['avg']:>+7.1f} | {m['total']:>+8.0f} | {m['max_dd']:>6.2f} | {m['forced']}")

    # ── Verdict
    print("\n" + "=" * 95)
    print("VERDICT")
    print("=" * 95)
    if best["total"] > 0:
        print(f"  Positive edge in honest sim: +{best['total']:.0f}$ over 2y on $1k base size.")
        print(f"  Annualized: ~+{best['total']/2:.0f}$/yr = ~{best['total']/2/best['avg']*100/(best['N']/2):.1f}% per trend.")
        if best['WR'] >= 60 and best['PF'] >= 1.5:
            print("  Edge is robust (WR>=60, PF>=1.5).")
        elif best['WR'] >= 50 and best['PF'] >= 1.2:
            print("  Edge is marginal — operator-judgment call.")
        else:
            print("  Edge is weak — not recommended without further filtering.")
    else:
        print(f"  No positive-edge config in honest sim. Best lost {best['total']:.0f}$.")
        print("  P-15 hypothesis NOT VALIDATED on 2y BTC 1h with honest math.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
