"""Cross-asset lead-lag analysis on 1-minute bars (BTC / ETH / XRP).

Goal: find if ETH or XRP leads BTC (or vice versa) by 1-5 minutes on 1m frame.
On 1h frame lead-lag = 0 (already established).

Last 90 days only -> ~130k bars overlap, fast enough.

Output:
  state/cross_asset_leadlag_1m.json
  state/cross_asset_leadlag_1m.md
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOOKBACK_DAYS = 90
MAX_LAG_MIN = 10
ROLLING_WINDOW_DAYS = 30


def _load(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(ROOT / "backtests" / "frozen" / f"{symbol}_1m_2y.csv")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()[["close"]]
    df.columns = [symbol]
    return df


def _align_three() -> pd.DataFrame:
    btc = _load("BTCUSDT")
    eth = _load("ETHUSDT")
    xrp = _load("XRPUSDT")
    df = btc.join([eth, xrp], how="inner")
    end = df.index.max()
    df = df[df.index >= end - timedelta(days=LOOKBACK_DAYS)]
    return df


def _returns(df: pd.DataFrame) -> pd.DataFrame:
    return np.log(df / df.shift(1)).dropna()


def lead_lag(returns: pd.DataFrame, max_lag: int = MAX_LAG_MIN) -> dict:
    """Cross-correlation at ±N lag (in minutes).
    Positive lag => first asset leads second by `lag` bars.
    """
    out = {}
    pairs = [("BTCUSDT", "ETHUSDT"), ("BTCUSDT", "XRPUSDT"), ("ETHUSDT", "XRPUSDT")]
    for a, b in pairs:
        results = {}
        for lag in range(-max_lag, max_lag + 1):
            if lag < 0:
                shifted = returns[b].shift(-lag)
                c = returns[a].corr(shifted)
            else:
                shifted = returns[a].shift(lag)
                c = returns[b].corr(shifted)
            results[lag] = round(float(c), 5) if not pd.isna(c) else None
        valid = {k: v for k, v in results.items() if v is not None}
        peak_lag = max(valid, key=lambda k: valid[k])
        out[f"{a}_{b}"] = {
            "by_lag_min": results,
            "peak_lag_min": peak_lag,
            "peak_corr": valid[peak_lag],
            "corr_at_lag0": results.get(0),
            "interpretation": (
                f"{a} leads {b} by {peak_lag}m (corr {valid[peak_lag]:.4f})"
                if peak_lag > 0 else
                f"{b} leads {a} by {abs(peak_lag)}m (corr {valid[peak_lag]:.4f})"
                if peak_lag < 0 else
                f"{a} and {b} synchronous (lag=0, corr {valid[peak_lag]:.4f})"
            ),
        }
    return out


def rolling_lead_lag(returns: pd.DataFrame, window_days: int = ROLLING_WINDOW_DAYS,
                     max_lag: int = MAX_LAG_MIN) -> dict:
    """Split history into 30-day windows, report peak lag/corr per window."""
    end = returns.index.max()
    start = returns.index.min()
    out = {}
    pairs = [("BTCUSDT", "ETHUSDT"), ("BTCUSDT", "XRPUSDT"), ("ETHUSDT", "XRPUSDT")]
    windows = []
    cursor_end = end
    while cursor_end - timedelta(days=window_days) >= start:
        cursor_start = cursor_end - timedelta(days=window_days)
        windows.append((cursor_start, cursor_end))
        cursor_end = cursor_start
    windows.reverse()

    for a, b in pairs:
        per_window = []
        for ws, we in windows:
            r = returns[(returns.index >= ws) & (returns.index < we)]
            if len(r) < 1000:
                continue
            best_lag = 0
            best_corr = -2.0
            corr_at_zero = None
            for lag in range(-max_lag, max_lag + 1):
                if lag < 0:
                    c = r[a].corr(r[b].shift(-lag))
                else:
                    c = r[b].corr(r[a].shift(lag))
                if pd.isna(c):
                    continue
                if lag == 0:
                    corr_at_zero = round(float(c), 5)
                if c > best_corr:
                    best_corr = float(c)
                    best_lag = lag
            per_window.append({
                "window_start": str(ws.date()),
                "window_end": str(we.date()),
                "n_bars": len(r),
                "peak_lag_min": best_lag,
                "peak_corr": round(best_corr, 5),
                "corr_at_lag0": corr_at_zero,
            })
        out[f"{a}_{b}"] = per_window
    return out


def main() -> dict:
    print(f"Loading 3 symbols (1m, last {LOOKBACK_DAYS}d)...")
    df = _align_three()
    print(f"Aligned: {len(df):,} bars, {df.index.min()} -> {df.index.max()}")
    returns = _returns(df)
    print(f"Returns: {len(returns):,} rows")

    print("Computing global lead-lag (±10m)...")
    ll_global = lead_lag(returns, max_lag=MAX_LAG_MIN)
    for pair, info in ll_global.items():
        print(f"  {pair}: {info['interpretation']}  (lag0 corr={info['corr_at_lag0']})")

    print("Computing rolling 30-day lead-lag windows...")
    ll_rolling = rolling_lead_lag(returns, window_days=ROLLING_WINDOW_DAYS, max_lag=MAX_LAG_MIN)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_window": {
            "start": str(df.index.min()),
            "end": str(df.index.max()),
            "bars": int(len(df)),
            "lookback_days": LOOKBACK_DAYS,
        },
        "params": {
            "max_lag_minutes": MAX_LAG_MIN,
            "rolling_window_days": ROLLING_WINDOW_DAYS,
        },
        "lead_lag_global": ll_global,
        "lead_lag_rolling_30d": ll_rolling,
    }

    out_dir = ROOT / "state"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cross_asset_leadlag_1m.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {json_path}")

    # Brief markdown summary
    md = []
    md.append(f"# Cross-asset lead-lag (1m) — generated {result['generated_at']}")
    md.append("")
    md.append(f"Window: {result['data_window']['start']} -> {result['data_window']['end']} ({result['data_window']['bars']:,} 1m bars)")
    md.append(f"Lag range: ±{MAX_LAG_MIN} minutes")
    md.append("")
    md.append("## Global peak lag")
    md.append("| Pair | Peak lag (min) | Peak corr | Corr@lag=0 | Interpretation |")
    md.append("|---|---|---|---|---|")
    for pair, info in ll_global.items():
        md.append(f"| {pair} | {info['peak_lag_min']} | {info['peak_corr']:.4f} | {info['corr_at_lag0']:.4f} | {info['interpretation']} |")
    md.append("")
    md.append("## Rolling 30-day windows (peak lag stability)")
    for pair, windows in ll_rolling.items():
        md.append(f"### {pair}")
        md.append("| Window | Peak lag (min) | Peak corr | Corr@lag=0 |")
        md.append("|---|---|---|---|")
        for w in windows:
            md.append(f"| {w['window_start']} -> {w['window_end']} | {w['peak_lag_min']} | {w['peak_corr']:.4f} | {w['corr_at_lag0']:.4f} |")
        md.append("")
    md_path = out_dir / "cross_asset_leadlag_1m.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"Saved: {md_path}")
    return result


if __name__ == "__main__":
    main()
