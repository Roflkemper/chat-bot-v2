"""P-15 reentry sweep — настоящий поиск edge на 15m данных.

После диагноза P15_LIVE_VS_BACKTEST_DIAGNOSIS.md:
  - dd_cap НЕ виноват (sweep 84 комбо все позитивные)
  - Реальная проблема в K (reentry offset) + n_reentries — на 15m данных
    бот делает много reentries и avg_entry уходит на 3-4% от стартовой цены

Этот sweep:
  - 15m bars (не 1h как старый!) — воспроизводит live frequency reentries
  - Sweep K (reentry offset): [0.5, 1.0, 1.5, 2.0]
  - Sweep max_reentries: [3, 5, 7, 10, 999]
  - Sweep harvest_pct (доля закрытия): [0.3, 0.5, 0.7]
  - Sweep R (retrace trigger): [0.2, 0.3, 0.5]
  - Fixed: dd_cap=3% (как live), slip=0.05%, gate=strict
  - 4 folds walk-forward

Каждая комбо = 4 × 2 (short/long) = 8 simulations.
4 × 5 × 3 × 3 = 180 unique combos × 8 = 1440 simulations.
15m bars в 2y: ~70k → 30-60min total runtime estimate.

Output: docs/STRATEGIES/P15_REENTRY_SWEEP.md
"""
from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

OUT_MD = ROOT / "docs" / "STRATEGIES" / "P15_REENTRY_SWEEP.md"
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

MAKER_REBATE = -0.0125 / 100
TAKER_FEE = 0.075 / 100
SLIPPAGE_PCT = 0.05 / 100

# Sweep variables (focus on what live diagnosis points to)
K_VARIANTS = [0.5, 1.0, 1.5, 2.0]                # reentry offset above harvest exit
MAX_REENTRIES_VARIANTS = [3, 5, 7, 10, 999]      # cap on reentry chain
HARVEST_PCT_VARIANTS = [0.3, 0.5, 0.7]           # доля позиции закрываемая на retrace
R_VARIANTS = [0.2, 0.3, 0.5]                     # retrace % to trigger harvest

# Fixed
DD_CAP_PCT = 3.0
BASE_SIZE_USD = 1000.0
N_FOLDS = 4
RESAMPLE_FREQ = "15min"


@dataclass
class Run:
    K_pct: float
    max_re: int
    harvest_pct: float
    R_pct: float
    direction: str
    n_trades: int
    realized_pnl: float
    pf: float
    forced_closes: int
    natural_closes: int
    max_layer: int


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _gate_short(e50, e200, c) -> bool:
    return e50 > e200 and c > e50


def _gate_long(e50, e200, c) -> bool:
    return e50 < e200 and c < e50


def _trade_pnl(entry, exit_price, qty, direction, fee_in_pct, fee_out_pct):
    if direction == "short":
        gross = qty * (entry - exit_price)
    else:
        gross = qty * (exit_price - entry)
    fee_in = entry * qty * fee_in_pct
    fee_out = exit_price * qty * fee_out_pct
    return gross - fee_in - fee_out


