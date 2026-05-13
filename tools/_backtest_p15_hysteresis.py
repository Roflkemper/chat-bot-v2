"""P-15 trend gate hysteresis backtest.

Operator feedback 2026-05-12: P-15 live теряет $765/24h. Live логи показывают
14 циклов open/close за ночь — каждый цикл $0-50 минус на entry/exit transitions.

Hypothesis: trend gate (EMA50>EMA200 + close>EMA50) на 1h данных flippery в
боковике. Если требовать **3 бара подряд** условия для входа — whipsaw уйдёт,
trend trades останутся.

Compare:
  confirm_bars=1 (current default): мгновенный flip
  confirm_bars=2:                   2 bar confirmation
  confirm_bars=3:                   3 bar confirmation (предложенный fix)
  confirm_bars=5:                   очень conservative

For close decision — always single-bar flip (responsive exit).

Metric: trades count, PnL, PF, walk-forward 4 folds.

Output: docs/STRATEGIES/P15_HYSTERESIS_SWEEP.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "P15_HYSTERESIS_SWEEP.md"
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

# Match current live params (post-2026-05-11 fix):
# K=0.5, max_re=5, harvest_pct=0.3, R=0.3, dd_cap=3.0
P15_R_PCT = 0.3
P15_K_PCT = 0.5
P15_DD_CAP_PCT = 3.0
P15_HARVEST_PCT = 0.3
P15_MAX_LAYERS = 6
BASE_SIZE_USD = 1000.0

CONFIRM_BARS_VARIANTS = [1, 2, 3, 5]
N_FOLDS = 4
SLIPPAGE_PCT = 0.05 / 100
TAKER_FEE_PCT = 0.075 / 100
MAKER_REBATE = -0.0125 / 100


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _gate_long_at(e50_arr, e200_arr, close_arr, i: int, confirm_bars: int) -> bool:
    """Returns True if for the last `confirm_bars` bars (ending at i),
    e50 < e200 and close < e50 — все condition'ы для LONG-fade (downtrend).
    Wait, P-15 LONG opens on UP-trend. Re-read p15_rolling.py:
       _trend_gate_long:  e50 < e200 AND close < e50    (LONG on DOWNtrend? No...)
    Looking at p15_rolling.py line 268-270:
       if direction == "long": return e50 > e200 and last > e50
    So LONG = uptrend confirmed. Match that here.
    """
    for offset in range(confirm_bars):
        idx = i - offset
        if idx < 200:
            return False
        if not (e50_arr[idx] > e200_arr[idx] and close_arr[idx] > e50_arr[idx]):
            return False
    return True


def _gate_short_at(e50_arr, e200_arr, close_arr, i: int, confirm_bars: int) -> bool:
    for offset in range(confirm_bars):
        idx = i - offset
        if idx < 200:
            return False
        if not (e50_arr[idx] < e200_arr[idx] and close_arr[idx] < e50_arr[idx]):
            return False
    return True


def _trade_pnl(entry: float, exit_p: float, qty: float, direction: str,
               fee_in_pct: float, fee_out_pct: float) -> float:
    if direction == "short":
        gross = qty * (entry - exit_p)
    else:
        gross = qty * (exit_p - entry)
    fee_in = entry * qty * fee_in_pct
    fee_out = exit_p * qty * fee_out_pct
    return gross - fee_in - fee_out


def simulate(df: pd.DataFrame, *, direction: str, confirm_bars: int) -> dict:
    if len(df) < 250:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0, "forced": 0, "natural": 0}

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    e50_arr = ema(df["close"], 50).values
    e200_arr = ema(df["close"], 200).values

    fee_in = MAKER_REBATE
    fee_out = TAKER_FEE_PCT + SLIPPAGE_PCT

    pnls: list[float] = []
    in_trend = False
    total_qty = 0.0
    weighted_entry = 0.0
    extreme = 0.0
    cum_dd = 0.0
    n_re = 0
    forced = 0
    natural = 0

    base_qty = BASE_SIZE_USD / close[200] if close[200] > 0 else 0.001

    for i in range(200, len(close)):
        c = close[i]
        h = high[i]
        l = low[i]

        # Gate check
        if direction == "long":
            gate_strict = _gate_long_at(e50_arr, e200_arr, close, i, confirm_bars)
            gate_single = _gate_long_at(e50_arr, e200_arr, close, i, 1)
        else:
            gate_strict = _gate_short_at(e50_arr, e200_arr, close, i, confirm_bars)
            gate_single = _gate_short_at(e50_arr, e200_arr, close, i, 1)

        # OPEN with strict
        if not in_trend and gate_strict:
            in_trend = True
            total_qty = base_qty
            weighted_entry = c * base_qty
            extreme = c
            n_re = 0
            cum_dd = 0.0
            continue

        if not in_trend:
            continue

        avg_entry = weighted_entry / total_qty if total_qty > 0 else c
        if direction == "long":
            extreme = max(extreme, h)
            adverse_pct = (extreme - avg_entry) / avg_entry * 100
            retrace_pct = (extreme - l) / extreme * 100 if extreme > 0 else 0
            exit_at = extreme * (1 - P15_R_PCT / 100)
            reentry_at = exit_at * (1 + P15_K_PCT / 100)
        else:
            extreme = max(extreme, h) if extreme == 0 else min(extreme, l)
            if extreme == 0:
                extreme = l
            adverse_pct = (avg_entry - extreme) / avg_entry * 100
            retrace_pct = (h - extreme) / extreme * 100 if extreme > 0 else 0
            exit_at = extreme * (1 + P15_R_PCT / 100)
            reentry_at = exit_at * (1 - P15_K_PCT / 100)

        cum_dd = max(cum_dd, adverse_pct)

        # dd_cap forced close
        if cum_dd >= P15_DD_CAP_PCT:
            pnl = _trade_pnl(avg_entry, c, total_qty, direction, fee_in, fee_out)
            pnls.append(pnl)
            forced += 1
            in_trend = False
            total_qty = 0.0
            weighted_entry = 0.0
            continue

        # gate flip — single-bar, responsive close
        if not gate_single:
            pnl = _trade_pnl(avg_entry, c, total_qty, direction, fee_in, fee_out)
            pnls.append(pnl)
            natural += 1
            in_trend = False
            total_qty = 0.0
            weighted_entry = 0.0
            continue

        # Harvest
        if retrace_pct >= P15_R_PCT and n_re < P15_MAX_LAYERS - 1:
            harvest_qty = total_qty * P15_HARVEST_PCT
            pnl = _trade_pnl(avg_entry, exit_at, harvest_qty, direction, fee_in, fee_out)
            pnls.append(pnl)
            total_qty -= harvest_qty
            weighted_entry -= avg_entry * harvest_qty
            weighted_entry += reentry_at * base_qty
            total_qty += base_qty
            n_re += 1
            extreme = reentry_at

    # final close
    if in_trend and total_qty > 0:
        c = close[-1]
        avg_entry = weighted_entry / total_qty
        pnl = _trade_pnl(avg_entry, c, total_qty, direction, fee_in, fee_out)
        pnls.append(pnl)

    if not pnls:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0, "forced": 0, "natural": 0}

    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    wr = float((arr > 0).mean() * 100)
    return {
        "n": len(arr), "pnl": float(arr.sum()), "pf": pf, "wr": wr,
        "forced": forced, "natural": natural,
    }


def walk_forward(df_15m: pd.DataFrame, *, direction: str, confirm_bars: int) -> list[dict]:
    n = len(df_15m)
    fold_size = n // N_FOLDS
    out = []
    for k in range(N_FOLDS):
        start = k * fold_size
        end = (k + 1) * fold_size if k < N_FOLDS - 1 else n
        sub = df_15m.iloc[start:end].reset_index(drop=True).copy()
        m = simulate(sub, direction=direction, confirm_bars=confirm_bars)
        out.append({"fold": k + 1, **m})
    return out


def main() -> int:
    print("[p15-hyst] loading 1m, resampling to 15m...")
    df = pd.read_csv(DATA_1M)
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df_15m = df.resample("15min", on="ts_utc").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna().reset_index()
    print(f"[p15-hyst] {len(df_15m)} 15m bars")

    results = []
    for cb in CONFIRM_BARS_VARIANTS:
        for direction in ("long", "short"):
            wf = walk_forward(df_15m, direction=direction, confirm_bars=cb)
            sum_pnl = sum(f["pnl"] for f in wf)
            sum_n = sum(f["n"] for f in wf)
            avg_pf = np.mean([f["pf"] for f in wf if f["pf"] < 999])
            pos = sum(1 for f in wf if f["pnl"] > 0)
            forced_tot = sum(f["forced"] for f in wf)
            natural_tot = sum(f["natural"] for f in wf)
            results.append({
                "confirm_bars": cb, "direction": direction,
                "sum_pnl": sum_pnl, "sum_n": sum_n,
                "avg_pf": avg_pf if not np.isnan(avg_pf) else 0,
                "pos_folds": pos, "forced": forced_tot, "natural": natural_tot,
                "fold_pnls": [round(f["pnl"], 0) for f in wf],
            })
            print(f"  confirm={cb} {direction:<5}  N={sum_n:>5} "
                  f"PnL=${sum_pnl:>+9,.0f}  avg_PF={avg_pf:.2f}  pos={pos}/4  "
                  f"forced={forced_tot} natural={natural_tot}")

    # Markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# P-15 Trend Gate Hysteresis Sweep\n\n"]
    md.append(f"**Период:** ~2y BTC ({len(df_15m)} 15m bars)\n")
    md.append("**Контекст:** Live P-15 теряет $765/24h из-за whipsaw в боковике.\n")
    md.append("Текущая логика: gate flip на одном баре → close + open циклы.\n")
    md.append("Гипотеза: требовать 2-3 bar confirmation для OPEN, сохранить single-bar для CLOSE.\n\n")
    md.append(f"**Fixed params:** R={P15_R_PCT}%, K={P15_K_PCT}%, "
              f"dd_cap={P15_DD_CAP_PCT}%, harvest={P15_HARVEST_PCT}, "
              f"max_layers={P15_MAX_LAYERS}\n\n")

    md.append("## Sweep по confirm_bars\n\n")
    md.append("| confirm_bars | dir | N trades | sum PnL ($) | avg PF | pos folds | forced | natural |\n")
    md.append("|---:|---|---:|---:|---:|---:|---:|---:|\n")
    for r in results:
        md.append(f"| {r['confirm_bars']} | {r['direction']} | {r['sum_n']} | "
                  f"{r['sum_pnl']:+,.0f} | {r['avg_pf']:.2f} | "
                  f"{r['pos_folds']}/{N_FOLDS} | {r['forced']} | {r['natural']} |\n")

    # Verdict
    md.append("\n## Verdict\n\n")
    short_results = [r for r in results if r["direction"] == "short"]
    long_results = [r for r in results if r["direction"] == "long"]
    best_short = max(short_results, key=lambda r: r["sum_pnl"])
    best_long = max(long_results, key=lambda r: r["sum_pnl"])
    md.append(f"**SHORT best:** confirm_bars={best_short['confirm_bars']} → "
              f"${best_short['sum_pnl']:+,.0f} ({best_short['pos_folds']}/4 folds)\n\n")
    md.append(f"**LONG best:** confirm_bars={best_long['confirm_bars']} → "
              f"${best_long['sum_pnl']:+,.0f} ({best_long['pos_folds']}/4 folds)\n\n")
    md.append("Per-fold PnL для best combo:\n")
    md.append(f"- SHORT confirm={best_short['confirm_bars']}: {best_short['fold_pnls']}\n")
    md.append(f"- LONG confirm={best_long['confirm_bars']}: {best_long['fold_pnls']}\n\n")

    # Compare cb=1 vs cb=3
    md.append("## Direct comparison: cb=1 (current) vs cb=3 (proposed)\n\n")
    for direction in ("long", "short"):
        cb1 = next(r for r in results if r["confirm_bars"] == 1 and r["direction"] == direction)
        cb3 = next(r for r in results if r["confirm_bars"] == 3 and r["direction"] == direction)
        delta_pnl = cb3["sum_pnl"] - cb1["sum_pnl"]
        delta_n = cb3["sum_n"] - cb1["sum_n"]
        md.append(f"**{direction.upper()}:**\n")
        md.append(f"- cb=1: PnL ${cb1['sum_pnl']:+,.0f} on N={cb1['sum_n']}\n")
        md.append(f"- cb=3: PnL ${cb3['sum_pnl']:+,.0f} on N={cb3['sum_n']}\n")
        md.append(f"- Δ PnL: ${delta_pnl:+,.0f}, Δ N: {delta_n:+d} trades\n\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[p15-hyst] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
