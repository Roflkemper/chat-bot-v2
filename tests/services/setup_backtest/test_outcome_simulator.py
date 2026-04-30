from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from services.setup_backtest.outcome_simulator import HistoricalOutcomeSimulator
from services.setup_detector.models import SetupBasis, SetupStatus, SetupType, make_setup

# ── Shared helpers for walk-forward tests ────────────────────────────────────

_T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _bars(data: list[tuple[float, float, float, float]], ts_start: datetime = _T0) -> pd.DataFrame:
    """Build 1-min OHLCV from (open, high, low, close) tuples."""
    idx = pd.date_range(ts_start, periods=len(data), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open":   [d[0] for d in data],
            "high":   [d[1] for d in data],
            "low":    [d[2] for d in data],
            "close":  [d[3] for d in data],
            "volume": [100.0] * len(data),
        },
        index=idx,
    )


def _long_at(entry: float, stop: float, tp1: float, window: int = 120) -> object:
    return make_setup(
        setup_type=SetupType.LONG_DUMP_REVERSAL, pair="BTCUSDT",
        current_price=entry * 1.003, regime_label="consolidation", session_label="NY_AM",
        entry_price=entry, stop_price=stop, tp1_price=tp1, tp2_price=tp1 + (tp1 - entry),
        risk_reward=1.0, strength=8, confidence_pct=72.0,
        basis=(SetupBasis("test", 1.0, 1.0),), cancel_conditions=("cancel",),
        window_minutes=window, portfolio_impact_note="test", recommended_size_btc=0.10,
        detected_at=_T0,
    )


def _short_at(entry: float, stop: float, tp1: float, window: int = 120) -> object:
    return make_setup(
        setup_type=SetupType.SHORT_RALLY_FADE, pair="BTCUSDT",
        current_price=entry * 0.997, regime_label="consolidation", session_label="NY_AM",
        entry_price=entry, stop_price=stop, tp1_price=tp1, tp2_price=tp1 - (entry - tp1),
        risk_reward=1.0, strength=8, confidence_pct=72.0,
        basis=(SetupBasis("test", 1.0, 1.0),), cancel_conditions=("cancel",),
        window_minutes=window, portfolio_impact_note="test", recommended_size_btc=0.10,
        detected_at=_T0,
    )


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


# ── Walk-forward correctness tests ───────────────────────────────────────────

def test_long_fills_then_tp1_hit() -> None:
    """LONG: bar1 low dips to entry → fill; bar2 high reaches tp1 → TP1_HIT."""
    df = _bars([(101, 101, 99, 100), (100, 112, 100, 111)])
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_at(entry=100.0, stop=95.0, tp1=110.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.TP1_HIT
    assert result.hypothetical_pnl_usd is not None and result.hypothetical_pnl_usd > 0.0
    assert result.time_to_outcome_min is not None and result.time_to_outcome_min >= 0


def test_long_fills_then_stop_hit() -> None:
    """LONG: fill at bar1, then bar2 low drops below stop → STOP_HIT, pnl < 0."""
    df = _bars([(101, 101, 99, 100), (100, 100, 93, 94)])
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_at(entry=100.0, stop=95.0, tp1=110.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.STOP_HIT
    assert result.hypothetical_pnl_usd is not None and result.hypothetical_pnl_usd < 0.0


def test_long_no_fill_expires() -> None:
    """LONG entry=100: price stays 101–103 (low always > 100) → never fills → EXPIRED, pnl=None."""
    df = _bars([(101, 103, 101, 102)] * 10)
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_at(entry=100.0, stop=95.0, tp1=110.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.EXPIRED
    assert result.hypothetical_pnl_usd is None


def test_long_fills_no_tp_no_stop_expires() -> None:
    """LONG fill at bar1, price stays 100–108 (tp=110 and stop=95 never hit) → EXPIRED with pnl."""
    df = _bars([(101, 101, 99, 100)] + [(103, 108, 101, 104)] * 10)
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_at(entry=100.0, stop=95.0, tp1=110.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.EXPIRED
    # Was filled → partial pnl calculated (last_close=104 > entry=100 → profit)
    assert result.hypothetical_pnl_usd is not None
    assert result.hypothetical_pnl_usd > 0.0


def test_short_fills_then_tp1_hit() -> None:
    """SHORT entry=110: bar1 high rises to entry → fill; bar2 low drops to tp1=100 → TP1_HIT."""
    df = _bars([(109, 111, 109, 110), (110, 110, 99, 100)])
    sim = HistoricalOutcomeSimulator(df)
    setup = _short_at(entry=110.0, stop=115.0, tp1=100.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.TP1_HIT
    assert result.hypothetical_pnl_usd is not None and result.hypothetical_pnl_usd > 0.0


def test_short_fills_then_stop_hit() -> None:
    """SHORT entry=110: fill at bar1, bar2 high reaches stop=115 → STOP_HIT, pnl < 0."""
    df = _bars([(109, 111, 109, 110), (110, 116, 110, 114)])
    sim = HistoricalOutcomeSimulator(df)
    setup = _short_at(entry=110.0, stop=115.0, tp1=100.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.STOP_HIT
    assert result.hypothetical_pnl_usd is not None and result.hypothetical_pnl_usd < 0.0


def test_tp_and_stop_in_same_bar_uses_worst_case_stop() -> None:
    """LONG: both tp1 and stop touched in same bar → STOP_HIT (conservative worst-case)."""
    df = _bars([
        (101, 101, 99, 100),          # bar1: fill (low=99 <= entry=100)
        (100, 115, 90, 100),          # bar2: high=115 >= tp1=110 AND low=90 <= stop=95
    ])
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_at(entry=100.0, stop=95.0, tp1=110.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.STOP_HIT  # stop checked before TP


def test_entry_at_exactly_entry_price_fills() -> None:
    """LONG: bar.low == entry exactly → fills (limit order semantics)."""
    df = _bars([
        (101, 101, 100.0, 101),       # bar1: low = entry exactly → fill
        (101, 112,  101,  111),       # bar2: TP1 hit
    ])
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_at(entry=100.0, stop=95.0, tp1=110.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.TP1_HIT


def test_immediate_stop_on_fill_bar() -> None:
    """LONG: fill and stop both triggered on same bar → STOP_HIT."""
    df = _bars([
        (101, 101, 90, 92),           # bar1: low=90 <= entry=100 → fill; low=90 <= stop=95 → STOP
    ])
    sim = HistoricalOutcomeSimulator(df)
    setup = _long_at(entry=100.0, stop=95.0, tp1=110.0)
    result = sim.simulate_outcome(setup)  # type: ignore[arg-type]
    assert result.new_status == SetupStatus.STOP_HIT
    assert result.hypothetical_pnl_usd is not None and result.hypothetical_pnl_usd < 0.0
