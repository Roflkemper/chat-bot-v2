from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from whatif import real_snapshot_replay as rr


def _write_feature_day(base: Path, date_str: str) -> None:
    idx = pd.date_range(f"{date_str} 00:00:00+00:00", periods=400, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * len(idx),
            "high": [101.0] * len(idx),
            "low": [99.0] * len(idx),
            "close": [100.0] * len(idx),
            "current_d_high": [101.0] * len(idx),
        },
        index=idx,
    )
    path = base / "BTCUSDT" / f"{date_str}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def test_schema_check_tracker_csv_columns(tmp_path, monkeypatch):
    snapshots = tmp_path / "snapshots_v2.csv"
    params = tmp_path / "params_v2.csv"
    snapshots.write_text(
        "\n".join(
            [
                "ts_utc,bot_id,bot_name,alias,status,position,profit,current_profit,"
                "in_filled_count,out_filled_count,average_price",
                "2026-04-24T10:00:00+00:00,1,BTC-LONG-B,BTC-LONG-B,2,0.1,10,12,1,1,100",
            ]
        ),
        encoding="utf-8",
    )
    params.write_text(
        "\n".join(
            [
                "ts_utc,bot_id,bot_name,alias,grid_step,border_top,border_bottom,target,side",
                "2026-04-24T10:00:00+00:00,1,BTC-LONG-B,BTC-LONG-B,0.03,110,90,0.25,1",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(rr, "TRACKER_SNAPSHOTS_CSV", snapshots)
    monkeypatch.setattr(rr, "TRACKER_PARAMS_CSV", params)
    monkeypatch.setattr(rr, "_load_price_series", lambda *args, **kwargs: pd.DataFrame({"ts_utc": [pd.Timestamp("2026-04-24T10:00:00+00:00")], "price": [100.0]}))

    df = rr.load_bot_episode("BTC-LONG-B", "2026-04-24T10:00:00+00:00", 1)
    expected = {
        "ts_utc",
        "bot_id",
        "symbol",
        "price",
        "position_btc",
        "unrealized_pnl",
        "grid_top",
        "grid_bottom",
        "grid_step",
        "n_filled_orders",
        "realized_pnl_session",
    }
    assert expected.issubset(df.columns)


def test_smoke_apply_play_to_real(tmp_path, monkeypatch):
    features = tmp_path / "features_out"
    _write_feature_day(features, "2026-04-24")
    monkeypatch.setattr(rr, "FEATURES_DIR", features)

    episode = pd.DataFrame(
        {
            "ts_utc": pd.date_range("2026-04-24T00:00:00+00:00", periods=6, freq="1min", tz="UTC"),
            "bot_id": [1] * 6,
            "bot_name": ["TEST_3"] * 6,
            "alias": ["TEST_3"] * 6,
            "symbol": ["BTCUSDT"] * 6,
            "price": [100.0] * 6,
            "position_btc": [-0.1] * 6,
            "unrealized_pnl": [-1.0, -0.5, 0.0, 0.4, 0.8, 1.0],
            "grid_top": [110.0] * 6,
            "grid_bottom": [90.0] * 6,
            "grid_step": [0.03] * 6,
            "n_filled_orders": [2] * 6,
            "realized_pnl_session": [10.0, 10.0, 10.2, 10.4, 10.4, 10.6],
            "average_price": [101.0] * 6,
            "target": [0.25] * 6,
            "side": [2] * 6,
        }
    )

    result = rr.apply_play_to_real(episode, "P-1", {"offset_pct": 0.5})
    assert result.play_id == "P-1"
    assert result.n_points == 6


def test_real_pnl_without_play_matches_tracker_delta():
    episode = pd.DataFrame(
        {
            "ts_utc": pd.date_range("2026-04-24T00:00:00+00:00", periods=3, freq="1min", tz="UTC"),
            "realized_pnl_session": [100.0, 100.5, 101.0],
            "unrealized_pnl": [5.0, 6.0, 7.0],
        }
    )
    pnl, _ = rr._real_baseline_metrics(episode)
    tracker_delta = (101.0 - 100.0) + (7.0 - 5.0)
    assert abs(pnl - tracker_delta) <= max(0.05 * abs(tracker_delta), 1e-9)

