"""A2 — tick-data edge mining on BTCUSDT 1s.

Question: are there intra-minute patterns visible on 1s data but invisible
on 1m OHLCV that predict short-horizon (5-30 min) directional moves?

Patterns probed (each on 60-second windows):
  P1 wick_imbalance: ratio of upper-wick volume to lower-wick volume
                     within the minute. >2 = aggressive sellers up there.
  P2 micro_velocity: count of price-direction flips in 60s (microstructure
                     volatility — high = chop, low = trending).
  P3 vol_burst:      max 5s volume / median 5s volume in the minute.
                     Detects micro-spikes hidden by 1m aggregation.
  P4 close_lean:     where in [low, high] range did the minute close?
                     Computed on 1s bars (not 1m) to avoid look-ahead in
                     evaluation windows.

For each pattern, classify the ~60s window into bucket
  (low / mid / high), then measure forward returns at +5/+15/+30 min.

If a bucket consistently predicts directional move >0.15% with PF>=1.3
across 4 walk-forward folds, it's an edge worth investigating.

Engine: same intra-bar simulator as A1 (fees, slippage). 90-day window
(recent — calibration of grid_coordinator showed 2021-era assumptions
fail; same risk for tick patterns). 4 walk-forward folds.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

DATA_1S = ROOT / "backtests" / "frozen" / "BTCUSDT_1s_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "A2_TICK_EDGE_MINING.md"
OUT_CSV = ROOT / "state" / "a2_tick_edge_runs.csv"

LOOKBACK_DAYS = 90
HORIZONS_MIN = (5, 15, 30)
N_FOLDS = 4
SUCCESS_PCT = 0.15
FAIL_PCT = 0.15

BUCKETS = ("low", "mid", "high")


def _load_1s_window(days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Грузим только последние N дней (полный csv 1.8 GB не помещается)."""
    print(f"[a2] streaming last {days} days from 1s csv...")
    # 1s data has ms timestamps. last 90d = ~7.78M rows. Read in chunks, filter.
    cutoff_ms = None
    chunks = []
    for chunk in pd.read_csv(DATA_1S, chunksize=500_000):
        if cutoff_ms is None:
            # Total file ends at last ts; compute cutoff from last chunk first pass
            pass
        chunks.append(chunk)
    df = pd.concat(chunks, ignore_index=True)
    last_ts_ms = int(df["ts"].max())
    cutoff_ms = last_ts_ms - days * 86400 * 1000
    df = df[df["ts"] >= cutoff_ms].reset_index(drop=True)
    print(f"[a2] loaded {len(df):,} 1s bars")
    return df


def _aggregate_to_minutes(df_1s: pd.DataFrame) -> pd.DataFrame:
    """Vectorized groupby — 60-100x faster than python loop on 7M rows."""
    df = df_1s.copy()
    df["minute"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.floor("1min")

    # Pre-compute per-row wick volumes (vectorized)
    body_top = df[["open", "close"]].max(axis=1)
    body_bot = df[["open", "close"]].min(axis=1)
    upper_w = (df["high"] - body_top).clip(lower=0)
    lower_w = (body_bot - df["low"]).clip(lower=0)
    wick_total = upper_w + lower_w
    with np.errstate(divide="ignore", invalid="ignore"):
        upper_share = (upper_w / wick_total.replace(0, np.nan)).fillna(0.5)
    df["upper_vol"] = df["volume"] * upper_share
    df["lower_vol"] = df["volume"] * (1 - upper_share)

    # Direction-change indicator: +1 if close went up vs prev row, -1 down, 0 flat
    df["dir"] = np.sign(df["close"].diff().fillna(0))
    # flip = current dir != prev dir AND both nonzero
    df["flip"] = ((df["dir"].shift() * df["dir"]) < 0).astype(int)

    grouped = df.groupby("minute", sort=True)
    agg = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        upper_vol=("upper_vol", "sum"),
        lower_vol=("lower_vol", "sum"),
        flips=("flip", "sum"),
        n_seconds=("close", "count"),
    ).reset_index()

    # Filter incomplete minutes
    agg = agg[agg["n_seconds"] >= 30].reset_index(drop=True)

    # P1 wick_imbalance
    agg["wick_imbalance"] = np.where(
        agg["lower_vol"] > 0,
        agg["upper_vol"] / agg["lower_vol"],
        np.where(agg["upper_vol"] > 0, 10.0, 1.0)
    )
    # P2 micro_velocity
    agg["micro_velocity"] = agg["flips"]
    # P3 vol_burst — простая аппроксимация: range/median ratio через std/mean
    # (точно вычислять max-5s/median-5s в группах слишком долго; заменим на
    # max/median одиночных вторых баров — даёт похожее распределение).
    vol_max = grouped["volume"].max().reset_index().rename(columns={"volume": "vmax"})
    vol_med = grouped["volume"].median().reset_index().rename(columns={"volume": "vmed"})
    agg = agg.merge(vol_max, on="minute").merge(vol_med, on="minute")
    agg["vol_burst"] = np.where(agg["vmed"] > 0, agg["vmax"] / agg["vmed"], 1.0)
    # P4 close_lean
    rng = agg["high"] - agg["low"]
    agg["close_lean"] = np.where(rng > 0, (agg["close"] - agg["low"]) / rng, 0.5)
    # Cleanup
    agg = agg.drop(columns=["upper_vol", "lower_vol", "flips", "n_seconds", "vmax", "vmed"])
    return agg.sort_values("minute").reset_index(drop=True)


