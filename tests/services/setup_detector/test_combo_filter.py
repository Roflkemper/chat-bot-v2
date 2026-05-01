from __future__ import annotations

import pytest

from services.setup_detector.combo_filter import COMBO_FILTER, filter_setups, is_combo_allowed
from services.setup_detector.models import SetupBasis, SetupType, make_setup


def _setup(setup_type: SetupType, regime: str) -> object:
    return make_setup(
        setup_type=setup_type,
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label=regime,
        session_label="NY_AM",
        strength=8,
        confidence_pct=70.0,
        basis=(SetupBasis("test", 1.0, 1.0),),
        cancel_conditions=("cancel",),
        window_minutes=120,
        portfolio_impact_note="test",
        recommended_size_btc=0.05,
    )


# ── ALLOW tests ───────────────────────────────────────────────────────────────

def test_long_pdl_bounce_trend_down_allowed() -> None:
    """Profitable combo +$5,165 on year backtest → must be allowed."""
    setup = _setup(SetupType.LONG_PDL_BOUNCE, "trend_down")
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True
    assert "allowed" in reason


def test_long_dump_reversal_trend_down_allowed() -> None:
    """Profitable combo +$8,851 → allowed."""
    setup = _setup(SetupType.LONG_DUMP_REVERSAL, "trend_down")
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True


def test_short_rally_fade_trend_up_allowed() -> None:
    """Profitable combo +$2,675 → allowed."""
    setup = _setup(SetupType.SHORT_RALLY_FADE, "trend_up")
    allowed, _ = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True


# ── BLOCK tests ───────────────────────────────────────────────────────────────

def test_long_dump_reversal_consolidation_blocked() -> None:
    """Losing combo -$5,282 on year backtest → must be blocked."""
    setup = _setup(SetupType.LONG_DUMP_REVERSAL, "consolidation")
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is False
    assert "blocked_combo" in reason


def test_short_rally_fade_consolidation_blocked() -> None:
    """Losing combo -$5,493 → blocked."""
    setup = _setup(SetupType.SHORT_RALLY_FADE, "consolidation")
    allowed, _ = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is False


def test_short_rally_fade_trend_down_blocked() -> None:
    """Mismatched direction -$309 → blocked."""
    setup = _setup(SetupType.SHORT_RALLY_FADE, "trend_down")
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is False
    assert "blocked_combo" in reason


# ── Exempt types ──────────────────────────────────────────────────────────────

def test_grid_booster_always_allowed() -> None:
    """Grid actions exempted from filter regardless of regime."""
    for regime in ("trend_down", "trend_up", "consolidation", "range_wide"):
        setup = _setup(SetupType.GRID_BOOSTER_ACTIVATE, regime)
        allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
        assert allowed is True, f"grid_booster blocked in regime={regime}"
        assert reason == "grid_or_defensive"


def test_defensive_margin_always_allowed() -> None:
    """Defensive setups exempted from filter."""
    setup = _setup(SetupType.DEFENSIVE_MARGIN_LOW, "trend_down")
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True
    assert reason == "grid_or_defensive"


# ── Default behaviour ─────────────────────────────────────────────────────────

def test_unknown_combo_defaults_allowed() -> None:
    """Combo not in COMBO_FILTER → ALLOW (conservative, don't block unknown)."""
    # LONG_LIQ_MAGNET is not in COMBO_FILTER
    setup = _setup(SetupType.LONG_LIQ_MAGNET, "range_wide")
    assert (SetupType.LONG_LIQ_MAGNET, "range_wide") not in COMBO_FILTER
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True
    assert "allowed" in reason


# ── filter_setups helper ──────────────────────────────────────────────────────

def test_filter_setups_separates_correctly() -> None:
    """filter_setups partitions into (allowed, blocked) lists correctly."""
    setups = [
        _setup(SetupType.LONG_PDL_BOUNCE,    "trend_down"),    # ALLOW
        _setup(SetupType.SHORT_RALLY_FADE,   "consolidation"), # BLOCK
        _setup(SetupType.LONG_DUMP_REVERSAL, "trend_down"),    # ALLOW
        _setup(SetupType.LONG_DUMP_REVERSAL, "consolidation"), # BLOCK
        _setup(SetupType.GRID_BOOSTER_ACTIVATE, "trend_up"),   # ALLOW (exempt)
    ]
    allowed, blocked = filter_setups(setups)  # type: ignore[arg-type]
    assert len(allowed) == 3
    assert len(blocked) == 2
    assert all(s.setup_type != SetupType.SHORT_RALLY_FADE for s in allowed)
    assert all(s.setup_type in (SetupType.SHORT_RALLY_FADE, SetupType.LONG_DUMP_REVERSAL)
               for s in blocked)
