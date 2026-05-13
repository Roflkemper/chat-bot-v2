"""Volume z-score climax edge — backtest.

Hypothesis: свеча с volume z-score > N сигм (исключительно высокий объём)
+ закрытие "против движения" = capitulation/blow-off → mean revert.

Definitions:
  - vol_z(i) = (volume[i] - rolling_mean) / rolling_std  over LOOKBACK bars
  - bullish-climax candle: open > close, close in lower 30% of bar range
    (продавцы выиграли свечу — but оптовая ликвидация уже выпотрошила offers)
    → expect bounce → LONG
  - bearish-climax candle: open < close, close in upper 30% of bar range
    (покупатели выиграли свечу, blow-off top)
    → expect drop → SHORT

Actually simpler формулировка (более стандартная):
  - LONG signal: huge volume + red candle + close near low → capitulation low
  - SHORT signal: huge volume + green candle + close near high → blow-off top

Strategy:
  - vol_z > threshold (X sigmas)
  - close position type matches
  - hold N hours → market exit
  - cooldown 4h per direction to avoid double-firing

Sweep:
  - threshold (sigmas): [2.0, 2.5, 3.0, 3.5]
  - hold_hours: [2, 4, 6, 12, 24]
  - lookback (bars for z-score): [20, 50, 100]
  - timeframe: 1h vs 15m

4 folds walk-forward.

Output:
  docs/STRATEGIES/VOLUME_CLIMAX_BACKTEST.md
  state/volume_climax_results.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "VOLUME_CLIMAX_BACKTEST.md"
CSV_OUT = ROOT / "state" / "volume_climax_results.csv"

PRICE_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"
PRICE_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

# Sweep
THRESHOLDS = [2.0, 2.5, 3.0, 3.5]
HOLD_HOURS = [2, 4, 6, 12, 24]
LOOKBACKS = [20, 50, 100]
TIMEFRAMES = ["1h", "15m"]
DIRECTIONS = ["both", "long_only", "short_only"]

# Trade params
BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075
COOLDOWN_HOURS = 4
CLOSE_ZONE_PCT = 0.30   # close must be in lower 30% (LONG climax) or upper 30% (SHORT climax)
N_FOLDS = 4


def load_ohlcv_1h() -> pd.DataFrame:
    df = pd.read_csv(PRICE_1H)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def load_ohlcv_15m() -> pd.DataFrame:
    df = pd.read_csv(PRICE_1M)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("dt")
    df_15m = df.resample("15min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum", "ts": "first",
    }).dropna().reset_index(drop=True)
    return df_15m


def simulate(df: pd.DataFrame, *, threshold: float, hold_hours: int,
             lookback: int, direction_filter: str,
             timeframe: str) -> dict:
    if len(df) < lookback + 10:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0,
                "avg_pnl": 0.0, "max_dd": 0.0, "trades": []}

    # Rolling mean/std over volume
    vol = df["volume"].values
    rolling_mean = pd.Series(vol).rolling(lookback, min_periods=lookback).mean().values
    rolling_std = pd.Series(vol).rolling(lookback, min_periods=lookback).std().values

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    open_arr = df["open"].values
    ts = df["ts"].values

    # bar size in minutes
    if timeframe == "1h":
        bar_min = 60
    elif timeframe == "15m":
        bar_min = 15
    else:
        bar_min = 60
    hold_bars = int(hold_hours * 60 / bar_min)
    cooldown_bars = int(COOLDOWN_HOURS * 60 / bar_min)

    trades = []
    last_signal_bar = {"long": -10**9, "short": -10**9}

    for i in range(lookback, len(df) - hold_bars):
        if np.isnan(rolling_std[i]) or rolling_std[i] <= 0:
            continue
        z = (vol[i] - rolling_mean[i]) / rolling_std[i]
        if z < threshold:
            continue

        # Classify candle
        body_top = max(open_arr[i], close[i])
        body_bot = min(open_arr[i], close[i])
        bar_range = high[i] - low[i]
        if bar_range <= 0:
            continue
        # position of close within range
        close_pos = (close[i] - low[i]) / bar_range  # 0 = at low, 1 = at high

        is_red = close[i] < open_arr[i]
        is_green = close[i] > open_arr[i]

        side = None
        if is_red and close_pos <= CLOSE_ZONE_PCT:
            side = "long"  # capitulation low
        elif is_green and close_pos >= (1 - CLOSE_ZONE_PCT):
            side = "short"  # blow-off top

        if side is None:
            continue
        if direction_filter == "long_only" and side != "long":
            continue
        if direction_filter == "short_only" and side != "short":
            continue
        # Cooldown
        if i - last_signal_bar[side] < cooldown_bars:
            continue
        last_signal_bar[side] = i

        # Entry at this bar close, exit hold_bars later
        entry_price = float(close[i])
        exit_idx = min(i + hold_bars, len(df) - 1)
        exit_price = float(close[exit_idx])
        if entry_price <= 0:
            continue

        if side == "long":
            gross_pct = (exit_price - entry_price) / entry_price * 100
        else:
            gross_pct = (entry_price - exit_price) / entry_price * 100
        fee_pct = 2 * TAKER_FEE_PCT
        pnl_usd = BASE_SIZE_USD * (gross_pct - fee_pct) / 100
        trades.append({
            "ts_open": int(ts[i]), "ts_exit": int(ts[exit_idx]),
            "side": side, "z": float(z),
            "entry": entry_price, "exit": exit_price,
            "gross_pct": gross_pct, "pnl_usd": pnl_usd,
        })

    if not trades:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0,
                "avg_pnl": 0.0, "max_dd": 0.0, "trades": []}

    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    wr = float((pnls > 0).mean() * 100)
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(peak - eq)) if len(eq) else 0.0
    return {
        "n": len(trades), "pnl": float(pnls.sum()),
        "pf": pf, "wr": wr, "avg_pnl": float(pnls.mean()),
        "max_dd": dd, "trades": trades,
    }


def walk_forward(df: pd.DataFrame, *, threshold: float, hold_hours: int,
                 lookback: int, direction_filter: str, timeframe: str,
                 n_folds: int = N_FOLDS) -> list[dict]:
    n = len(df)
    fold_size = n // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub = df.iloc[start:end].reset_index(drop=True)
        m = simulate(sub, threshold=threshold, hold_hours=hold_hours,
                     lookback=lookback, direction_filter=direction_filter,
                     timeframe=timeframe)
        out.append({"fold": k + 1, "n": m["n"], "pnl": m["pnl"],
                    "pf": m["pf"], "wr": m["wr"], "max_dd": m["max_dd"]})
    return out


def main() -> int:
    print("[vol-climax] loading 1h...")
    df_1h = load_ohlcv_1h()
    print(f"[vol-climax] {len(df_1h)} 1h bars")
    print("[vol-climax] loading 15m (resample from 1m, takes a moment)...")
    df_15m = load_ohlcv_15m()
    print(f"[vol-climax] {len(df_15m)} 15m bars")

    results = []
    n_combos = (len(THRESHOLDS) * len(HOLD_HOURS) * len(LOOKBACKS)
                * len(TIMEFRAMES) * len(DIRECTIONS))
    print(f"[vol-climax] {n_combos} combos to evaluate\n")
    idx = 0
    for tf in TIMEFRAMES:
        df_tf = df_1h if tf == "1h" else df_15m
        for th in THRESHOLDS:
            for hh in HOLD_HOURS:
                for lb in LOOKBACKS:
                    for direction in DIRECTIONS:
                        idx += 1
                        m = simulate(df_tf, threshold=th, hold_hours=hh,
                                     lookback=lb, direction_filter=direction,
                                     timeframe=tf)
                        wf = walk_forward(df_tf, threshold=th, hold_hours=hh,
                                          lookback=lb, direction_filter=direction,
                                          timeframe=tf)
                        pos_folds = sum(1 for f in wf if f["pnl"] > 0)
                        results.append({
                            "timeframe": tf, "threshold": th, "hold_hours": hh,
                            "lookback": lb, "direction": direction,
                            "n_trades": m["n"], "pnl_usd": m["pnl"],
                            "pf": m["pf"], "wr_pct": m["wr"],
                            "avg_pnl_usd": m["avg_pnl"], "max_dd_usd": m["max_dd"],
                            "fold_pos": pos_folds, "fold_total": len(wf),
                            "fold_pnls": [f["pnl"] for f in wf],
                        })
                        if idx % 30 == 0 or idx == n_combos:
                            print(f"  [{idx}/{n_combos}] tf={tf} z>={th} hold={hh}h "
                                  f"lb={lb} {direction:<10} N={m['n']:>4} "
                                  f"PnL=${m['pnl']:+,.0f} PF={m['pf']:.2f} "
                                  f"pos={pos_folds}/{len(wf)}")

    results.sort(key=lambda r: r["pnl_usd"], reverse=True)
    print("\n[vol-climax] TOP 15 by PnL:")
    print(f"  {'tf':<3} {'z':>4} {'hold':>4} {'lb':>4} {'dir':<10} {'N':>4} "
          f"{'PnL':>10} {'PF':>5} {'WR%':>5} {'pos':>4}")
    for r in results[:15]:
        print(f"  {r['timeframe']:<3} {r['threshold']:>4.1f} {r['hold_hours']:>4} "
              f"{r['lookback']:>4} {r['direction']:<10} {r['n_trades']:>4} "
              f"${r['pnl_usd']:>+9,.0f} {r['pf']:>5.2f} {r['wr_pct']:>5.0f} "
              f"{r['fold_pos']}/{r['fold_total']}")

    # Markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Volume Climax Backtest — BTCUSDT 2y\n\n"]
    md.append("**Стратегия:**\n")
    md.append("- LONG: vol_z >= threshold AND red candle AND close in lower 30% of range "
              "(capitulation low)\n")
    md.append("- SHORT: vol_z >= threshold AND green candle AND close in upper 30% of range "
              "(blow-off top)\n")
    md.append(f"- Hold N hours, market exit. Cooldown {COOLDOWN_HOURS}h per direction.\n")
    md.append(f"- fees: 2 × {TAKER_FEE_PCT}% taker. size: ${BASE_SIZE_USD}.\n\n")

    md.append("**Sweep:**\n")
    md.append(f"- timeframes: {TIMEFRAMES}\n")
    md.append(f"- threshold (sigmas): {THRESHOLDS}\n")
    md.append(f"- hold_hours: {HOLD_HOURS}\n")
    md.append(f"- lookback (bars): {LOOKBACKS}\n")
    md.append(f"- direction: {DIRECTIONS}\n")
    md.append(f"- Total combos: {len(results)}\n\n")

    md.append("## Топ-25 по PnL\n\n")
    md.append("| tf | z | hold | lb | dir | N | PnL ($) | PF | WR% | avg | DD | pos |\n")
    md.append("|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results[:25]:
        md.append(f"| {r['timeframe']} | {r['threshold']} | {r['hold_hours']} | "
                  f"{r['lookback']} | {r['direction']} | {r['n_trades']} | "
                  f"{r['pnl_usd']:+,.0f} | {r['pf']:.2f} | {r['wr_pct']:.0f} | "
                  f"{r['avg_pnl_usd']:+,.1f} | {r['max_dd_usd']:,.0f} | "
                  f"{r['fold_pos']}/{r['fold_total']} |\n")

    md.append("\n## Худшие 5\n\n")
    md.append("| tf | z | hold | lb | dir | N | PnL ($) | PF |\n|---|---:|---:|---:|---|---:|---:|---:|\n")
    for r in results[-5:]:
        md.append(f"| {r['timeframe']} | {r['threshold']} | {r['hold_hours']} | "
                  f"{r['lookback']} | {r['direction']} | {r['n_trades']} | "
                  f"{r['pnl_usd']:+,.0f} | {r['pf']:.2f} |\n")

    md.append("\n## Best combo per direction (filtered: PF>1, pos folds >=3)\n\n")
    for direction in DIRECTIONS:
        rows = [r for r in results if r["direction"] == direction
                and r["pf"] > 1 and r["fold_pos"] >= 3]
        if not rows:
            md.append(f"### {direction}\nНет комбинаций с PF>1 и 3+/4 pos folds.\n\n")
            continue
        best = max(rows, key=lambda r: r["pnl_usd"])
        md.append(f"### {direction}\n")
        md.append(f"- tf={best['timeframe']}, z={best['threshold']}, "
                  f"hold={best['hold_hours']}h, lookback={best['lookback']}\n")
        md.append(f"- N={best['n_trades']}, PnL=**${best['pnl_usd']:+,.0f}**, "
                  f"PF={best['pf']:.2f}, WR={best['wr_pct']:.0f}%\n")
        md.append(f"- Pos folds: {best['fold_pos']}/{best['fold_total']}\n")
        md.append(f"- Per-fold PnL: {[round(p, 0) for p in best['fold_pnls']]}\n\n")

    md.append("\n## Verdict\n\n")
    best_overall = results[0]
    if best_overall["pf"] >= 1.5 and best_overall["fold_pos"] >= 3 and best_overall["n_trades"] >= 30:
        md.append(f"✅ **Volume climax edge подтверждён.** "
                  f"tf={best_overall['timeframe']}, z={best_overall['threshold']}, "
                  f"hold={best_overall['hold_hours']}h, "
                  f"{best_overall['direction']} → PF {best_overall['pf']:.2f}, "
                  f"{best_overall['fold_pos']}/{best_overall['fold_total']} positive folds, "
                  f"N={best_overall['n_trades']}.\n\n")
    elif best_overall["pf"] >= 1.0:
        md.append(f"⚠️ Слабый edge: best PF {best_overall['pf']:.2f}, N={best_overall['n_trades']}. "
                  f"Possibly weak/marginal.\n\n")
    else:
        md.append(f"❌ Edge не подтверждён: best PF {best_overall['pf']:.2f}.\n\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[vol-climax] wrote {OUT_MD}")

    pd.DataFrame([{k: v for k, v in r.items() if k != "fold_pnls"} for r in results]).to_csv(
        CSV_OUT, index=False)
    print(f"[vol-climax] wrote {CSV_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
