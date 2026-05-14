"""Dual independent legs — operator's actual setup.

Operator clarification (2026-05-08):
  - Two bots on same asset, INDEPENDENT (don't know about each other)
  - Each has own conditions, own TP/SL, own activation
  - Run on shared balance
  - DO NOT close in minus — instead average down (add to position)
  - More frequent entries with each its own profit target
  - Linear add size (predictable), but position averages

Logic per leg:
  Trend gate active:
    - Open base $1000 at close
  In position:
    - If adverse >= K_add%, ADD $1000 at current price (average down)
      until max_layers reached or dd_cap_pct breached
    - If retrace R% from extreme price → harvest 50% at exit_price (+K%
      offset reentry above/below depending on direction) — this is the
      P-15 harvest mechanic
    - If gate flips → close all at current price (only natural exit)
    - DO NOT close at adverse alone (no SL except dd_cap_pct safety)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

FEE_BPS = 5.0


def ema(s, n): return s.ewm(span=n, adjust=False).mean()


def _gate(e50, e200, c, direction):
    if direction == "long":
        return e50 > e200 and c > e50
    return e50 < e200 and c < e50


def simulate_leg(df, *, direction, R_pct, K_pct, K_add_pct, dd_cap_pct,
                 add_size_usd=1000.0, max_layers=10):
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    e50 = ema(df["close"], 50).values
    e200 = ema(df["close"], 200).values
    fee = FEE_BPS / 10000

    pnls = []
    forced = 0
    natural = 0
    in_pos = False
    total_size = 0.0
    weighted_entry = 0.0  # sum entry_i * size_i
    extreme = 0.0          # running_high (long) / running_low (short)
    last_add_price = 0.0
    layers = 0
    cum_dd = 0.0

    for i in range(200, len(close)):
        gate = _gate(e50[i], e200[i], close[i], direction)
        c = close[i]

        if not in_pos and gate:
            in_pos = True
            total_size = add_size_usd
            weighted_entry = c * add_size_usd
            extreme = c
            last_add_price = c
            layers = 1
            cum_dd = 0.0
            continue

        if not in_pos:
            continue

        avg_entry = weighted_entry / total_size

        if direction == "long":
            extreme = max(extreme, high[i])  # running_high since entry
            adverse_from_avg = (avg_entry - low[i]) / avg_entry * 100
            adverse_from_last_add = (last_add_price - low[i]) / last_add_price * 100
            retrace = (extreme - low[i]) / extreme * 100  # not used for long retrace logic
            # For long: harvest on a PULLBACK (low went down R% from extreme high)
            harvest_trigger = retrace >= R_pct
            exit_at = extreme * (1 - R_pct / 100.0)
            reentry_at = exit_at * (1 + K_pct / 100.0)  # reentry above retrace exit
        else:  # short
            extreme = min(extreme, low[i])  # running_low since entry
            adverse_from_avg = (high[i] - avg_entry) / avg_entry * 100
            adverse_from_last_add = (high[i] - last_add_price) / last_add_price * 100
            retrace = (high[i] - extreme) / extreme * 100  # bounce up from low
            harvest_trigger = retrace >= R_pct
            exit_at = extreme * (1 + R_pct / 100.0)
            reentry_at = exit_at * (1 - K_pct / 100.0)

        cum_dd = max(cum_dd, adverse_from_avg)

        # Safety dd_cap (rare emergency exit, last resort)
        if cum_dd >= dd_cap_pct:
            pnl_pct = ((c - avg_entry) / avg_entry) if direction == "long" else ((avg_entry - c) / avg_entry)
            pnls.append(total_size * (pnl_pct - 2 * fee))
            forced += 1
            in_pos = False
            total_size = 0.0
            weighted_entry = 0.0
            layers = 0
            continue

        # Operator rule: DO NOT close at minus on gate flip.
        # Gate flip can be a natural exit ONLY if PnL is positive.
        if not gate:
            pnl_pct = ((c - avg_entry) / avg_entry) if direction == "long" else ((avg_entry - c) / avg_entry)
            pnl_at_now = total_size * (pnl_pct - 2 * fee)
            if pnl_at_now > 0:
                pnls.append(pnl_at_now)
                natural += 1
                in_pos = False
                total_size = 0.0
                weighted_entry = 0.0
                layers = 0
                continue
            # else: hold, wait for next harvest opportunity / dd_cap / liquidation

        # Average-down: if adverse from last add >= K_add%, add another layer
        if adverse_from_last_add >= K_add_pct and layers < max_layers:
            if direction == "long":
                add_price = last_add_price * (1 - K_add_pct / 100.0)
            else:
                add_price = last_add_price * (1 + K_add_pct / 100.0)
            weighted_entry += add_price * add_size_usd
            total_size += add_size_usd
            last_add_price = add_price
            layers += 1
            # don't continue; harvest may also trigger same bar
            avg_entry = weighted_entry / total_size

        # Harvest 50% on retrace
        if harvest_trigger and layers > 0:
            harvest_size = total_size * 0.5
            pnl_pct_harvest = ((exit_at - avg_entry) / avg_entry) if direction == "long" else ((avg_entry - exit_at) / avg_entry)
            pnl = harvest_size * (pnl_pct_harvest - fee)
            # Only log harvest if profitable (operator: "не закрывать в минус")
            if pnl > 0:
                pnls.append(pnl)
                total_size -= harvest_size
                weighted_entry -= avg_entry * harvest_size
                # Reentry layer
                weighted_entry += reentry_at * add_size_usd
                total_size += add_size_usd
                last_add_price = reentry_at
                extreme = reentry_at  # reset

    if in_pos:
        c = close[-1]
        avg_entry = weighted_entry / total_size
        pnl_pct = ((c - avg_entry) / avg_entry) if direction == "long" else ((avg_entry - c) / avg_entry)
        pnls.append(total_size * (pnl_pct - 2 * fee))

    if not pnls:
        return _zero(direction, R_pct, K_pct, K_add_pct, dd_cap_pct)

    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    std = arr.std(ddof=1) if len(arr) > 1 else 1.0
    sharpe = float(arr.mean() / std) if std > 0 else 0.0
    return {
        "direction": direction, "R": R_pct, "K": K_pct, "K_add": K_add_pct,
        "dd_cap": dd_cap_pct,
        "N": len(arr), "WR": float(len(wins) / len(arr) * 100),
        "PF": pf, "total": float(arr.sum()), "avg": float(arr.mean()),
        "sharpe": sharpe, "forced": forced, "natural": natural,
    }


def _zero(d, R, K, Ka, dd):
    return {"direction": d, "R": R, "K": K, "K_add": Ka, "dd_cap": dd,
            "N": 0, "WR": 0.0, "PF": 0.0, "total": 0.0, "avg": 0.0,
            "sharpe": 0.0, "forced": 0, "natural": 0}


def simulate_dual(df, **kwargs):
    long_r = simulate_leg(df, direction="long", **kwargs)
    short_r = simulate_leg(df, direction="short", **kwargs)
    # Normalize keys for the printer
    return {
        "R_pct": kwargs["R_pct"], "K_pct": kwargs["K_pct"],
        "K_add_pct": kwargs["K_add_pct"], "dd_cap_pct": kwargs["dd_cap_pct"],
        "dd_cap": kwargs["dd_cap_pct"],
        "long_N": long_r["N"], "long_pnl": long_r["total"], "long_PF": long_r["PF"],
        "long_WR": long_r["WR"], "long_forced": long_r["forced"],
        "short_N": short_r["N"], "short_pnl": short_r["total"], "short_PF": short_r["PF"],
        "short_WR": short_r["WR"], "short_forced": short_r["forced"],
        "total": long_r["total"] + short_r["total"],
    }


def main():
    print("=" * 110)
    print("DUAL INDEPENDENT LEGS — operator model (no SL minus, average down + P-15 harvest)")
    print("=" * 110)

    df_15m = pd.read_csv("backtests/frozen/BTCUSDT_15m_2y.csv").reset_index(drop=True)
    df_1h = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    print(f"  15m: {len(df_15m)} bars   1h: {len(df_1h)} bars")
    print()
    print("Logic: each leg opens on its trend gate, averages down at K_add%,")
    print("       harvests 50% on R% retrace (only if profitable),")
    print("       reentries at K% offset, exits naturally on gate flip.")
    print("       dd_cap is emergency safety only.")

    # Sweep
    print("\n" + "=" * 110)
    print("SECTION 1: 15m PARAM SWEEP")
    print("=" * 110)
    print(f"  {'R':>4} {'K':>4} {'K_add':>5} {'dd':>4} | "
          f"LONG: {'N':>4} {'WR':>5} {'PF':>5} {'PnL$':>7} {'fc':>3} | "
          f"SHORT:{'N':>4} {'WR':>5} {'PF':>5} {'PnL$':>7} {'fc':>3} | "
          f"{'TOTAL$':>8}")
    print("  " + "-" * 105)

    rows = []
    for R in (0.3, 0.5, 0.8):
        for K in (0.3, 0.5, 1.0):
            for K_add in (0.5, 1.0, 1.5):
                r = simulate_dual(df_15m, R_pct=R, K_pct=K,
                                  K_add_pct=K_add, dd_cap_pct=5.0)
                rows.append(r)
                print(f"  {R:>4.1f} {K:>4.1f} {K_add:>5.1f} {r['dd_cap']:>4.1f} | "
                      f"      {r['long_N']:>4} {r['long_WR']:>4.1f} {r['long_PF']:>5.2f} "
                      f"{r['long_pnl']:>+7.0f} {r['long_forced']:>3} | "
                      f"      {r['short_N']:>4} {r['short_WR']:>4.1f} {r['short_PF']:>5.2f} "
                      f"{r['short_pnl']:>+7.0f} {r['short_forced']:>3} | "
                      f"{r['total']:>+8.0f}")

    best = max(rows, key=lambda r: r["total"])
    print(f"\n  BEST 15m: R={best['R_pct']} K={best['K_pct']} "
          f"K_add={best['K_add_pct']} dd={best['dd_cap_pct']}  ->  "
          f"TOTAL {best['total']:+.0f}$")
    print(f"    long: {best['long_pnl']:+.0f}$ (N={best['long_N']}, WR={best['long_WR']:.1f}%, "
          f"PF={best['long_PF']:.2f}, forced={best['long_forced']})")
    print(f"    short: {best['short_pnl']:+.0f}$ (N={best['short_N']}, WR={best['short_WR']:.1f}%, "
          f"PF={best['short_PF']:.2f}, forced={best['short_forced']})")

    # Compare 1h
    print("\n" + "=" * 110)
    print(f"SECTION 2: 1h with same best params")
    print("=" * 110)
    r1h = simulate_dual(df_1h, R_pct=best["R_pct"], K_pct=best["K_pct"],
                        K_add_pct=best["K_add_pct"], dd_cap_pct=best["dd_cap_pct"])
    print(f"  long:  N={r1h['long_N']}, WR={r1h['long_WR']:.1f}%, "
          f"PF={r1h['long_PF']:.2f}, PnL={r1h['long_pnl']:+.0f}$, forced={r1h['long_forced']}")
    print(f"  short: N={r1h['short_N']}, WR={r1h['short_WR']:.1f}%, "
          f"PF={r1h['short_PF']:.2f}, PnL={r1h['short_pnl']:+.0f}$, forced={r1h['short_forced']}")
    print(f"  TOTAL: {r1h['total']:+.0f}$")

    # Per-direction edge analysis
    print("\n" + "=" * 110)
    print("SECTION 3: edge by direction (15m, top 5 configs)")
    print("=" * 110)
    rows_sorted = sorted(rows, key=lambda r: r["total"], reverse=True)[:5]
    for i, r in enumerate(rows_sorted, 1):
        print(f"  #{i}: R={r['R_pct']} K={r['K_pct']} K_add={r['K_add_pct']}  "
              f"long={r['long_pnl']:+.0f}$ ({r['long_PF']:.2f}PF)  "
              f"short={r['short_pnl']:+.0f}$ ({r['short_PF']:.2f}PF)  "
              f"total={r['total']:+.0f}$")

    return 0


if __name__ == "__main__":
    sys.exit(main())
