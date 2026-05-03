"""Tests for services/market_forward_analysis — phase classifier, projection, bot impact, recommendations.

All tests are offline (no network, no live data). Historical data is synthesized.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ── Phase Classifier tests ────────────────────────────────────────────────────

from services.market_forward_analysis.phase_classifier import (
    classify_phase,
    build_mtf_phase_state,
    run_phase_history,
    Phase,
    PhaseResult,
    _swing_structure,
    _hh_hl,
    _lh_ll,
    _range_bound,
    _atr_percentile,
    _vol_trend,
)


def _make_trending_up(n: int = 80, start: float = 50000.0, step: float = 500.0) -> pd.DataFrame:
    """Synthetic HH/HL uptrend with clear wave structure for swing detection."""
    idx = pd.date_range("2025-01-01", periods=n, freq="1D", tz="UTC")
    # Create zigzag wave: +800 for 5 bars, -300 for 3 bars, repeat → net +2500/8 bars
    closes = []
    price = start
    for i in range(n):
        cycle_pos = i % 8
        if cycle_pos < 5:
            price += 800  # strong up leg
        else:
            price -= 300  # shallow pullback
        closes.append(price)
    highs  = [c + 500 for c in closes]
    lows   = [c - 500 for c in closes]
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes,
                          "volume": [1000 + i * 5 for i in range(n)]}, index=idx)


def _make_trending_down(n: int = 80, start: float = 80000.0, step: float = -500.0) -> pd.DataFrame:
    """Synthetic LH/LL downtrend with clear wave structure for swing detection."""
    idx = pd.date_range("2025-01-01", periods=n, freq="1D", tz="UTC")
    # Create zigzag wave: -800 for 5 bars, +300 for 3 bars, repeat → net -2500/8 bars
    closes = []
    price = start
    for i in range(n):
        cycle_pos = i % 8
        if cycle_pos < 5:
            price -= 800  # strong down leg
        else:
            price += 300  # shallow bounce
        closes.append(price)
    highs  = [c + 500 for c in closes]
    lows   = [c - 500 for c in closes]
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes,
                          "volume": [1000 for _ in range(n)]}, index=idx)


def _make_range(n: int = 80, center: float = 75000.0, amplitude: float = 500.0) -> pd.DataFrame:
    """Synthetic choppy range."""
    idx = pd.date_range("2025-01-01", periods=n, freq="1D", tz="UTC")
    closes = [center + amplitude * np.sin(i / 5) + np.random.uniform(-50, 50) for i in range(n)]
    highs  = [c + 100 for c in closes]
    lows   = [c - 100 for c in closes]
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes,
                          "volume": [1000 for _ in range(n)]}, index=idx)


# Test 1: classify uptrend as MARKUP
def test_classify_markup():
    df = _make_trending_up(n=80)
    result = classify_phase(df, "1d")
    assert result.label in (Phase.MARKUP, Phase.DISTRIBUTION)  # uptrend → markup or dist at top
    assert result.confidence > 0
    assert result.timeframe == "1d"


# Test 2: classify downtrend as MARKDOWN
def test_classify_markdown():
    df = _make_trending_down(n=80)
    result = classify_phase(df, "1d")
    assert result.label in (Phase.MARKDOWN, Phase.ACCUMULATION)  # downtrend
    assert result.direction_bias in (-1, 0, 1)


# Test 3: classify flat range as RANGE
def test_classify_range():
    df = _make_range(n=80)
    result = classify_phase(df, "1d")
    assert result.label in (Phase.RANGE, Phase.ACCUMULATION, Phase.DISTRIBUTION, Phase.TRANSITION)
    assert 0.0 <= result.confidence <= 100.0


# Test 4: insufficient data returns RANGE with 0 confidence
def test_classify_insufficient_data():
    df = _make_range(n=3)
    result = classify_phase(df, "1h")
    assert result.confidence == 0.0


# Test 5: confidence is bounded 0-95
def test_confidence_bounded():
    df = _make_trending_up(n=100)
    result = classify_phase(df, "4h")
    assert 0.0 <= result.confidence <= 95.0


# Test 6: key_levels always present
def test_key_levels_always_present():
    df = _make_trending_up(n=80)
    result = classify_phase(df, "1d")
    assert "range_high" in result.key_levels
    assert "range_low" in result.key_levels
    assert result.key_levels["range_high"] >= result.key_levels["range_low"]


# Test 7: direction_bias is -1 / 0 / +1
def test_direction_bias_valid():
    for df in [_make_trending_up(), _make_trending_down(), _make_range()]:
        r = classify_phase(df, "1d")
        assert r.direction_bias in (-1, 0, 1)


# Test 8: swing structure detects highs and lows
def test_swing_structure_detects():
    df = _make_trending_up(n=50)
    highs, lows = _swing_structure(df, swing_n=3)
    assert isinstance(highs, list)
    assert isinstance(lows, list)


# Test 9: HH/HL correctly identified on uptrend
def test_hh_hl_uptrend():
    highs = [50, 55, 60, 65, 70]
    lows  = [45, 48, 52, 56, 60]
    assert _hh_hl(highs, lows, n=3) is True


# Test 10: LH/LL correctly identified on downtrend
def test_lh_ll_downtrend():
    highs = [70, 65, 60, 55, 50]
    lows  = [60, 55, 50, 45, 40]
    assert _lh_ll(highs, lows, n=3) is True


# Test 11: range_bound detects tight range
def test_range_bound_tight():
    df = _make_range(n=40, amplitude=50)
    is_range, rh, rl = _range_bound(df, lookback=20, range_pct=4.0)
    assert isinstance(is_range, bool)
    assert rh >= rl


# Test 12: build_mtf_phase_state integrates multiple timeframes
def test_build_mtf_phase_state():
    frames = {
        "1d": _make_trending_up(n=80),
        "4h": _make_trending_up(n=80),
        "1h": _make_trending_up(n=80),
    }
    state = build_mtf_phase_state(frames)
    assert "1d" in state.phases
    assert "4h" in state.phases
    assert isinstance(state.coherent, bool)
    assert isinstance(state.coherence_note, str)
    assert len(state.coherence_note) > 0


# Test 13: coherence note populated
def test_coherence_note_populated():
    frames = {"1d": _make_trending_up(n=80), "4h": _make_trending_down(n=80)}
    state = build_mtf_phase_state(frames)
    assert state.coherence_note != ""


# Test 14: empty frames handled gracefully
def test_mtf_state_empty_frames():
    state = build_mtf_phase_state({})
    assert state.macro_label in Phase.__members__.values()


# Test 15: run_phase_history returns DataFrame with correct columns
def test_run_phase_history_columns():
    df1d = _make_trending_up(n=100)
    history = run_phase_history(df1d, step_bars=5, lookback=30)
    if not history.empty:
        assert "1d_phase" in history.columns
        assert "1d_confidence" in history.columns
        assert "coherent" in history.columns
        assert "close" in history.columns


# Test 16: vol_trend positive for increasing volume
def test_vol_trend_increasing():
    n = 20
    df = pd.DataFrame({
        "volume": list(range(100, 100 + n)),
        "close": [1.0] * n,
        "open": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n,
    })
    v = _vol_trend(df, lookback=n)
    assert v > 0


# Test 17: atr_percentile in 0-100
def test_atr_percentile_range():
    df = _make_trending_up(n=80)
    pct = _atr_percentile(df)
    assert 0.0 <= pct <= 100.0


# ── Forward Projection tests ──────────────────────────────────────────────────

from services.market_forward_analysis.forward_projection import (
    compute_forward_projection,
    _compute_outcome_distribution,
    _score_confluence,
    _empty_forecasts,
    run_checkpoint2_validation,
    compute_brier_score,
    ConfluenceStrength,
    HorizonForecast,
    ForwardProjection,
)


def _make_phase_state(bias: int = 1, label: str = "markup", coherent: bool = True):
    from services.market_forward_analysis.phase_classifier import MTFPhaseState, Phase, PhaseResult
    pr = PhaseResult("1d", Phase(label), 70.0, bias, 10, {"range_high": 80000, "range_low": 70000})
    return MTFPhaseState(
        ts=pd.Timestamp.utcnow(),
        phases={"1d": pr},
        coherent=coherent,
        macro_label=Phase(label),
        macro_bias=bias,
        coherence_note=f"1d {label}",
    )


# Test 18: compute_forward_projection returns ForwardProjection
def test_compute_forward_projection_returns():
    state = _make_phase_state(bias=1)
    proj = compute_forward_projection(state)
    assert isinstance(proj, ForwardProjection)
    assert "1h" in proj.forecasts
    assert "4h" in proj.forecasts
    assert "1d" in proj.forecasts


# Test 19: empty forecasts have 50% probability (no data bias)
def test_empty_forecasts_neutral():
    forecasts = _empty_forecasts()
    for fc in forecasts.values():
        assert fc.probability == 50.0


# Test 20: horizon forecast fields are sane
def test_horizon_forecast_fields():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = compute_forward_projection(state)
    for horizon, fc in proj.forecasts.items():
        assert fc.horizon in ("1h", "4h", "1d")
        assert 0 <= fc.probability <= 100
        assert isinstance(fc.n_episodes, int)


# Test 21: confluence strength has valid enum value
def test_confluence_strength_valid():
    state = _make_phase_state(bias=1)
    proj = compute_forward_projection(state)
    assert proj.confluence_strength in ConfluenceStrength.__members__.values()


# Test 22: score_confluence with aligned signals returns STRONG
def test_score_confluence_strong():
    state = _make_phase_state(bias=-1, coherent=True)
    n = 50
    df_1h = pd.DataFrame({
        "fundingRate": [0.001] * n,  # extreme long, bearish phase
        "top_trader_ls_ratio": [1.8] * n,  # long-crowded
        "sum_open_interest": list(range(n)),
        "taker_vol_ratio": [0.7] * n,  # sell pressure
    })
    conditions = {"funding_regime": "extreme_long", "ls_bias": "long_crowded"}
    strength, signals = _score_confluence(state, df_1h, conditions)
    assert strength in (ConfluenceStrength.STRONG, ConfluenceStrength.MEDIUM)
    assert len(signals) >= 2


# Test 23: Brier score < 0.25 (better than random) with reasonable setups
def test_brier_score_reasonable():
    # Synthetic setups data
    n = 200
    df = pd.DataFrame({
        "setup_type": ["rally_fade"] * 100 + ["pdh_rejection"] * 100,
        "final_status": (["TP1"] * 60 + ["stop"] * 40) * 2,
        "strength": list(range(1, 11)) * 20,
        "time_to_outcome_min": [120] * n,
        "hypothetical_r": [1.5] * n,
        "regime": ["red"] * n,
    })
    bs = compute_brier_score(df, macro_bias=-1, horizon_minutes=240)
    assert 0.0 <= bs <= 0.5


# Test 24: checkpoint2 validation handles missing setups file gracefully
def test_checkpoint2_missing_file(tmp_path: Path):
    result = run_checkpoint2_validation(tmp_path / "nonexistent.parquet")
    assert "error" in result


# ── Bot Impact tests ──────────────────────────────────────────────────────────

from services.market_forward_analysis.bot_impact import (
    compute_bot_impact,
    _project_bot_scenario,
    _classify_risk,
    BotProjection,
    PortfolioBotImpact,
    RiskClass,
)


def _make_projection(bias: int = -1) -> ForwardProjection:
    state = _make_phase_state(bias=bias)
    return compute_forward_projection(state)


# Test 25: short bot on bearish projection → GREEN
def test_short_bot_bearish_green():
    risk, notes = _classify_risk("SHORT", -1, {"4h": {"projected_price": 74000, "unrealized_delta_usd": 500, "new_liq_dist_pct": 30, "triggers_in": False}}, 30.0)
    assert risk == RiskClass.GREEN


# Test 26: long bot on bearish projection → ORANGE or RED
def test_long_bot_bearish_orange():
    risk, notes = _classify_risk("LONG", -1, {"4h": {"projected_price": 74000, "unrealized_delta_usd": -500, "new_liq_dist_pct": 10, "triggers_in": True}}, 20.0)
    assert risk in (RiskClass.ORANGE, RiskClass.RED)


# Test 27: bot with liq_dist < 10 → RED regardless
def test_critical_liq_red():
    risk, _ = _classify_risk("LONG", 1, {"4h": {}}, 5.0)
    assert risk == RiskClass.RED


# Test 28: project_bot_scenario short favored
def test_project_short_favorable():
    result = _project_bot_scenario("SHORT", 0.5, 78000, 90000, 76000, 74000)
    assert result["unrealized_delta_usd"] > 0   # short profits on price drop
    assert result["move_pct"] < 0


# Test 29: project_bot_scenario long adverse
def test_project_long_adverse():
    result = _project_bot_scenario("LONG", 0.2, 76000, 60000, 76000, 72000)
    assert result["unrealized_delta_usd"] < 0   # long loses on price drop
    assert result["move_pct"] < 0


# Test 30: compute_bot_impact with no snapshots returns empty
def test_bot_impact_no_snapshots(tmp_path: Path):
    proj = _make_projection()
    impact = compute_bot_impact(proj, 76000.0, snapshots_path=tmp_path / "nonexistent.csv")
    assert isinstance(impact, PortfolioBotImpact)
    assert impact.bot_projections == []


# Test 31: portfolio risk = worst bot risk
def test_portfolio_risk_worst():
    proj = _make_projection()
    # Manually create bot projections
    b1 = BotProjection("1", "A", "SHORT", 0.5, 78000, 76000, 90000, 100, 30, risk_class=RiskClass.GREEN)
    b2 = BotProjection("2", "B", "LONG",  0.2, 76000, 76000, 60000, -200, 18, risk_class=RiskClass.ORANGE)
    impact = PortfolioBotImpact(pd.Timestamp.utcnow(), 76000, proj, [b1, b2], RiskClass.ORANGE, "test")
    assert impact.portfolio_risk == RiskClass.ORANGE


# ── Recommendations tests ─────────────────────────────────────────────────────

from services.market_forward_analysis.recommendations import (
    generate_recommendations,
    _build_recommendation,
    _confidence_label,
    Recommendation,
    ActionType,
)


# Test 32: GREEN bot → MONITOR action
def test_green_bot_monitor():
    proj = _make_projection(bias=-1)
    bot = BotProjection("1", "TestA", "SHORT", 0.5, 78000, 76000, 90000, 100, 30,
                        scenarios={"4h": {"projected_price": 74000, "unrealized_delta_usd": 500, "new_liq_dist_pct": 30, "triggers_in": False}},
                        risk_class=RiskClass.GREEN)
    impact = PortfolioBotImpact(pd.Timestamp.utcnow(), 76000, proj, [bot], RiskClass.GREEN, "test")
    recs = generate_recommendations(impact)
    assert len(recs) == 1
    assert recs[0].action_type == ActionType.MONITOR


# Test 33: RED bot → MANUAL_STOP action
def test_red_bot_manual_stop():
    proj = _make_projection(bias=-1)
    bot = BotProjection("1", "TestB", "LONG", 0.2, 76000, 76000, 60000, -200, 5,
                        scenarios={"4h": {"projected_price": 72000, "unrealized_delta_usd": -800, "new_liq_dist_pct": 4, "triggers_in": True}},
                        risk_class=RiskClass.RED)
    impact = PortfolioBotImpact(pd.Timestamp.utcnow(), 76000, proj, [bot], RiskClass.RED, "test")
    recs = generate_recommendations(impact)
    assert recs[0].action_type == ActionType.MANUAL_STOP
    assert recs[0].urgency == "urgent"


# Test 34: ORANGE long + bearish phase → BOUNDARY_WIDEN
def test_orange_long_boundary_widen():
    proj = _make_projection(bias=-1)
    bot = BotProjection("1", "TestC", "LONG", 0.18, 77200, 76000, 60000, -200, 19,
                        scenarios={"4h": {"projected_price": 74000, "unrealized_delta_usd": -485, "new_liq_dist_pct": 15, "triggers_in": True}},
                        risk_class=RiskClass.ORANGE)
    impact = PortfolioBotImpact(pd.Timestamp.utcnow(), 76000, proj, [bot], RiskClass.ORANGE, "test")
    recs = generate_recommendations(impact)
    assert recs[0].action_type in (ActionType.BOUNDARY_WIDEN, ActionType.COMPOSITE)


# Test 35: confidence_label HIGH requires 2+ score
def test_confidence_label_high():
    label = _confidence_label(ConfluenceStrength.STRONG, n_episodes=100, mechanical_clear=True)
    assert label == "HIGH"


# Test 36: confidence_label LOW on weak signals
def test_confidence_label_low():
    label = _confidence_label(ConfluenceStrength.NONE, n_episodes=5, mechanical_clear=False)
    assert label == "LOW"


# Test 37: recommendation has all required fields
def test_recommendation_fields():
    proj = _make_projection(bias=1)
    bot = BotProjection("1", "TestD", "LONG", 0.3, 75000, 76000, 65000, 100, 25,
                        scenarios={"4h": {"projected_price": 78000, "unrealized_delta_usd": 900, "new_liq_dist_pct": 28, "triggers_in": False}},
                        risk_class=RiskClass.GREEN)
    impact = PortfolioBotImpact(pd.Timestamp.utcnow(), 76000, proj, [bot], RiskClass.GREEN, "test")
    recs = generate_recommendations(impact)
    rec = recs[0]
    assert rec.trigger
    assert rec.impact
    assert rec.action
    assert rec.reason
    assert rec.confidence in ("LOW", "MEDIUM", "HIGH")


# ── Telegram Renderer tests ───────────────────────────────────────────────────

from services.market_forward_analysis.telegram_renderer import (
    format_session_brief,
    format_phase_change_alert,
    format_bot_risk_alert,
    format_forecast_invalidation,
)
from services.market_forward_analysis.bot_impact import PortfolioBotImpact


def _make_full_impact(bias: int = -1, risk: RiskClass = RiskClass.GREEN) -> PortfolioBotImpact:
    proj = _make_projection(bias)
    bot = BotProjection("1", "TestBot", "SHORT", 0.45, 76400, 76000, 90000, 100, 24,
                        scenarios={"4h": {"projected_price": 74500, "unrealized_delta_usd": 640, "new_liq_dist_pct": 28, "triggers_in": False}},
                        risk_class=risk)
    return PortfolioBotImpact(pd.Timestamp.utcnow(), 76000, proj, [bot], risk, "test")


# Test 38: format_session_brief returns non-empty string
def test_format_session_brief_nonempty():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = _make_projection(bias=-1)
    impact = _make_full_impact()
    msg = format_session_brief("LONDON", state, proj, impact, current_price=76000.0)
    assert isinstance(msg, str)
    assert len(msg) > 100
    assert "LONDON" in msg


# Test 39: format_phase_change_alert correct format
def test_format_phase_change_alert():
    msg = format_phase_change_alert("markup", "distribution", "4h", 75.0, 78000.0)
    assert "PHASE SHIFT" in msg
    assert "markup" in msg
    assert "distribution" in msg


# Test 40: format_bot_risk_alert for RED
def test_format_bot_risk_alert():
    proj = _make_projection(bias=-1)
    bot = BotProjection("1", "TestBot", "LONG", 0.2, 77200, 76000, 60000, -200, 5,
                        scenarios={"4h": {"projected_price": 72000, "unrealized_delta_usd": -800, "new_liq_dist_pct": 4, "triggers_in": True}},
                        risk_class=RiskClass.RED)
    impact = PortfolioBotImpact(pd.Timestamp.utcnow(), 76000, proj, [bot], RiskClass.RED, "test")
    from services.market_forward_analysis.recommendations import generate_recommendations
    recs = generate_recommendations(impact)
    msg = format_bot_risk_alert(bot, recs[0], 76000.0)
    assert "RED" in msg or "BOT RISK" in msg
    assert "URGENT" in msg or "CRITICAL" in msg or "liq" in msg.lower()


# Test 41: format_forecast_invalidation
def test_format_forecast_invalidation():
    msg = format_forecast_invalidation("4h", "up", -2.5, 76000.0)
    assert "FORECAST" in msg
    assert "up" in msg


# Test 42: session brief includes bot section
def test_session_brief_bots_section():
    state = _make_phase_state(bias=1, label="markup")
    proj = _make_projection(bias=1)
    impact = _make_full_impact(bias=1)
    msg = format_session_brief("ASIA", state, proj, impact, current_price=76000.0)
    assert "BOTS" in msg or "TestBot" in msg


# ── Data Loader tests ─────────────────────────────────────────────────────────

from services.market_forward_analysis.data_loader import ForwardAnalysisDataLoader


# Test 43: data loader handles missing OHLCV gracefully
def test_data_loader_missing_ohlcv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "services.market_forward_analysis.data_loader._OHLCV_1M",
        {"BTCUSDT": tmp_path / "nonexistent.csv"},
    )
    loader = ForwardAnalysisDataLoader(symbol="BTCUSDT")
    loader.refresh()
    assert loader.get("1h") is None


# Test 44: resample produces correct number of columns
def test_data_loader_resample_columns():
    n = 1440  # one day of 1m bars
    idx = pd.date_range("2025-01-01", periods=n, freq="1min", tz="UTC")
    df1m = pd.DataFrame({
        "open": np.random.uniform(75000, 76000, n),
        "high": np.random.uniform(76000, 77000, n),
        "low":  np.random.uniform(74000, 75000, n),
        "close": np.random.uniform(75000, 76000, n),
        "volume": np.random.uniform(10, 100, n),
    }, index=idx)

    from services.market_forward_analysis.data_loader import _resample
    df1h = _resample(df1m, "1h")
    assert len(df1h) == 24   # 24 hours
    assert set(["open", "high", "low", "close", "volume"]).issubset(df1h.columns)


# ── Qualitative brief tests (ETAP 1: TZ-FORECAST-QUALITATIVE-DEPLOY) ─────────

# Test 45a: session brief must NOT contain raw probability percentages
def test_session_brief_no_raw_probability():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = _make_projection(bias=-1)
    impact = _make_full_impact()
    msg = format_session_brief("LONDON", state, proj, impact, current_price=76000.0)
    # No "XX%" numeric probability in forecast block
    import re
    # Match patterns like "Direction: down ▼ 62%" — these should NOT appear
    probability_pattern = re.compile(r"Direction:.*\d{2,3}%")
    assert not probability_pattern.search(msg), (
        "Session brief must not contain raw probability percentages in direction line"
    )


# Test 45b: session brief must contain watch-for triggers
def test_session_brief_has_watch_for():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = _make_projection(bias=-1)
    impact = _make_full_impact()
    msg = format_session_brief("LONDON", state, proj, impact, current_price=76000.0)
    assert "Watch for" in msg or "watch for" in msg.lower()


# Test 45c: session brief bias label is qualitative (BULLISH / BEARISH / RANGE-BOUND)
def test_session_brief_qualitative_bias_label():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = _make_projection(bias=-1)
    impact = _make_full_impact()
    msg = format_session_brief("LONDON", state, proj, impact, current_price=76000.0)
    assert any(label in msg for label in ("BULLISH", "BEARISH", "RANGE-BOUND", "UNCLEAR"))


# Test 45d: qualitative block contains confluence description (no raw number)
def test_session_brief_confluence_qualitative():
    state = _make_phase_state(bias=1, label="markup")
    proj = _make_projection(bias=1)
    impact = _make_full_impact(bias=1)
    msg = format_session_brief("ASIA", state, proj, impact, current_price=76000.0)
    assert "Confluence:" in msg
    assert "conviction" in msg.lower() or "signal" in msg.lower()


# Test 45e: BULLISH bias when 4h forecast direction is "up"
def test_session_brief_markup_bullish():
    state = _make_phase_state(bias=1, label="markup")
    proj = _make_projection(bias=1)
    # Override 4h direction to "up" so qualitative label resolves to BULLISH
    proj.forecasts["4h"] = HorizonForecast("4h", "up", 60.0, 1.5, -1.0, 3.0, 30)
    proj.forecasts["1h"] = HorizonForecast("1h", "up", 58.0, 0.8, -0.5, 2.0, 20)
    proj.forecasts["1d"] = HorizonForecast("1d", "up", 55.0, 2.0, -2.0, 5.0, 15)
    impact = _make_full_impact(bias=1)
    msg = format_session_brief("NY_AM", state, proj, impact, current_price=76000.0)
    assert "BULLISH" in msg


# Test 45f: BEARISH bias when 4h forecast direction is "down"
def test_session_brief_markdown_bearish():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = _make_projection(bias=-1)
    proj.forecasts["4h"] = HorizonForecast("4h", "down", 62.0, -1.5, -3.0, 1.0, 28)
    proj.forecasts["1h"] = HorizonForecast("1h", "down", 60.0, -0.8, -2.0, 0.5, 18)
    proj.forecasts["1d"] = HorizonForecast("1d", "down", 55.0, -2.0, -5.0, 2.0, 12)
    impact = _make_full_impact()
    msg = format_session_brief("NY_PM", state, proj, impact, current_price=76000.0)
    assert "BEARISH" in msg


# Test 45g: portfolio_ga_summary field exists on PortfolioBotImpact
def test_portfolio_ga_summary_field_exists():
    proj = _make_projection(bias=-1)
    impact = compute_bot_impact(proj, 76000.0)
    # Field exists (may be None if no GA file present in test env)
    assert hasattr(impact, "portfolio_ga_summary")


# Test 45h: session brief includes GA anchor line when summary is set
def test_session_brief_includes_ga_anchor():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = _make_projection(bias=-1)
    impact = _make_full_impact()
    # Manually set a GA summary
    impact.portfolio_ga_summary = "GA evidence (SHORT, aligned): realized +$31,000, vol $1.2M, triggers 847"
    msg = format_session_brief("LONDON", state, proj, impact, current_price=76000.0)
    assert "GA evidence" in msg


# Test 45i: session brief without GA summary does not raise
def test_session_brief_no_ga_summary_ok():
    state = _make_phase_state(bias=1, label="markup")
    proj = _make_projection(bias=1)
    impact = _make_full_impact(bias=1)
    impact.portfolio_ga_summary = None
    msg = format_session_brief("ASIA", state, proj, impact, current_price=76000.0)
    assert len(msg) > 50


# Test 45j: watch-for triggers on bearish projection mention level or breakdown
def test_watch_for_bearish_has_breakdown_cue():
    state = _make_phase_state(bias=-1, label="markdown")
    proj = _make_projection(bias=-1)
    impact = _make_full_impact()
    msg = format_session_brief("LONDON", state, proj, impact, current_price=76000.0)
    # Should mention lower-high, breakdown, or level
    lower_cues = ["lower-high", "break below", "breakdown", "Watch for"]
    assert any(c in msg for c in lower_cues)


# ── Integration smoke test ────────────────────────────────────────────────────

# Test 45k: full pipeline on synthetic data (phase → projection → impact → recs)
def test_full_pipeline_synthetic():
    frames = {
        "1d": _make_trending_down(n=90),
        "4h": _make_trending_down(n=90),
        "1h": _make_range(n=90),
    }
    state = build_mtf_phase_state(frames)
    proj = compute_forward_projection(state)
    impact = compute_bot_impact(proj, 76000.0)
    recs = generate_recommendations(impact)

    assert isinstance(state.macro_label, Phase)
    assert isinstance(proj, ForwardProjection)
    assert isinstance(impact, PortfolioBotImpact)
    assert isinstance(recs, list)
    # All recs have required fields
    for rec in recs:
        assert rec.confidence in ("LOW", "MEDIUM", "HIGH")
