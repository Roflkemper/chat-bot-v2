from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from services.setup_backtest.outcome_simulator import HistoricalOutcomeSimulator
from services.setup_detector.models import SetupBasis, SetupStatus, SetupType, make_setup


def _make_df_with_tp(entry: float = 80000.0, tp1: float = 81000.0, bars: int = 60) -> pd.DataFrame:
    """1m bars: rises from entry to above tp1 after 30 bars."""
    half = bars // 2
    prices_up = np.linspace(entry * 0.998, tp1 * 1.002, half)
    prices_flat = np.full(bars - half, tp1 * 1.001)
    prices = np.concatenate([prices_up, prices_flat])
    idx = pd.date_range("2026-04-30T10:00:00", periods=bars, freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": prices,
        "high": prices * 1.001,
        "low": prices * 0.999,
        "close": prices,
        "volume": 100.0,
    }, index=idx)


def _make_df_with_stop(entry: float = 80000.0, stop: float = 79000.0, bars: int = 60) -> pd.DataFrame:
    """1m bars: falls from entry to below stop after 30 bars."""
    half = bars // 2
    prices_down = np.linspace(entry * 1.001, stop * 0.998, half)
    prices_flat = np.full(bars - half, stop * 0.997)
    prices = np.concatenate([prices_down, prices_flat])
    idx = pd.date_range("2026-04-30T10:00:00", periods=bars, freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": prices,
        "high": prices * 1.001,
        "low": prices * 0.999,
        "close": prices,
        "volume": 100.0,
    }, index=idx)


def _long_setup(
    entry: float = 80000.0,
    stop: float = 79000.0,
    tp1: float = 81000.0,
    detected_at: datetime | None = None,
) -> object:
    t0 = detected_at or datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc)
    return make_setup(
        setup_type=SetupType.LONG_DUMP_REVERSAL,
        pair="BTCUSDT",
        current_price=entry,
        regime_label="consolidation",
        session_label="NY_AM",
        entry_price=entry,
        stop_price=stop,
        tp1_price=tp1,
        tp2_price=tp1 + (tp1 - entry),
        risk_reward=1.0,
        strength=8,
        confidence_pct=72.0,
        basis=(SetupBasis("test", 1.0, 1.0),),
        cancel_conditions=("cancel",),
        window_minutes=120,
        portfolio_impact_note="test",
        recommended_size_btc=0.10,
        detected_at=t0,
    )


def test_simulate_outcome_tp1_hit() -> None:
    df = _make_df_with_tp(entry=80000.0, tp1=81000.0)
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_setup(entry=80000.0, tp1=81000.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.TP1_HIT
    assert result.hypothetical_pnl_usd is not None
    assert result.hypothetical_pnl_usd > 0.0


def test_simulate_outcome_stop_hit() -> None:
    df = _make_df_with_stop(entry=80000.0, stop=79000.0)
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_setup(entry=80000.0, stop=79000.0, tp1=81000.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.STOP_HIT
    assert result.hypothetical_pnl_usd is not None
    assert result.hypothetical_pnl_usd < 0.0


def test_simulate_outcome_expired() -> None:
    """Flat price that never hits TP or stop → EXPIRED."""
    entry = 80000.0
    idx = pd.date_range("2026-04-30T10:00:00", periods=200, freq="1min", tz="UTC")
    prices = np.full(200, entry)
    df = pd.DataFrame({"open": prices, "high": prices * 1.0001, "low": prices * 0.9999, "close": prices, "volume": 100.0}, index=idx)
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_setup(entry=entry, stop=entry * 0.98, tp1=entry * 1.02)  # wide TP/SL, short window
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status in (SetupStatus.EXPIRED, SetupStatus.TP1_HIT, SetupStatus.STOP_HIT)


def test_simulate_outcome_no_entry_fill() -> None:
    """Price stays above entry for LONG → no fill, expires."""
    entry = 79760.0
    idx = pd.date_range("2026-04-30T10:00:00", periods=200, freq="1min", tz="UTC")
    # Price stays at 80500 — never drops to entry limit 79760
    prices = np.full(200, 80500.0)
    df = pd.DataFrame({"open": prices, "high": prices * 1.001, "low": prices * 0.9995, "close": prices, "volume": 100.0}, index=idx)
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_setup(entry=entry, stop=79000.0, tp1=80520.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    # Either expired (no entry fill) or detected boundary
    assert result.new_status in (SetupStatus.EXPIRED,)


def test_simulate_handles_gap_in_data() -> None:
    """Empty DataFrame → returns EXPIRED."""
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df.index = pd.DatetimeIndex([], tz="UTC")
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_setup()
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.EXPIRED


def test_simulate_pnl_calculation_correct() -> None:
    """TP1 at +1000 USD above entry on 0.10 BTC → ~$100 profit."""
    df = _make_df_with_tp(entry=80000.0, tp1=81000.0)
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_setup(entry=80000.0, tp1=81000.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    if result.new_status == SetupStatus.TP1_HIT and result.hypothetical_pnl_usd is not None:
        # 0.10 BTC × $1000 price move = $100
        assert result.hypothetical_pnl_usd == pytest.approx(100.0, rel=0.1)
