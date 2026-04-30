from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.setup_detector.models import SetupBasis, SetupStatus, SetupType, make_setup, setup_side
from services.setup_detector.outcomes import ProgressResult, check_setup_progress

# Use a fixed "now" that is within the window for all tests that don't test expiry
_NOW = datetime(2026, 4, 30, 10, 5, 0, tzinfo=timezone.utc)   # 5 min after detection


def _long_setup(
    entry: float = 79760.0,
    stop: float = 79000.0,
    tp1: float = 80520.0,
    window: int = 120,
    detected_at: datetime | None = None,
) -> object:
    t0 = detected_at or datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc)
    return make_setup(
        setup_type=SetupType.LONG_DUMP_REVERSAL,
        pair="BTCUSDT",
        current_price=80000.0,
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
        cancel_conditions=("test",),
        window_minutes=window,
        portfolio_impact_note="test",
        recommended_size_btc=0.05,
        detected_at=t0,
    )


def _short_setup(entry: float = 82500.0, stop: float = 83000.0, tp1: float = 82000.0) -> object:
    return make_setup(
        setup_type=SetupType.SHORT_RALLY_FADE,
        pair="BTCUSDT",
        current_price=82000.0,
        regime_label="consolidation",
        session_label="LONDON",
        entry_price=entry,
        stop_price=stop,
        tp1_price=tp1,
        tp2_price=tp1 - (entry - tp1),
        risk_reward=1.0,
        strength=7,
        confidence_pct=65.0,
        basis=(SetupBasis("test", 1.0, 1.0),),
        cancel_conditions=("test",),
        window_minutes=120,
        portfolio_impact_note="test",
        recommended_size_btc=0.05,
    )


# ── Entry hit ─────────────────────────────────────────────────────────────────

def test_entry_hit_detected_long() -> None:
    """Price drops to entry → ENTRY_HIT."""
    setup = _long_setup(entry=79760.0)
    result = check_setup_progress(setup, current_price=79760.0, now=_NOW)  # type: ignore[arg-type]
    assert result.status_changed
    assert result.new_status == SetupStatus.ENTRY_HIT


def test_entry_hit_detected_short() -> None:
    """Price rises to entry → ENTRY_HIT for short."""
    setup = _short_setup(entry=82500.0)
    result = check_setup_progress(setup, current_price=82500.0, now=_NOW)  # type: ignore[arg-type]
    assert result.status_changed
    assert result.new_status == SetupStatus.ENTRY_HIT


def test_entry_not_hit_if_price_above() -> None:
    """For long, if price is above entry, no entry hit."""
    setup = _long_setup(entry=79760.0)
    result = check_setup_progress(setup, current_price=80500.0, now=_NOW)  # type: ignore[arg-type]
    assert not result.status_changed


# ── TP / Stop ─────────────────────────────────────────────────────────────────

def test_tp1_hit_after_entry() -> None:
    setup = _long_setup(entry=79760.0, tp1=80520.0)
    import dataclasses
    entry_setup = dataclasses.replace(setup, status=SetupStatus.ENTRY_HIT)  # type: ignore[type-var]
    result = check_setup_progress(entry_setup, current_price=80520.0, now=_NOW)  # type: ignore[arg-type]
    assert result.status_changed
    assert result.new_status == SetupStatus.TP1_HIT
    assert result.hypothetical_pnl_usd is not None


def test_stop_hit_no_tp() -> None:
    import dataclasses
    setup = _long_setup(entry=79760.0, stop=79000.0)
    entry_setup = dataclasses.replace(setup, status=SetupStatus.ENTRY_HIT)  # type: ignore[type-var]
    result = check_setup_progress(entry_setup, current_price=79000.0, now=_NOW)  # type: ignore[arg-type]
    assert result.status_changed
    assert result.new_status == SetupStatus.STOP_HIT
    assert result.hypothetical_pnl_usd is not None
    assert result.hypothetical_pnl_usd < 0.0  # loss


# ── Expiry ────────────────────────────────────────────────────────────────────

def test_expiration_without_entry() -> None:
    t0 = datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc)
    setup = _long_setup(entry=79760.0, window=120, detected_at=t0)
    future = t0 + timedelta(minutes=121)
    result = check_setup_progress(setup, current_price=81000.0, now=future)  # type: ignore[arg-type]
    assert result.status_changed
    assert result.new_status == SetupStatus.EXPIRED


def test_no_change_within_window() -> None:
    t0 = datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc)
    setup = _long_setup(entry=79760.0, window=120, detected_at=t0)
    # Price is above entry, within window
    result = check_setup_progress(setup, current_price=81000.0, now=t0 + timedelta(minutes=30))  # type: ignore[arg-type]
    assert not result.status_changed


# ── PnL calculation ───────────────────────────────────────────────────────────

def test_setup_pnl_calculation_long_positive() -> None:
    import dataclasses
    setup = _long_setup(entry=79760.0, tp1=80520.0)
    entry_setup = dataclasses.replace(setup, status=SetupStatus.ENTRY_HIT)  # type: ignore[type-var]
    result = check_setup_progress(entry_setup, current_price=80520.0, now=_NOW)  # type: ignore[arg-type]
    assert result.hypothetical_pnl_usd is not None
    assert result.hypothetical_pnl_usd > 0.0  # TP hit = profit


def test_setup_pnl_calculation_short_positive() -> None:
    import dataclasses
    setup = _short_setup(entry=82500.0, stop=83000.0, tp1=82000.0)
    entry_setup = dataclasses.replace(setup, status=SetupStatus.ENTRY_HIT)  # type: ignore[type-var]
    result = check_setup_progress(entry_setup, current_price=82000.0, now=_NOW)  # type: ignore[arg-type]
    assert result.hypothetical_pnl_usd is not None
    assert result.hypothetical_pnl_usd > 0.0  # TP hit = profit
