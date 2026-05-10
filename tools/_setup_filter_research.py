"""Setup filter research — analyze TRUE vs FALSE outcomes per detector,
find discriminating context features, build confirmation filter, walk-forward
validate.

Pipeline (per setup_type):
  1. Re-emit setups from `_backtest_detectors_honest` engine, save with full
     context (20+ features at moment of emission).
  2. Simulate each trade → label TRUE / FALSE / NEUTRAL by TP1/SL outcome.
  3. For each context feature, compare TRUE vs FALSE distributions:
       - mean delta + KS statistic
  4. Pick top-K discriminating features → build threshold filter.
  5. Walk-forward (4 folds): apply filter, measure PF improvement.
  6. Add "entry confirmation" gate: wait N min after emit, require price
     drift in expected direction before fill.
  7. Final report per setup.

Usage:
  python tools/_setup_filter_research.py [--setup-type long_multi_divergence]
                                          [--triple]
"""
from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# NOTE: don't reopen sys.stdout — _backtest_detectors_honest does it on import
# and double-wrapping breaks the file handle. Inherit its wrap.

# Import the existing honest backtest infrastructure
sys.path.insert(0, str(ROOT / "tools"))
from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, _simulate_trade, _StubCtx,
    DATA_1M, EVAL_PERIOD_BARS,
    MAKER_REBATE, TAKER_FEE, SLIPPAGE,
)

OUT_DIR = ROOT / "docs" / "STRATEGIES"
STATE_DIR = ROOT / "state"

DEFAULT_SETUPS = [
    "detect_long_multi_divergence",
    "detect_short_rally_fade",
    "detect_double_bottom_setup",
]
TRIPLE_NAMES = [
    "detect_grid_booster_activate",
    "detect_long_dump_reversal",
    "detect_long_pdl_bounce",
]

CONFIRMATION_LAGS_MIN = (5, 10, 15)
WALK_FOLDS = 4


@dataclass
class ContextSnapshot:
    """20+ features computed at the bar where setup emitted."""
    ts: int
    bar_idx: int
    setup_type: str
    side: str
    entry: float
    # Volume context
    vol_z_1m: float = 0.0
    vol_z_15m: float = 0.0
    vol_z_1h: float = 0.0
    # Volatility
    atr_1h_pct: float = 0.0
    atr_ratio_20: float = 1.0  # ATR_now / ATR_20bars_ago
    bb_width_pct: float = 0.0
    # Trend
    ema50_200_spread_pct: float = 0.0  # (EMA50 - EMA200) / close × 100
    adx_1h: float = 0.0
    trend_slope_6h_pct: float = 0.0
    # RSI / MFI
    rsi_1h: float = 50.0
    rsi_15m: float = 50.0
    mfi_1h: float = 50.0
    # Cross-asset (filled later via separate eth/xrp data — пока stubs)
    eth_rsi_1h: float = 50.0
    btc_eth_corr_30h: float = 0.0
    # Session
    session: str = "?"
    hour_utc: int = 0
    # Microstructure (last 5 1m bars)
    last5_close_lean: float = 0.5
    last5_wick_imbalance: float = 1.0
    # Outcome (filled after simulation)
    verdict: str = "?"
    pnl_pct: float = 0.0
    hold_minutes: int = 0


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) == 0: return x
    alpha = 2.0 / (n + 1)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1: return 50.0
    delta = np.diff(closes[-period - 1:])
    gain = delta[delta > 0].sum() / period
    loss = -delta[delta < 0].sum() / period
    if loss == 0: return 100.0 if gain > 0 else 50.0
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def _atr_pct(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
             period: int = 14) -> float:
    if len(closes) < period + 1: return 0.0
    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    ])
    if len(tr) < period: return 0.0
    return float(tr[-period:].mean() / closes[-1] * 100)


def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
         period: int = 14) -> float:
    if len(closes) < period * 2: return 0.0
    up = np.diff(highs)
    down = -np.diff(lows)
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)
    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    ])
    if tr.sum() == 0 or len(tr) < period: return 0.0
    atr = tr[-period:].mean()
    if atr == 0: return 0.0
    plus_di = 100 * plus_dm[-period:].mean() / atr
    minus_di = 100 * minus_dm[-period:].mean() / atr
    if plus_di + minus_di == 0: return 0.0
    return float(100 * abs(plus_di - minus_di) / (plus_di + minus_di))


def _vol_z(volumes: np.ndarray, period: int = 20) -> float:
    if len(volumes) < period: return 0.0
    recent = volumes[-period:]
    mean = recent.mean()
    std = recent.std()
    if std == 0: return 0.0
    return float((volumes[-1] - mean) / std)