def simulate(df_15m: pd.DataFrame, *, K_pct: float, max_re: int,
             harvest_pct: float, R_pct: float, direction: str) -> Run:
    if len(df_15m) < 250:
        return Run(K_pct, max_re, harvest_pct, R_pct, direction,
                   0, 0, 0, 0, 0, 0)

    close_arr = df_15m["close"].values
    high_arr = df_15m["high"].values
    low_arr = df_15m["low"].values
    e50_arr = ema(df_15m["close"], 50).values
    e200_arr = ema(df_15m["close"], 200).values

    pnls: list[float] = []
    in_trend = False
    total_qty = 0.0
    weighted_entry = 0.0
    extreme = 0.0
    cum_dd = 0.0
    n_re = 0
    max_layer = 0
    forced = 0
    natural = 0

    fee_in = MAKER_REBATE
    fee_out = TAKER_FEE + SLIPPAGE_PCT

    base_qty = BASE_SIZE_USD / close_arr[200] if close_arr[200] > 0 else 0.001

    for i in range(200, len(close_arr)):
        if direction == "short":
            gate = _gate_short(e50_arr[i], e200_arr[i], close_arr[i])
        else:
            gate = _gate_long(e50_arr[i], e200_arr[i], close_arr[i])
        c = close_arr[i]
        h = high_arr[i]
        l = low_arr[i]

        if not in_trend and gate:
            in_trend = True
            total_qty = base_qty
            weighted_entry = c * base_qty
            extreme = c
            n_re = 0
            cum_dd = 0.0
            max_layer = 1
            continue

        if in_trend:
            avg_entry = weighted_entry / total_qty if total_qty > 0 else c
            if direction == "short":
                extreme = max(extreme, h)
                adverse_pct = (extreme - avg_entry) / avg_entry * 100
                retrace_pct = (extreme - l) / extreme * 100
                exit_at = extreme * (1 - R_pct / 100)
                reentry_at = exit_at * (1 + K_pct / 100)
            else:
                extreme = min(extreme, l)
                adverse_pct = (avg_entry - extreme) / avg_entry * 100
                retrace_pct = (h - extreme) / extreme * 100
                exit_at = extreme * (1 + R_pct / 100)
                reentry_at = exit_at * (1 - K_pct / 100)

            cum_dd = max(cum_dd, adverse_pct)

            if cum_dd >= DD_CAP_PCT:
                pnl = _trade_pnl(avg_entry, c, total_qty, direction, fee_in, fee_out)
                pnls.append(pnl)
                forced += 1
                in_trend = False
                total_qty = 0.0
                weighted_entry = 0.0
                continue

            if not gate:
                pnl = _trade_pnl(avg_entry, c, total_qty, direction, fee_in, fee_out)
                pnls.append(pnl)
                natural += 1
                in_trend = False
                total_qty = 0.0
                weighted_entry = 0.0
                continue

            if retrace_pct >= R_pct and n_re < max_re:
                harvest_qty = total_qty * harvest_pct
                pnl = _trade_pnl(avg_entry, exit_at, harvest_qty, direction, fee_in, fee_out)
                pnls.append(pnl)
                total_qty -= harvest_qty
                weighted_entry -= avg_entry * harvest_qty
                # reentry
                weighted_entry += reentry_at * base_qty
                total_qty += base_qty
                n_re += 1
                max_layer = max(max_layer, n_re + 1)
                extreme = reentry_at

    # final close
    if in_trend and total_qty > 0:
        c = close_arr[-1]
        avg_entry = weighted_entry / total_qty
        pnl = _trade_pnl(avg_entry, c, total_qty, direction, fee_in, fee_out)
        pnls.append(pnl)

    arr = np.array(pnls) if pnls else np.array([0.0])
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    return Run(
        K_pct=K_pct, max_re=max_re, harvest_pct=harvest_pct, R_pct=R_pct,
        direction=direction, n_trades=len(arr),
        realized_pnl=round(float(arr.sum()), 2),
        pf=round(pf, 2), forced_closes=forced, natural_closes=natural,
        max_layer=max_layer,
    )


