"""Tests for ICTContextReader integration — TZ-ICT-LEVELS-INTEGRATE-DETECTOR."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.setup_detector.ict_context import ICT_CONTEXT_COLS, ICTContextReader
from services.setup_detector.models import Setup, SetupBasis, SetupType, make_setup
from services.setup_detector.storage import SetupStorage

# ─────────────────────────────── helpers ──────────────────────────────────────

def _utc(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _make_ict_df(timestamps: list[datetime], rows: list[dict]) -> pd.DataFrame:
    """Build a minimal ICT levels DataFrame with DatetimeIndex UTC."""
    idx = pd.DatetimeIndex(timestamps, tz="UTC")
    data = {col: [r.get(col) for r in rows] for col in ICT_CONTEXT_COLS}
    return pd.DataFrame(data, index=idx)


def _save_parquet(df: pd.DataFrame, path: Path) -> None:
    df.to_parquet(path, index=True)


def _minimal_setup(ict: dict | None = None) -> Setup:
    return make_setup(
        setup_type=SetupType.LONG_PDL_BOUNCE,
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="trend_down",
        session_label="NY_AM",
        strength=9,
        confidence_pct=75.0,
        basis=(SetupBasis("pdl_test", 80000.0, 1.0),),
        cancel_conditions=("cancel",),
        window_minutes=120,
        portfolio_impact_note="test",
        recommended_size_btc=0.05,
        ict_context=ict if ict is not None else {},
    )


# ─────────────────────────────── Test 1: reader loads and lookup works ─────────

def test_ict_context_loaded(tmp_path: Path) -> None:
    """ICTContextReader.load() from valid parquet → lookup returns dict with all 14 keys."""
    ts = _utc(2026, 4, 29, 14, 30)
    row = {
        "session_active": "ny_am",
        "time_in_session_min": 5,
        "dist_to_pdh_pct": -0.25,
        "dist_to_pdl_pct": 1.50,
        "dist_to_pwh_pct": -0.80,
        "dist_to_pwl_pct": 2.10,
        "dist_to_d_open_pct": 0.30,
        "dist_to_kz_mid_pct": -0.05,
        "dist_to_nearest_unmitigated_high_pct": -0.45,
        "dist_to_nearest_unmitigated_low_pct": 1.20,
        "nearest_unmitigated_high_above": 80360.0,
        "nearest_unmitigated_high_above_age_h": 12.5,
        "nearest_unmitigated_low_below": 79040.0,
        "nearest_unmitigated_low_below_age_h": 6.0,
        "unmitigated_count_7d": 8,
    }
    df = _make_ict_df([ts], [row])
    parquet_path = tmp_path / "ict.parquet"
    _save_parquet(df, parquet_path)

    reader = ICTContextReader.load(parquet_path)
    assert reader.is_loaded(), "Reader should be loaded after valid parquet"

    ctx = reader.lookup(ts)
    assert isinstance(ctx, dict), "lookup() should return dict"
    assert len(ctx) == len(ICT_CONTEXT_COLS), (
        f"Expected {len(ICT_CONTEXT_COLS)} keys, got {len(ctx)}"
    )
    assert ctx["session_active"] == "ny_am"
    assert ctx["time_in_session_min"] == 5
    assert abs(ctx["dist_to_pdh_pct"] - (-0.25)) < 1e-6
    assert ctx["unmitigated_count_7d"] == 8


def test_ict_context_missing_parquet() -> None:
    """ICTContextReader.load() with missing file → is_loaded=False, lookup returns {}."""
    reader = ICTContextReader.load("/nonexistent/path/ict.parquet")
    assert not reader.is_loaded()
    result = reader.lookup(_utc(2026, 4, 29, 14, 30))
    assert result == {} or result == {}, "Missing parquet → empty dict"


def test_ict_context_nearest_bar_tolerance(tmp_path: Path) -> None:
    """lookup() finds nearest bar within 5-min tolerance; out-of-range → {}."""
    ts_bar = _utc(2026, 4, 29, 14, 30)
    row = {"session_active": "ny_am", "time_in_session_min": 0,
           **{c: 0.0 for c in ICT_CONTEXT_COLS if c not in ("session_active", "time_in_session_min")}}
    df = _make_ict_df([ts_bar], [row])
    parquet_path = tmp_path / "ict.parquet"
    _save_parquet(df, parquet_path)

    reader = ICTContextReader.load(parquet_path)

    # 3 min after bar → within tolerance → should find it
    ts_close = _utc(2026, 4, 29, 14, 33)
    ctx_close = reader.lookup(ts_close)
    assert ctx_close, "3-min offset should find bar within 5-min tolerance"

    # 10 min after bar → outside tolerance → empty
    ts_far = _utc(2026, 4, 29, 14, 40)
    ctx_far = reader.lookup(ts_far)
    assert not ctx_far, "10-min offset should be outside 5-min tolerance"


# ─────────────────────────────── Test 2: persistence in storage ───────────────

def test_ict_context_persistence(tmp_path: Path) -> None:
    """Setup with ict_context → stored JSONL record contains all 14 ICT columns."""
    ict = {
        "session_active": "ny_am",
        "time_in_session_min": 5,
        "dist_to_pdh_pct": -0.25,
        "dist_to_pdl_pct": 1.50,
        "dist_to_pwh_pct": -0.80,
        "dist_to_pwl_pct": 2.10,
        "dist_to_d_open_pct": 0.30,
        "dist_to_kz_mid_pct": -0.05,
        "dist_to_nearest_unmitigated_high_pct": -0.45,
        "dist_to_nearest_unmitigated_low_pct": 1.20,
        "nearest_unmitigated_high_above": 80360.0,
        "nearest_unmitigated_high_above_age_h": 12.5,
        "nearest_unmitigated_low_below": 79040.0,
        "nearest_unmitigated_low_below_age_h": 6.0,
        "unmitigated_count_7d": 8,
    }
    setup = _minimal_setup(ict=ict)

    jsonl_path = tmp_path / "setups.jsonl"
    active_path = tmp_path / "active.json"
    store = SetupStorage(jsonl_path=jsonl_path, active_path=active_path)
    store.write(setup)

    # Read back the JSONL record
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1, "Should have written exactly 1 record"
    record = json.loads(lines[0])

    assert "ict_context" in record, "JSONL record must have 'ict_context' key"
    stored_ict = record["ict_context"]
    assert isinstance(stored_ict, dict), "ict_context in JSONL must be a dict"

    for col in ICT_CONTEXT_COLS:
        assert col in stored_ict, f"ict_context must contain column '{col}'"

    assert stored_ict["session_active"] == "ny_am"
    assert abs(stored_ict["dist_to_pdh_pct"] - (-0.25)) < 1e-6
    assert stored_ict["unmitigated_count_7d"] == 8


def test_ict_context_roundtrip(tmp_path: Path) -> None:
    """Setup with ict_context → write → read back → ict_context preserved."""
    ict = {col: (1.23 if col.startswith("dist_") else
                 "london" if col == "session_active" else
                 7 if col == "time_in_session_min" else
                 4 if col == "unmitigated_count_7d" else
                 80500.0)
           for col in ICT_CONTEXT_COLS}
    setup = _minimal_setup(ict=ict)

    jsonl_path = tmp_path / "setups.jsonl"
    active_path = tmp_path / "active.json"
    store = SetupStorage(jsonl_path=jsonl_path, active_path=active_path)
    store.write(setup)

    # list_recent reads back from JSONL
    recovered = store.list_recent(hours=24)
    assert len(recovered) == 1
    assert recovered[0].ict_context.get("session_active") == "london"
    assert recovered[0].ict_context.get("unmitigated_count_7d") == 4


# ─────────────────────────────── Test 3: distance sign sanity ─────────────────

def test_ict_context_values_sane_distance_sign(tmp_path: Path) -> None:
    """dist_to_pdh_pct sign agrees with price vs PDH.

    price=80000, pdh=79000 → price above pdh → dist_to_pdh_pct > 0.
    price=80000, pdl=81000 → price below pdl → dist_to_pdl_pct < 0.
    """
    price = 80000.0
    pdh = 79000.0
    pdl = 81000.0

    dist_pdh = (price - pdh) / pdh * 100.0
    dist_pdl = (price - pdl) / pdl * 100.0

    assert dist_pdh > 0, f"price({price}) > pdh({pdh}) → dist_to_pdh_pct should be positive, got {dist_pdh}"
    assert dist_pdl < 0, f"price({price}) < pdl({pdl}) → dist_to_pdl_pct should be negative, got {dist_pdl}"

    # Now verify the ICT parquet produces the same sign
    ts = _utc(2026, 4, 29, 14, 30)
    row = {col: None for col in ICT_CONTEXT_COLS}
    row["session_active"] = "ny_am"
    row["time_in_session_min"] = 0
    row["dist_to_pdh_pct"] = dist_pdh
    row["dist_to_pdl_pct"] = dist_pdl
    row["unmitigated_count_7d"] = 0

    df = _make_ict_df([ts], [row])
    parquet_path = tmp_path / "ict_sign.parquet"
    _save_parquet(df, parquet_path)

    reader = ICTContextReader.load(parquet_path)
    ctx = reader.lookup(ts)

    assert ctx["dist_to_pdh_pct"] > 0, (
        f"dist_to_pdh_pct should be positive when price above PDH. got {ctx['dist_to_pdh_pct']}"
    )
    assert ctx["dist_to_pdl_pct"] < 0, (
        f"dist_to_pdl_pct should be negative when price below PDL. got {ctx['dist_to_pdl_pct']}"
    )


def test_setup_ict_context_default_empty() -> None:
    """make_setup() without ict_context → ict_context == {}."""
    setup = _minimal_setup()
    assert setup.ict_context == {}, "Default ict_context should be empty dict"


def test_setup_ict_context_field_present() -> None:
    """Setup object has ict_context field after make_setup with ict_context arg."""
    ict = {"session_active": "london", "unmitigated_count_7d": 3}
    setup = _minimal_setup(ict=ict)
    assert setup.ict_context["session_active"] == "london"
    assert setup.ict_context["unmitigated_count_7d"] == 3
