"""short_pdh_rejection — calibration of additional trend filters.

Background: precision tracker showed -0.15% expectancy on N=59 live setups,
with 29/59 (49%) clustered on 2026-05-01 (trending-up day) where every
short went to SL. Current detector already has RSI_1h>=72 + slope_6h>=1%
gates but those don't prevent firing during strong trending rallies.

Hypotheses:
  H1: slope_24h <= +2% — filter out trending-up days
  H2: close <= SMA200_1h * 1.02 — filter when price is far above long-term mean
  H3: BOTH

Approach: re-emit short_pdh_rejection on full 2y 1m, post-filter each emit
through candidate filters, simulate trades, compare PF/PnL/WR/WF.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_detectors_honest import (  # noqa: E402
    DATA_1M, _build_aggregations, _emit_setups, _simulate_trade,
)
from services.setup_detector.setup_types import detect_short_pdh_rejection  # noqa: E402


def _slope_24h_for(ts_1h: np.ndarray, close_1h: np.ndarray, ts_target: int) -> float | None:
    """Return % change between close 24h ago and the close at-or-before ts_target."""
    h_idx = np.searchsorted(ts_1h, ts_target, side="right") - 1
    if h_idx < 24:
        return None
    p_now = float(close_1h[h_idx])
    p_24 = float(close_1h[h_idx - 24])
    if p_24 <= 0:
        return None
    return (p_now / p_24 - 1.0) * 100.0


def _sma200_for(ts_1h: np.ndarray, close_1h: np.ndarray, ts_target: int) -> float | None:
    h_idx = np.searchsorted(ts_1h, ts_target, side="right") - 1
    if h_idx < 200:
        return None
    return float(np.mean(close_1h[h_idx - 199:h_idx + 1]))


def _stats(trades: list, label: str, n_folds: int = 4,
           ts_min: int | None = None, ts_max: int | None = None) -> dict:
    if not trades:
        return {"label": label, "n": 0, "wr_%": 0, "pf": 0, "pnl_%": 0,
                "folds_pos": f"0/{n_folds}"}
    n = len(trades)
    wr = sum(1 for t in trades if t.pnl_pct > 0) / n * 100
    wins = sum(t.pnl_pct for t in trades if t.pnl_pct > 0)
    losses = -sum(t.pnl_pct for t in trades if t.pnl_pct < 0)
    pf = wins / losses if losses > 0 else 999.0
    pnl = sum(t.pnl_pct for t in trades)
    folds_pos = 0
    if ts_min is not None and ts_max is not None and ts_max > ts_min:
        fold_span = (ts_max - ts_min) / n_folds
        for k in range(n_folds):
            lo = ts_min + k * fold_span
            hi = ts_min + (k + 1) * fold_span
            sub = [t for t in trades if lo <= t.entry_ts < hi]
            if sub and sum(s.pnl_pct for s in sub) > 0:
                folds_pos += 1
    return {
        "label": label, "n": n, "wr_%": round(wr, 1), "pf": round(pf, 3),
        "pnl_%": round(pnl, 2), "folds_pos": f"{folds_pos}/{n_folds}",
    }


def main() -> int:
    print("[calib] loading 1m...")
    df = pd.read_csv(DATA_1M)
    print(f"[calib] {len(df):,} 1m bars")
    print("[calib] aggregations...")
    df_15m, df_1h = _build_aggregations(df)
    print(f"[calib]   15m: {len(df_15m):,}  1h: {len(df_1h):,}")

    ts_1h = df_1h["ts"].values
    close_1h = df_1h["close"].values

    print("[calib] emitting short_pdh_rejection on full data...")
    t0 = time.time()
    emits = _emit_setups(detect_short_pdh_rejection, df, df_15m, df_1h, freq_bars=60)
    print(f"  baseline emits: {len(emits)}  (took {time.time()-t0:.1f}s)")

    if not emits:
        print("[calib] no emits — abort"); return 1

    # Annotate each emit with slope_24h and SMA200 ratio
    for e in emits:
        ts = e["ts"]
        e["slope_24h"] = _slope_24h_for(ts_1h, close_1h, ts)
        sma = _sma200_for(ts_1h, close_1h, ts)
        e["sma200"] = sma
        if sma:
            # close in 1h at ts
            h_idx = np.searchsorted(ts_1h, ts, side="right") - 1
            e["close_to_sma_pct"] = (float(close_1h[h_idx]) / sma - 1.0) * 100.0
        else:
            e["close_to_sma_pct"] = None

    # Simulate baseline once
    print("[calib] simulating baseline trades...")
    base_trades = []
    for e in emits:
        r = _simulate_trade(e, df)
        base_trades.append(r)

    ts_min = int(df["ts"].iloc[0])
    ts_max = int(df["ts"].iloc[-1])
    rows = [_stats(base_trades, "BASELINE (current detector)", ts_min=ts_min, ts_max=ts_max)]

    # H1: slope_24h <= +2%
    h1_trades = [t for t, e in zip(base_trades, emits)
                 if e.get("slope_24h") is not None and e["slope_24h"] <= 2.0]
    rows.append(_stats(h1_trades, "H1: slope_24h <= +2%", ts_min=ts_min, ts_max=ts_max))

    # H1b: slope_24h <= +1%
    h1b_trades = [t for t, e in zip(base_trades, emits)
                  if e.get("slope_24h") is not None and e["slope_24h"] <= 1.0]
    rows.append(_stats(h1b_trades, "H1b: slope_24h <= +1%", ts_min=ts_min, ts_max=ts_max))

    # H1c: slope_24h <= 0%
    h1c_trades = [t for t, e in zip(base_trades, emits)
                  if e.get("slope_24h") is not None and e["slope_24h"] <= 0.0]
    rows.append(_stats(h1c_trades, "H1c: slope_24h <= 0%", ts_min=ts_min, ts_max=ts_max))

    # H2: close <= SMA200 * 1.02
    h2_trades = [t for t, e in zip(base_trades, emits)
                 if e.get("close_to_sma_pct") is not None and e["close_to_sma_pct"] <= 2.0]
    rows.append(_stats(h2_trades, "H2: close <= SMA200*1.02", ts_min=ts_min, ts_max=ts_max))

    # H2b: close <= SMA200 * 1.05
    h2b_trades = [t for t, e in zip(base_trades, emits)
                  if e.get("close_to_sma_pct") is not None and e["close_to_sma_pct"] <= 5.0]
    rows.append(_stats(h2b_trades, "H2b: close <= SMA200*1.05", ts_min=ts_min, ts_max=ts_max))

    # H3: H1b AND H2b
    h3_trades = [t for t, e in zip(base_trades, emits)
                 if e.get("slope_24h") is not None and e["slope_24h"] <= 1.0
                 and e.get("close_to_sma_pct") is not None and e["close_to_sma_pct"] <= 5.0]
    rows.append(_stats(h3_trades, "H3: slope_24h<=1% AND close<=SMA200*1.05",
                       ts_min=ts_min, ts_max=ts_max))

    df_out = pd.DataFrame(rows)
    print()
    print(df_out.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
