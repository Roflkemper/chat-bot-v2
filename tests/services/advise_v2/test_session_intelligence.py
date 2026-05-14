from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.advise_v2 import SessionContext, compute_session_context, is_session_open_window


def test_compute_session_context_ny_am_window() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 14, 0, tzinfo=timezone.utc))
    assert ctx.kz_active == "NY_AM"


def test_compute_session_context_asia_window() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 1, 0, tzinfo=timezone.utc))
    assert ctx.kz_active == "ASIA"


def test_compute_session_context_none_window() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 17, 0, tzinfo=timezone.utc))
    assert ctx.kz_active == "NONE"
    assert ctx.minutes_into_session is None


def test_session_context_naive_ts_raises() -> None:
    with pytest.raises(ValueError):
        compute_session_context(datetime(2026, 4, 29, 14, 0))


def test_minutes_into_session_at_start() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 13, 30, tzinfo=timezone.utc))
    assert ctx.kz_active == "NY_AM"
    assert ctx.minutes_into_session == 0


def test_minutes_into_session_at_end() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 14, 59, tzinfo=timezone.utc))
    assert ctx.kz_active == "NY_AM"
    assert ctx.minutes_into_session == 89


def test_is_friday_close_true_friday_evening() -> None:
    ctx = compute_session_context(datetime(2026, 5, 1, 19, 5, tzinfo=timezone.utc))
    assert ctx.is_friday_close is True


def test_is_friday_close_false_friday_morning() -> None:
    ctx = compute_session_context(datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc))
    assert ctx.is_friday_close is False


def test_is_session_open_window_first_15_min() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 13, 45, tzinfo=timezone.utc))
    assert is_session_open_window(ctx, 30) is True


def test_is_session_open_window_after_threshold() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 14, 15, tzinfo=timezone.utc))
    assert is_session_open_window(ctx, 30) is False


def test_session_context_dow_sat_sun() -> None:
    sat = compute_session_context(datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc))
    sun = compute_session_context(datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc))
    assert sat.dow_ny == 7
    assert sat.is_weekend is True
    assert sun.dow_ny == 1
    assert sun.is_weekend is True


def test_session_context_round_trip_pydantic() -> None:
    ctx = compute_session_context(datetime(2026, 4, 29, 14, 0, tzinfo=timezone.utc))
    restored = SessionContext.model_validate(ctx.model_dump())
    assert restored == ctx
