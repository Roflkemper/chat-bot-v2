"""Dual-leg oscillation harvesting — operator's actual setup.

Reality check (operator clarification 2026-05-08):
  Operator runs TWO contracts on SAME asset (BTC):
    - LONG contract (BTCUSDT linear)  — earns on price up
    - SHORT contract (BTCUSD inverse) — earns on price down
  Both bots active simultaneously. On flat market BTC oscillates 1-2 % over
  1-5 days. Each oscillation: LONG harvests up-move, SHORT harvests down-move.
  Net = 2x edge per full cycle.

Key params per operator:
  - LINEAR size (fixed $1000 per leg, not averaging — predictability)
  - take_profit $TP per leg (close whole leg at +$TP, reopen)
  - Two legs independent, sum PnL

Scenarios tested:
  TP_USD ∈ {1, 3, 5, 10, 20}      — bot's tpAuto value
  reentry_mode ∈ {immediate, wait_K_pct}  — reopen right after close, or wait pullback
  K_pct (if wait) ∈ {0.1, 0.3, 0.5}        — pullback before reentry

Markets tested separately:
  flat (RANGE)        — operator's main income
  trending up
  trending down
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

FEE_BPS = 5.0   # 0.05% per side


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean() / c * 100


def classify_market(df: pd.DataFrame) -> pd.Series:
    """Per-bar regime: flat / up / down. Operator's flat = ATR<1% AND price within EMA200±2%."""
    e200 = ema(df["close"], 200)
    a = atr_pct(df, 14)
    dev = (df["close"] - e200) / e200 * 100
    out = pd.Series("normal", index=df.index, dtype=object)
    out[(a < 1.0) & (dev.abs() < 2.0)] = "flat"
    out[dev > 2.0] = "up"
    out[dev < -2.0] = "down"
    return out


