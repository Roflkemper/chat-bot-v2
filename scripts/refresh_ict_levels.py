"""Refresh ICT levels parquet from latest 1m data.

The parquet at data/ict_levels/BTCUSDT_ict_levels_1m.parquet is read on
setup_detector startup and used to attach `ict_context` to each setup.
If stale, detectors that depend on ICT context (ict_killzone, fvg_reaction,
etc) get an empty context and silently degrade.

This script:
  1. Combines frozen 2y CSV + market_live/market_1m.csv into a unified
     1m frame.
  2. Writes a temp combined CSV.
  3. Calls services.ict_levels.builder.build_ict_levels with the
     extended data → new parquet.
  4. Atomically replaces the production parquet.

Run via cron daily, or manually after big data backfills.

Memory: build_ict_levels processes 1m rows in pandas. ~1M rows × 8 cols
is ~120MB peak. Safe to run on operator machine.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FROZEN_CSV = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
LIVE_CSV = ROOT / "market_live" / "market_1m.csv"
OUT_PARQUET = ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"


def _combine_csvs(out_path: Path) -> int:
    """Concat frozen + live, dedupe by ts, write to out_path. Returns rows."""
    if not FROZEN_CSV.exists():
        print(f"[refresh-ict] {FROZEN_CSV} missing")
        return 0
    df_frozen = pd.read_csv(FROZEN_CSV)
    df_frozen["ts_utc"] = pd.to_datetime(df_frozen["ts"], unit="ms", utc=True)

    frames = [df_frozen[["ts_utc", "open", "high", "low", "close", "volume"]]]
    if LIVE_CSV.exists():
        df_live = pd.read_csv(LIVE_CSV)
        df_live["ts_utc"] = pd.to_datetime(df_live["ts_utc"], utc=True, errors="coerce")
        df_live = df_live.dropna(subset=["ts_utc"])
        frames.append(df_live[["ts_utc", "open", "high", "low", "close", "volume"]])
    else:
        print("[refresh-ict] no market_live/market_1m.csv — using frozen only")

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates("ts_utc").sort_values("ts_utc")
    combined["ts"] = (combined["ts_utc"].astype("int64") // 10**6).astype("int64")
    combined = combined[["ts", "open", "high", "low", "close", "volume"]]
    combined.to_csv(out_path, index=False)
    print(f"[refresh-ict] combined CSV {len(combined):,} rows -> {out_path}")
    return len(combined)


def main() -> int:
    from services.ict_levels.builder import build_ict_levels

    with tempfile.TemporaryDirectory() as td:
        combined_csv = Path(td) / "combined_1m.csv"
        n = _combine_csvs(combined_csv)
        if n == 0:
            return 1

        print(f"[refresh-ict] building ICT levels...")
        tmp_parquet = Path(td) / "ict.parquet"
        df = build_ict_levels(
            input_path=str(combined_csv),
            output_path=str(tmp_parquet),
        )
        print(f"[refresh-ict] built {len(df):,} rows, {len(df.columns)} cols")

        OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace via copy to staging then rename
        staging = OUT_PARQUET.with_suffix(".parquet.tmp")
        shutil.copy(tmp_parquet, staging)
        staging.replace(OUT_PARQUET)
        print(f"[refresh-ict] wrote {OUT_PARQUET} ({OUT_PARQUET.stat().st_size/1024/1024:.0f}MB)")
        # Show new range
        check = pd.read_parquet(OUT_PARQUET)
        print(f"[refresh-ict] new range: {check.index.min()} -> {check.index.max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
