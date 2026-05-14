"""P-15 rolling rebalance — FULL exploration: LONG + SHORT, 1h + 15m, TP mode.

Extends _backtest_p15_honest.py with:
  1. Direction sweep: SHORT on uptrend (original) + LONG on downtrend (mirror).
  2. Timeframe sweep: 1h + 15m.
  3. TP mode: close ENTIRE position when unrealized >= TP_USD.
     Mirrors the bot's `take_profit` parameter where the whole grid closes
     at +$X profit and reopens fresh when conditions re-fire.
  4. Sharpe ratio + Sortino computed for acceptance criteria.
  5. Walk-forward: 4 folds (each 6 months), test edge stability over time.

Two operating modes simulated:
  A) "harvest" (the original P-15) — close 50% on R% retrace, reentry K% above.
  B) "tp-flat" (the bot's take_profit) — close 100% when unrealized >= $TP,
     wait for trend gate to flip OFF and back ON before reopening.

For LONG mirror: gate is EMA50<EMA200 AND close<EMA50, position is LONG,
retracement is BOUNCE upward, K% offset is BELOW reentry.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

FEE_BPS = 5.0  # 0.05% per side


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _trend_gate(e50: float, e200: float, c: float, direction: str) -> bool:
    if direction == "short":  # uptrend -> bot opens SHORT
        return e50 > e200 and c > e50
    return e50 < e200 and c < e50  # downtrend -> bot opens LONG


def _pnl_pct(entry: float, exit_price: float, direction: str) -> float:
    if direction == "short":
        return (entry - exit_price) / entry
    return (exit_price - entry) / entry


# ── Mode A: harvest+reentry (original P-15) ──────────────────────────────────


def simulate_harvest(df: pd.DataFrame, R_pct: float, K_pct: float, dd_cap_pct: float,
                     direction: str = "short", base_size_usd: float = 1000.0,
                     max_reentries: int = 10) -> dict:
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    e50 = ema(df["close"], 50).values
    e200 = ema(df["close"], 200).values

    trades_pnl: list[float] = []
    forced = 0
    natural = 0
    in_trend = False
    total_size = 0.0
    weighted_entry = 0.0
    extreme = 0.0  # running_high for short, running_low for long
    cum_dd = 0.0
    n_reentries = 0
    fee = FEE_BPS / 10000

    for i in range(200, len(close)):
        gate = _trend_gate(e50[i], e200[i], close[i], direction)
        c = close[i]

        if not in_trend and gate:
            in_trend = True
            total_size = base_size_usd
            weighted_entry = c * base_size_usd
            extreme = c
            n_reentries = 0
            cum_dd = 0.0
            continue

        if in_trend:
            avg_entry = weighted_entry / total_size
            if direction == "short":
                extreme = max(extreme, high[i])
                adverse_pct = (extreme - avg_entry) / avg_entry * 100.0
                retrace_pct = (extreme - low[i]) / extreme * 100.0
                exit_at = extreme * (1 - R_pct / 100.0)
                reentry_at = exit_at * (1 + K_pct / 100.0)
            else:  # long
                extreme = min(extreme, low[i])
                adverse_pct = (avg_entry - extreme) / avg_entry * 100.0
                retrace_pct = (high[i] - extreme) / extreme * 100.0
                exit_at = extreme * (1 + R_pct / 100.0)
                reentry_at = exit_at * (1 - K_pct / 100.0)

            cum_dd = max(cum_dd, adverse_pct)

            if cum_dd >= dd_cap_pct:
                pnl = total_size * (_pnl_pct(avg_entry, c, direction) - fee * 2)
                trades_pnl.append(pnl)
                forced += 1
                in_trend = False
                total_size = 0.0
                weighted_entry = 0.0
                continue

            if not gate:
                pnl = total_size * (_pnl_pct(avg_entry, c, direction) - fee * 2)
                trades_pnl.append(pnl)
                natural += 1
                in_trend = False
                total_size = 0.0
                weighted_entry = 0.0
                continue

            if retrace_pct >= R_pct and n_reentries < max_reentries:
                harvest_size = total_size * 0.5
                pnl = harvest_size * (_pnl_pct(avg_entry, exit_at, direction) - fee)
                trades_pnl.append(pnl)
                total_size -= harvest_size
                weighted_entry -= avg_entry * harvest_size
                weighted_entry += reentry_at * base_size_usd
                total_size += base_size_usd
                n_reentries += 1
                extreme = reentry_at

    if in_trend:
        c = close[-1]
        avg_entry = weighted_entry / total_size
        pnl = total_size * (_pnl_pct(avg_entry, c, direction) - fee * 2)
        trades_pnl.append(pnl)

    return _summarize(trades_pnl, forced, natural, R_pct, K_pct, dd_cap_pct, direction, "harvest")


# ── Mode B: tp-flat (bot's take_profit param) ────────────────────────────────


def simulate_tp_flat(df: pd.DataFrame, tp_usd: float, dd_cap_pct: float,
                     direction: str = "short", base_size_usd: float = 1000.0) -> dict:
    """Close ENTIRE position when unrealized PnL >= tp_usd. Reopen on next gate trigger.

    Mirrors the bot's `take_profit` parameter: whole grid closes at +$X
    (bot's tpAuto), waits for fresh entry conditions, then reopens.
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    e50 = ema(df["close"], 50).values
    e200 = ema(df["close"], 200).values

    trades_pnl: list[float] = []
    forced = 0
    tp_hit = 0
    natural = 0
    in_trend = False
    entry = 0.0
    extreme = 0.0
    cum_dd = 0.0
    fee = FEE_BPS / 10000

    for i in range(200, len(close)):
        gate = _trend_gate(e50[i], e200[i], close[i], direction)
        c = close[i]

        if not in_trend and gate:
            in_trend = True
            entry = c
            extreme = c
            cum_dd = 0.0
            continue

        if in_trend:
            if direction == "short":
                extreme = max(extreme, high[i])
                adverse_pct = (extreme - entry) / entry * 100.0
                # Best price for closing short = lowest low
                best_close = low[i]
                pnl_at_best = (entry - best_close) / entry * base_size_usd
            else:
                extreme = min(extreme, low[i])
                adverse_pct = (entry - extreme) / entry * 100.0
                best_close = high[i]
                pnl_at_best = (best_close - entry) / entry * base_size_usd

            cum_dd = max(cum_dd, adverse_pct)

            # TP hit (whole position closes at TP target price)
            if pnl_at_best >= tp_usd:
                # Compute exact close price that yields tp_usd profit
                if direction == "short":
                    close_price = entry * (1 - tp_usd / base_size_usd)
                else:
                    close_price = entry * (1 + tp_usd / base_size_usd)
                pnl = base_size_usd * (_pnl_pct(entry, close_price, direction) - fee * 2)
                trades_pnl.append(pnl)
                tp_hit += 1
                in_trend = False
                continue

            # DD cap -> forced close
            if cum_dd >= dd_cap_pct:
                pnl = base_size_usd * (_pnl_pct(entry, c, direction) - fee * 2)
                trades_pnl.append(pnl)
                forced += 1
                in_trend = False
                continue

            # Trend flip -> natural close
            if not gate:
                pnl = base_size_usd * (_pnl_pct(entry, c, direction) - fee * 2)
                trades_pnl.append(pnl)
                natural += 1
                in_trend = False
                continue

    if in_trend:
        c = close[-1]
        pnl = base_size_usd * (_pnl_pct(entry, c, direction) - fee * 2)
        trades_pnl.append(pnl)

    out = _summarize(trades_pnl, forced, natural, tp_usd, 0.0, dd_cap_pct, direction, "tp-flat")
    out["tp_hit"] = tp_hit
    return out


def _summarize(pnls: list[float], forced: int, natural: int,
               R: float, K: float, dd: float, direction: str, mode: str) -> dict:
    if not pnls:
        return {"mode": mode, "direction": direction, "R": R, "K": K, "dd_cap": dd,
                "N": 0, "WR": 0.0, "PF": 0.0, "total": 0.0, "avg": 0.0,
                "sharpe": 0.0, "sortino": 0.0, "forced": 0, "natural": 0}
    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    # Sharpe-ish (per-trade): mean / std × sqrt(N) — annualize by time later
    std = arr.std(ddof=1) if len(arr) > 1 else 1.0
    sharpe_per_trade = float(arr.mean() / std) if std > 0 else 0.0
    downside = arr[arr < 0].std(ddof=1) if (arr < 0).sum() > 1 else std
    sortino_per_trade = float(arr.mean() / downside) if downside > 0 else 0.0
    return {
        "mode": mode, "direction": direction,
        "R": R, "K": K, "dd_cap": dd,
        "N": len(arr), "WR": float(len(wins) / len(arr) * 100),
        "PF": pf, "total": float(arr.sum()), "avg": float(arr.mean()),
        "sharpe": sharpe_per_trade, "sortino": sortino_per_trade,
        "forced": forced, "natural": natural,
    }


# ── Walk-forward (4 folds) ────────────────────────────────────────────────────


def walk_forward(df: pd.DataFrame, simulator, params: dict, n_folds: int = 4) -> list[dict]:
    fold_size = len(df) // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else len(df)
        fold_df = df.iloc[start:end].reset_index(drop=True)
        m = simulator(fold_df, **params)
        m["fold"] = k + 1
        out.append(m)
    return out


def print_table(rows: list[dict], title: str) -> None:
    print(f"\n{title}")
    print(f"  {'mode':<8} | {'dir':<5} | {'R':>4} | {'K':>4} | {'dd':>4} | "
          f"{'N':>4} | {'WR%':>5} | {'PF':>5} | {'avg$':>6} | {'PnL$':>8} | "
          f"{'Sharpe':>6} | {'Sortino':>7} | f/n")
    print("  " + "-" * 105)
    for m in rows:
        if m["N"] == 0:
            continue
        pf = f"{m['PF']:.2f}" if m['PF'] != float('inf') else " inf"
        print(f"  {m['mode']:<8} | {m['direction']:<5} | "
              f"{m['R']:>4.1f} | {m['K']:>4.1f} | {m['dd_cap']:>4.1f} | "
              f"{m['N']:>4} | {m['WR']:>5.1f} | {pf:>5} | "
              f"{m['avg']:>+6.1f} | {m['total']:>+8.0f} | "
              f"{m['sharpe']:>6.2f} | {m['sortino']:>7.2f} | "
              f"{m['forced']}/{m['natural']}")


def main() -> int:
    print("=" * 110)
    print("P-15 ROLLING REBALANCE — FULL EXPLORATION")
    print("=" * 110)

    df_1h = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    df_15m = pd.read_csv("backtests/frozen/BTCUSDT_15m_2y.csv").reset_index(drop=True)
    print(f"  1h bars: {len(df_1h)}  |  15m bars: {len(df_15m)}")

    # ── Section 1: Harvest mode, both directions, both TFs
    print("\n" + "=" * 110)
    print("SECTION 1: HARVEST MODE (R% retrace + K% reentry)")
    print("=" * 110)

    rows = []
    for tf_name, df in (("1h", df_1h), ("15m", df_15m)):
        for direction in ("short", "long"):
            for R, K in [(0.3, 1.0), (0.5, 1.0), (0.5, 0.5), (0.8, 0.5)]:
                m = simulate_harvest(df, R, K, dd_cap_pct=3.0, direction=direction)
                m["tf"] = tf_name
                rows.append(m)

    # Group by TF for readability
    for tf in ("1h", "15m"):
        print_table([r for r in rows if r.get("tf") == tf],
                    f"--- TF={tf} ---")

    # ── Section 2: TP-flat mode (bot's take_profit param)
    print("\n" + "=" * 110)
    print("SECTION 2: TP-FLAT MODE (close whole position at +$TP, reopen on gate)")
    print("=" * 110)

    rows_tp = []
    for tf_name, df in (("1h", df_1h), ("15m", df_15m)):
        for direction in ("short", "long"):
            for tp in (1.0, 5.0, 10.0, 20.0, 50.0):
                m = simulate_tp_flat(df, tp_usd=tp, dd_cap_pct=3.0, direction=direction)
                m["tf"] = tf_name
                rows_tp.append(m)

    for tf in ("1h", "15m"):
        print(f"\n--- TF={tf} ---")
        print(f"  {'TP$':>5} | {'dir':<5} | {'N':>4} | {'WR%':>5} | {'PF':>6} | "
              f"{'avg$':>5} | {'PnL$':>8} | {'Sharpe':>6} | tp/forced/natural")
        print("  " + "-" * 95)
        for m in rows_tp:
            if m.get("tf") != tf or m["N"] == 0:
                continue
            pf = f"{m['PF']:.2f}" if m['PF'] != float('inf') else " inf"
            print(f"  {m['R']:>5.1f} | {m['direction']:<5} | {m['N']:>4} | "
                  f"{m['WR']:>5.1f} | {pf:>6} | {m['avg']:>+5.1f} | "
                  f"{m['total']:>+8.0f} | {m['sharpe']:>6.2f} | "
                  f"{m.get('tp_hit', 0)}/{m['forced']}/{m['natural']}")

    # ── Section 3: Best-of-each summary
    print("\n" + "=" * 110)
    print("SECTION 3: BEST PER (mode, direction, TF)")
    print("=" * 110)

    by_key: dict = {}
    for r in rows + rows_tp:
        if r["N"] == 0:
            continue
        key = (r["mode"], r["direction"], r.get("tf"))
        if key not in by_key or r["total"] > by_key[key]["total"]:
            by_key[key] = r

    print(f"  {'mode':<8} | {'dir':<5} | {'tf':<4} | best params {' ':<10} | "
          f"{'PnL$':>7} | {'PF':>5} | {'Sharpe':>6}")
    print("  " + "-" * 90)
    for (mode, direction, tf), r in sorted(by_key.items()):
        if mode == "tp-flat":
            params = f"TP={r['R']}$"
        else:
            params = f"R={r['R']} K={r['K']}"
        pf = f"{r['PF']:.2f}" if r['PF'] != float('inf') else " inf"
        print(f"  {mode:<8} | {direction:<5} | {tf:<4} | {params:<22} | "
              f"{r['total']:>+7.0f} | {pf:>5} | {r['sharpe']:>6.2f}")

    # ── Section 4: Walk-forward on top harvest config (1h short)
    top = max((r for r in rows if r["mode"] == "harvest" and r["direction"] == "short"
               and r.get("tf") == "1h"), key=lambda x: x["total"])
    print("\n" + "=" * 110)
    print(f"SECTION 4: WALK-FORWARD (4 folds x 6mo) on best 1h-short harvest "
          f"R={top['R']} K={top['K']}")
    print("=" * 110)
    folds = walk_forward(df_1h, simulate_harvest,
                         dict(R_pct=top["R"], K_pct=top["K"], dd_cap_pct=3.0,
                              direction="short"))
    print(f"  fold | period       | N    | WR%  | PF    | PnL$    | Sharpe")
    print("  " + "-" * 65)
    for f in folds:
        period = f"6mo (fold {f['fold']})"
        pf = f"{f['PF']:.2f}" if f['PF'] != float('inf') else "inf"
        print(f"  {f['fold']:>4} | {period:<13} | {f['N']:>4} | "
              f"{f['WR']:>4.1f} | {pf:>5} | {f['total']:>+7.0f} | {f['sharpe']:>6.2f}")
    fold_pnls = [f['total'] for f in folds]
    print(f"\n  Folds with positive PnL: {sum(1 for p in fold_pnls if p > 0)}/4")
    print(f"  Stability (min/max PnL ratio): "
          f"{min(fold_pnls)/max(fold_pnls):.2f}" if max(fold_pnls) > 0 else "  unstable")

    # ── Acceptance verdict
    print("\n" + "=" * 110)
    print("ACCEPTANCE CHECK (P-15 -> CONFIRMED criteria from HYPOTHESES_BACKLOG)")
    print("=" * 110)
    best_global = max(by_key.values(), key=lambda r: r["total"])
    print(f"  Top configuration: mode={best_global['mode']}, "
          f"dir={best_global['direction']}, tf={best_global.get('tf')}, "
          f"R={best_global['R']} K={best_global['K']}")
    print(f"  PnL 2y:  {best_global['total']:+.0f}$")
    print(f"  PF:      {best_global['PF']:.2f}  (req: > 1.5) "
          f"{'OK' if best_global['PF'] > 1.5 else 'FAIL'}")
    print(f"  Sharpe:  {best_global['sharpe']:.2f}  (req per-trade > 0.05) "
          f"{'OK' if best_global['sharpe'] > 0.05 else 'FAIL'}")
    print(f"  WR:      {best_global['WR']:.1f}%")
    print(f"  Walk-fwd positive folds: {sum(1 for p in fold_pnls if p > 0)}/4 "
          f"{'OK' if sum(1 for p in fold_pnls if p > 0) >= 3 else 'FAIL (need 3+ positive)'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
