"""P-15 dd_cap sweep — поиск менее агрессивного cap который не убивает edge.

Контекст:
  Live P-15 теряет −$926/мес на paper, тогда как backtest (HONEST V2) обещал
  большие плюсы. Главное подозрение: dd_cap=3% слишком агрессивный для
  range-рынков и срабатывает раньше чем тренд реально кончился.

Что меряем:
  - dd_cap_pct ∈ [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]      — главная переменная
  - SLIPPAGE_PCT ∈ [0.02, 0.05, 0.10]                      — sensitivity
  - trend_gate ∈ ['strict' (e50/e200/close>e50), 'loose' (только e50/e200)]

База: точный engine из _backtest_p15_honest_v2.py — копируем simulate_p15_harvest
и парам-ом подменяем dd_cap/slippage/gate_mode. Walk-forward 4 folds × 6 mo.

Output: docs/STRATEGIES/P15_DD_CAP_SWEEP.md
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

OUT_MD = ROOT / "docs" / "STRATEGIES" / "P15_DD_CAP_SWEEP.md"
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

MAKER_REBATE = -0.0125 / 100
TAKER_FEE = 0.075 / 100

# Sweep matrix
DD_CAP_VARIANTS = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
SLIPPAGE_VARIANTS = [0.02 / 100, 0.05 / 100, 0.10 / 100]
GATE_VARIANTS = ["strict", "loose"]

# Fixed harvest params (V2 defaults — separate sweep later if needed)
R_PCT = 0.3
K_PCT = 1.0
BASE_SIZE_USD = 1000.0
MAX_REENTRIES = 10
N_FOLDS = 4


@dataclass
class Run:
    dd_cap: float
    slip: float
    gate: str
    direction: str
    fold: int
    n_trades: int
    realized_pnl: float
    win_rate: float
    pf: float
    max_dd_usd: float
    forced_closes: int   # how many times dd_cap fired
    natural_closes: int  # trend-flip closes


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _gate_short(e50: float, e200: float, c: float, mode: str) -> bool:
    if mode == "strict":
        return e50 > e200 and c > e50
    return e50 > e200  # loose: только структурный uptrend


def _gate_long(e50: float, e200: float, c: float, mode: str) -> bool:
    if mode == "strict":
        return e50 < e200 and c < e50
    return e50 < e200


def _trade_pnl(entry: float, exit_price: float, qty: float, direction: str,
               fee_in_pct: float, fee_out_pct: float) -> float:
    if direction == "short":
        gross = qty * (entry - exit_price)
    else:
        gross = qty * (exit_price - entry)
    fee_in_usd = entry * qty * fee_in_pct
    fee_out_usd = exit_price * qty * fee_out_pct
    return gross - fee_in_usd - fee_out_usd


def simulate(df_1h: pd.DataFrame, *, dd_cap_pct: float, slip_pct: float,
             gate_mode: str, direction: str) -> Run:
    if len(df_1h) < 250:
        return Run(dd_cap_pct, slip_pct, gate_mode, direction, 0, 0, 0, 0, 0, 0, 0, 0)
    close_1h = df_1h["close"].values
    high_1h = df_1h["high"].values
    low_1h = df_1h["low"].values
    e50_arr = ema(df_1h["close"], 50).values
    e200_arr = ema(df_1h["close"], 200).values

    pnls: list[float] = []
    in_trend = False
    total_qty_btc = 0.0
    weighted_entry = 0.0
    extreme = 0.0
    cum_dd = 0.0
    n_re = 0
    equity = 0.0
    equity_peak = 0.0
    max_dd_usd = 0.0
    forced = 0
    natural = 0

    fee_in = MAKER_REBATE
    fee_out = TAKER_FEE + slip_pct

    base_qty = BASE_SIZE_USD / close_1h[200] if close_1h[200] > 0 else 0.001

    for i in range(200, len(close_1h)):
        if direction == "short":
            gate = _gate_short(e50_arr[i], e200_arr[i], close_1h[i], gate_mode)
        else:
            gate = _gate_long(e50_arr[i], e200_arr[i], close_1h[i], gate_mode)
        c = close_1h[i]
        h = high_1h[i]
        l = low_1h[i]

        if not in_trend and gate:
            in_trend = True
            total_qty_btc = base_qty
            weighted_entry = c * total_qty_btc
            extreme = c
            n_re = 0
            cum_dd = 0.0
            continue

        if in_trend:
            avg_entry = weighted_entry / total_qty_btc if total_qty_btc > 0 else c
            if direction == "short":
                extreme = max(extreme, h)
                adverse_pct = (extreme - avg_entry) / avg_entry * 100
                retrace_pct = (extreme - l) / extreme * 100
                exit_at = extreme * (1 - R_PCT / 100)
                reentry_at = exit_at * (1 + K_PCT / 100)
            else:
                extreme = min(extreme, l)
                adverse_pct = (avg_entry - extreme) / avg_entry * 100
                retrace_pct = (h - extreme) / extreme * 100
                exit_at = extreme * (1 + R_PCT / 100)
                reentry_at = exit_at * (1 - K_PCT / 100)

            cum_dd = max(cum_dd, adverse_pct)

            # dd_cap forced close
            if cum_dd >= dd_cap_pct:
                pnl = _trade_pnl(avg_entry, c, total_qty_btc, direction, fee_in, fee_out)
                pnls.append(pnl)
                equity += pnl
                equity_peak = max(equity_peak, equity)
                max_dd_usd = min(max_dd_usd, equity - equity_peak)
                forced += 1
                in_trend = False
                total_qty_btc = 0.0
                weighted_entry = 0.0
                continue

            # gate flip — natural close
            if not gate:
                pnl = _trade_pnl(avg_entry, c, total_qty_btc, direction, fee_in, fee_out)
                pnls.append(pnl)
                equity += pnl
                equity_peak = max(equity_peak, equity)
                max_dd_usd = min(max_dd_usd, equity - equity_peak)
                natural += 1
                in_trend = False
                total_qty_btc = 0.0
                weighted_entry = 0.0
                continue

            # harvest 50%
            if retrace_pct >= R_PCT and n_re < MAX_REENTRIES:
                harvest_qty = total_qty_btc * 0.5
                pnl = _trade_pnl(avg_entry, exit_at, harvest_qty, direction, fee_in, fee_out)
                pnls.append(pnl)
                equity += pnl
                equity_peak = max(equity_peak, equity)
                max_dd_usd = min(max_dd_usd, equity - equity_peak)
                total_qty_btc -= harvest_qty
                weighted_entry -= avg_entry * harvest_qty
                weighted_entry += reentry_at * base_qty
                total_qty_btc += base_qty
                n_re += 1
                extreme = reentry_at

    # final position close
    if in_trend and total_qty_btc > 0:
        c = close_1h[-1]
        avg_entry = weighted_entry / total_qty_btc
        pnl = _trade_pnl(avg_entry, c, total_qty_btc, direction, fee_in, fee_out)
        pnls.append(pnl)
        equity += pnl

    arr = np.array(pnls) if pnls else np.array([0.0])
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    wr = float((arr > 0).mean() * 100) if len(arr) else 0.0
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    return Run(
        dd_cap=dd_cap_pct, slip=slip_pct, gate=gate_mode, direction=direction,
        fold=0, n_trades=len(arr), realized_pnl=round(float(arr.sum()), 2),
        win_rate=round(wr, 1), pf=round(pf, 2),
        max_dd_usd=round(max_dd_usd, 2), forced_closes=forced, natural_closes=natural,
    )


def main() -> int:
    print(f"[p15-sweep] loading {DATA_1M}...")
    df = pd.read_csv(DATA_1M)
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    print(f"[p15-sweep] {len(df)} bars 1m, period: "
          f"{df.iloc[0]['ts_utc']} → {df.iloc[-1]['ts_utc']}")

    # Pre-resample once
    df_1h_all = df.resample("1h", on="ts_utc").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna().reset_index()
    print(f"[p15-sweep] {len(df_1h_all)} 1h bars after resample")

    # Walk-forward folds
    fold_size = len(df_1h_all) // N_FOLDS
    print(f"[p15-sweep] fold size = {fold_size} 1h bars (~6 mo)\n")

    all_runs: list[dict] = []
    n_combos = len(DD_CAP_VARIANTS) * len(SLIPPAGE_VARIANTS) * len(GATE_VARIANTS) * 2  # dirs
    print(f"[p15-sweep] {n_combos} param combos × {N_FOLDS} folds = "
          f"{n_combos * N_FOLDS} simulations\n")

    combo_idx = 0
    for dd_cap in DD_CAP_VARIANTS:
        for slip in SLIPPAGE_VARIANTS:
            for gate in GATE_VARIANTS:
                for direction in ("short", "long"):
                    combo_idx += 1
                    fold_pnls = []
                    fold_dds = []
                    fold_ns = []
                    forced_total = 0
                    natural_total = 0
                    for k in range(N_FOLDS):
                        start = k * fold_size
                        end = (k + 1) * fold_size if k < N_FOLDS - 1 else len(df_1h_all)
                        fold_df = df_1h_all.iloc[start:end].reset_index(drop=True).copy()
                        r = simulate(fold_df, dd_cap_pct=dd_cap, slip_pct=slip,
                                     gate_mode=gate, direction=direction)
                        fold_pnls.append(r.realized_pnl)
                        fold_dds.append(r.max_dd_usd)
                        fold_ns.append(r.n_trades)
                        forced_total += r.forced_closes
                        natural_total += r.natural_closes
                    sum_pnl = sum(fold_pnls)
                    sum_n = sum(fold_ns)
                    worst_dd = min(fold_dds) if fold_dds else 0.0
                    pos_folds = sum(1 for p in fold_pnls if p > 0)
                    all_runs.append({
                        "dd_cap_pct": dd_cap, "slippage_pct": slip * 100,
                        "gate_mode": gate, "direction": direction,
                        "sum_pnl_usd": sum_pnl, "sum_n_trades": sum_n,
                        "worst_fold_dd_usd": worst_dd, "pos_folds": pos_folds,
                        "forced_closes_total": forced_total,
                        "natural_closes_total": natural_total,
                        "fold_pnls": fold_pnls,
                    })
                    print(f"  [{combo_idx}/{n_combos}] dd={dd_cap:.1f}%  "
                          f"slip={slip*100:.2f}%  gate={gate:<6}  {direction:<5}  "
                          f"PnL=${sum_pnl:+,.0f}  N={sum_n}  "
                          f"forced={forced_total}  pos={pos_folds}/4")

    # Sort & report
    all_runs.sort(key=lambda r: r["sum_pnl_usd"], reverse=True)
    print("\n[p15-sweep] TOP 10 by sum_pnl_usd:")
    print(f"  {'dd':>4}  {'slip':>5}  {'gate':<6}  {'dir':<5}  {'PnL':>10}  "
          f"{'N':>4}  {'forced':>7}  {'pos':>3}")
    for r in all_runs[:10]:
        print(f"  {r['dd_cap_pct']:>4.1f}  {r['slippage_pct']:>5.2f}  "
              f"{r['gate_mode']:<6}  {r['direction']:<5}  "
              f"${r['sum_pnl_usd']:>+9,.0f}  {r['sum_n_trades']:>4}  "
              f"{r['forced_closes_total']:>7}  {r['pos_folds']}/4")

    # Markdown report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# P-15 dd_cap Sweep — поиск устойчивого cap\n\n"]
    md.append(f"**Период:** {df.iloc[0]['ts_utc']} → {df.iloc[-1]['ts_utc']}  "
              f"({len(df_1h_all)} 1h bars after resample)\n")
    md.append(f"**Walk-forward:** {N_FOLDS} folds × {fold_size} 1h bars (~6 mo каждый)\n\n")
    md.append(f"**Контекст:** Live P-15 paper-trade теряет −$926/мес при backtest-ожиданиях +$132k/2y. "
              f"Гипотеза: dd_cap=3% слишком агрессивный в range-рынках, форсит close раньше времени.\n\n")
    md.append("**Sweep:**\n")
    md.append(f"- dd_cap_pct: {DD_CAP_VARIANTS}\n")
    md.append(f"- slippage_pct: {[s*100 for s in SLIPPAGE_VARIANTS]}\n")
    md.append(f"- gate_mode: {GATE_VARIANTS} (strict=e50/e200/close>e50, loose=только e50/e200)\n")
    md.append(f"- direction: short/long\n")
    md.append(f"- harvest: R={R_PCT}% retrace, K={K_PCT}% reentry, max {MAX_REENTRIES} reentries\n\n")

    md.append("## Топ-20 каскадов по суммарному PnL (4 folds)\n\n")
    md.append("| dd_cap% | slip% | gate | dir | sum PnL ($) | N trades | "
              "forced | natural | pos folds | worst fold DD |\n")
    md.append("|---:|---:|---|---|---:|---:|---:|---:|---:|---:|\n")
    for r in all_runs[:20]:
        md.append(f"| {r['dd_cap_pct']:.1f} | {r['slippage_pct']:.2f} | "
                  f"{r['gate_mode']} | {r['direction']} | "
                  f"{r['sum_pnl_usd']:+,.0f} | {r['sum_n_trades']} | "
                  f"{r['forced_closes_total']} | {r['natural_closes_total']} | "
                  f"{r['pos_folds']}/4 | {r['worst_fold_dd_usd']:+,.0f} |\n")

    # Aggregates per dd_cap level (worst case across slip+gate)
    md.append("\n## Усреднение по dd_cap (показывает чувствительность)\n\n")
    md.append("| dd_cap% | dir | avg sum PnL | min sum PnL (worst slip) | "
              "avg forced | avg pos folds |\n")
    md.append("|---:|---|---:|---:|---:|---:|\n")
    for dd_cap in DD_CAP_VARIANTS:
        for direction in ("short", "long"):
            rows = [r for r in all_runs
                    if r["dd_cap_pct"] == dd_cap and r["direction"] == direction]
            if not rows:
                continue
            avg_pnl = np.mean([r["sum_pnl_usd"] for r in rows])
            min_pnl = min(r["sum_pnl_usd"] for r in rows)
            avg_forced = np.mean([r["forced_closes_total"] for r in rows])
            avg_pos = np.mean([r["pos_folds"] for r in rows])
            md.append(f"| {dd_cap:.1f} | {direction} | {avg_pnl:+,.0f} | "
                      f"{min_pnl:+,.0f} | {avg_forced:.0f} | {avg_pos:.1f}/4 |\n")

    # Best per direction
    md.append("\n## Best combo per direction\n\n")
    for direction in ("short", "long"):
        rows = [r for r in all_runs if r["direction"] == direction]
        if not rows:
            continue
        best = max(rows, key=lambda r: r["sum_pnl_usd"])
        md.append(f"### {direction.upper()}\n")
        md.append(f"- dd_cap **{best['dd_cap_pct']}%**, slip {best['slippage_pct']:.2f}%, "
                  f"gate **{best['gate_mode']}**\n")
        md.append(f"- Sum PnL: **${best['sum_pnl_usd']:+,.0f}** across {N_FOLDS} folds\n")
        md.append(f"- Pos folds: {best['pos_folds']}/{N_FOLDS}\n")
        md.append(f"- Forced closes: {best['forced_closes_total']}, "
                  f"natural: {best['natural_closes_total']}\n")
        md.append(f"- Per-fold PnL: {best['fold_pnls']}\n\n")

    # Verdict
    md.append("## Verdict\n\n")
    best_short = max((r for r in all_runs if r["direction"] == "short"),
                     key=lambda r: r["sum_pnl_usd"], default=None)
    best_long = max((r for r in all_runs if r["direction"] == "long"),
                    key=lambda r: r["sum_pnl_usd"], default=None)
    if best_short and best_short["sum_pnl_usd"] > 0 and best_short["pos_folds"] >= 3:
        md.append(f"✅ **SHORT:** dd_cap={best_short['dd_cap_pct']}% gate={best_short['gate_mode']} "
                  f"даёт +${best_short['sum_pnl_usd']:,.0f} с {best_short['pos_folds']}/4 фолдов в плюсе. "
                  f"Готово для paper.\n\n")
    else:
        md.append(f"⚠️ **SHORT:** даже лучшая комбинация не даёт устойчивый плюс. "
                  f"Возможно P-15 фундаментально не работает на текущих данных.\n\n")
    if best_long and best_long["sum_pnl_usd"] > 0 and best_long["pos_folds"] >= 3:
        md.append(f"✅ **LONG:** dd_cap={best_long['dd_cap_pct']}% gate={best_long['gate_mode']} "
                  f"даёт +${best_long['sum_pnl_usd']:,.0f}.\n\n")
    else:
        md.append(f"⚠️ **LONG:** не нашёл устойчивого профиля.\n\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[p15-sweep] report → {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