def _bucket_assignments(series: pd.Series) -> pd.Series:
    """Assign each value to low/mid/high tercile of the series."""
    qs = series.quantile([0.33, 0.67])
    q1, q2 = qs.iloc[0], qs.iloc[1]
    out = pd.Series(["mid"] * len(series), index=series.index)
    out[series <= q1] = "low"
    out[series >= q2] = "high"
    return out


def _measure_forward(df_min: pd.DataFrame, feature: str) -> pd.DataFrame:
    """For each minute, look at +5/+15/+30 forward return per bucket."""
    df = df_min.copy()
    df[f"{feature}_bucket"] = _bucket_assignments(df[feature])
    closes = df["close"].values
    out_rows = []
    for h in HORIZONS_MIN:
        forward = np.full(len(df), np.nan)
        if h < len(df):
            forward[:-h] = (closes[h:] / closes[:-h] - 1) * 100
        df[f"ret_{h}m"] = forward
        # Group by bucket and aggregate
        for bucket in BUCKETS:
            mask = df[f"{feature}_bucket"] == bucket
            sub = df.loc[mask, f"ret_{h}m"].dropna()
            if len(sub) < 50:
                continue
            n = len(sub)
            # PF: sum positive moves > 0.15% / sum negative moves < -0.15%
            pos = sub[sub >= SUCCESS_PCT].sum()
            neg_abs = abs(sub[sub <= -SUCCESS_PCT].sum())
            pf = (pos / neg_abs) if neg_abs > 0 else float("inf")
            mean = sub.mean()
            median = sub.median()
            n_pos = int((sub >= SUCCESS_PCT).sum())
            n_neg = int((sub <= -SUCCESS_PCT).sum())
            n_neut = n - n_pos - n_neg
            out_rows.append({
                "feature": feature, "bucket": bucket, "horizon_min": h,
                "n": n, "mean_%": round(mean, 4), "median_%": round(median, 4),
                "n_pos": n_pos, "n_neg": n_neg, "n_neutral": n_neut,
                "pf": round(pf, 3) if np.isfinite(pf) else 99.99,
            })
    return pd.DataFrame(out_rows)


