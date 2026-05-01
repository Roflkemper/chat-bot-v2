from __future__ import annotations

import pytest

from services.setup_detector.combo_filter import (
    COMBO_FILTER,
    MIN_ALLOWED_STRENGTH,
    THREE_WAY_BLOCKS,
    filter_setups,
    is_combo_allowed,
)
from services.setup_detector.models import SetupBasis, SetupType, make_setup


def _setup(
    setup_type: SetupType,
    regime: str,
    session: str = "NY_PM",
    strength: int = 9,  # default 9 = MIN_ALLOWED_STRENGTH (tests combo logic, not strength gate)
) -> object:
    return make_setup(
        setup_type=setup_type,
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label=regime,
        session_label=session,
        strength=strength,
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

# ── Strength gate tests ───────────────────────────────────────────────────────

def test_low_strength_blocked() -> None:
    """strength=8 → blocked even on profitable type×regime combo."""
    setup = _setup(SetupType.LONG_PDL_BOUNCE, "trend_down", strength=8)
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is False
    assert "low_strength" in reason
    assert str(MIN_ALLOWED_STRENGTH) in reason


def test_strength_7_blocked() -> None:
    """strength=7 → blocked (small N in backtest, not statistically reliable)."""
    setup = _setup(SetupType.LONG_DUMP_REVERSAL, "trend_down", strength=7)
    allowed, _ = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is False


def test_strength_9_passes_strength_gate() -> None:
    """strength=9 on profitable combo → allowed."""
    setup = _setup(SetupType.LONG_PDL_BOUNCE, "trend_down", strength=9)
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True
    assert "allowed" in reason


def test_grid_booster_bypass_strength_filter() -> None:
    """Grid actions exempt from strength filter even at strength=5."""
    setup = _setup(SetupType.GRID_BOOSTER_ACTIVATE, "trend_down", strength=5)
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True
    assert reason == "grid_or_defensive"


def test_defensive_bypass_strength_filter() -> None:
    """Defensive types exempt from strength filter even at strength=5."""
    setup = _setup(SetupType.DEFENSIVE_MARGIN_LOW, "consolidation", strength=5)
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True
    assert reason == "grid_or_defensive"


# ── 3-way block tests ─────────────────────────────────────────────────────────

def test_three_way_block_long_dump_trend_down_nylunch() -> None:
    """LONG_DUMP_REVERSAL × trend_down × NY_LUNCH = -$1,033 on year backtest → blocked."""
    setup = _setup(SetupType.LONG_DUMP_REVERSAL, "trend_down", session="NY_LUNCH", strength=9)
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is False
    assert "blocked_3way" in reason
    assert "NY_LUNCH" in reason


def test_three_way_block_long_dump_trend_down_nyam() -> None:
    """LONG_DUMP_REVERSAL × trend_down × NY_AM = -$886 → blocked."""
    setup = _setup(SetupType.LONG_DUMP_REVERSAL, "trend_down", session="NY_AM", strength=9)
    allowed, _ = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is False


def test_three_way_allow_long_dump_trend_down_nypm() -> None:
    """LONG_DUMP_REVERSAL × trend_down × NY_PM — NOT in THREE_WAY_BLOCKS → allowed."""
    assert (SetupType.LONG_DUMP_REVERSAL, "trend_down", "NY_PM") not in THREE_WAY_BLOCKS
    setup = _setup(SetupType.LONG_DUMP_REVERSAL, "trend_down", session="NY_PM", strength=9)
    allowed, reason = is_combo_allowed(setup)  # type: ignore[arg-type]
    assert allowed is True
    assert "allowed" in reason


# ── filter_setups helper ──────────────────────────────────────────────────────

def test_filter_setups_separates_correctly() -> None:
    """filter_setups partitions into (allowed, blocked) lists correctly."""
    setups = [
        _setup(SetupType.LONG_PDL_BOUNCE,       "trend_down",    strength=9),  # ALLOW
        _setup(SetupType.SHORT_RALLY_FADE,       "consolidation", strength=9),  # BLOCK (combo)
        _setup(SetupType.LONG_DUMP_REVERSAL,     "trend_down",    strength=9),  # ALLOW
        _setup(SetupType.LONG_DUMP_REVERSAL,     "consolidation", strength=9),  # BLOCK (combo)
        _setup(SetupType.GRID_BOOSTER_ACTIVATE,  "trend_up",      strength=9),  # ALLOW (exempt)
        _setup(SetupType.LONG_PDL_BOUNCE,        "trend_down",    strength=8),  # BLOCK (strength)
    ]
    allowed, blocked = filter_setups(setups)  # type: ignore[arg-type]
    assert len(allowed) == 3
    assert len(blocked) == 3
