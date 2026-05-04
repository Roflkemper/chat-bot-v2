"""Tests for setup_bridge: attach setups to forecast results across regime branches."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

from services.market_forward_analysis.regime_switcher import (
    RegimeForecastSwitcher, ForecastResult,
)
from services.market_forward_analysis.setup_bridge import (
    attach_setups, detect_and_attach,
    _setup_to_context, _horizon_for_setup_type, _select_best_per_horizon,
)
from services.setup_detector.models import (
    Setup, SetupType, SetupStatus, SetupBasis, make_setup,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_setup(setup_type: SetupType, strength: int = 7, confidence_pct: float = 70.0,
                regime: str = "MARKDOWN") -> Setup:
    return make_setup(
        setup_type=setup_type, pair="BTCUSDT", current_price=67000,
        regime_label=regime, session_label="ny_pm",
        entry_price=67000.0, stop_price=66640.0, tp1_price=67540.0, tp2_price=68080.0,
        risk_reward=2.5,
        strength=strength, confidence_pct=confidence_pct,
        basis=(SetupBasis(label="rsi_oversold", value=27, weight=0.4),
               SetupBasis(label="pdl_proximity", value=0.3, weight=0.3)),
        cancel_conditions=("price < SL",),
        window_minutes=60,
        portfolio_impact_note="—",
        recommended_size_btc=0.005,
    )


def _live_bar(parquet: str) -> pd.DataFrame:
    df = pd.read_parquet(parquet)
    return df.iloc[[-1]]


@pytest.fixture
def markup_bar():
    return _live_bar("data/forecast_features/regime_splits/regime_markup.parquet")


@pytest.fixture
def markdown_bar():
    return _live_bar("data/forecast_features/regime_splits/regime_markdown.parquet")


@pytest.fixture
def range_bar():
    return _live_bar("data/forecast_features/regime_splits/regime_range.parquet")


@pytest.fixture
def empty_forecasts():
    return {
        "1h": ForecastResult("1h", "numeric",      0.55, 0.18, None, None),
        "4h": ForecastResult("4h", "numeric",      0.50, 0.10, None, None),
        "1d": ForecastResult("1d", "qualitative", "lean_down", 0.0, None, None),
    }


# ── Pure helper unit tests ────────────────────────────────────────────────────

def test_horizon_for_setup_long():
    assert _horizon_for_setup_type("long_pdl_bounce") == "1h"


def test_horizon_for_setup_short():
    assert _horizon_for_setup_type("short_rally_fade") == "1h"


def test_horizon_for_setup_grid():
    assert _horizon_for_setup_type("grid_raise_boundary") == "4h"


def test_horizon_for_setup_defensive():
    assert _horizon_for_setup_type("def_margin_low") == "1h"


def test_horizon_for_setup_unknown():
    assert _horizon_for_setup_type("totally_made_up") == "1h"  # safe default


def test_select_best_picks_highest_strength():
    weak = _make_setup(SetupType.LONG_PDL_BOUNCE, strength=6)
    strong = _make_setup(SetupType.LONG_OVERSOLD_RECLAIM, strength=8)
    best = _select_best_per_horizon([weak, strong])
    assert best["1h"].setup_type == SetupType.LONG_OVERSOLD_RECLAIM


def test_select_best_breaks_tie_on_confidence():
    a = _make_setup(SetupType.LONG_PDL_BOUNCE, strength=7, confidence_pct=60)
    b = _make_setup(SetupType.LONG_OVERSOLD_RECLAIM, strength=7, confidence_pct=80)
    best = _select_best_per_horizon([a, b])
    assert best["1h"].setup_type == SetupType.LONG_OVERSOLD_RECLAIM


def test_select_best_separates_horizons():
    long_setup = _make_setup(SetupType.LONG_PDL_BOUNCE, strength=7)
    grid_setup = _make_setup(SetupType.GRID_PAUSE_ENTRIES, strength=7)
    best = _select_best_per_horizon([long_setup, grid_setup])
    assert "1h" in best and best["1h"].setup_type == SetupType.LONG_PDL_BOUNCE
    assert "4h" in best and best["4h"].setup_type == SetupType.GRID_PAUSE_ENTRIES


def test_setup_to_context_compact():
    s = _make_setup(SetupType.SHORT_RALLY_FADE, strength=8, confidence_pct=75)
    ctx = _setup_to_context(s)
    assert ctx["direction"] == "short"
    assert ctx["strength"] == 8
    assert ctx["entry"] == 67000.0
    assert "rsi_oversold" in ctx["basis_summary"]


# ── attach_setups: 4 regime branches × hit/miss ───────────────────────────────

def test_attach_no_setups_clears_context(empty_forecasts):
    out = attach_setups(empty_forecasts, [])
    for hz in ("1h", "4h", "1d"):
        assert out[hz].setup_context is None


def test_attach_long_setup_in_markup_bar(markup_bar, empty_forecasts):
    """MARKUP-region: LONG setup → 1h gets context, 4h/1d clean."""
    s = _make_setup(SetupType.LONG_PDL_BOUNCE, strength=7, regime="MARKUP")
    out = attach_setups(empty_forecasts, [s])
    assert out["1h"].setup_context is not None
    assert out["1h"].setup_context["direction"] == "long"
    assert out["4h"].setup_context is None
    assert out["1d"].setup_context is None


def test_attach_short_setup_in_markdown_bar(markdown_bar, empty_forecasts):
    """MARKDOWN-region: SHORT setup → 1h gets context."""
    s = _make_setup(SetupType.SHORT_RALLY_FADE, strength=8, regime="MARKDOWN")
    out = attach_setups(empty_forecasts, [s])
    assert out["1h"].setup_context is not None
    assert out["1h"].setup_context["direction"] == "short"
    assert out["1h"].setup_context["strength"] == 8


def test_attach_grid_setup_in_range_bar(range_bar, empty_forecasts):
    """RANGE-region: GRID setup → 4h gets context."""
    s = _make_setup(SetupType.GRID_RAISE_BOUNDARY, strength=7, regime="RANGE")
    out = attach_setups(empty_forecasts, [s])
    assert out["1h"].setup_context is None
    assert out["4h"].setup_context is not None
    assert out["4h"].setup_context["direction"] == "grid"


def test_attach_distribution_branch_no_setup(empty_forecasts):
    """DISTRIBUTION = qualitative everywhere; no matching setups → all clean."""
    out = attach_setups(empty_forecasts, [])
    for hz in ("1h", "4h", "1d"):
        assert out[hz].setup_context is None


def test_attach_multiple_setups_picks_strongest(empty_forecasts):
    weak_long = _make_setup(SetupType.LONG_PDL_BOUNCE, strength=6)
    strong_long = _make_setup(SetupType.LONG_OVERSOLD_RECLAIM, strength=9)
    grid = _make_setup(SetupType.GRID_BOOSTER_ACTIVATE, strength=7)
    out = attach_setups(empty_forecasts, [weak_long, strong_long, grid])
    # 1h gets the stronger LONG
    assert out["1h"].setup_context["setup_type"] == "long_oversold_reclaim"
    assert out["1h"].setup_context["strength"] == 9
    # 4h gets the grid setup
    assert out["4h"].setup_context["setup_type"] == "grid_booster"


def test_attach_does_not_mutate_input(empty_forecasts):
    s = _make_setup(SetupType.SHORT_RALLY_FADE, strength=7)
    _ = attach_setups(empty_forecasts, [s])
    # original forecasts dict stays clean
    assert empty_forecasts["1h"].setup_context is None


# ── detect_and_attach end-to-end (graceful degradation) ──────────────────────

def test_detect_and_attach_with_none_ctx(empty_forecasts):
    """No detection context → all setup_context None, no exception."""
    out = detect_and_attach(empty_forecasts, detection_ctx=None)
    for hz in ("1h", "4h", "1d"):
        assert out[hz].setup_context is None


def test_detect_and_attach_with_empty_registry(empty_forecasts):
    """Empty registry → no setups → all None."""
    class _FakeCtx:
        pass
    out = detect_and_attach(empty_forecasts, detection_ctx=_FakeCtx(), detector_registry=())
    for hz in ("1h", "4h", "1d"):
        assert out[hz].setup_context is None


def test_detect_and_attach_with_failing_detector(empty_forecasts):
    """One detector raising should not break the chain."""
    def _broken(ctx):
        raise RuntimeError("boom")

    def _good(ctx):
        return _make_setup(SetupType.LONG_PDL_BOUNCE, strength=7)

    class _FakeCtx:
        pass

    out = detect_and_attach(empty_forecasts, detection_ctx=_FakeCtx(),
                            detector_registry=(_broken, _good))
    assert out["1h"].setup_context is not None
    assert out["1h"].setup_context["setup_type"] == "long_pdl_bounce"


# ── Integration: switcher → bridge ────────────────────────────────────────────

def test_full_switcher_to_bridge_chain(markdown_bar):
    """End-to-end: switcher.forecast() → attach_setups() → ForecastResult enriched."""
    sw = RegimeForecastSwitcher()
    forecasts = sw.forecast(markdown_bar, "MARKDOWN", regime_confidence=0.85, regime_stability=0.8)
    setup = _make_setup(SetupType.SHORT_RALLY_FADE, strength=8)
    enriched = attach_setups(forecasts, [setup])
    assert enriched["1h"].setup_context["direction"] == "short"
    # Other modes preserved
    assert enriched["1h"].mode == forecasts["1h"].mode
    assert enriched["1d"].mode == forecasts["1d"].mode
