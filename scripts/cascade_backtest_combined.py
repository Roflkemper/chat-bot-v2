"""Cascade backtest: 2024 historical + 2026 live (Bybit), price from BTCUSDT_1m_2y.csv.

Replaces the Feb-Jun 2024-only window of backtest_post_cascade.py:
- Uses 1m BTC prices (more precise than 1h)
- Combines `data/historical/bybit_liquidations_2024.parquet`
  + Bybit rows from `market_live/liquidations.csv`
- Outputs:
    state/cascade_backtest_combined.json
    stdout summary table

Run:  python scripts/cascade_backtest_combined.py
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HIST_PARQUET = ROOT / "data/historical/bybit_liquidations_2024.parquet"
LIVE_CSV = ROOT / "market_live/liquidations.csv"
PRICE_CSV = ROOT / "backtests/frozen/BTCUSDT_1m_2y.csv"
OUTPUT_JSON = ROOT / "state/cascade_backtest_combined.json"

WINDOW_MIN = 5
THRESHOLDS = [0.5, 1.0, 2.0, 5.0, 10.0]
HORIZONS_H = [1, 4, 12, 24]
STRONG_PCT = 0.3  # |move| > 0.3% considered "strong"


def load_liquidations() -> pd.DataFrame:
    """Combine historical 2024 parquet + live 2026 CSV (Bybit only), normalize to long/short side flags."""
    hist = pd.read_parquet(HIST_PARQUET)
    hist["ts"] = pd.to_datetime(hist["ts_ms"], unit="ms", utc=True)
    hist["is_long_liq"] = hist["side"].str.lower() == "sell"
    hist["is_short_liq"] = hist["side"].str.lower() == "buy"
    hist = hist[["ts", "qty", "is_long_liq", "is_short_liq"]].copy()
    hist["source"] = "hist_2024"
    print(f"  historical: {len(hist):,} rows, {hist.ts.min()} → {hist.ts.max()}")

    live = pd.read_csv(LIVE_CSV)
    live = live[live["exchange"] == "bybit"].copy()
    live["ts"] = pd.to_datetime(live["ts_utc"], errors="coerce", utc=True)
    live = live.dropna(subset=["ts", "qty"])
    live["is_long_liq"] = live["side"].str.lower() == "long"
    live["is_short_liq"] = live["side"].str.lower() == "short"
    live = live[["ts", "qty", "is_long_liq", "is_short_liq"]].copy()
    live["source"] = "live_2026"
    print(f"  live bybit: {len(live):,} rows, {live.ts.min()} → {live.ts.max()}")

    df = pd.concat([hist, live], ignore_index=True).sort_values("ts")
    return df


def detect_cascades(df_liq: pd.DataFrame, threshold_btc: float, window_min: int) -> pd.DataFrame:
    """Rolling 5-min sum per side; emit one cascade event per (side, peak-window-end) with dedup.

    Returns DataFrame columns: ts, side (long_liq/short_liq), threshold_btc, total_btc, source.
    """
    df = df_liq.set_index("ts").sort_index()
    # Per-side qty series
    long_qty = df.loc[df["is_long_liq"], "qty"]
    short_qty = df.loc[df["is_short_liq"], "qty"]

    out = []
    for side_name, series in [("long_liq", long_qty), ("short_liq", short_qty)]:
        if series.empty:
            continue
        # Rolling sum over window
        roll = series.rolling(f"{window_min}min").sum()
        triggered = roll >= threshold_btc
        # Dedup: only first ts in a contiguous triggered run (no re-fire until window_min cooldown)
        last_emit = None
        for ts, val in triggered[triggered].items():
            if last_emit is not None and (ts - last_emit) < timedelta(minutes=window_min):
                continue
            out.append({
                "ts": ts,
                "side": side_name,
                "threshold_btc": threshold_btc,
                "total_btc": float(val),
            })
            last_emit = ts
    return pd.DataFrame(out)


def measure_returns(events: pd.DataFrame, price: pd.DataFrame, horizons_h: list[int]) -> pd.DataFrame:
    """For each cascade event, attach forward returns at horizon hours."""
    if events.empty:
        return events.copy()
    price_idx = price.index  # DatetimeIndex
    closes = price["close"].values

    def fwd_ret(t0, hours):
        t1 = t0 + pd.Timedelta(hours=hours)
        if t1 > price_idx[-1]:
            return np.nan
        i0 = price_idx.get_indexer([t0], method="nearest")[0]
        i1 = price_idx.get_indexer([t1], method="nearest")[0]
        if i0 < 0 or i1 < 0 or i0 == i1:
            return np.nan
        return (closes[i1] / closes[i0] - 1) * 100

    rows = events.copy()
    for h in horizons_h:
        rows[f"r{h}h"] = [fwd_ret(t, h) for t in rows["ts"]]
    return rows


def aggregate(events: pd.DataFrame, horizons_h: list[int]) -> dict:
    """Aggregate per (side, threshold) over horizons. Mirrors backtest_post_cascade output schema."""
    out = {}
    for (side, thr), grp in events.groupby(["side", "threshold_btc"]):
        key = f"{side}_{thr:g}btc"
        node = {"side": side, "threshold_btc": float(thr), "n": int(len(grp))}
        for h in horizons_h:
            col = f"r{h}h"
            s = grp[col].dropna()
            if s.empty:
                node[f"{h}h"] = None
                continue
            node[f"{h}h"] = {
                "n": int(len(s)),
                "mean": round(float(s.mean()), 3),
                "median": round(float(s.median()), 3),
                "p25": round(float(s.quantile(0.25)), 3),
                "p75": round(float(s.quantile(0.75)), 3),
                "pct_up": round(float((s > 0).mean() * 100), 1),
                "pct_strong_up": round(float((s > STRONG_PCT).mean() * 100), 1),
                "pct_strong_down": round(float((s < -STRONG_PCT).mean() * 100), 1),
            }
        out[key] = node
    return out


def main() -> int:
    print("Loading liquidations...")
    df_liq = load_liquidations()
    print(f"  combined: {len(df_liq):,} rows, sides long={df_liq['is_long_liq'].sum():,}  short={df_liq['is_short_liq'].sum():,}")

    print(f"\nLoading 1m price from {PRICE_CSV.name}...")
    price = pd.read_csv(PRICE_CSV, usecols=["ts", "close"])
    price["ts"] = pd.to_datetime(price["ts"], unit="ms", utc=True)
    price = price.set_index("ts").sort_index()
    print(f"  price: {len(price):,} bars, {price.index.min()} → {price.index.max()}")

    all_events = []
    for thr in THRESHOLDS:
        ev = detect_cascades(df_liq, threshold_btc=thr, window_min=WINDOW_MIN)
        if ev.empty:
            continue
        ev = measure_returns(ev, price, HORIZONS_H)
        # Source tag — derived from time
        ev["source"] = ev["ts"].apply(lambda t: "live_2026" if t.year >= 2026 else "hist_2024")
        all_events.append(ev)
        n_l = int((ev["side"] == "long_liq").sum())
        n_s = int((ev["side"] == "short_liq").sum())
        print(f"  thr={thr:g}BTC: long={n_l}  short={n_s}  total={len(ev)}")
    df_ev = pd.concat(all_events, ignore_index=True) if all_events else pd.DataFrame()

    print(f"\nTotal cascade events: {len(df_ev):,}")
    if df_ev.empty:
        print("No events — aborting.")
        return 1

    # Aggregate overall + per-source
    summary = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "data_window": {
            "start": str(df_liq["ts"].min()),
            "end": str(df_liq["ts"].max()),
        },
        "config": {
            "window_min": WINDOW_MIN,
            "thresholds_btc": THRESHOLDS,
            "horizons_h": HORIZONS_H,
            "strong_pct_threshold": STRONG_PCT,
        },
        "events_count_by_source": df_ev["source"].value_counts().to_dict(),
        "scenarios_all": aggregate(df_ev, HORIZONS_H),
        "scenarios_hist_2024": aggregate(df_ev[df_ev["source"] == "hist_2024"], HORIZONS_H),
        "scenarios_live_2026": aggregate(df_ev[df_ev["source"] == "live_2026"], HORIZONS_H),
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved → {OUTPUT_JSON}")

    # Print compact table
    print("\n" + "=" * 80)
    print(f"{'scenario':>22} {'n':>5} {'4h_mean':>9} {'4h_up%':>7} {'12h_mean':>10} {'12h_up%':>8} {'24h_mean':>10} {'24h_up%':>8}")
    print("=" * 80)
    for key, node in summary["scenarios_all"].items():
        row = [key, node["n"]]
        for h in [4, 12, 24]:
            h_data = node[f"{h}h"]
            if h_data:
                row += [h_data["mean"], h_data["pct_up"]]
            else:
                row += ["--", "--"]
        print(f"{row[0]:>22} {row[1]:>5} {row[2]:>+9.3f} {row[3]:>6.1f}% {row[4]:>+10.3f} {row[5]:>7.1f}% {row[6]:>+10.3f} {row[7]:>7.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
