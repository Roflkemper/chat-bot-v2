from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRACKER_SNAPSHOTS_CSV = ROOT / "ginarea_tracker" / "ginarea_live" / "snapshots_v2.csv"
FEATURES_DIR = ROOT / "features_out"


@dataclass(frozen=True)
class EpisodesWindow:
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp


def _floor_to_hour(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts, tz="UTC") if not isinstance(ts, pd.Timestamp) else ts
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.floor("h")


def compute_tracker_window(bot_selectors: list[str], *, snapshots_csv: Path = TRACKER_SNAPSHOTS_CSV) -> EpisodesWindow:
    if not snapshots_csv.exists():
        raise FileNotFoundError(f"Tracker snapshots CSV not found: {snapshots_csv}")

    df = pd.read_csv(snapshots_csv, usecols=["ts_utc", "bot_id", "bot_name", "alias"], low_memory=False)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df["alias"] = df["alias"].fillna("").astype(str).str.strip()
    df["bot_name"] = df["bot_name"].fillna("").astype(str).str.strip()
    df["bot_id"] = df["bot_id"].astype(str).str.strip()

    starts: list[pd.Timestamp] = []
    for selector in bot_selectors:
        s = str(selector).strip()
        sub = df[(df["alias"] == s) | (df["bot_name"] == s) | (df["bot_id"] == s)]
        if sub.empty:
            raise ValueError(f"Bot selector not found in tracker snapshots: {selector!r}")
        starts.append(pd.Timestamp(sub["ts_utc"].min()))

    start_ts = max(starts)
    end_ts = _floor_to_hour(pd.Timestamp(datetime.now(timezone.utc)))
    # Clip by features_out coverage (episodes extractor requires DatetimeIndex partitions).
    features_end = latest_features_ts("BTCUSDT", features_dir=FEATURES_DIR)
    if features_end is not None:
        end_ts = min(end_ts, _floor_to_hour(features_end))
    if start_ts >= end_ts:
        raise ValueError(f"Tracker window is empty: start_ts={start_ts} end_ts={end_ts}")
    return EpisodesWindow(start_ts=start_ts, end_ts=end_ts)


def latest_features_ts(symbol: str, *, features_dir: Path = FEATURES_DIR) -> pd.Timestamp | None:
    """Return the latest timestamp covered by valid (DatetimeIndex) feature partitions."""
    sym_dir = features_dir / symbol
    if not sym_dir.exists():
        return None
    files = sorted(sym_dir.glob("*.parquet"))
    for path in reversed(files):
        try:
            df = pd.read_parquet(path, columns=["close"])
        except Exception:
            continue
        # Valid partitions are indexed by timestamp.
        if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
            continue
        if len(df.index) == 0:
            continue
        return pd.Timestamp(df.index.max())
    return None


def write_window_json(window: EpisodesWindow, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"start_ts": window.start_ts.isoformat(), "end_ts": window.end_ts.isoformat()}
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
