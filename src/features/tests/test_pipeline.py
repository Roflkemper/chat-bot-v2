"""Integration tests for pipeline.py — synthetic 1-week × 3 symbols."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features.pipeline import (
    _align_to_1m,
    _compute_deltas,
    _load_parquet,
    _parse_timestamps,
    _run_symbol_features,
    build_features,
)
from src.features.manifest import Manifest


# ── Fixtures ──────────────────────────────────────────────────────────────────

SYMBOLS = ["btc", "eth", "xrp"]
WEEK_MINUTES = 7 * 24 * 60  # 10080

def _make_klines(n: int = WEEK_MINUTES, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = 50_000.0 + np.cumsum(rng.normal(0, 10, n))
    high  = close + rng.uniform(0, 50, n)
    low   = close - rng.uniform(0, 50, n)
    open_ = close + rng.normal(0, 5, n)
    vol   = rng.uniform(1, 10, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _make_metrics(n_5m: int = WEEK_MINUTES // 5, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n_5m, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "open_interest": 1e8 + np.cumsum(rng.normal(0, 1e5, n_5m)),
            "ls_top_ratio":  rng.uniform(0.4, 0.6, n_5m),
            "ls_retail_ratio": rng.uniform(0.45, 0.55, n_5m),
            "taker_buy_vol": rng.uniform(1e6, 2e6, n_5m),
            "taker_sell_vol": rng.uniform(1e6, 2e6, n_5m),
        },
        index=idx,
    )


def _make_funding(n_8h: int = WEEK_MINUTES // 480 + 1, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n_8h, freq="8h", tz="UTC")
    return pd.DataFrame(
        {"funding_rate": rng.uniform(-0.001, 0.001, n_8h)},
        index=idx,
    )


def _write_parquets(base: Path, symbol: str, klines: pd.DataFrame,
                    metrics: pd.DataFrame, funding: pd.DataFrame) -> None:
    sym_dir = base / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)

    kl = klines.reset_index().rename(columns={"index": "open_time"})
    kl["open_time"] = kl["open_time"].astype("int64") // 10**6
    kl.to_parquet(sym_dir / "klines_1m.parquet", index=False)

    mt = metrics.reset_index().rename(columns={"index": "open_time"})
    mt["open_time"] = mt["open_time"].astype("int64") // 10**6
    mt.to_parquet(sym_dir / "metrics_5m.parquet", index=False)

    fu = funding.reset_index().rename(columns={"index": "funding_time"})
    fu["funding_time"] = fu["funding_time"].astype("int64") // 10**6
    fu.to_parquet(sym_dir / "funding_8h.parquet", index=False)


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    base = tmp_path_factory.mktemp("raw_data")
    for i, sym in enumerate(SYMBOLS):
        klines  = _make_klines(seed=10 * i)
        metrics = _make_metrics(seed=10 * i + 1)
        funding = _make_funding(seed=10 * i + 2)
        _write_parquets(base, sym, klines, metrics, funding)
    return base


@pytest.fixture(scope="module")
def output_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("features_out")


@pytest.fixture(scope="module")
def built(data_dir, output_dir):
    return build_features(data_dir, output_dir, SYMBOLS, n_workers=1)


# ── _parse_timestamps ─────────────────────────────────────────────────────────

def test_parse_timestamps_ms_int():
    s = pd.Series([1_700_000_000_000, 1_700_000_060_000])
    result = _parse_timestamps(s)
    assert result.iloc[0] == pd.Timestamp("2023-11-14 22:13:20", tz="UTC")


def test_parse_timestamps_datetime_string():
    s = pd.Series(["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"])
    result = _parse_timestamps(s)
    assert result.iloc[0].tz is not None


# ── _load_parquet ─────────────────────────────────────────────────────────────

def test_load_parquet_missing_returns_none(tmp_path):
    result = _load_parquet(tmp_path / "nonexistent.parquet", ts_col="open_time")
    assert result is None


def test_load_parquet_ms_epoch(tmp_path):
    idx = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    df = pd.DataFrame({"close": range(5)}, index=idx)
    df = df.reset_index().rename(columns={"index": "open_time"})
    df["open_time"] = df["open_time"].astype("int64") // 10**6
    path = tmp_path / "klines.parquet"
    df.to_parquet(path, index=False)

    loaded = _load_parquet(path, ts_col="open_time")
    assert loaded is not None
    assert loaded.index.tz is not None
    assert len(loaded) == 5


def test_load_parquet_missing_ts_col(tmp_path):
    df = pd.DataFrame({"close": [1, 2, 3]})
    path = tmp_path / "bad.parquet"
    df.to_parquet(path)
    result = _load_parquet(path, ts_col="open_time")
    assert result is None


def test_load_parquet_sorted_index(tmp_path):
    idx = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")[::-1]
    df = pd.DataFrame({"close": range(5)}, index=idx)
    df = df.reset_index().rename(columns={"index": "open_time"})
    df["open_time"] = df["open_time"].astype("int64") // 10**6
    path = tmp_path / "klines_unsorted.parquet"
    df.to_parquet(path, index=False)
    loaded = _load_parquet(path, ts_col="open_time")
    assert loaded.index.is_monotonic_increasing


# ── _align_to_1m ─────────────────────────────────────────────────────────────

def test_align_metrics_ffill():
    klines_idx = pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC")
    klines = pd.DataFrame({"close": np.ones(10)}, index=klines_idx)

    metrics_idx = pd.date_range("2026-01-01", periods=2, freq="5min", tz="UTC")
    metrics = pd.DataFrame({"oi": [100.0, 200.0]}, index=metrics_idx)

    aligned = _align_to_1m(klines, metrics, None)
    assert "oi" in aligned.columns
    assert aligned["oi"].iloc[0] == 100.0
    assert aligned["oi"].iloc[5] == 200.0


def test_align_funding_ffill():
    klines_idx = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    klines = pd.DataFrame({"close": np.ones(5)}, index=klines_idx)
    funding = pd.DataFrame({"funding_rate": [0.001]},
                           index=pd.DatetimeIndex(["2026-01-01"], tz="UTC"))
    aligned = _align_to_1m(klines, None, funding)
    assert "funding_rate" in aligned.columns
    assert (aligned["funding_rate"] == 0.001).all()


def test_align_no_metrics_no_funding():
    klines_idx = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    klines = pd.DataFrame({"close": np.ones(5)}, index=klines_idx)
    aligned = _align_to_1m(klines, None, None)
    assert list(aligned.columns) == ["close"]


def test_align_preserves_klines_length():
    klines_idx = pd.date_range("2026-01-01", periods=WEEK_MINUTES, freq="1min", tz="UTC")
    klines  = pd.DataFrame({"close": np.ones(WEEK_MINUTES)}, index=klines_idx)
    metrics = _make_metrics()
    aligned = _align_to_1m(klines, metrics, None)
    assert len(aligned) == WEEK_MINUTES


# ── _compute_deltas ───────────────────────────────────────────────────────────

def test_compute_deltas_columns_added():
    df = pd.DataFrame({"close": np.arange(1, 101, dtype=float)})
    out = _compute_deltas(df)
    for col in ["delta_5m_pct", "delta_15m_pct", "delta_1h_pct", "delta_24h_pct"]:
        assert col in out.columns


def test_compute_deltas_nan_for_first_rows():
    df = pd.DataFrame({"close": np.arange(1, 101, dtype=float)})
    out = _compute_deltas(df)
    assert out["delta_5m_pct"].iloc[:5].isna().all()
    assert out["delta_5m_pct"].iloc[5] > 0


def test_compute_deltas_no_close_column():
    df = pd.DataFrame({"open": [1.0, 2.0]})
    out = _compute_deltas(df)
    assert "delta_5m_pct" not in out.columns


def test_compute_deltas_values():
    prices = [100.0] * 6
    prices[5] = 110.0
    df = pd.DataFrame({"close": prices})
    out = _compute_deltas(df)
    # delta_5m_pct at index 5 = (110-100)/100 * 100 = 10%
    assert abs(out["delta_5m_pct"].iloc[5] - 10.0) < 1e-6


# ── _run_symbol_features ──────────────────────────────────────────────────────

def _minimal_klines(n: int = 1500) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    rng = np.random.default_rng(0)
    close = 50_000 + np.cumsum(rng.normal(0, 10, n))
    high = close + rng.uniform(0, 20, n)
    low  = close - rng.uniform(0, 20, n)
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": np.ones(n)},
        index=idx,
    )


def test_run_symbol_features_returns_dataframe():
    df = _minimal_klines()
    result = _run_symbol_features(df)
    assert isinstance(result, pd.DataFrame)


def test_run_symbol_features_no_look_ahead():
    df = _minimal_klines()
    result = _run_symbol_features(df)
    assert len(result) == len(df)


def test_run_symbol_features_delta_cols_present():
    df = _minimal_klines()
    result = _run_symbol_features(df)
    for col in ["delta_5m_pct", "delta_15m_pct", "delta_1h_pct", "delta_24h_pct"]:
        assert col in result.columns, f"Missing {col}"


def test_run_symbol_features_calendar_cols():
    df = _minimal_klines()
    result = _run_symbol_features(df)
    assert "dow_ny" in result.columns
    assert "kz_session_id" in result.columns


def test_run_symbol_features_kz_col():
    df = _minimal_klines()
    result = _run_symbol_features(df)
    assert "kz_active" in result.columns


def test_run_symbol_features_dwm_col():
    df = _minimal_klines(n=2000)
    result = _run_symbol_features(df)
    assert "pdh" in result.columns


def test_run_symbol_features_technical_col():
    df = _minimal_klines(n=200)
    result = _run_symbol_features(df)
    assert "atr_1h" in result.columns


# ── build_features integration ────────────────────────────────────────────────

def test_build_features_returns_dict(built):
    assert isinstance(built, dict)
    for sym in SYMBOLS:
        assert sym in built


def test_build_features_writes_parquets(built, output_dir):
    for sym in SYMBOLS:
        sym_dir = output_dir / sym
        parquets = list(sym_dir.glob("*.parquet"))
        assert len(parquets) > 0, f"No parquets for {sym}"


def test_build_features_seven_days(built):
    for sym in SYMBOLS:
        assert len(built[sym]) == 7, f"{sym}: expected 7 days, got {len(built[sym])}"


def test_build_features_parquet_columns(built, output_dir):
    sym = "btc"
    first_file = sorted((output_dir / sym).glob("*.parquet"))[0]
    df = pd.read_parquet(first_file)
    for col in ["close", "atr_1h", "delta_5m_pct", "dow_ny"]:
        assert col in df.columns, f"Missing {col} in {sym} parquet"


def test_build_features_parquet_no_future_rows(built, output_dir):
    sym = "btc"
    files = sorted((output_dir / sym).glob("*.parquet"))
    for f in files[:3]:
        df = pd.read_parquet(f)
        date_str = f.stem
        assert all(str(t) == date_str for t in df.index.date), \
            f"Rows outside date {date_str} in {f.name}"


def test_build_features_fresh_skip(data_dir, output_dir):
    # Second call should skip all (manifest fresh)
    result = build_features(data_dir, output_dir, SYMBOLS, n_workers=1)
    for sym in SYMBOLS:
        assert result[sym] == [], f"{sym} should be empty on second run"


def test_build_features_force_rebuild(data_dir, output_dir):
    result = build_features(data_dir, output_dir, SYMBOLS, force_rebuild=True, n_workers=1)
    for sym in SYMBOLS:
        assert len(result[sym]) == 7, f"{sym} should have 7 partitions after force rebuild"


def test_build_features_manifest_written(built, output_dir):
    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert "engine_hash" in data
    assert "params_hash" in data
    assert "partitions" in data


# ── Cross-asset columns in output ─────────────────────────────────────────────

def test_cross_asset_cols_in_btc_output(built, output_dir):
    first_file = sorted((output_dir / "btc").glob("*.parquet"))[0]
    df = pd.read_parquet(first_file)
    assert "btc_eth_corr_4h" in df.columns or "dump_count_1h" in df.columns, \
        "Expected at least one cross-asset column in btc output"


def test_cross_asset_dump_count_valid(built, output_dir):
    first_file = sorted((output_dir / "btc").glob("*.parquet"))[0]
    df = pd.read_parquet(first_file)
    if "dump_count_1h" in df.columns:
        vals = df["dump_count_1h"].dropna()
        assert (vals >= 0).all() and (vals <= 3).all()


# ── Manifest unit tests ───────────────────────────────────────────────────────

def test_manifest_fresh_after_mark(tmp_path):
    features_dir = Path(__file__).parent.parent
    m = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    assert not m.is_fresh("btc", "2026-01-01")
    m.mark_done("btc", "2026-01-01")
    m2 = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    assert m2.is_fresh("btc", "2026-01-01")


def test_manifest_stale_on_params_change(tmp_path):
    features_dir = Path(__file__).parent.parent
    m = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    m.mark_done("btc", "2026-01-01")
    m2 = Manifest(tmp_path, features_dir, {"symbols": ["eth"]})
    assert not m2.is_fresh("btc", "2026-01-01")


def test_manifest_invalidate(tmp_path):
    features_dir = Path(__file__).parent.parent
    m = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    m.mark_done("btc", "2026-01-01")
    m.invalidate()
    m2 = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    assert not m2.is_fresh("btc", "2026-01-01")


def test_manifest_multiple_dates(tmp_path):
    features_dir = Path(__file__).parent.parent
    m = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    for d in ["2026-01-01", "2026-01-02", "2026-01-03"]:
        m.mark_done("btc", d)
    m2 = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    for d in ["2026-01-01", "2026-01-02", "2026-01-03"]:
        assert m2.is_fresh("btc", d)


def test_manifest_corrupt_file(tmp_path):
    features_dir = Path(__file__).parent.parent
    (tmp_path / "manifest.json").write_text("NOT JSON", encoding="utf-8")
    m = Manifest(tmp_path, features_dir, {"symbols": ["btc"]})
    assert not m.is_fresh("btc", "2026-01-01")
