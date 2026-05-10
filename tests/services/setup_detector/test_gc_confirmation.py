"""Tests for GC-confirmation gating in setup_detector loop (2026-05-10)."""
from __future__ import annotations

from datetime import datetime, timezone

from services.setup_detector.loop import (
    _GC_BOOST_PCT,
    _GC_MISALIGNED_HARD_BLOCK,
    _GC_PENALTY_PCT,
    _apply_gc_confirmation,
    _gc_alignment,
)
from services.setup_detector.models import (
    Setup,
    SetupBasis,
    SetupStatus,
    SetupType,
    make_setup,
)


def _mk(setup_type: SetupType, conf: float = 70.0) -> Setup:
    return make_setup(
        setup_type=setup_type,
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="range_wide",
        session_label="EU",
        basis=(SetupBasis(label="test", value=1.0, weight=1.0),),
        cancel_conditions=(),
        strength=8,
        confidence_pct=conf,
    )


def test_alignment_long_aligned_when_gc_downside():
    s = _mk(SetupType.LONG_PDL_BOUNCE)
    gc = {"upside_score": 0, "downside_score": 4}
    assert _gc_alignment(s, gc) == "aligned"


def test_alignment_long_misaligned_when_gc_upside():
    s = _mk(SetupType.LONG_MULTI_DIVERGENCE)
    gc = {"upside_score": 4, "downside_score": 0}
    assert _gc_alignment(s, gc) == "misaligned"


def test_alignment_short_aligned_when_gc_upside():
    s = _mk(SetupType.SHORT_RALLY_FADE)
    gc = {"upside_score": 4, "downside_score": 0}
    assert _gc_alignment(s, gc) == "aligned"


def test_alignment_short_misaligned_when_gc_downside():
    s = _mk(SetupType.SHORT_PDH_REJECTION)
    gc = {"upside_score": 0, "downside_score": 4}
    assert _gc_alignment(s, gc) == "misaligned"


def test_alignment_neutral_below_threshold():
    s = _mk(SetupType.LONG_PDL_BOUNCE)
    gc = {"upside_score": 2, "downside_score": 2}
    assert _gc_alignment(s, gc) == "neutral"


def test_apply_aligned_boosts_confidence():
    s = _mk(SetupType.LONG_PDL_BOUNCE, conf=70.0)
    gc = {"upside_score": 0, "downside_score": 4}
    result, decision = _apply_gc_confirmation(s, gc, "2026-05-10T10:00:00Z")
    assert result is not None
    assert result.confidence_pct == 70.0 + _GC_BOOST_PCT
    assert decision == "aligned"


def test_apply_aligned_capped_at_99():
    s = _mk(SetupType.LONG_PDL_BOUNCE, conf=90.0)
    gc = {"upside_score": 0, "downside_score": 4}
    result, _ = _apply_gc_confirmation(s, gc, "2026-05-10T10:00:00Z")
    assert result.confidence_pct == 99.0  # capped at 99 (90 + 15)


def test_apply_misaligned_penalty_for_normal_detector():
    # short_rally_fade is not in HARD_BLOCK, gets penalty
    assert "short_rally_fade" not in _GC_MISALIGNED_HARD_BLOCK
    s = _mk(SetupType.SHORT_RALLY_FADE, conf=70.0)
    gc = {"upside_score": 0, "downside_score": 4}
    result, decision = _apply_gc_confirmation(s, gc, "2026-05-10T10:00:00Z")
    assert result is not None
    assert result.confidence_pct == 70.0 - _GC_PENALTY_PCT
    assert decision == "misaligned-penalty"


def test_apply_misaligned_hard_block_for_noisy_detector():
    assert "long_multi_divergence" in _GC_MISALIGNED_HARD_BLOCK
    s = _mk(SetupType.LONG_MULTI_DIVERGENCE, conf=70.0)
    gc = {"upside_score": 4, "downside_score": 0}
    result, decision = _apply_gc_confirmation(s, gc, "2026-05-10T10:00:00Z")
    assert result is None  # blocked
    assert decision == "misaligned-blocked"


def test_apply_neutral_passes_through_unchanged():
    s = _mk(SetupType.LONG_PDL_BOUNCE, conf=70.0)
    gc = {"upside_score": 1, "downside_score": 2}  # both <3
    result, decision = _apply_gc_confirmation(s, gc, "2026-05-10T10:00:00Z")
    assert result is not None
    assert result.confidence_pct == 70.0  # unchanged
    assert decision == "neutral"


def test_penalty_does_not_go_below_10():
    s = _mk(SetupType.SHORT_RALLY_FADE, conf=15.0)
    gc = {"upside_score": 0, "downside_score": 4}
    result, _ = _apply_gc_confirmation(s, gc, "2026-05-10T10:00:00Z")
    assert result.confidence_pct == 10.0  # floor