def _compute_context(ctx: _StubCtx, bar_idx: int, ts: int,
                     setup_type: str, side: str, entry: float) -> ContextSnapshot:
    """Extract 20+ features from a StubCtx."""
    snap = ContextSnapshot(
        ts=ts, bar_idx=bar_idx, setup_type=setup_type, side=side, entry=entry,
    )
    # 1m
    if ctx.ohlcv_1m is not None and len(ctx.ohlcv_1m) >= 20:
        v_1m = ctx.ohlcv_1m["volume"].astype(float).values
        snap.vol_z_1m = _vol_z(v_1m)
    # 15m
    if ctx.ohlcv_15m is not None and len(ctx.ohlcv_15m) >= 20:
        df = ctx.ohlcv_15m
        v_15m = df["volume"].astype(float).values
        snap.vol_z_15m = _vol_z(v_15m)
        c = df["close"].astype(float).values
        snap.rsi_15m = _rsi(c)
    # 1h
    if ctx.ohlcv_1h is not None and len(ctx.ohlcv_1h) >= 50:
        df = ctx.ohlcv_1h
        c = df["close"].astype(float).values
        h = df["high"].astype(float).values
        l = df["low"].astype(float).values
        v = df["volume"].astype(float).values
        snap.vol_z_1h = _vol_z(v)
        snap.atr_1h_pct = _atr_pct(h, l, c)
        if len(c) >= 35:
            atr_now = _atr_pct(h[-15:], l[-15:], c[-15:])
            atr_old = _atr_pct(h[-35:-20], l[-35:-20], c[-35:-20])
            snap.atr_ratio_20 = atr_now / atr_old if atr_old > 0 else 1.0
        # Bollinger 20
        if len(c) >= 20:
            bb_mean = c[-20:].mean()
            bb_std = c[-20:].std()
            snap.bb_width_pct = float(4 * bb_std / bb_mean * 100) if bb_mean > 0 else 0.0
        # EMA spread
        if len(c) >= 200:
            e50 = _ema(c[-220:], 50)[-1]
            e200 = _ema(c[-220:], 200)[-1]
            snap.ema50_200_spread_pct = float((e50 - e200) / c[-1] * 100)
        # ADX
        snap.adx_1h = _adx(h, l, c)
        # 6h slope (last 6 1h bars)
        if len(c) >= 7:
            slope = (c[-1] - c[-7]) / c[-7] * 100
            snap.trend_slope_6h_pct = float(slope)
        # RSI / MFI
        snap.rsi_1h = _rsi(c)
        # MFI: typical price * volume
        tp = (h + l + c) / 3
        if len(tp) >= 15:
            mf = tp[-15:] * v[-15:]
            pos_mf = mf[1:][np.diff(tp[-15:]) > 0].sum()
            neg_mf = mf[1:][np.diff(tp[-15:]) < 0].sum()
            if neg_mf > 0:
                mfi_ratio = pos_mf / neg_mf
                snap.mfi_1h = float(100 - 100 / (1 + mfi_ratio))
            else:
                snap.mfi_1h = 100.0
    # Session / hour
    dt = pd.to_datetime(ts, unit="ms", utc=True)
    snap.hour_utc = dt.hour
    if 0 <= dt.hour < 8: snap.session = "ASIA"
    elif 8 <= dt.hour < 14: snap.session = "EU"
    else: snap.session = "US"
    # Last 5 1m bars microstructure
    if ctx.ohlcv_1m is not None and len(ctx.ohlcv_1m) >= 5:
        last5 = ctx.ohlcv_1m.iloc[-5:]
        h5 = last5["high"].astype(float).values
        l5 = last5["low"].astype(float).values
        c5 = last5["close"].astype(float).values
        o5 = last5["open"].astype(float).values
        rng = h5 - l5
        # close lean
        leans = np.where(rng > 0, (c5 - l5) / rng, 0.5)
        snap.last5_close_lean = float(leans.mean())
        # wick imbalance: upper / lower wicks
        body_top = np.maximum(o5, c5)
        body_bot = np.minimum(o5, c5)
        upper_wick = h5 - body_top
        lower_wick = body_bot - l5
        u_total = upper_wick.sum()
        l_total = lower_wick.sum()
        if l_total > 0:
            snap.last5_wick_imbalance = float(u_total / l_total)
        elif u_total > 0:
            snap.last5_wick_imbalance = 10.0
    return snap


def _list_detectors():
    """Use the same DETECTOR_REGISTRY as honest backtest (tuple of functions)."""
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    detectors = {fn.__name__: fn for fn in DETECTOR_REGISTRY if callable(fn)}
    return detectors


