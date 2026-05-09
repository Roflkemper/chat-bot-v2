"""TZ-TP-AUTOUPDATE-BACKTEST - operator's starred task (2026-05-09).

Question:
  TP+autoupdate (close whole leg at +$TP, reopen fresh) survives volume better
  than grid-with-bag (accumulate counter-trend size, hope to mean-revert)?

Comparison on 7d BTC 1m:
  Mode A - TP-FLAT (autoupdate):
      open at gate, close at +$TP (or DD-cap), reopen on next gate.
      Variants: TP in {1, 2, 5, 10}, dd_cap in {3%, 5%},
                reentry in {immediate, wait_K=0.3%}.
  Mode B - GRID-WITH-BAG (current GinArea V1/V2 style):
      open, every -K% adverse move add another $size to position.
      Close whole bag at +$TP (cumulative). Force-close at dd_cap.
      Variants: same TP/dd_cap, ladder K in {0.5%, 1.0%}.

Output:
  Console table + CSV at backtests/frozen/tp_autoupdate_vs_bag_2026-05-09.csv

Run:
  python tools/_backtest_tp_autoupdate_vs_bag.py [--start-day N]
  --start-day picks which 7d slice from end of 2y data (0 = last 7d, 1 = prev, ...)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_CSV = ROOT / "backtests" / "frozen" / "tp_autoupdate_vs_bag_2026-05-09.csv"

FEE_BPS = 5.0
BARS_PER_DAY = 60 * 24
WINDOW_DAYS = 7
WARMUP_BARS = 300


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _trend_gate(e50: float, e200: float, price: float, direction: str) -> bool:
    if direction == "short":
        return e50 > e200 and price > e50
    return e50 < e200 and price < e50


def _realized_pnl_pct(entry: float, exit_price: float, direction: str) -> float:
    if direction == "short":
        return (entry - exit_price) / entry
    return (exit_price - entry) / entry


def _mark_to_market_equity(realized_equity: float, avg_entry: float, mark_price: float,
                           total_size: float, direction: str, fee: float) -> float:
    pnl_pct = _realized_pnl_pct(avg_entry, mark_price, direction)
    return realized_equity + total_size * (pnl_pct - 2 * fee)


def _max_drawdown(equity_curve: list[float]) -> float:
    eq = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min())


def load_slice(start_day: int = 0) -> pd.DataFrame:
    """Return 7d simulation window with prepended EMA warmup bars."""
    df = pd.read_csv(DATA)
    sim_bars = WINDOW_DAYS * BARS_PER_DAY
    bars_back = (start_day + 1) * sim_bars
    if bars_back > len(df):
        raise SystemExit(f"requested {(start_day + 1) * WINDOW_DAYS}d but only {len(df) // BARS_PER_DAY}d available")

    end = len(df) - start_day * sim_bars
    start = end - sim_bars
    warmup = max(0, start - WARMUP_BARS)
    sliced = df.iloc[warmup:end].reset_index(drop=True)
    sliced.attrs["sim_start"] = start - warmup
    sliced.attrs["sim_bars"] = sim_bars
    return sliced


def simulate_tp_flat(df: pd.DataFrame, tp_usd: float, dd_cap_pct: float,
                     direction: str, base_size_usd: float = 1000.0,
                     reentry: str = "immediate", k_pct: float = 0.3) -> dict:
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    e50 = ema(df["close"], 50).to_numpy()
    e200 = ema(df["close"], 200).to_numpy()

    fee = FEE_BPS / 10000.0
    sim_start = max(200, int(df.attrs.get("sim_start", 200)))
    pnls: list[float] = []
    realized_equity = 0.0
    equity_curve = [realized_equity]
    volume_traded = 0.0
    in_pos = False
    entry = 0.0
    extreme = 0.0
    cum_dd = 0.0
    waiting_pullback = False
    last_close_price = 0.0
    n_tp = 0
    n_forced = 0
    peak_notional = 0.0

    for i in range(sim_start, len(close)):
        gate = _trend_gate(e50[i], e200[i], close[i], direction)
        c = close[i]

        if not in_pos:
            equity_curve.append(realized_equity)
            if waiting_pullback and gate:
                if direction == "short":
                    target = last_close_price * (1 + k_pct / 100.0)
                    hit_target = high[i] >= target
                else:
                    target = last_close_price * (1 - k_pct / 100.0)
                    hit_target = low[i] <= target
                if hit_target:
                    entry = target
                    in_pos = True
                    waiting_pullback = False
                    extreme = entry
                    cum_dd = 0.0
                    volume_traded += base_size_usd
                continue

            if gate:
                entry = c
                in_pos = True
                extreme = c
                cum_dd = 0.0
                volume_traded += base_size_usd
            continue

        equity_curve.append(
            _mark_to_market_equity(
                realized_equity=realized_equity,
                avg_entry=entry,
                mark_price=c,
                total_size=base_size_usd,
                direction=direction,
                fee=fee,
            )
        )

        if direction == "short":
            extreme = max(extreme, high[i])
            adverse_pct = (extreme - entry) / entry * 100.0
            tp_price = entry * (1 - tp_usd / base_size_usd)
            tp_hit = low[i] <= tp_price
        else:
            extreme = min(extreme, low[i])
            adverse_pct = (entry - extreme) / entry * 100.0
            tp_price = entry * (1 + tp_usd / base_size_usd)
            tp_hit = high[i] >= tp_price

        cum_dd = max(cum_dd, adverse_pct)
        peak_notional = max(peak_notional, base_size_usd)

        if tp_hit:
            pnl = base_size_usd * (_realized_pnl_pct(entry, tp_price, direction) - 2 * fee)
            pnls.append(pnl)
            realized_equity += pnl
            equity_curve[-1] = realized_equity
            volume_traded += base_size_usd
            last_close_price = tp_price
            in_pos = False
            n_tp += 1
            waiting_pullback = reentry == "wait_K_pct"
            continue

        if cum_dd >= dd_cap_pct:
            pnl = base_size_usd * (_realized_pnl_pct(entry, c, direction) - 2 * fee)
            pnls.append(pnl)
            realized_equity += pnl
            equity_curve[-1] = realized_equity
            volume_traded += base_size_usd
            in_pos = False
            n_forced += 1
            waiting_pullback = False

    if in_pos:
        c = close[-1]
        pnl = base_size_usd * (_realized_pnl_pct(entry, c, direction) - 2 * fee)
        pnls.append(pnl)
        realized_equity += pnl
        equity_curve[-1] = realized_equity
        volume_traded += base_size_usd

    pnl_total = float(np.sum(pnls)) if pnls else 0.0
    return {
        "mode": "tp-flat",
        "direction": direction,
        "tp_usd": tp_usd,
        "dd_cap": dd_cap_pct,
        "reentry": reentry,
        "K": k_pct,
        "ladder_K": 0.0,
        "N": len(pnls),
        "pnl_total": pnl_total,
        "max_dd": _max_drawdown(equity_curve),
        "peak_notional": peak_notional,
        "volume": volume_traded,
        "n_tp": n_tp,
        "n_forced": n_forced,
        "pnl_per_volume_bps": (pnl_total / volume_traded * 10000.0) if volume_traded > 0 else 0.0,
    }


def simulate_grid_bag(df: pd.DataFrame, tp_usd: float, dd_cap_pct: float,
                      direction: str, ladder_k_pct: float = 1.0,
                      base_size_usd: float = 1000.0, max_legs: int = 10) -> dict:
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    e50 = ema(df["close"], 50).to_numpy()
    e200 = ema(df["close"], 200).to_numpy()

    fee = FEE_BPS / 10000.0
    sim_start = max(200, int(df.attrs.get("sim_start", 200)))
    pnls: list[float] = []
    realized_equity = 0.0
    equity_curve = [realized_equity]
    volume_traded = 0.0
    in_pos = False
    weighted_entry = 0.0
    total_size = 0.0
    n_legs = 0
    last_add_price = 0.0
    n_tp = 0
    n_forced = 0
    peak_notional = 0.0

    for i in range(sim_start, len(close)):
        gate = _trend_gate(e50[i], e200[i], close[i], direction)
        c = close[i]

        if not in_pos:
            equity_curve.append(realized_equity)
            if gate:
                in_pos = True
                weighted_entry = c * base_size_usd
                total_size = base_size_usd
                n_legs = 1
                last_add_price = c
                volume_traded += base_size_usd
            continue

        avg_entry = weighted_entry / total_size
        if direction == "short":
            while high[i] >= last_add_price * (1 + ladder_k_pct / 100.0) and n_legs < max_legs:
                add_price = last_add_price * (1 + ladder_k_pct / 100.0)
                weighted_entry += add_price * base_size_usd
                total_size += base_size_usd
                n_legs += 1
                last_add_price = add_price
                volume_traded += base_size_usd
                avg_entry = weighted_entry / total_size
            unrealized_pct = (avg_entry - low[i]) / avg_entry
            adverse_pct = (high[i] - avg_entry) / avg_entry * 100.0
        else:
            while low[i] <= last_add_price * (1 - ladder_k_pct / 100.0) and n_legs < max_legs:
                add_price = last_add_price * (1 - ladder_k_pct / 100.0)
                weighted_entry += add_price * base_size_usd
                total_size += base_size_usd
                n_legs += 1
                last_add_price = add_price
                volume_traded += base_size_usd
                avg_entry = weighted_entry / total_size
            unrealized_pct = (high[i] - avg_entry) / avg_entry
            adverse_pct = (avg_entry - low[i]) / avg_entry * 100.0

        equity_curve.append(
            _mark_to_market_equity(
                realized_equity=realized_equity,
                avg_entry=avg_entry,
                mark_price=c,
                total_size=total_size,
                direction=direction,
                fee=fee,
            )
        )
        peak_notional = max(peak_notional, total_size)
        unrealized_usd = total_size * unrealized_pct

        if unrealized_usd >= tp_usd:
            close_price_pct = tp_usd / total_size
            close_price = avg_entry * (1 - close_price_pct if direction == "short" else 1 + close_price_pct)
            pnl = total_size * (_realized_pnl_pct(avg_entry, close_price, direction) - 2 * fee)
            pnls.append(pnl)
            realized_equity += pnl
            equity_curve[-1] = realized_equity
            volume_traded += total_size
            in_pos = False
            total_size = 0.0
            weighted_entry = 0.0
            n_legs = 0
            n_tp += 1
            continue

        if adverse_pct >= dd_cap_pct:
            pnl = total_size * (_realized_pnl_pct(avg_entry, c, direction) - 2 * fee)
            pnls.append(pnl)
            realized_equity += pnl
            equity_curve[-1] = realized_equity
            volume_traded += total_size
            in_pos = False
            total_size = 0.0
            weighted_entry = 0.0
            n_legs = 0
            n_forced += 1

    if in_pos:
        c = close[-1]
        avg_entry = weighted_entry / total_size
        pnl = total_size * (_realized_pnl_pct(avg_entry, c, direction) - 2 * fee)
        pnls.append(pnl)
        realized_equity += pnl
        equity_curve[-1] = realized_equity
        volume_traded += total_size

    pnl_total = float(np.sum(pnls)) if pnls else 0.0
    return {
        "mode": "grid-bag",
        "direction": direction,
        "tp_usd": tp_usd,
        "dd_cap": dd_cap_pct,
        "reentry": "n/a",
        "K": 0.0,
        "ladder_K": ladder_k_pct,
        "N": len(pnls),
        "pnl_total": pnl_total,
        "max_dd": _max_drawdown(equity_curve),
        "peak_notional": peak_notional,
        "volume": volume_traded,
        "n_tp": n_tp,
        "n_forced": n_forced,
        "pnl_per_volume_bps": (pnl_total / volume_traded * 10000.0) if volume_traded > 0 else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-day", type=int, default=0, help="0=last 7d, 1=prev 7d, etc.")
    args = parser.parse_args()

    print("=" * 110)
    print("TZ-TP-AUTOUPDATE-BACKTEST - TP-flat vs Grid-with-bag (BTC 1m, 7d)")
    print("=" * 110)
    df = load_slice(args.start_day)
    sim_bars = int(df.attrs.get("sim_bars", len(df)))
    print(f"  bars: {sim_bars} simulated + {len(df) - sim_bars} warmup")

    rows: list[dict] = []

    for direction in ("short", "long"):
        for tp in (1.0, 2.0, 5.0, 10.0):
            for dd in (3.0, 5.0):
                for reentry, k_pct in (("immediate", 0.0), ("wait_K_pct", 0.3)):
                    rows.append(
                        simulate_tp_flat(
                            df,
                            tp_usd=tp,
                            dd_cap_pct=dd,
                            direction=direction,
                            reentry=reentry,
                            k_pct=k_pct,
                        )
                    )

    for direction in ("short", "long"):
        for tp in (1.0, 2.0, 5.0, 10.0):
            for dd in (3.0, 5.0):
                for ladder_k in (0.5, 1.0):
                    rows.append(
                        simulate_grid_bag(
                            df,
                            tp_usd=tp,
                            dd_cap_pct=dd,
                            direction=direction,
                            ladder_k_pct=ladder_k,
                        )
                    )

    print()
    print(f"  {'mode':<9} {'dir':<5} {'TP$':>4} {'dd%':>4} {'K%':>4} "
          f"{'lad%':>4} {'N':>3} {'PnL$':>8} {'maxDD$':>8} {'peak$':>7} "
          f"{'vol$':>9} {'bps':>6} {'tp/forced':>10}")
    print("  " + "-" * 105)
    for row in sorted(rows, key=lambda item: -item["pnl_total"]):
        print(f"  {row['mode']:<9} {row['direction']:<5} {row['tp_usd']:>4.0f} "
              f"{row['dd_cap']:>4.1f} {row['K']:>4.1f} {row['ladder_K']:>4.1f} "
              f"{row['N']:>3} {row['pnl_total']:>+8.1f} {row['max_dd']:>+8.1f} "
              f"{row['peak_notional']:>7.0f} {row['volume']:>9.0f} "
              f"{row['pnl_per_volume_bps']:>+6.1f} {row['n_tp']:>3}/{row['n_forced']:<5}")

    by_mode: dict[str, list[dict]] = {"tp-flat": [], "grid-bag": []}
    for row in rows:
        by_mode[row["mode"]].append(row)

    print("\n" + "=" * 110)
    print("VERDICT")
    print("=" * 110)
    for mode in ("tp-flat", "grid-bag"):
        sub = by_mode[mode]
        best_pnl = max(sub, key=lambda item: item["pnl_total"])
        best_eff = max(sub, key=lambda item: item["pnl_per_volume_bps"])
        worst_dd = min(sub, key=lambda item: item["max_dd"])
        print(f"\n  [{mode}]")
        print(f"    best PnL:        {best_pnl['pnl_total']:+.1f}$ "
              f"(dir={best_pnl['direction']} TP=${best_pnl['tp_usd']:.0f} "
              f"dd={best_pnl['dd_cap']:.0f}%) maxDD={best_pnl['max_dd']:+.1f}$")
        print(f"    best efficiency: {best_eff['pnl_per_volume_bps']:+.1f} bps "
              f"(dir={best_eff['direction']} TP=${best_eff['tp_usd']:.0f} "
              f"vol={best_eff['volume']:.0f}$)")
        print(f"    worst maxDD:     {worst_dd['max_dd']:+.1f}$ "
              f"(dir={worst_dd['direction']} TP=${worst_dd['tp_usd']:.0f} "
              f"dd_cap={worst_dd['dd_cap']:.0f}%)")

    print("\n" + "=" * 110)
    print("HEAD-TO-HEAD (same TP, dd_cap, direction)")
    print("=" * 110)
    print(f"  {'dir':<5} {'TP$':>4} {'dd%':>4} | {'TP-flat PnL':>12} {'maxDD':>8} {'vol':>8} | "
          f"{'Grid-bag PnL':>13} {'maxDD':>8} {'vol':>8} | {'winner':>8}")
    print("  " + "-" * 100)
    for direction in ("short", "long"):
        for tp in (1.0, 2.0, 5.0, 10.0):
            for dd in (3.0, 5.0):
                tp_flat = next(
                    (
                        row for row in rows
                        if row["mode"] == "tp-flat"
                        and row["direction"] == direction
                        and row["tp_usd"] == tp
                        and row["dd_cap"] == dd
                        and row["reentry"] == "immediate"
                    ),
                    None,
                )
                grid_bag = next(
                    (
                        row for row in rows
                        if row["mode"] == "grid-bag"
                        and row["direction"] == direction
                        and row["tp_usd"] == tp
                        and row["dd_cap"] == dd
                        and row["ladder_K"] == 1.0
                    ),
                    None,
                )
                if not tp_flat or not grid_bag:
                    continue
                winner = "tp-flat" if tp_flat["pnl_total"] > grid_bag["pnl_total"] else "grid-bag"
                print(f"  {direction:<5} {tp:>4.0f} {dd:>4.0f} | "
                      f"{tp_flat['pnl_total']:>+12.1f} {tp_flat['max_dd']:>+8.1f} {tp_flat['volume']:>8.0f} | "
                      f"{grid_bag['pnl_total']:>+13.1f} {grid_bag['max_dd']:>+8.1f} {grid_bag['volume']:>8.0f} | "
                      f"{winner:>8}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  CSV: {OUT_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
