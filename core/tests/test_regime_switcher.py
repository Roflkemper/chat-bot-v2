"""Tests for RegimeForecastSwitcher: routing, hysteresis, gating, end-to-end."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.market_forward_analysis.regime_switcher import (
    RegimeForecastSwitcher,
    ForecastResult,
    _DELIVERY_MATRIX,
    _HYSTERESIS_BARS,
    _REGIME_CONF_THRESHOLD,
    _STABILITY_THRESHOLD,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _live_bar(parquet: str) -> pd.DataFrame:
    """Load last row from a live regime split parquet."""
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


# ── Routing per validated matrix ──────────────────────────────────────────────

def test_markup_routing(markup_bar):
    sw = RegimeForecastSwitcher()
    res = sw.forecast(markup_bar, "MARKUP", regime_confidence=1.0, regime_stability=0.9)
    assert res["1h"].mode == "qualitative"   # 0.273 above gate
    assert res["4h"].mode == "numeric"
    assert res["1d"].mode == "numeric"       # gated, stability 0.9 > 0.7


def test_markup_1d_gating_qualitative_on_unstable(markup_bar):
    sw = RegimeForecastSwitcher()
    res = sw.forecast(markup_bar, "MARKUP", regime_confidence=1.0, regime_stability=0.5)
    assert res["1d"].mode == "qualitative"
    assert res["1d"].caveat is not None
    assert "transition risk" in res["1d"].caveat


def test_markdown_routing(markdown_bar):
    sw = RegimeForecastSwitcher()
    res = sw.forecast(markdown_bar, "MARKDOWN", regime_confidence=1.0, regime_stability=1.0)
    assert res["1h"].mode == "numeric"       # GREEN cell
    assert res["4h"].mode == "numeric"
    assert res["1d"].mode == "qualitative"   # variance 0.197 → a priori qualitative


def test_range_routing_all_numeric(range_bar):
    sw = RegimeForecastSwitcher()
    res = sw.forecast(range_bar, "RANGE", regime_confidence=1.0, regime_stability=1.0)
    for hz in ("1h", "4h", "1d"):
        assert res[hz].mode == "numeric"


def test_distribution_all_qualitative(range_bar):
    sw = RegimeForecastSwitcher()
    res = sw.forecast(range_bar, "DISTRIBUTION", regime_confidence=1.0, regime_stability=1.0)
    for hz in ("1h", "4h", "1d"):
        assert res[hz].mode == "qualitative"


# ── Numeric outputs are valid probabilities ──────────────────────────────────

def test_numeric_outputs_valid_prob(range_bar):
    sw = RegimeForecastSwitcher()
    res = sw.forecast(range_bar, "RANGE", regime_confidence=1.0, regime_stability=1.0)
    for hz in ("1h", "4h", "1d"):
        v = res[hz].value
        assert isinstance(v, float)
        assert 0.0 <= v <= 1.0


def test_qualitative_returns_label(markup_bar):
    sw = RegimeForecastSwitcher()
    res = sw.forecast(markup_bar, "MARKUP", regime_confidence=1.0, regime_stability=0.9)
    assert isinstance(res["1h"].value, str)
    assert "lean" in res["1h"].value


# ── Hysteresis ────────────────────────────────────────────────────────────────

def test_hysteresis_no_thrash_on_low_confidence(range_bar):
    sw = RegimeForecastSwitcher()
    sw.forecast(range_bar, "RANGE", regime_confidence=1.0)
    # Now feed a different regime with low confidence — should stay in RANGE
    res = sw.forecast(range_bar, "MARKDOWN", regime_confidence=0.4)
    # Effective regime is still RANGE, so 1d is numeric (RANGE-1d), not qualitative (MARKDOWN-1d)
    assert res["1d"].mode == "numeric"
    assert sw.state.last_regime == "RANGE"


def test_hysteresis_switch_after_n_bars(range_bar):
    sw = RegimeForecastSwitcher()
    sw.forecast(range_bar, "RANGE", regime_confidence=1.0)
    # Feed N-1 bars of MARKDOWN with high confidence — still in RANGE
    for _ in range(_HYSTERESIS_BARS - 1):
        sw.forecast(range_bar, "MARKDOWN", regime_confidence=0.9)
    assert sw.state.last_regime == "RANGE"
    # One more bar — promotes
    sw.forecast(range_bar, "MARKDOWN", regime_confidence=0.9)
    assert sw.state.last_regime == "MARKDOWN"


def test_hysteresis_resets_on_return(range_bar):
    sw = RegimeForecastSwitcher()
    sw.forecast(range_bar, "RANGE", regime_confidence=1.0)
    # Feed a few bars of MARKDOWN candidate
    for _ in range(5):
        sw.forecast(range_bar, "MARKDOWN", regime_confidence=0.9)
    assert sw.state.candidate_bars == 5
    # Return to RANGE — candidate should clear
    sw.forecast(range_bar, "RANGE", regime_confidence=1.0)
    assert sw.state.candidate_bars == 0
    assert sw.state.candidate_regime is None


def test_first_call_direct_routing(range_bar):
    sw = RegimeForecastSwitcher()
    # Even with low confidence, first call routes directly (no history to anchor to)
    res = sw.forecast(range_bar, "MARKDOWN", regime_confidence=0.3)
    assert sw.state.last_regime == "MARKDOWN"


# ── Gating validation on identified contamination zones ──────────────────────

def test_gating_qualitative_fallback_unstable_zone(markup_bar):
    """MARKUP-1d should fall back to qualitative when regime_stability < 0.70.

    This simulates the 2026-01-05 to 2026-02-25 contamination zone where W2 Brier
    spiked to 0.2943 with 65% DOWN outcomes (regime fade).
    """
    sw = RegimeForecastSwitcher()
    # Stable: numeric expected
    res_stable = sw.forecast(markup_bar, "MARKUP", regime_confidence=1.0, regime_stability=0.9)
    assert res_stable["1d"].mode == "numeric"
    # Unstable (transition zone): qualitative expected
    sw.reset()
    res_unstable = sw.forecast(markup_bar, "MARKUP", regime_confidence=1.0, regime_stability=0.5)
    assert res_unstable["1d"].mode == "qualitative"


# ── End-to-end live test ──────────────────────────────────────────────────────

@pytest.mark.skipif(
    not Path("data/forecast_features/regime_splits/regime_markdown.parquet").exists(),
    reason="Live MARKDOWN parquet not present",
)
def test_end_to_end_live_bar(markdown_bar):
    """Feed a real MARKDOWN bar and verify all 3 horizons return valid forecasts."""
    sw = RegimeForecastSwitcher()
    res = sw.forecast(markdown_bar, "MARKDOWN", regime_confidence=0.85, regime_stability=0.8)
    assert set(res.keys()) == {"1h", "4h", "1d"}
    for hz, fr in res.items():
        assert isinstance(fr, ForecastResult)
        assert fr.mode in {"numeric", "qualitative"}
        assert 0.0 <= fr.confidence <= 1.0
        if fr.mode == "numeric":
            assert 0.0 <= fr.value <= 1.0
        else:
            assert isinstance(fr.value, str)


def test_reset_clears_state(range_bar):
    sw = RegimeForecastSwitcher()
    sw.forecast(range_bar, "RANGE", regime_confidence=1.0)
    sw.reset()
    assert sw.state.last_regime is None
    assert sw.state.bars_in_current_regime == 0
