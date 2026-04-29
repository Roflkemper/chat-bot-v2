"""H10 Backtest Harness.

Usage:
    python scripts/backtest_h10.py [--full-grid] [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Default params grid: 5 protective_stop variants × 1 core param set.
--full-grid: expands to all combinations of tp_pct × grid_step_pct × time_stop × stop.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from tqdm import tqdm

from services.h10_detector import detect_setup
from services.h10_grid import ProbeParams, simulate_probe
from services.liquidity_map import build_liquidity_map

OHLCV_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"
OHLCV_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
REPORTS_DIR = ROOT / "reports"


def _utc(dt: datetime | None) -> pd.Timestamp | None:
    """Convert a datetime (tz-aware or naive) to a UTC pandas Timestamp."""
    if dt is None:
        return None
    ts = pd.Timestamp(dt)
    return ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")


def _load_ohlcv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts").sort_index()
    return df


def _default_params_grid() -> list[ProbeParams]:
    return [
        ProbeParams(protective_stop_pct=None),
        ProbeParams(protective_stop_pct=-0.003),
        ProbeParams(protective_stop_pct=-0.005),
        ProbeParams(protective_stop_pct=-0.008),
        ProbeParams(protective_stop_pct=-0.010),
    ]


def _full_params_grid() -> list[ProbeParams]:
    params = []
    for tp in [0.003, 0.005, 0.008, 0.012]:
        for step in [0.002, 0.0025, 0.003]:
            for time_stop in [1, 2, 4]:
                for stop in [None, -0.003, -0.005, -0.008, -0.010]:
                    params.append(
                        ProbeParams(
                            tp_pct=tp,
                            grid_step_pct=step,
                            time_stop_hours=time_stop,
                            protective_stop_pct=stop,
                        )
                    )
    return params


def detect_only(
    ohlcv_1h: pd.DataFrame,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    step_hours: int = 1,
    dedup_gap_hours: int = 6,
) -> pd.DataFrame:
    """Walk 1h data, detect setups, return one row per raw detection.

    Unique events are marked by dedup_event_id: a new event starts when the gap
    from the previous detection exceeds dedup_gap_hours OR target_side flips.
    """
    ts_index = ohlcv_1h.index
    if start is not None:
        ts_index = ts_index[ts_index >= _utc(start)]
    if end is not None:
        ts_index = ts_index[ts_index <= _utc(end)]
    ts_index = ts_index[72:]

    rows: list[dict] = []
    print(f"Scanning {len(ts_index)} hourly bars (detector only)...")

    prev_ts = None
    prev_side = None
    event_id = 0

    for ts in tqdm(ts_index[::step_hours]):
        ts_py = ts.to_pydatetime()
        liq_map = build_liquidity_map(ts_py, ohlcv_1h, lookback_hours=72)
        if not liq_map:
            continue
        setup = detect_setup(ts_py, ohlcv_1h, liq_map)
        if setup is None:
            continue

        gap_h = (ts - prev_ts).total_seconds() / 3600 if prev_ts is not None else 999
        if gap_h > dedup_gap_hours or setup.target_side != prev_side:
            event_id += 1
        prev_ts = ts
        prev_side = setup.target_side

        rows.append({
            "setup_ts": setup.timestamp,
            "event_id": event_id,
            "impulse_pct": round(setup.impulse_pct * 100, 3),
            "impulse_dir": setup.impulse_direction,
            "impulse_window_hours": setup.impulse_window_hours,
            "cons_low": round(setup.consolidation_low, 1),
            "cons_high": round(setup.consolidation_high, 1),
            "consolidation_hours": setup.consolidation_hours,
            "target_price": round(setup.target_zone.price_level, 1),
            "target_weight": round(setup.target_zone.weight, 3),
            "target_side": setup.target_side,
        })

    return pd.DataFrame(rows)


def backtest_h10(
    ohlcv_1h: pd.DataFrame,
    ohlcv_1m: pd.DataFrame,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    params_grid: Optional[list[ProbeParams]] = None,
    step_hours: int = 1,
) -> pd.DataFrame:
    """Walk 1h data, detect setups, simulate probes for each param set.

    Returns DataFrame: one row per (setup_timestamp × ProbeParams).
    """
    if params_grid is None:
        params_grid = _default_params_grid()

    ts_index = ohlcv_1h.index
    if start is not None:
        ts_index = ts_index[ts_index >= _utc(start)]
    if end is not None:
        ts_index = ts_index[ts_index <= _utc(end)]
    # Skip first 72h (need lookback for liquidity map)
    ts_index = ts_index[72:]

    rows: list[dict] = []
    print(f"Scanning {len(ts_index)} hourly bars for H10 setups...")

    for ts in tqdm(ts_index[::step_hours]):
        ts_py = ts.to_pydatetime()

        liq_map = build_liquidity_map(ts_py, ohlcv_1h, lookback_hours=72)
        if not liq_map:
            continue

        setup = detect_setup(ts_py, ohlcv_1h, liq_map)
        if setup is None:
            continue

        for p in params_grid:
            result = simulate_probe(setup, ohlcv_1m, p)
            if result is None:
                continue

            rows.append({
                "setup_ts": setup.timestamp,
                "impulse_pct": round(setup.impulse_pct * 100, 3),
                "impulse_dir": setup.impulse_direction,
                "impulse_window_hours": setup.impulse_window_hours,
                "cons_low": setup.consolidation_low,
                "cons_high": setup.consolidation_high,
                "consolidation_hours": setup.consolidation_hours,
                "target_price": setup.target_zone.price_level,
                "target_weight": setup.target_zone.weight,
                "target_side": setup.target_side,
                # params
                "grid_steps": p.grid_steps,
                "grid_step_pct": p.grid_step_pct,
                "tp_pct": p.tp_pct,
                "time_stop_hours": p.time_stop_hours,
                "protective_stop_pct": p.protective_stop_pct,
                "total_btc": p.total_btc,
                # results
                "n_filled": result.n_orders_filled,
                "avg_entry": result.avg_entry,
                "exit_price": result.exit_price,
                "exit_reason": result.exit_reason,
                "pnl_btc": round(result.pnl_btc, 6),
                "pnl_usd": round(result.pnl_usd, 2),
                "volume_btc": round(result.volume_btc, 4),
                "volume_usd": round(result.volume_usd, 2),
                "duration_min": result.duration_minutes,
                "max_drawdown_pct": round(result.max_drawdown_pct * 100, 3),
            })

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="H10 MVP Backtest")
    parser.add_argument("--full-grid", action="store_true")
    parser.add_argument("--detector-only", action="store_true",
                        help="Run detector only (no simulation); prints setup list")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--out", default=None, help="Output CSV path")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc) if args.start else None
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else None

    print("Loading 1h OHLCV...")
    ohlcv_1h = _load_ohlcv(OHLCV_1H)
    print(f"  1h: {len(ohlcv_1h)} bars ({ohlcv_1h.index[0].date()} to {ohlcv_1h.index[-1].date()})")

    if args.detector_only:
        df = detect_only(ohlcv_1h, start=start, end=end)
        n_raw = len(df)
        n_events = df["event_id"].nunique() if n_raw else 0
        print(f"\n{'='*60}")
        print(f"Raw detections: {n_raw}  |  Unique events: {n_events}")
        print(f"{'='*60}")
        if n_raw:
            # Print first detection of each event
            first = df.groupby("event_id").first().reset_index()
            for _, row in first.iterrows():
                ts_str = pd.Timestamp(row["setup_ts"]).strftime("%Y-%m-%d %H:%M")
                print(
                    f"  [{row['event_id']:>3}] {ts_str}  {row['target_side']:<14}"
                    f"  imp={row['impulse_pct']:.1f}%/{row['impulse_window_hours']}h"
                    f"  cons={row['consolidation_hours']}h/{((row['cons_high']-row['cons_low'])/row['cons_low']*100):.1f}%"
                    f"  zone={row['target_price']:.0f} w={row['target_weight']:.2f}"
                )
        REPORTS_DIR.mkdir(exist_ok=True)
        out_path = args.out or str(REPORTS_DIR / f"h10_detect_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
        df.to_csv(out_path, index=False)
        print(f"\nSaved: {out_path}")
        return

    ohlcv_1m = _load_ohlcv(OHLCV_1M)
    print(f"  1m: {len(ohlcv_1m)} bars")

    params_grid = _full_params_grid() if args.full_grid else _default_params_grid()
    print(f"Param combinations: {len(params_grid)}")

    df = backtest_h10(ohlcv_1h, ohlcv_1m, start=start, end=end, params_grid=params_grid)
    print(f"\nResults: {len(df)} rows ({df['setup_ts'].nunique() if len(df) else 0} unique setups)")

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = args.out or str(REPORTS_DIR / f"h10_backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    df.to_csv(out_path, index=False)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
