"""Tests for snapshot.py — §14.2 TZ-022."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.whatif.snapshot import Snapshot, _unrealized, build_snapshot

# ── Fixtures ──────────────────────────────────────────────────────────────────

_FEATURES_DIR = Path("features_out")
_SYMBOL = "BTCUSDT"
_KNOWN_TS = pd.Timestamp("2026-03-15 08:00", tz="UTC")   # within frozen data
_KNOWN_TS2 = pd.Timestamp("2026-01-10 12:30", tz="UTC")


def _has_real_data() -> bool:
    return (_FEATURES_DIR / _SYMBOL / "2026-03-15.parquet").exists()


skip_no_data = pytest.mark.skipif(
    not _has_real_data(),
    reason="features_out not present (run scripts/run_features.py first)",
)


# ── _unrealized ───────────────────────────────────────────────────────────────

def test_unrealized_short_profit():
    # Short -0.18 BTC, entry 85000, close 84000 → profit
    pnl = _unrealized(-0.18, 85_000, 84_000)
    assert pnl == pytest.approx(-0.18 * (84_000 - 85_000), rel=1e-6)
    assert pnl > 0


def test_unrealized_short_loss():
    pnl = _unrealized(-0.18, 85_000, 86_000)
    assert pnl < 0


def test_unrealized_long_profit():
    pnl = _unrealized(0.1, 80_000, 82_000)
    assert pnl > 0


def test_unrealized_flat():
    assert _unrealized(0.0, 80_000, 82_000) == 0.0


def test_unrealized_zero_entry():
    assert _unrealized(-0.1, 0.0, 80_000) == 0.0


# ── Snapshot dataclass ────────────────────────────────────────────────────────

def _make_snap(**kwargs) -> Snapshot:
    defaults = dict(
        timestamp=_KNOWN_TS,
        symbol=_SYMBOL,
        close=84_000.0,
        feature_row={"close": 84_000.0, "atr_1h": 500.0},
        position_size_btc=-0.18,
        avg_entry=85_000.0,
        unrealized_pnl_usd=180.0,
        grid_target_pct=1.0,
        grid_step_pct=0.5,
        boundary_top=87_000.0,
        boundary_bottom=80_000.0,
    )
    defaults.update(kwargs)
    return Snapshot(**defaults)


def test_snapshot_is_short():
    s = _make_snap(position_size_btc=-0.18)
    assert s.is_short
    assert not s.is_long
    assert not s.is_flat


def test_snapshot_is_long():
    s = _make_snap(position_size_btc=0.1)
    assert s.is_long
    assert not s.is_short


def test_snapshot_is_flat():
    s = _make_snap(position_size_btc=0.0)
    assert s.is_flat


def test_snapshot_notional():
    s = _make_snap(position_size_btc=-0.5, close=80_000.0)
    assert s.notional_usd == pytest.approx(40_000.0)


def test_snapshot_notional_long():
    s = _make_snap(position_size_btc=0.25, close=80_000.0)
    assert s.notional_usd == pytest.approx(20_000.0)


def test_snapshot_default_status():
    s = _make_snap()
    assert s.bot_status == "running"


def test_snapshot_copy_is_independent():
    s = _make_snap()
    s2 = s.copy()
    s2.close = 99_000.0
    s2.feature_row["close"] = 99_000.0
    assert s.close == 84_000.0
    assert s.feature_row["close"] == 84_000.0


def test_snapshot_copy_feature_row_is_deep():
    s = _make_snap(feature_row={"close": 84_000.0, "rsi": 55.0})
    s2 = s.copy()
    s2.feature_row["rsi"] = 99.0
    assert s.feature_row["rsi"] == 55.0


def test_snapshot_realized_pnl_default():
    s = _make_snap()
    assert s.realized_pnl_session == 0.0


def test_snapshot_capital_default():
    s = _make_snap()
    assert s.capital_usd == 14_000.0


# ── build_snapshot with real data ─────────────────────────────────────────────

@skip_no_data
def test_build_snapshot_basic():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert isinstance(snap, Snapshot)
    assert snap.symbol == _SYMBOL
    assert snap.close > 0


@skip_no_data
def test_build_snapshot_timestamp_preserved():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert snap.timestamp == _KNOWN_TS


@skip_no_data
def test_build_snapshot_feature_row_has_cols():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    for col in ["close", "atr_1h", "delta_5m_pct", "kz_active", "dow_ny"]:
        assert col in snap.feature_row, f"Missing {col}"


@skip_no_data
def test_build_snapshot_feature_row_len():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert len(snap.feature_row) >= 170


@skip_no_data
def test_build_snapshot_close_matches_feature_row():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert snap.close == pytest.approx(snap.feature_row["close"])


@skip_no_data
def test_build_snapshot_position_synthetic():
    snap = build_snapshot(
        _KNOWN_TS, _SYMBOL,
        features_dir=_FEATURES_DIR,
        position_size_btc=-0.18,
        avg_entry=85_000.0,
    )
    assert snap.position_size_btc == pytest.approx(-0.18)
    assert snap.avg_entry == pytest.approx(85_000.0)


@skip_no_data
def test_build_snapshot_unrealized_auto():
    close_snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    close = close_snap.close
    snap = build_snapshot(
        _KNOWN_TS, _SYMBOL,
        features_dir=_FEATURES_DIR,
        position_size_btc=-0.18,
        avg_entry=close + 500,   # entry 500 above close → short in profit
    )
    assert snap.unrealized_pnl_usd > 0


@skip_no_data
def test_build_snapshot_unrealized_override():
    snap = build_snapshot(
        _KNOWN_TS, _SYMBOL,
        features_dir=_FEATURES_DIR,
        position_size_btc=-0.18,
        avg_entry=85_000.0,
        unrealized_pnl_usd=999.0,
    )
    assert snap.unrealized_pnl_usd == pytest.approx(999.0)


@skip_no_data
def test_build_snapshot_default_boundaries():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert snap.boundary_top > snap.close
    assert snap.boundary_bottom < snap.close


@skip_no_data
def test_build_snapshot_custom_boundaries():
    snap = build_snapshot(
        _KNOWN_TS, _SYMBOL,
        features_dir=_FEATURES_DIR,
        boundary_top=90_000.0,
        boundary_bottom=75_000.0,
    )
    assert snap.boundary_top == pytest.approx(90_000.0)
    assert snap.boundary_bottom == pytest.approx(75_000.0)


@skip_no_data
def test_build_snapshot_string_timestamp():
    snap = build_snapshot("2026-03-15 08:00", _SYMBOL, features_dir=_FEATURES_DIR)
    assert isinstance(snap.timestamp, pd.Timestamp)
    assert snap.timestamp.tzinfo is not None


@skip_no_data
def test_build_snapshot_second_date():
    snap = build_snapshot(_KNOWN_TS2, _SYMBOL, features_dir=_FEATURES_DIR)
    assert snap.close > 0
    assert len(snap.feature_row) >= 170


@skip_no_data
def test_build_snapshot_flat_position():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert snap.is_flat
    assert snap.unrealized_pnl_usd == 0.0


@skip_no_data
def test_build_snapshot_missing_partition_raises():
    ts = pd.Timestamp("2020-01-01 00:00", tz="UTC")
    with pytest.raises(FileNotFoundError):
        build_snapshot(ts, _SYMBOL, features_dir=_FEATURES_DIR)


@skip_no_data
def test_build_snapshot_eth():
    ts = pd.Timestamp("2026-03-15 10:00", tz="UTC")
    snap = build_snapshot(ts, "ETHUSDT", features_dir=_FEATURES_DIR)
    assert snap.symbol == "ETHUSDT"
    assert snap.close > 0


@skip_no_data
def test_build_snapshot_capital_default():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert snap.capital_usd == 14_000.0


@skip_no_data
def test_build_snapshot_capital_custom():
    snap = build_snapshot(
        _KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR, capital_usd=50_000.0
    )
    assert snap.capital_usd == pytest.approx(50_000.0)


@skip_no_data
def test_build_snapshot_copy_then_modify():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    snap2 = snap.copy()
    snap2.close = 1.0
    assert snap.close != 1.0


@skip_no_data
def test_build_snapshot_avg_entry_defaults_to_close():
    snap = build_snapshot(_KNOWN_TS, _SYMBOL, features_dir=_FEATURES_DIR)
    assert snap.avg_entry == pytest.approx(snap.close)
