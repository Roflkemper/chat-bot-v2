"""
forecast_regime_split.py — Split full_features_1y.parquet by regime labels.

Uses phase_classifier to label each 1h bar with its regime, then joins labels
into the 5m feature parquet and splits into per-regime files.

Output:
    data/forecast_features/regime_splits/
        regime_MARKUP.parquet
        regime_MARKDOWN.parquet
        regime_RANGE.parquet
        regime_DISTRIBUTION.parquet
        regime_ACCUMULATION.parquet
        regime_TRANSITION.parquet
        regime_split_report.json

Usage:
    python scripts/forecast_regime_split.py
    python scripts/forecast_regime_split.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES_PATH = ROOT / "data" / "forecast_features" / "full_features_1y.parquet"
SPLITS_DIR    = ROOT / "data" / "forecast_features" / "regime_splits"

# Regime int mapping (mirrors phase_classifier Phase enum)
REGIME_LABELS = {
    "MARKUP":       1,
    "MARKDOWN":     2,
    "RANGE":        3,
    "DISTRIBUTION": 4,
    "ACCUMULATION": 5,
    "TRANSITION":   6,
}


def _build_regime_labels(tail_days: int = 370) -> pd.Series:
    """Run phase classifier on 1h bars → return Series[regime_label] indexed by timestamp."""
    from services.market_forward_analysis.data_loader import _load_1m, _resample
    from services.market_forward_analysis.phase_classifier import run_phase_history

    print("Loading 1m OHLCV data...")
    df1m = _load_1m("BTCUSDT", tail_days=tail_days)
    if df1m is None or df1m.empty:
        raise RuntimeError("No 1m OHLCV data found — ensure data/backtests/frozen/BTCUSDT_1m_2y.csv exists")

    df1d = _resample(df1m, "1D")
    df4h = _resample(df1m, "4h")
    df1h = _resample(df1m, "1h")

    print(f"Running phase history on {len(df1d)} 1d bars...")
    history = run_phase_history(df1d, df_4h=df4h, df_1h=df1h, step_bars=1, lookback=60)

    if history.empty:
        raise RuntimeError("Phase history returned empty — check data quality")

    print(f"Phase history: {len(history)} bars, columns: {list(history.columns)}")

    # Extract 1d phase label per bar
    if "1d_phase" not in history.columns:
        # Fallback: try first phase column
        phase_cols = [c for c in history.columns if "phase" in c]
        if not phase_cols:
            raise RuntimeError(f"No phase column in history. Columns: {list(history.columns)}")
        phase_col = phase_cols[0]
    else:
        phase_col = "1d_phase"

    labels = history[phase_col].rename("regime_label")
    labels.index = pd.to_datetime(labels.index, utc=True)
    print(f"Regime label distribution (1d bars):\n{labels.value_counts().to_string()}")
    return labels


def _join_labels_to_features(features: pd.DataFrame, labels: pd.Series) -> pd.DataFrame:
    """Downsample 1d regime labels to 5m feature timestamps via forward-fill."""
    # labels is indexed by 1d timestamps, features by 5m timestamps
    # Strategy: for each 5m bar, find the most recent 1d label
    labels_5m = labels.resample("5min").ffill()

    # Align to features index
    df = features.copy()
    df["regime_label"] = labels_5m.reindex(df.index, method="ffill")

    # Fill leading NaN (before first phase label) with RANGE as safe default
    df["regime_label"] = df["regime_label"].fillna("RANGE")

    return df


def split_features(dry_run: bool = False) -> dict:
    """Main entry point. Returns split report dict."""
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Feature parquet not found: {FEATURES_PATH}")

    print(f"Loading features: {FEATURES_PATH}")
    features = pd.read_parquet(FEATURES_PATH)
    print(f"Features: {features.shape[0]:,} rows × {features.shape[1]} cols")
    print(f"Date range: {features.index.min()} → {features.index.max()}")

    # Build regime labels from phase classifier
    labels = _build_regime_labels()

    # Join labels to 5m features
    print("Joining regime labels to features...")
    df = _join_labels_to_features(features, labels)

    label_dist = df["regime_label"].value_counts().to_dict()
    print(f"Feature regime distribution (5m bars):\n{pd.Series(label_dist).to_string()}")

    report = {
        "total_bars": int(len(df)),
        "date_range": {
            "start": str(df.index.min()),
            "end":   str(df.index.max()),
        },
        "regime_distribution": {k: int(v) for k, v in label_dist.items()},
        "splits": {},
    }

    if dry_run:
        print("\n[DRY RUN] Would write splits:")
        for regime, count in label_dist.items():
            out = SPLITS_DIR / f"regime_{regime}.parquet"
            pct = count / len(df) * 100
            print(f"  {out.name}: {count:,} rows ({pct:.1f}%)")
        return report

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)

    # Write per-regime splits
    regimes_written = 0
    for regime in sorted(label_dist.keys()):
        subset = df[df["regime_label"] == regime].drop(columns=["regime_label"])
        out_path = SPLITS_DIR / f"regime_{regime}.parquet"
        subset.to_parquet(out_path, index=True)
        count = len(subset)
        pct = count / len(df) * 100
        print(f"Written: {out_path.name} — {count:,} rows ({pct:.1f}%)")
        report["splits"][regime] = {
            "path": str(out_path),
            "rows": count,
            "pct": round(pct, 1),
        }
        regimes_written += 1

    # Also write the full df with regime_label column for convenience
    full_labeled = SPLITS_DIR / "full_features_labeled.parquet"
    df.to_parquet(full_labeled, index=True)
    print(f"Written: {full_labeled.name} — {len(df):,} rows (full with labels)")
    report["full_labeled"] = str(full_labeled)

    # Write report JSON
    report_path = SPLITS_DIR / "regime_split_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Report: {report_path}")

    print(f"\nSplit complete: {regimes_written} regime files + 1 labeled full")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split feature parquet by regime labels")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    args = parser.parse_args(argv)

    try:
        report = split_features(dry_run=args.dry_run)
        n = len(report.get("regime_distribution", {}))
        print(f"\nOK — {n} regimes {'identified' if args.dry_run else 'written'}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