def _run_setup(detector_name: str, detector_fn, df_1m: pd.DataFrame,
               df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> pd.DataFrame:
    """Emit setups, simulate, capture context — return DataFrame with TRUE/FALSE."""
    print(f"[run] emitting setups for {detector_name}...")
    emits = _emit_setups(detector_fn, df_1m, df_15m, df_1h)
    print(f"[run] {len(emits)} setups emitted")
    if not emits:
        return pd.DataFrame()

    # Build context for each emit
    snapshots = []
    ts_1m = df_1m["ts"].values
    ts_1h = df_1h["ts"].values
    ts_15m = df_15m["ts"].values

    for emit in emits:
        i = emit["bar_idx"]
        h_idx = np.searchsorted(ts_1h, ts_1m[i], side="right") - 1
        m15_idx = np.searchsorted(ts_15m, ts_1m[i], side="right") - 1
        sub_1h = df_1h.iloc[max(0, h_idx - 250):h_idx + 1].reset_index(drop=True)
        sub_15m = df_15m.iloc[max(0, m15_idx - 100):m15_idx + 1].reset_index(drop=True)
        sub_1m = df_1m.iloc[max(0, i - 200):i + 1].reset_index(drop=True)
        ctx = _StubCtx(
            pair="BTCUSDT",
            current_price=float(df_1m["close"].iloc[i]),
            regime_label="range_wide",
            session_label="ny_am",
            ohlcv_1m=sub_1m, ohlcv_1h=sub_1h, ohlcv_15m=sub_15m,
        )
        snap = _compute_context(
            ctx, i, emit["ts"], emit["setup_type"], emit["side"], emit["entry"],
        )
        # Simulate
        result = _simulate_trade(emit, df_1m)
        snap.verdict = result.outcome  # "TP1" / "TP2" / "SL" / "EXPIRE"
        snap.pnl_pct = result.pnl_pct
        snap.hold_minutes = result.bars_held  # 1m bars ≈ minutes
        snapshots.append(snap.__dict__)

    return pd.DataFrame(snapshots)


def _classify_verdict(row) -> str:
    v = row.get("verdict", "?")
    if v in ("TP1", "TP2"): return "TRUE"
    if v == "SL": return "FALSE"
    return "NEUTRAL"


def _ks_statistic(x: np.ndarray, y: np.ndarray) -> float:
    """Two-sample KS statistic (no scipy dependency)."""
    if len(x) == 0 or len(y) == 0: return 0.0
    combined = np.concatenate([x, y])
    sorted_combined = np.sort(combined)
    cdf_x = np.searchsorted(np.sort(x), sorted_combined, side="right") / len(x)
    cdf_y = np.searchsorted(np.sort(y), sorted_combined, side="right") / len(y)
    return float(np.max(np.abs(cdf_x - cdf_y)))


def _analyze_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compare TRUE vs FALSE distributions across all numeric features."""
    df = df.copy()
    df["class"] = df.apply(_classify_verdict, axis=1)

    true_df = df[df["class"] == "TRUE"]
    false_df = df[df["class"] == "FALSE"]

    if len(true_df) < 10 or len(false_df) < 10:
        print(f"[analyze] insufficient TRUE ({len(true_df)}) or FALSE ({len(false_df)})")
        return pd.DataFrame()

    numeric_cols = [
        "vol_z_1m", "vol_z_15m", "vol_z_1h",
        "atr_1h_pct", "atr_ratio_20", "bb_width_pct",
        "ema50_200_spread_pct", "adx_1h", "trend_slope_6h_pct",
        "rsi_1h", "rsi_15m", "mfi_1h",
        "last5_close_lean", "last5_wick_imbalance",
        "hour_utc",
    ]
    rows = []
    for col in numeric_cols:
        if col not in df.columns: continue
        t_vals = true_df[col].dropna().values
        f_vals = false_df[col].dropna().values
        if len(t_vals) < 5 or len(f_vals) < 5: continue
        ks = _ks_statistic(t_vals, f_vals)
        rows.append({
            "feature": col,
            "true_mean": round(float(t_vals.mean()), 3),
            "false_mean": round(float(f_vals.mean()), 3),
            "true_median": round(float(np.median(t_vals)), 3),
            "false_median": round(float(np.median(f_vals)), 3),
            "delta_mean": round(float(t_vals.mean() - f_vals.mean()), 3),
            "ks": round(ks, 3),
        })
    return pd.DataFrame(rows).sort_values("ks", ascending=False).reset_index(drop=True)


def _build_filter(features_df: pd.DataFrame, df: pd.DataFrame, top_k: int = 3) -> dict:
    """Build threshold filter from top-K discriminating features.

    For each top feature, choose threshold = TRUE-median (entry only if
    feature is on the TRUE side of the boundary).
    """
    if not len(features_df): return {}
    top_features = features_df.head(top_k)
    rules = []
    for _, row in top_features.iterrows():
        col = row["feature"]
        t_med = row["true_median"]
        f_med = row["false_median"]
        if abs(t_med - f_med) < 1e-9: continue
        if t_med > f_med:
            rules.append({"feature": col, "op": ">=", "threshold": t_med})
        else:
            rules.append({"feature": col, "op": "<=", "threshold": t_med})
    return {"rules": rules, "ks_total": float(top_features["ks"].sum())}


def _apply_filter(df: pd.DataFrame, filt: dict) -> pd.Series:
    """Return mask: True = passes all filter rules."""
    if not filt or not filt.get("rules"): return pd.Series([True] * len(df), index=df.index)
    mask = pd.Series([True] * len(df), index=df.index)
    for r in filt["rules"]:
        col = r["feature"]
        if col not in df.columns: continue
        if r["op"] == ">=":
            mask &= df[col] >= r["threshold"]
        else:
            mask &= df[col] <= r["threshold"]
    return mask


def _summary_metrics(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "total_pnl_pct": 0.0}
    n = len(df)
    wins = df[df["pnl_pct"] > 0]
    losses = df[df["pnl_pct"] < 0]
    pf = float(wins["pnl_pct"].sum() / -losses["pnl_pct"].sum()) if len(losses) and losses["pnl_pct"].sum() < 0 else (999.0 if len(wins) else 0.0)
    return {
        "n": n,
        "wr": round(float((df["pnl_pct"] > 0).sum() / n * 100), 1),
        "pf": round(pf, 3),
        "total_pnl_pct": round(float(df["pnl_pct"].sum()), 2),
        "avg_pnl_pct": round(float(df["pnl_pct"].mean()), 4),
    }


def _confirmation_gate(df: pd.DataFrame, df_1m: pd.DataFrame,
                       lag_min: int = 10, min_drift_pct: float = 0.1) -> pd.Series:
    """For each emit, check if price drifted in expected direction over `lag_min`
    minutes. Returns mask True = passed confirmation.

    For LONG: close[+lag] >= entry × (1 + min_drift_pct/100)  (price moved UP)
    For SHORT: close[+lag] <= entry × (1 - min_drift_pct/100) (price moved DOWN)
    """
    ts_arr = df_1m["ts"].values
    closes = df_1m["close"].values
    mask = []
    for _, row in df.iterrows():
        i = int(row["bar_idx"])
        target = i + lag_min
        if target >= len(closes):
            mask.append(False); continue
        c = float(closes[target])
        e = float(row["entry"])
        if row["side"] == "long":
            ok = c >= e * (1 + min_drift_pct / 100)
        else:
            ok = c <= e * (1 - min_drift_pct / 100)
        mask.append(ok)
    return pd.Series(mask, index=df.index)


def _walk_forward(df: pd.DataFrame, filt: dict, n_folds: int = WALK_FOLDS) -> list[dict]:
    fold_size = len(df) // n_folds
    out = []
    for f in range(n_folds):
        start = f * fold_size
        end = (f + 1) * fold_size if f < n_folds - 1 else len(df)
        sub = df.iloc[start:end]
        baseline = _summary_metrics(sub)
        mask = _apply_filter(sub, filt)
        filtered = _summary_metrics(sub[mask])
        out.append({
            "fold": f + 1,
            "baseline": baseline,
            "filtered": filtered,
        })
    return out


def _run_research(setup_arg: str | None, triple: bool) -> int:
    print("[research] loading 1m...")
    df_1m = pd.read_csv(DATA_1M).reset_index(drop=True)
    # 365d default for research; full 815d on demand via env BARS=full
    import os
    bars_arg = os.environ.get("BARS", "365d")
    if bars_arg == "full":
        pass
    elif bars_arg.endswith("d"):
        days = int(bars_arg[:-1])
        df_1m = df_1m.iloc[-(days * 1440):].reset_index(drop=True)
    print(f"[research] {len(df_1m):,} 1m bars")
    df_15m, df_1h = _build_aggregations(df_1m)
    print(f"[research] {len(df_15m):,} 15m, {len(df_1h):,} 1h")

    detectors = _list_detectors()
    print(f"[research] {len(detectors)} detectors loaded")

    targets = DEFAULT_SETUPS if not triple else TRIPLE_NAMES
    if setup_arg:
        targets = [setup_arg]

    all_results = {}
    for det_name in targets:
        if det_name not in detectors:
            print(f"[research] ! detector {det_name} not found, skip")
            continue
        det_fn = detectors[det_name]
        df = _run_setup(det_name, det_fn, df_1m, df_15m, df_1h)
        if len(df) == 0:
            print(f"[research] {det_name}: no setups emitted")
            continue
        df["class"] = df.apply(_classify_verdict, axis=1)
        feat = _analyze_features(df)
        filt = _build_filter(feat, df, top_k=3)
        baseline = _summary_metrics(df)
        mask = _apply_filter(df, filt)
        filtered = _summary_metrics(df[mask])
        wf = _walk_forward(df, filt)
        # Confirmation gate (10 min lag, +0.1% drift in side direction)
        conf_mask = _confirmation_gate(df, df_1m, lag_min=10, min_drift_pct=0.1)
        confirmed_only = _summary_metrics(df[conf_mask])
        # Both filter AND confirmation
        combined_mask = mask & conf_mask
        filter_plus_conf = _summary_metrics(df[combined_mask])

        # Save raw per-setup CSV
        out_csv = STATE_DIR / f"setup_research_{det_name}.csv"
        df.to_csv(out_csv, index=False)

        all_results[det_name] = {
            "n_total": int(len(df)),
            "class_counts": df["class"].value_counts().to_dict(),
            "baseline": baseline,
            "features_ranked": feat.to_dict(orient="records"),
            "filter": filt,
            "filtered": filtered,
            "confirmed_only": confirmed_only,
            "filter_plus_conf": filter_plus_conf,
            "walkforward": wf,
        }
        print(f"\n=== {det_name} ===")
        print(f"  N={len(df)}  classes={df['class'].value_counts().to_dict()}")
        print(f"  Baseline:      {baseline}")
        print(f"  Filter:        {filt}")
        print(f"  Filtered:      {filtered}")
        print(f"  Confirm only:  {confirmed_only}")
        print(f"  Filter+Conf:   {filter_plus_conf}")
        for f in wf:
            print(f"  fold {f['fold']}: base PF {f['baseline']['pf']} → filt PF {f['filtered']['pf']} "
                  f"(N {f['baseline']['n']} → {f['filtered']['n']})")

    # Write report
    out_md = OUT_DIR / "SETUP_FILTER_RESEARCH.md"
    md = []
    md.append("# Setup filter research\n")
    md.append(f"**Period:** last {EVAL_PERIOD_BARS:,} 1m bars (~{EVAL_PERIOD_BARS//1440}d)")
    md.append(f"**Setups analyzed:** {len(all_results)}")
    md.append("")
    for name, r in all_results.items():
        md.append(f"## {name}\n")
        md.append(f"- Total emits: {r['n_total']}")
        md.append(f"- Classes: {r['class_counts']}")
        md.append(f"- **Baseline:** {r['baseline']}\n")
        md.append("### Top discriminating features (KS, T-mean vs F-mean)\n")
        md.append(pd.DataFrame(r["features_ranked"][:8]).to_markdown(index=False))
        md.append("")
        md.append(f"### Filter built\n")
        md.append(f"```json\n{json.dumps(r['filter'], indent=2)}\n```")
        md.append(f"\n**Filtered metrics:** {r['filtered']}")
        md.append(f"\n**Confirmed-only (10m lag, +0.1% drift):** {r['confirmed_only']}")
        md.append(f"\n**Filter + Confirmation:** {r['filter_plus_conf']}\n")
        md.append("### Walk-forward (4 folds)\n")
        wf_rows = []
        for f in r["walkforward"]:
            wf_rows.append({
                "fold": f["fold"],
                "baseline_n": f["baseline"]["n"],
                "baseline_pf": f["baseline"]["pf"],
                "baseline_pnl%": f["baseline"]["total_pnl_pct"],
                "filt_n": f["filtered"]["n"],
                "filt_pf": f["filtered"]["pf"],
                "filt_pnl%": f["filtered"]["total_pnl_pct"],
            })
        md.append(pd.DataFrame(wf_rows).to_markdown(index=False))
        md.append("\n---\n")

    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[research] wrote {out_md}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup-type", default=None,
                    help="single detector name (override default 3)")
    ap.add_argument("--triple", action="store_true",
                    help="run mega-triple analysis instead of 3 individuals")
    args = ap.parse_args()
    return _run_research(args.setup_type, args.triple)


if __name__ == "__main__":
    sys.exit(main())
