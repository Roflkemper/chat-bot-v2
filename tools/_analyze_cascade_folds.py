"""Анализ почему 1 из 4 folds теряет деньги в cascade LONG bounce.

Берёт лучшую стратегию (LONG on LONG-cascade, thr=7 BTC, win=3 мин,
hold=24h, TP=2%, SL=2%) и разбивает по folds:
- Какие даты каждого fold
- BTC price change в fold (тренд up/down/range)
- Сколько trades в каждом fold
- PnL по folds + распределение TP/SL/timeout
- ADX/EMA50/EMA200 распределение в каждом fold

Цель: понять чем плохой fold отличается от хороших.

Запуск: python tools/_analyze_cascade_folds.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICE_CSV = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
LIQ_PARQUET = ROOT / "data" / "historical" / "bybit_liquidations_2024.parquet"

# Best config from previous sweep
CONFIG = {
    "casc_side": "long", "thr_btc": 7, "win_min": 3,
    "trade_side": "long", "hold_hrs": 24, "sl_pct": 2.0, "tp_pct": 2.0,
}
FEE_RT_PCT = 0.17
SIZE_USD = 1000.0
N_FOLDS = 4


def load_price():
    df = pd.read_csv(PRICE_CSV)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    return df[~df.index.duplicated(keep="first")]


def load_liq():
    df = pd.read_parquet(LIQ_PARQUET)
    df["liq_side"] = df["side"].apply(lambda x: "long" if x == "Sell" else "short")
    return df.set_index("ts").sort_index()


def detect_cascades(liq_df, *, threshold_btc, window_min, side="long"):
    cascades = []
    last_ts = None
    side_df = liq_df[liq_df["liq_side"] == side].copy()
    side_df["bucket"] = side_df.index.floor("1min")
    per_min = side_df.groupby("bucket")["qty"].sum().sort_index()
    rolling = per_min.rolling(f"{window_min}min").sum()
    for ts, total in rolling.items():
        if total >= threshold_btc:
            if last_ts is None or (ts - last_ts) >= pd.Timedelta(minutes=30):
                cascades.append((ts, float(total)))
                last_ts = ts
    return cascades


def simulate(price_df, entry_ts, side, hold_hrs, sl_pct, tp_pct):
    try:
        idx = price_df.index.get_indexer([entry_ts], method="bfill")[0]
        if idx < 0 or idx >= len(price_df):
            return None
    except Exception:
        return None
    entry = float(price_df.iloc[idx]["close"])
    sl = entry * (1 - sl_pct/100) if side == "long" else entry * (1 + sl_pct/100)
    tp = entry * (1 + tp_pct/100) if side == "long" else entry * (1 - tp_pct/100)
    end_idx = min(idx + hold_hrs * 60, len(price_df) - 1)
    for i in range(idx + 1, end_idx + 1):
        bar = price_df.iloc[i]
        hi, lo = float(bar["high"]), float(bar["low"])
        if side == "long":
            if lo <= sl: return {"entry": entry, "exit": sl, "reason": "SL", "exit_ts": bar.name}
            if hi >= tp: return {"entry": entry, "exit": tp, "reason": "TP", "exit_ts": bar.name}
        else:
            if hi >= sl: return {"entry": entry, "exit": sl, "reason": "SL", "exit_ts": bar.name}
            if lo <= tp: return {"entry": entry, "exit": tp, "reason": "TP", "exit_ts": bar.name}
    last_close = float(price_df.iloc[end_idx]["close"])
    return {"entry": entry, "exit": last_close, "reason": "timeout", "exit_ts": price_df.iloc[end_idx].name}


def pnl_usd(side, entry, exit):
    sign = 1 if side == "long" else -1
    return (sign * (exit - entry) / entry * 100 - FEE_RT_PCT) / 100 * SIZE_USD


def main():
    price_df = load_price()
    liq_df = load_liq()
    price_df = price_df.loc[liq_df.index[0]:liq_df.index[-1]]

    print(f"Period: {liq_df.index[0]} → {liq_df.index[-1]}", file=sys.stderr)
    print(f"Config: {CONFIG}\n", file=sys.stderr)

    cascades = detect_cascades(liq_df, threshold_btc=CONFIG["thr_btc"],
                               window_min=CONFIG["win_min"], side=CONFIG["casc_side"])
    print(f"Total cascades: {len(cascades)}", file=sys.stderr)

    # Build folds
    fold_edges = pd.date_range(liq_df.index[0], liq_df.index[-1], periods=N_FOLDS+1)
    folds = []
    for i in range(N_FOLDS):
        folds.append((fold_edges[i], fold_edges[i+1]))

    # Simulate
    trades = []
    for ts, casc_qty in cascades:
        sim = simulate(price_df, ts, CONFIG["trade_side"], CONFIG["hold_hrs"],
                       CONFIG["sl_pct"], CONFIG["tp_pct"])
        if sim is None:
            continue
        pnl = pnl_usd(CONFIG["trade_side"], sim["entry"], sim["exit"])
        trades.append({
            "ts": ts, "casc_qty_btc": casc_qty,
            "entry": sim["entry"], "exit": sim["exit"],
            "reason": sim["reason"], "exit_ts": sim["exit_ts"],
            "pnl_usd": pnl,
        })

    print(f"Trades: {len(trades)}\n", file=sys.stderr)

    # Per fold analysis
    print(f"{'='*100}", file=sys.stderr)
    print(f"{'Fold':<6} {'Period':<48} {'BTC %Δ':<8} {'N':<4} {'Wins':<5} {'TP':<3} {'SL':<3} {'TO':<3} {'PnL':<8}", file=sys.stderr)
    print(f"{'='*100}", file=sys.stderr)

    for i, (fs, fe) in enumerate(folds):
        fold_trades = [t for t in trades if fs <= t["ts"] < fe]
        # BTC price change in this fold
        try:
            p_start = float(price_df.loc[price_df.index >= fs].iloc[0]["close"])
            p_end = float(price_df.loc[price_df.index < fe].iloc[-1]["close"])
            pct_change = (p_end - p_start) / p_start * 100
        except Exception:
            pct_change = 0
        n_tp = sum(1 for t in fold_trades if t["reason"] == "TP")
        n_sl = sum(1 for t in fold_trades if t["reason"] == "SL")
        n_to = sum(1 for t in fold_trades if t["reason"] == "timeout")
        n_wins = sum(1 for t in fold_trades if t["pnl_usd"] > 0)
        pnl_total = sum(t["pnl_usd"] for t in fold_trades)

        period_str = f"{fs.strftime('%Y-%m-%d')} → {fe.strftime('%Y-%m-%d')}"
        print(f"{i+1:<6} {period_str:<48} {pct_change:+6.1f}%  "
              f"{len(fold_trades):<4} {n_wins:<5} {n_tp:<3} {n_sl:<3} {n_to:<3} ${pnl_total:+.1f}", file=sys.stderr)

    # Detailed: bad fold (negative PnL)
    print(f"\n{'='*100}", file=sys.stderr)
    print("DETAILED VIEW OF BAD FOLD (negative PnL)", file=sys.stderr)
    print(f"{'='*100}", file=sys.stderr)

    for i, (fs, fe) in enumerate(folds):
        fold_trades = [t for t in trades if fs <= t["ts"] < fe]
        pnl_total = sum(t["pnl_usd"] for t in fold_trades)
        if pnl_total >= 0:
            continue
        print(f"\n--- Fold #{i+1}: {fs.strftime('%Y-%m-%d')} → {fe.strftime('%Y-%m-%d')} | PnL ${pnl_total:+.1f} ---", file=sys.stderr)

        # Show first 10 trades
        print(f"{'Entry TS':<30} {'Casc BTC':<10} {'Entry':<10} {'Exit':<10} {'Reason':<10} {'PnL':<8}", file=sys.stderr)
        for t in fold_trades[:15]:
            print(f"{t['ts'].strftime('%Y-%m-%d %H:%M:%S'):<30} "
                  f"{t['casc_qty_btc']:<10.2f} ${t['entry']:<9.0f} ${t['exit']:<9.0f} "
                  f"{t['reason']:<10} ${t['pnl_usd']:+.1f}", file=sys.stderr)

        # Distribution
        wins = [t['pnl_usd'] for t in fold_trades if t['pnl_usd'] > 0]
        losses = [t['pnl_usd'] for t in fold_trades if t['pnl_usd'] <= 0]
        print(f"\n  Wins: {len(wins)} avg=${np.mean(wins):.1f if wins else 0}", file=sys.stderr)
        print(f"  Losses: {len(losses)} avg=${np.mean(losses):.1f if losses else 0}", file=sys.stderr)

    # Trend context for ALL folds — what was happening
    print(f"\n{'='*100}", file=sys.stderr)
    print("BTC PRICE TREND CONTEXT (1d resample)", file=sys.stderr)
    print(f"{'='*100}", file=sys.stderr)
    df_1d = price_df.resample("1D")["close"].last().dropna()
    for i, (fs, fe) in enumerate(folds):
        sub = df_1d[(df_1d.index >= fs) & (df_1d.index < fe)]
        if len(sub) < 2:
            continue
        p_start, p_end = float(sub.iloc[0]), float(sub.iloc[-1])
        hi, lo = float(sub.max()), float(sub.min())
        pct_change = (p_end - p_start) / p_start * 100
        max_dd_pct = (lo - hi) / hi * 100
        max_run_pct = (hi - lo) / lo * 100
        trend = "🔴 DOWN" if pct_change < -5 else "🟢 UP" if pct_change > 5 else "🟡 RANGE"
        print(f"Fold #{i+1}: {trend}  Δ={pct_change:+.1f}%  range_low=${lo:.0f}  range_high=${hi:.0f}  max_drawdown={max_dd_pct:.1f}%", file=sys.stderr)

    print("\nDONE.", file=sys.stderr)


if __name__ == "__main__":
    main()