def main() -> int:
    print(f"[p15-reentry] loading {DATA_1M}...")
    df = pd.read_csv(DATA_1M)
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    print(f"[p15-reentry] {len(df)} 1m bars")

    df_15m = df.resample(RESAMPLE_FREQ, on="ts_utc").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna().reset_index()
    print(f"[p15-reentry] {len(df_15m)} 15m bars after resample")

    fold_size = len(df_15m) // N_FOLDS
    print(f"[p15-reentry] fold size = {fold_size} 15m bars\n")

    n_combos = (len(K_VARIANTS) * len(MAX_REENTRIES_VARIANTS)
                * len(HARVEST_PCT_VARIANTS) * len(R_VARIANTS) * 2)
    print(f"[p15-reentry] {n_combos} combos × {N_FOLDS} folds = "
          f"{n_combos * N_FOLDS} sims\n")

    all_runs: list[dict] = []
    combo_idx = 0
    for K_pct in K_VARIANTS:
        for max_re in MAX_REENTRIES_VARIANTS:
            for harvest_pct in HARVEST_PCT_VARIANTS:
                for R_pct in R_VARIANTS:
                    for direction in ("short", "long"):
                        combo_idx += 1
                        fold_pnls = []
                        fold_ns = []
                        forced_total = 0
                        natural_total = 0
                        max_layer_seen = 0
                        for k in range(N_FOLDS):
                            start = k * fold_size
                            end = (k + 1) * fold_size if k < N_FOLDS - 1 else len(df_15m)
                            fold_df = df_15m.iloc[start:end].reset_index(drop=True).copy()
                            r = simulate(fold_df, K_pct=K_pct, max_re=max_re,
                                         harvest_pct=harvest_pct, R_pct=R_pct,
                                         direction=direction)
                            fold_pnls.append(r.realized_pnl)
                            fold_ns.append(r.n_trades)
                            forced_total += r.forced_closes
                            natural_total += r.natural_closes
                            max_layer_seen = max(max_layer_seen, r.max_layer)
                        sum_pnl = sum(fold_pnls)
                        sum_n = sum(fold_ns)
                        pos_folds = sum(1 for p in fold_pnls if p > 0)
                        all_runs.append({
                            "K_pct": K_pct, "max_re": max_re,
                            "harvest_pct": harvest_pct, "R_pct": R_pct,
                            "direction": direction,
                            "sum_pnl": sum_pnl, "sum_n": sum_n,
                            "pos_folds": pos_folds,
                            "forced_total": forced_total,
                            "natural_total": natural_total,
                            "max_layer": max_layer_seen,
                            "fold_pnls": fold_pnls,
                        })
                        if combo_idx % 30 == 0 or combo_idx == n_combos:
                            print(f"  [{combo_idx}/{n_combos}] K={K_pct} re_max={max_re} "
                                  f"harv={harvest_pct} R={R_pct} {direction:<5}  "
                                  f"PnL=${sum_pnl:+,.0f}  N={sum_n}  "
                                  f"forced={forced_total}  pos={pos_folds}/4  "
                                  f"maxL={max_layer_seen}")

    all_runs.sort(key=lambda r: r["sum_pnl"], reverse=True)
    print("\n[p15-reentry] TOP 15 by sum_pnl:")
    print(f"  {'K':>4} {'maxR':>4} {'harv':>5} {'R':>4} {'dir':<5} {'PnL':>10} "
          f"{'N':>4} {'forced':>7} {'pos':>3} {'mxL':>4}")
    for r in all_runs[:15]:
        print(f"  {r['K_pct']:>4.1f} {r['max_re']:>4} {r['harvest_pct']:>5.1f} "
              f"{r['R_pct']:>4.1f} {r['direction']:<5} "
              f"${r['sum_pnl']:>+9,.0f} {r['sum_n']:>4} "
              f"{r['forced_total']:>7} {r['pos_folds']}/4 {r['max_layer']:>4}")

    # Markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# P-15 Reentry Sweep — 15m данные, поиск edge\n\n"]
    md.append(f"**Период:** {df.iloc[0]['ts_utc']} → {df.iloc[-1]['ts_utc']}  "
              f"({len(df_15m):,} 15m bars after resample)\n")
    md.append(f"**Walk-forward:** {N_FOLDS} folds × {fold_size} 15m bars\n\n")
    md.append(f"**Контекст:** диагноз [P15_LIVE_VS_BACKTEST_DIAGNOSIS.md](./P15_LIVE_VS_BACKTEST_DIAGNOSIS.md) "
              f"показал что reentry-логика догоняет максимумы. dd_cap не виноват. "
              f"Этот sweep на 15m данных (как live) ищет K/max_re/harvest_pct/R комбо без анти-edge.\n\n")
    md.append("**Sweep:**\n")
    md.append(f"- K (reentry offset): {K_VARIANTS}\n")
    md.append(f"- max_reentries: {MAX_REENTRIES_VARIANTS}\n")
    md.append(f"- harvest_pct: {HARVEST_PCT_VARIANTS}\n")
    md.append(f"- R (retrace trigger): {R_VARIANTS}\n")
    md.append(f"- Fixed: dd_cap={DD_CAP_PCT}%, slippage={SLIPPAGE_PCT*100:.2f}%, gate=strict\n\n")

    md.append("## Топ-25 по sum_pnl\n\n")
    md.append("| K% | maxR | harv | R% | dir | sum PnL ($) | N | forced | natural | "
              "pos folds | max layer |\n")
    md.append("|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|\n")
    for r in all_runs[:25]:
        md.append(f"| {r['K_pct']} | {r['max_re']} | {r['harvest_pct']} | {r['R_pct']} | "
                  f"{r['direction']} | {r['sum_pnl']:+,.0f} | {r['sum_n']} | "
                  f"{r['forced_total']} | {r['natural_total']} | "
                  f"{r['pos_folds']}/4 | {r['max_layer']} |\n")

    md.append("\n## Худшие 10 (что НЕ делать)\n\n")
    md.append("| K% | maxR | harv | R% | dir | sum PnL ($) | forced |\n|---:|---:|---:|---:|---|---:|---:|\n")
    for r in all_runs[-10:]:
        md.append(f"| {r['K_pct']} | {r['max_re']} | {r['harvest_pct']} | {r['R_pct']} | "
                  f"{r['direction']} | {r['sum_pnl']:+,.0f} | {r['forced_total']} |\n")

    md.append("\n## Aggregates по K (главная переменная)\n\n")
    md.append("| K% | dir | avg PnL | min PnL | max PnL | avg forced |\n|---:|---|---:|---:|---:|---:|\n")
    for K in K_VARIANTS:
        for direction in ("short", "long"):
            rows = [r for r in all_runs if r["K_pct"] == K and r["direction"] == direction]
            if not rows: continue
            avg = np.mean([r["sum_pnl"] for r in rows])
            mn = min(r["sum_pnl"] for r in rows)
            mx = max(r["sum_pnl"] for r in rows)
            avg_f = np.mean([r["forced_total"] for r in rows])
            md.append(f"| {K} | {direction} | {avg:+,.0f} | {mn:+,.0f} | {mx:+,.0f} | {avg_f:.0f} |\n")

    md.append("\n## Aggregates по max_reentries\n\n")
    md.append("| maxR | dir | avg PnL | min PnL | max PnL | avg forced |\n|---:|---|---:|---:|---:|---:|\n")
    for mr in MAX_REENTRIES_VARIANTS:
        for direction in ("short", "long"):
            rows = [r for r in all_runs if r["max_re"] == mr and r["direction"] == direction]
            if not rows: continue
            avg = np.mean([r["sum_pnl"] for r in rows])
            mn = min(r["sum_pnl"] for r in rows)
            mx = max(r["sum_pnl"] for r in rows)
            avg_f = np.mean([r["forced_total"] for r in rows])
            md.append(f"| {mr} | {direction} | {avg:+,.0f} | {mn:+,.0f} | {mx:+,.0f} | {avg_f:.0f} |\n")

    md.append("\n## Best combo per direction\n\n")
    for direction in ("short", "long"):
        rows = [r for r in all_runs if r["direction"] == direction]
        if not rows: continue
        best = max(rows, key=lambda r: r["sum_pnl"])
        md.append(f"### {direction.upper()}\n")
        md.append(f"- K=**{best['K_pct']}%**, max_re=**{best['max_re']}**, "
                  f"harvest_pct=**{best['harvest_pct']}**, R=**{best['R_pct']}%**\n")
        md.append(f"- Sum PnL: **${best['sum_pnl']:+,.0f}** across {N_FOLDS} folds\n")
        md.append(f"- Pos folds: {best['pos_folds']}/{N_FOLDS}\n")
        md.append(f"- Forced closes: {best['forced_total']}, natural: {best['natural_total']}\n")
        md.append(f"- Max layer reached: {best['max_layer']}\n")
        md.append(f"- Per-fold PnL: {best['fold_pnls']}\n\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[p15-reentry] report → {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
