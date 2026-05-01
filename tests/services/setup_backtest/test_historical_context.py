from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from services.setup_backtest.historical_context import HistoricalContextBuilder, _session_at


def test_session_at_uses_active_labels_not_only_none() -> None:
    assert _session_at(datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)) == "LONDON"
    assert _session_at(datetime(2026, 4, 1, 18, 0, tzinfo=timezone.utc)) == "NY_PM"


def test_build_context_sets_session_label(synthetic_parquet: Path) -> None:
    builder = HistoricalContextBuilder(synthetic_parquet, pair="BTCUSDT")
    ts = builder._df_1m.index[400].to_pydatetime()
    ctx = builder.build_context_at(ts)
    assert ctx is not None
    assert ctx.session_label in {"ASIA", "LONDON", "NY_AM", "NY_LUNCH", "NY_PM", "NONE"}


def test_build_context_session_not_none_during_ny_window(synthetic_parquet: Path) -> None:
    builder = HistoricalContextBuilder(synthetic_parquet, pair="BTCUSDT")
    ts = datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)
    ctx = builder.build_context_at(ts)
    assert ctx is not None
    assert ctx.session_label == "NY_AM"
