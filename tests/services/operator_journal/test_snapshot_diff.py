from __future__ import annotations

import json

import pandas as pd

from services.operator_journal.snapshot_diff import build_decision_records, run_extraction


def _write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_ict(path, start: str, periods: int):
    idx = pd.date_range(start, periods=periods, freq="1min", tz="UTC")
    pd.DataFrame(
        {
            "session_active": ["london"] * periods,
            "dist_to_pdh_pct": [0.1] * periods,
            "dist_to_nearest_unmitigated_high_pct": [0.2] * periods,
        },
        index=idx,
    ).to_parquet(path)


def _write_frozen(path, start: str, periods: int, close_start: float = 100.0):
    idx = pd.date_range(start, periods=periods, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "ts": (idx.view("int64") // 1_000_000).astype("int64"),
            "open": [close_start + i for i in range(periods)],
            "high": [close_start + i + 0.5 for i in range(periods)],
            "low": [close_start + i - 0.5 for i in range(periods)],
            "close": [close_start + i for i in range(periods)],
            "volume": [1.0] * periods,
        }
    )
    df.to_csv(path, index=False)


def _params_row(ts: str, target: float, *, dsblin: bool = False, order_size: float = 0.001):
    raw = {"q": {"minQ": order_size}}
    return {
        "ts_utc": ts,
        "bot_id": "1",
        "bot_name": "bot",
        "alias": "BTC",
        "strategy_id": "",
        "side": 2,
        "grid_step": 0.03,
        "grid_step_ratio": "",
        "max_opened_orders": 10,
        "border_top": 110,
        "border_bottom": 90,
        "instop": 0.01,
        "minstop": 0.01,
        "maxstop": 0.03,
        "target": target,
        "total_sl": "",
        "total_tp": "",
        "leverage": 0,
        "otc": True,
        "dsblin": dsblin,
        "raw_params_json": json.dumps(raw),
        "schema_version": 3,
    }


def _snap_row(ts: str, *, status: int = 2, profit: float = 10.0, current_profit: float = 1.0, position: float = -0.1):
    return {
        "ts_utc": ts,
        "bot_id": "1",
        "bot_name": "bot",
        "alias": "BTC",
        "status": status,
        "position": position,
        "profit": profit,
        "current_profit": current_profit,
        "in_filled_count": 0,
        "in_filled_qty": 0,
        "out_filled_count": 0,
        "out_filled_qty": 0,
        "trigger_count": 0,
        "trigger_qty": 0,
        "average_price": 100.0,
        "trade_volume": 0,
        "balance": 0,
        "liquidation_price": 130.0,
        "schema_version": 3,
    }


def test_diff_detects_target_change(tmp_path):
    params = tmp_path / "params.csv"
    snaps = tmp_path / "snapshots.csv"
    ict = tmp_path / "ict.parquet"
    frozen = tmp_path / "btc.csv"
    _write_csv(params, [_params_row("2026-04-30T00:00:00+00:00", 0.20), _params_row("2026-04-30T01:00:00+00:00", 0.25)])
    _write_csv(snaps, [_snap_row("2026-04-30T00:00:00+00:00"), _snap_row("2026-04-30T01:00:00+00:00")])
    _write_ict(ict, "2026-04-29T00:00:00+00:00", 3000)
    _write_frozen(frozen, "2026-04-29T00:00:00+00:00", 3000)

    df = build_decision_records(params_csv=params, snapshots_csv=snaps, ict_parquet=ict, frozen_ohlcv_csv=frozen)

    row = df[df["field"] == "target"].iloc[0]
    assert row["change_type"] == "param_change"
    assert row["old_value"] == "0.2"
    assert row["new_value"] == "0.25"


def test_market_context_attached(tmp_path):
    params = tmp_path / "params.csv"
    snaps = tmp_path / "snapshots.csv"
    ict = tmp_path / "ict.parquet"
    frozen = tmp_path / "btc.csv"
    _write_csv(params, [_params_row("2026-04-30T00:00:00+00:00", 0.20), _params_row("2026-04-30T01:00:00+00:00", 0.25)])
    _write_csv(snaps, [_snap_row("2026-04-30T00:00:00+00:00"), _snap_row("2026-04-30T01:00:00+00:00")])
    _write_ict(ict, "2026-04-29T00:00:00+00:00", 3000)
    _write_frozen(frozen, "2026-04-29T00:00:00+00:00", 3000)

    df = build_decision_records(params_csv=params, snapshots_csv=snaps, ict_parquet=ict, frozen_ohlcv_csv=frozen)
    row = df.iloc[0]
    assert row["session_active"] == "london"
    assert pd.notna(row["price"])
    assert pd.notna(row["dist_to_pdh_pct"])
    assert pd.notna(row["dist_to_nearest_unmitigated_high_pct"])


def test_outcome_horizons(tmp_path):
    params = tmp_path / "params.csv"
    snaps = tmp_path / "snapshots.csv"
    ict = tmp_path / "ict.parquet"
    frozen = tmp_path / "btc.csv"
    _write_csv(params, [_params_row("2026-04-30T00:00:00+00:00", 0.20), _params_row("2026-04-30T01:00:00+00:00", 0.25)])
    snap_rows = [
        _snap_row("2026-04-30T00:00:00+00:00", profit=10.0, current_profit=1.0),
        _snap_row("2026-04-30T01:00:00+00:00", profit=12.0, current_profit=1.5),
        _snap_row("2026-04-30T02:00:00+00:00", profit=16.0, current_profit=2.0),
        _snap_row("2026-04-30T05:00:00+00:00", profit=18.0, current_profit=2.5),
    ]
    _write_csv(snaps, snap_rows)
    _write_ict(ict, "2026-04-29T00:00:00+00:00", 3000)
    _write_frozen(frozen, "2026-04-29T00:00:00+00:00", 3000)

    df = build_decision_records(params_csv=params, snapshots_csv=snaps, ict_parquet=ict, frozen_ohlcv_csv=frozen)
    row = df.iloc[0]
    assert row["bot_realized_pnl_1h"] == 4.0
    assert pd.notna(row["price_change_pct_1h"])
    assert pd.isna(row["bot_realized_pnl_24h"])


def test_incremental_no_duplicates(tmp_path):
    params = tmp_path / "params.csv"
    snaps = tmp_path / "snapshots.csv"
    ict = tmp_path / "ict.parquet"
    frozen = tmp_path / "btc.csv"
    output = tmp_path / "decisions.parquet"
    _write_csv(params, [_params_row("2026-04-30T00:00:00+00:00", 0.20), _params_row("2026-04-30T01:00:00+00:00", 0.25)])
    _write_csv(snaps, [_snap_row("2026-04-30T00:00:00+00:00"), _snap_row("2026-04-30T01:00:00+00:00")])
    _write_ict(ict, "2026-04-29T00:00:00+00:00", 3000)
    _write_frozen(frozen, "2026-04-29T00:00:00+00:00", 3000)

    first = run_extraction(
        rebuild=True,
        output=output,
        paths=type("P", (), {"params_csv": params, "snapshots_csv": snaps, "ict_parquet": ict, "frozen_ohlcv_csv": frozen, "output_parquet": output})(),
    )
    second = run_extraction(
        incremental=True,
        output=output,
        paths=type("P", (), {"params_csv": params, "snapshots_csv": snaps, "ict_parquet": ict, "frozen_ohlcv_csv": frozen, "output_parquet": output})(),
    )
    assert len(first) == len(second) == 1
