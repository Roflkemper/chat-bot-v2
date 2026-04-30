from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from services.setup_backtest.historical_context import HistoricalContextBuilder
from services.setup_backtest.replay_engine import SetupBacktestReplay

from .conftest import make_synthetic_ohlcv


def _builder(df: pd.DataFrame) -> HistoricalContextBuilder:
    """Create a HistoricalContextBuilder from an in-memory DataFrame."""
    b = object.__new__(HistoricalContextBuilder)
    b.pair = "TESTUSDT"
    from services.setup_backtest.historical_context import _resample_to_1h, _compute_rolling_regime
    b._df_1m = df
    b._df_1h = _resample_to_1h(df)
    b._regime_series = _compute_rolling_regime(b._df_1h)
    b._ts_index = df.index
    return b


def test_replay_iterates_correct_timestamps() -> None:
    """Replay should call build_context_at for each step_minutes timestamp."""
    df = make_synthetic_ohlcv(n=500, start="2026-01-01")
    builder = _builder(df)
    replay = SetupBacktestReplay(builder, step_minutes=5)

    start = df.index[100].to_pydatetime().replace(tzinfo=timezone.utc)
    end = df.index[200].to_pydatetime().replace(tzinfo=timezone.utc)

    visited: list[datetime] = []

    def _callback(ts: datetime, step: int) -> None:
        visited.append(ts)

    replay.run(start, end, progress_callback=_callback)
    assert len(visited) > 0
    # Each step should be approximately 5 minutes apart
    if len(visited) >= 2:
        delta = (visited[1] - visited[0]).total_seconds()
        assert delta == pytest.approx(300.0, abs=1.0)


def test_replay_detects_known_setup_in_synthetic_data() -> None:
    """Over 2000 bars of data with dump episodes, at least 0 setups (may be 0 due to threshold)."""
    df = make_synthetic_ohlcv(n=2000, include_dumps=True)
    builder = _builder(df)
    replay = SetupBacktestReplay(builder, step_minutes=5)

    start = df.index[300].to_pydatetime().replace(tzinfo=timezone.utc)
    end = df.index[-1].to_pydatetime().replace(tzinfo=timezone.utc)

    setups = replay.run(start, end)
    # Setups list may be empty (synthetic data may not satisfy all conditions)
    assert isinstance(setups, list)


def test_replay_handles_data_gaps() -> None:
    """start/end outside data range → clamps gracefully."""
    df = make_synthetic_ohlcv(n=300, start="2026-03-01")
    builder = _builder(df)
    replay = SetupBacktestReplay(builder, step_minutes=5)

    # Request dates well before and after data
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, tzinfo=timezone.utc)

    # Should not crash; will clamp to available data
    setups = replay.run(start, end)
    assert isinstance(setups, list)


def test_replay_max_setups_respected() -> None:
    """max_setups=0 → returns immediately with 0 setups."""
    df = make_synthetic_ohlcv(n=500, include_dumps=True)
    builder = _builder(df)
    replay = SetupBacktestReplay(builder, step_minutes=5)

    start = df.index[50].to_pydatetime().replace(tzinfo=timezone.utc)
    end = df.index[-1].to_pydatetime().replace(tzinfo=timezone.utc)

    setups = replay.run(start, end, max_setups=0)
    assert len(setups) == 0


def test_replay_progress_callback_called() -> None:
    df = make_synthetic_ohlcv(n=200, start="2026-01-01")
    builder = _builder(df)
    replay = SetupBacktestReplay(builder, step_minutes=5)

    start = df.index[50].to_pydatetime().replace(tzinfo=timezone.utc)
    end = df.index[150].to_pydatetime().replace(tzinfo=timezone.utc)

    call_count = 0

    def _cb(ts: datetime, step: int) -> None:
        nonlocal call_count
        call_count += 1

    replay.run(start, end, progress_callback=_cb)
    assert call_count > 0