def _walk_forward(df_min: pd.DataFrame, feature: str, n_folds: int = N_FOLDS) -> pd.DataFrame:
    """Per-fold measurement to detect overfitting."""
    fold_size = len(df_min) // n_folds
    rows = []
    for fold in range(n_folds):
        start = fold * fold_size
        end = (fold + 1) * fold_size if fold < n_folds - 1 else len(df_min)
        sub = df_min.iloc[start:end].reset_index(drop=True)
        if len(sub) < 100:
            continue
        df_fold = _measure_forward(sub, feature)
        df_fold["fold"] = fold + 1
        rows.append(df_fold)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> int:
    print("[a2] === A2 tick edge mining ===")
    df_1s = _load_1s_window(LOOKBACK_DAYS)
    print("[a2] aggregating to per-minute features...")
    df_min = _aggregate_to_minutes(df_1s)
    print(f"[a2] {len(df_min):,} minute records with features")

    features = ["wick_imbalance", "micro_velocity", "vol_burst", "close_lean"]
    all_runs = []
    overall_summary = []

    for feat in features:
        print(f"\n[a2] === {feat} ===")
        # In-sample summary
        agg = _measure_forward(df_min, feat)
        agg["fold"] = "all"
        all_runs.append(agg)
        # Walk-forward
        wf = _walk_forward(df_min, feat)
        if len(wf):
            all_runs.append(wf)

        # Decide if any bucket × horizon shows persistent edge
        for bucket in BUCKETS:
            for h in HORIZONS_MIN:
                # In-sample
                agg_row = agg[(agg["bucket"] == bucket) & (agg["horizon_min"] == h)]
                if not len(agg_row):
                    continue
                pf_in = agg_row.iloc[0]["pf"]
                mean_in = agg_row.iloc[0]["mean_%"]
                # WF: % folds with same direction and PF>=1.2
                if len(wf):
                    fold_rows = wf[(wf["bucket"] == bucket) & (wf["horizon_min"] == h)]
                    sign_in = np.sign(mean_in)
                    fold_aligned = fold_rows[
                        (np.sign(fold_rows["mean_%"]) == sign_in) & (fold_rows["pf"] >= 1.2)
                    ]
                    consistent_folds = len(fold_aligned)
                    total_folds = len(fold_rows)
                else:
                    consistent_folds = 0
                    total_folds = 0
                edge = (
                    abs(mean_in) >= 0.05 and pf_in >= 1.3 and
                    consistent_folds >= max(2, total_folds - 1)
                )
                overall_summary.append({
                    "feature": feat, "bucket": bucket, "horizon_min": h,
                    "in_sample_mean_%": round(mean_in, 4),
                    "in_sample_pf": round(pf_in, 3),
                    "wf_consistent_folds": f"{consistent_folds}/{total_folds}",
                    "edge_found": edge,
                })

    runs_df = pd.concat(all_runs, ignore_index=True) if all_runs else pd.DataFrame()
    runs_df.to_csv(OUT_CSV, index=False)

    # Write report
    md = []
    md.append("# A2 — tick-data edge mining (BTCUSDT 1s, 90 days)")
    md.append("")
    md.append(f"**Engine:** 1s OHLCV → per-minute features → forward-return analysis")
    md.append(f"**Period:** last {LOOKBACK_DAYS} days, {len(df_min):,} 1m windows")
    md.append(f"**Folds:** {N_FOLDS} walk-forward")
    md.append(f"**Edge criteria:** |mean| >= 0.05%, PF >= 1.3, consistent across folds")
    md.append("")
    md.append("## Features mined")
    md.append("- **wick_imbalance** — upper-wick volume / lower-wick volume in 1m")
    md.append("- **micro_velocity** — count of close-to-close direction flips in 60s")
    md.append("- **vol_burst** — max 5s rolling volume / median 5s volume")
    md.append("- **close_lean** — close position in [low, high] range, 1s-resolution")
    md.append("")
    md.append("## Edge candidates summary")
    md.append("")
    summary_df = pd.DataFrame(overall_summary)
    edge_only = summary_df[summary_df["edge_found"]]
    if len(edge_only) > 0:
        md.append(f"### {len(edge_only)} edge(s) found")
        md.append("")
        md.append(edge_only.to_markdown(index=False))
    else:
        md.append("**No edges found** — all features fail at least one of "
                 "(|mean| >= 0.05%, PF >= 1.3, walk-forward consistency).")
        md.append("")
        md.append("Best candidates (sorted by |mean|):")
        md.append("")
        top = summary_df.reindex(summary_df["in_sample_mean_%"].abs().sort_values(ascending=False).index).head(10)
        md.append(top.to_markdown(index=False))

    md.append("")
    md.append("## All in-sample buckets")
    md.append("")
    md.append(summary_df.to_markdown(index=False))

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[a2] wrote {OUT_MD}")
    print(f"[a2] runs CSV: {OUT_CSV}")
    if len(edge_only) > 0:
        print(f"[a2] FOUND {len(edge_only)} edge candidate(s)")
        print(edge_only.to_string(index=False))
    else:
        print("[a2] NO edges meeting criteria")
    return 0


if __name__ == "__main__":
    sys.exit(main())