def simulate_leg(df: pd.DataFrame, *, direction: str, tp_usd: float,
                 reentry_mode: str = "immediate", K_pct: float = 0.0,
                 size_usd: float = 1000.0,
                 regime_filter: str | None = None) -> dict:
    """Single-leg sim. direction='long' or 'short'.

    State machine per bar:
      - if not in pos and gate ok → open at close[i] (immediate) or wait
      - if in pos and (high/low) crossed TP target → close at TP price, log PnL
      - after close, if reentry_mode='immediate': re-open next bar
        else: wait until pullback K% from close price, then reopen
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    regimes = classify_market(df).values

    fee = FEE_BPS / 10000
    pnls: list[float] = []
    in_pos = False
    entry = 0.0
    waiting_for_pullback = False
    last_close_price = 0.0
    n_open = 0

    for i in range(200, len(close)):
        if regime_filter is not None and regimes[i] != regime_filter:
            # If currently in pos and regime changed away — close at current price
            if in_pos:
                pnl_pct = (close[i] - entry) / entry if direction == "long" else (entry - close[i]) / entry
                pnls.append(size_usd * (pnl_pct - 2 * fee))
                in_pos = False
                waiting_for_pullback = False
            continue

        if not in_pos:
            if waiting_for_pullback:
                # Reopen when price pulled back K% from last close
                if direction == "long":
                    target = last_close_price * (1 - K_pct / 100.0)
                    if low[i] <= target:
                        entry = target
                        in_pos = True
                        waiting_for_pullback = False
                        n_open += 1
                else:  # short
                    target = last_close_price * (1 + K_pct / 100.0)
                    if high[i] >= target:
                        entry = target
                        in_pos = True
                        waiting_for_pullback = False
                        n_open += 1
            else:
                # Immediate: open at close[i]
                entry = close[i]
                in_pos = True
                n_open += 1
            continue

        # In position — check TP hit (intra-bar)
        if direction == "long":
            tp_price = entry * (1 + tp_usd / size_usd)
            if high[i] >= tp_price:
                pnl = size_usd * ((tp_price - entry) / entry - 2 * fee)
                pnls.append(pnl)
                last_close_price = tp_price
                in_pos = False
                waiting_for_pullback = (reentry_mode == "wait_K_pct")
                if reentry_mode == "immediate":
                    # Reopen at close[i] (post-TP price ≈ tp_price + drift)
                    entry = close[i]
                    in_pos = True
                    n_open += 1
        else:  # short
            tp_price = entry * (1 - tp_usd / size_usd)
            if low[i] <= tp_price:
                pnl = size_usd * ((entry - tp_price) / entry - 2 * fee)
                pnls.append(pnl)
                last_close_price = tp_price
                in_pos = False
                waiting_for_pullback = (reentry_mode == "wait_K_pct")
                if reentry_mode == "immediate":
                    entry = close[i]
                    in_pos = True
                    n_open += 1

    if not pnls:
        return _empty(direction, tp_usd, reentry_mode, K_pct, regime_filter)

    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    std = arr.std(ddof=1) if len(arr) > 1 else 1.0
    sharpe = float(arr.mean() / std) if std > 0 else 0.0
    return {
        "direction": direction, "tp_usd": tp_usd,
        "reentry": reentry_mode, "K": K_pct, "regime": regime_filter,
        "N": len(arr), "WR": float(len(wins) / len(arr) * 100),
        "PF": pf, "total": float(arr.sum()), "avg": float(arr.mean()),
        "sharpe": sharpe, "n_open": n_open,
    }


def _empty(direction, tp, reentry, K, regime):
    return {"direction": direction, "tp_usd": tp, "reentry": reentry, "K": K,
            "regime": regime, "N": 0, "WR": 0.0, "PF": 0.0, "total": 0.0,
            "avg": 0.0, "sharpe": 0.0, "n_open": 0}


def simulate_dual(df, **kwargs) -> dict:
    """Run both legs in parallel, sum PnLs."""
    long_res = simulate_leg(df, direction="long", **kwargs)
    short_res = simulate_leg(df, direction="short", **kwargs)
    return {
        "tp_usd": kwargs["tp_usd"],
        "reentry": kwargs["reentry_mode"],
        "K": kwargs.get("K_pct", 0.0),
        "regime": kwargs.get("regime_filter"),
        "long_pnl": long_res["total"], "long_N": long_res["N"], "long_PF": long_res["PF"],
        "short_pnl": short_res["total"], "short_N": short_res["N"], "short_PF": short_res["PF"],
        "total": long_res["total"] + short_res["total"],
        "total_N": long_res["N"] + short_res["N"],
    }


def main() -> int:
    print("=" * 110)
    print("DUAL-LEG OSCILLATION HARVESTING (LONG + SHORT contracts on BTC, parallel)")
    print("=" * 110)
    print("Operator setup: 2 bots on same asset, both directions, linear size, tp_auto.")
    print("Edge thesis: on flat market, each oscillation gives both legs a harvest.")
    print()

    df_15m = pd.read_csv("backtests/frozen/BTCUSDT_15m_2y.csv").reset_index(drop=True)
    print(f"  bars 15m: {len(df_15m)}")
    regimes = classify_market(df_15m)
    print(f"  regime split: flat={(regimes=='flat').sum()}  "
          f"up={(regimes=='up').sum()}  down={(regimes=='down').sum()}  "
          f"normal={(regimes=='normal').sum()}")

    # ── Section 1: dual-leg sweep, all-period
    print("\n" + "=" * 110)
    print("SECTION 1: DUAL-LEG TP SWEEP (15m, all-period, immediate reentry)")
    print("=" * 110)
    print(f"  {'TP$':>5} | {'reentry':<10} | {'K':>4} | "
          f"{'long N':>6} {'long PnL':>9} {'long PF':>7} | "
          f"{'short N':>7} {'short PnL':>9} {'short PF':>7} | "
          f"{'total':>9}")
    print("  " + "-" * 105)

    rows = []
    for tp in (1.0, 3.0, 5.0, 10.0, 20.0):
        for reentry, K in (("immediate", 0.0),
                           ("wait_K_pct", 0.1), ("wait_K_pct", 0.3), ("wait_K_pct", 0.5)):
            r = simulate_dual(df_15m, tp_usd=tp, reentry_mode=reentry, K_pct=K)
            rows.append(r)
            print(f"  {tp:>5.1f} | {reentry:<10} | {K:>4.1f} | "
                  f"{r['long_N']:>6} {r['long_pnl']:>+9.0f} {r['long_PF']:>7.2f} | "
                  f"{r['short_N']:>7} {r['short_pnl']:>+9.0f} {r['short_PF']:>7.2f} | "
                  f"{r['total']:>+9.0f}")

    best = max(rows, key=lambda r: r["total"])
    print(f"\n  BEST all-period: TP=${best['tp_usd']:.0f} "
          f"reentry={best['reentry']} K={best['K']} -> total {best['total']:+.0f}$")

    # ── Section 2: best config by regime
    print("\n" + "=" * 110)
    print(f"SECTION 2: BEST CONFIG (TP=${best['tp_usd']:.0f}, "
          f"reentry={best['reentry']}, K={best['K']}) BY REGIME")
    print("=" * 110)
    print(f"  {'regime':<8} | {'long N':>6} {'long PnL':>9} {'long PF':>7} | "
          f"{'short N':>7} {'short PnL':>9} {'short PF':>7} | {'total':>9}")
    print("  " + "-" * 95)
    for reg in ("flat", "up", "down", "normal"):
        r = simulate_dual(df_15m, tp_usd=best["tp_usd"],
                          reentry_mode=best["reentry"], K_pct=best["K"],
                          regime_filter=reg)
        print(f"  {reg:<8} | "
              f"{r['long_N']:>6} {r['long_pnl']:>+9.0f} {r['long_PF']:>7.2f} | "
              f"{r['short_N']:>7} {r['short_pnl']:>+9.0f} {r['short_PF']:>7.2f} | "
              f"{r['total']:>+9.0f}")

    # ── Section 3: per-TP edge in flat regime only
    print("\n" + "=" * 110)
    print("SECTION 3: TP SWEEP FILTERED TO FLAT REGIME ONLY")
    print("=" * 110)
    print(f"  {'TP$':>5} | {'reentry':<10} | {'K':>4} | "
          f"{'long N':>6} {'long PnL':>9} | {'short N':>7} {'short PnL':>9} | {'total':>9}")
    print("  " + "-" * 90)
    flat_rows = []
    for tp in (1.0, 3.0, 5.0, 10.0, 20.0):
        for reentry, K in (("immediate", 0.0), ("wait_K_pct", 0.3)):
            r = simulate_dual(df_15m, tp_usd=tp, reentry_mode=reentry, K_pct=K,
                              regime_filter="flat")
            flat_rows.append(r)
            print(f"  {tp:>5.1f} | {reentry:<10} | {K:>4.1f} | "
                  f"{r['long_N']:>6} {r['long_pnl']:>+9.0f} | "
                  f"{r['short_N']:>7} {r['short_pnl']:>+9.0f} | "
                  f"{r['total']:>+9.0f}")

    best_flat = max(flat_rows, key=lambda r: r["total"])
    print(f"\n  BEST flat-only: TP=${best_flat['tp_usd']:.0f} "
          f"reentry={best_flat['reentry']} K={best_flat['K']} "
          f"-> total {best_flat['total']:+.0f}$")

    # ── Section 4: TP=5 across all TFs (1h vs 15m)
    print("\n" + "=" * 110)
    print("SECTION 4: TP=$5 IMMEDIATE REENTRY — TF COMPARISON")
    print("=" * 110)
    df_1h = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    for tf_name, df in (("1h", df_1h), ("15m", df_15m)):
        r = simulate_dual(df, tp_usd=5.0, reentry_mode="immediate", K_pct=0.0)
        print(f"  TF={tf_name:<3}  long_N={r['long_N']}  long_pnl={r['long_pnl']:+.0f}  "
              f"short_N={r['short_N']}  short_pnl={r['short_pnl']:+.0f}  "
              f"TOTAL={r['total']:+.0f}$")

    # ── Verdict
    print("\n" + "=" * 110)
    print("OPERATOR-MODEL VERDICT")
    print("=" * 110)
    print(f"  Best dual-leg config (full period): "
          f"TP=${best['tp_usd']:.0f} reentry={best['reentry']} K={best['K']}")
    print(f"    annualized: ~{best['total']/2:+.0f}$/yr on $1000 base size per leg")
    print(f"  Best dual-leg config (FLAT regime only): "
          f"TP=${best_flat['tp_usd']:.0f} reentry={best_flat['reentry']} K={best_flat['K']}")
    print(f"    flat-period PnL: {best_flat['total']:+.0f}$ "
          f"(operator's main income source)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
