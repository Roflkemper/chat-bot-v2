"""Liquidation cluster detector backtest on April-May 2026 (~12 days).

Walk through liq parquet files, simulate detector at each minute, evaluate
forward 60-min outcomes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "LIQ_CLUSTER_BACKTEST.md"

LIQ_DIR = ROOT / "market_live" / "liquidations"
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

LIQ_WINDOW_MIN = 5
LIQ_THRESHOLD_USD = 1_000_000.0
LIQ_DOMINANCE_RATIO = 0.3
TP_PCT = 0.5
SL_PCT = 0.4
HOLD_MIN = 60


def _load_all_liq():
    """Load all parquet files from market_live/liquidations/<ex>/BTCUSDT/."""
    frames = []
    for ex_dir in LIQ_DIR.iterdir():
        if not ex_dir.is_dir(): continue
        sym_dir = ex_dir / "BTCUSDT"
        if not sym_dir.exists(): continue
        for p in sorted(sym_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(p)
                frames.append(df)
            except Exception:
                continue
    if not frames: return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if "ts_ms" in df.columns:
        df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True, errors="coerce")
    df = df.dropna(subset=["ts", "price", "value_usd"])
    return df.sort_values("ts").reset_index(drop=True)


def main() -> int:
    print("[liq-bt] loading parquet liquidations...")
    liq = _load_all_liq()
    if liq.empty:
        print("[liq-bt] no liquidations data"); return 1
    print(f"[liq-bt] {len(liq):,} liquidations  ({liq['ts'].min()} → {liq['ts'].max()})")
    print(f"  long: {(liq['side']=='long').sum()}  short: {(liq['side']=='short').sum()}")

    print("[liq-bt] loading 1m close prices...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m["ts_utc"] = pd.to_datetime(df_1m["ts"], unit="ms", utc=True)
    # Keep only overlap with liq period
    start = liq["ts"].min()
    end = liq["ts"].max()
    df_1m = df_1m[(df_1m["ts_utc"] >= start) & (df_1m["ts_utc"] <= end)].reset_index(drop=True)
    print(f"  {len(df_1m):,} 1m bars in overlap period")
    if df_1m.empty:
        print("[liq-bt] no overlap"); return 1

    closes_idx = df_1m.set_index("ts_utc")["close"]

    # Walk through 1m bars, at each compute LONG/SHORT liq totals over last 5min
    print("[liq-bt] scanning for cluster signals...")
    long_signals = []
    short_signals = []
    last_long_signal_ts = None
    last_short_signal_ts = None
    cooldown_min = 30  # 30min between signals same direction

    # Pre-bin liquidations by minute for speed
    liq["minute"] = liq["ts"].dt.floor("1min")

    for i in range(0, len(df_1m), 5):  # check every 5 min
        ts = df_1m["ts_utc"].iloc[i]
        window_start = ts - pd.Timedelta(minutes=LIQ_WINDOW_MIN)
        window_liq = liq[(liq["ts"] >= window_start) & (liq["ts"] <= ts)]
        if window_liq.empty: continue
        long_total = float(window_liq.loc[window_liq["side"] == "long", "value_usd"].sum())
        short_total = float(window_liq.loc[window_liq["side"] == "short", "value_usd"].sum())

        # LONG cluster (long liquidations dominate → bounce setup)
        if long_total >= LIQ_THRESHOLD_USD and short_total <= long_total * LIQ_DOMINANCE_RATIO:
            if (last_long_signal_ts is None or
                (ts - last_long_signal_ts).total_seconds() / 60 >= cooldown_min):
                price0 = float(df_1m["close"].iloc[i])
                long_signals.append({
                    "ts": ts, "side": "long", "price0": price0,
                    "long_liq_5m": long_total, "short_liq_5m": short_total,
                })
                last_long_signal_ts = ts

        # SHORT cluster
        if short_total >= LIQ_THRESHOLD_USD and long_total <= short_total * LIQ_DOMINANCE_RATIO:
            if (last_short_signal_ts is None or
                (ts - last_short_signal_ts).total_seconds() / 60 >= cooldown_min):
                price0 = float(df_1m["close"].iloc[i])
                short_signals.append({
                    "ts": ts, "side": "short", "price0": price0,
                    "long_liq_5m": long_total, "short_liq_5m": short_total,
                })
                last_short_signal_ts = ts

    print(f"[liq-bt] {len(long_signals)} LONG signals, {len(short_signals)} SHORT signals")
    all_signals = long_signals + short_signals

    if not all_signals:
        print("[liq-bt] no signals at threshold"); return 0

    # Evaluate forward 60-min: TP/SL hit
    print("[liq-bt] evaluating outcomes...")
    results = []
    for sig in all_signals:
        ts = sig["ts"]
        side = sig["side"]
        price0 = sig["price0"]
        target_end = ts + pd.Timedelta(minutes=HOLD_MIN)
        forward_bars = df_1m[(df_1m["ts_utc"] > ts) & (df_1m["ts_utc"] <= target_end)]
        if forward_bars.empty:
            results.append({**sig, "outcome": "NO_DATA", "pnl_pct": 0.0})
            continue
        if side == "long":
            tp = price0 * (1 + TP_PCT / 100)
            sl = price0 * (1 - SL_PCT / 100)
        else:
            tp = price0 * (1 - TP_PCT / 100)
            sl = price0 * (1 + SL_PCT / 100)
        outcome = "TIMEOUT"
        for _, bar in forward_bars.iterrows():
            if side == "long":
                if bar["high"] >= tp: outcome = "TP"; break
                if bar["low"] <= sl: outcome = "SL"; break
            else:
                if bar["low"] <= tp: outcome = "TP"; break
                if bar["high"] >= sl: outcome = "SL"; break
        if outcome == "TP":
            pnl_pct = TP_PCT - 0.165  # net of round-trip fee
        elif outcome == "SL":
            pnl_pct = -SL_PCT - 0.165
        else:
            exit_price = float(forward_bars["close"].iloc[-1])
            if side == "long":
                pnl_pct = (exit_price - price0) / price0 * 100 - 0.165
            else:
                pnl_pct = (price0 - exit_price) / price0 * 100 - 0.165
        results.append({**sig, "outcome": outcome, "pnl_pct": pnl_pct})

    df_res = pd.DataFrame(results)

    md = []
    md.append("# Liquidation cluster detector backtest")
    md.append("")
    md.append(f"**Period:** {start} → {end} (~{(end-start).days} days)")
    md.append(f"**Threshold:** $1M one-side / 5min, dominance ratio < 0.3")
    md.append(f"**Trade:** TP=+{TP_PCT}%, SL=-{SL_PCT}%, hold={HOLD_MIN}min, fees 0.165%")
    md.append("")
    md.append("## Per-direction summary")
    md.append("")
    rows = []
    for side in ("long", "short"):
        sub = df_res[df_res["side"] == side]
        if sub.empty: continue
        n = len(sub)
        wins = sub[sub["pnl_pct"] > 0]["pnl_pct"].sum()
        losses = -sub[sub["pnl_pct"] < 0]["pnl_pct"].sum()
        pf = (wins / losses) if losses > 0 else 999.0
        rows.append({
            "side": side, "n": n,
            "n_TP": int((sub["outcome"] == "TP").sum()),
            "n_SL": int((sub["outcome"] == "SL").sum()),
            "n_TIMEOUT": int((sub["outcome"] == "TIMEOUT").sum()),
            "wr": round((sub["pnl_pct"] > 0).sum() / n * 100, 1),
            "pf": round(pf, 3),
            "pnl_pct_total": round(sub["pnl_pct"].sum(), 2),
            "avg_pnl_pct": round(sub["pnl_pct"].mean(), 4),
        })
    md.append(pd.DataFrame(rows).to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    long_pnl = sum(r["pnl_pct"] for r in results if r["side"] == "long")
    short_pnl = sum(r["pnl_pct"] for r in results if r["side"] == "short")
    if long_pnl > 0.5 and len(long_signals) >= 5:
        md.append(f"✅ LONG cluster detector promising: +{long_pnl:.2f}% on N={len(long_signals)} "
                  f"in {(end-start).days}d.")
    if short_pnl > 0.5 and len(short_signals) >= 5:
        md.append(f"✅ SHORT cluster detector promising: +{short_pnl:.2f}% on N={len(short_signals)}.")
    if long_pnl <= 0 and short_pnl <= 0:
        md.append(f"❌ Both directions unprofitable. "
                  f"LONG: {long_pnl:+.2f}%, SHORT: {short_pnl:+.2f}%. "
                  f"Threshold/dominance/TP/SL need tuning, OR liquidations don't predict bounces "
                  f"in this regime.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[liq-bt] wrote {OUT_MD}")
    if rows:
        print(pd.DataFrame(rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
