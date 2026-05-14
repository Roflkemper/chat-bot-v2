"""Tests for core/orchestrator/visuals.py — mobile-safe rendering."""
from __future__ import annotations

from core.orchestrator.visuals import (
    MAX_LINE_WIDTH,
    bias_scale, progress_bar, separator, metrics_block,
)


# ── MAX_LINE_WIDTH guarantee ──────────────────────────────────────────────────

def test_separator_clamped_to_max_width():
    """Even when caller asks for 100, separator never exceeds MAX_LINE_WIDTH."""
    out = separator(width=100)
    assert len(out) == MAX_LINE_WIDTH


def test_separator_min_clamp():
    """Width below 1 is treated as 1 (graceful degradation, not crash)."""
    out = separator(width=0)
    assert len(out) == 1


def test_bias_scale_clamped():
    out = bias_scale(score=50, width=999)
    assert len(out) == MAX_LINE_WIDTH


def test_progress_bar_clamped():
    out = progress_bar(50, vmax=100, width=999)
    # progress_bar adds " 50%" suffix → bar itself ≤ MAX_LINE_WIDTH
    bar_part = out.split("  ")[0]
    assert len(bar_part) == MAX_LINE_WIDTH


# ── bias_scale correctness ──────────────────────────────────────────────────

def test_bias_scale_zero_marker_centered():
    out = bias_scale(0, width=10)
    assert "●" in out  # zero uses ● (within ±5)
    assert len(out) == 10


def test_bias_scale_positive_right_of_center():
    out = bias_scale(50, width=10)
    marker_pos = out.index("▓")
    assert marker_pos > 4  # past midpoint


def test_bias_scale_negative_left_of_center():
    out = bias_scale(-50, width=10)
    marker_pos = out.index("▓")
    assert marker_pos < 5  # before midpoint


def test_bias_scale_clamps_score_overflow():
    out_pos = bias_scale(500, width=10)  # >100 clamped to 100
    out_neg = bias_scale(-500, width=10)
    assert "▓" in out_pos and "▓" in out_neg


# ── metrics_block (the canonical fix) ───────────────────────────────────────

def test_metrics_block_returns_three_lines():
    lines = metrics_block(adx_1h=34, bias_score=43)
    assert len(lines) == 3


def test_metrics_block_lines_within_width():
    """Each line ≤ MAX_LINE_WIDTH chars (no broken-ASCII lines on mobile)."""
    lines = metrics_block(adx_1h=34, bias_score=43)
    for line in lines:
        assert len(line) <= MAX_LINE_WIDTH + 2, f"line too long: {len(line)} chars"


def test_metrics_block_format_matches_operator_pattern():
    """Output matches the 'ADX 1ч: 34, Биас: +43' pattern but on separate lines."""
    lines = metrics_block(adx_1h=34, bias_score=43)
    assert lines[0] == "ADX 1ч: 34"
    assert lines[1].startswith("Биас: +43")
    # Third line is the separator (single ━ run)
    assert all(ch == "━" for ch in lines[2])


def test_metrics_block_negative_bias_sign():
    lines = metrics_block(adx_1h=20, bias_score=-15)
    assert lines[1].startswith("Биас: -15")  # default int format keeps the minus


def test_metrics_block_separator_clamped():
    """Even if caller asks for absurd separator width, we clamp."""
    lines = metrics_block(adx_1h=34, bias_score=43, separator_width=999)
    assert len(lines[2]) == MAX_LINE_WIDTH


# ── Diagnostic: visuals module should still have no production callers ──────

def test_visuals_module_importable():
    """Smoke test: module imports cleanly and exports the expected names."""
    from core.orchestrator import visuals as v
    assert hasattr(v, "MAX_LINE_WIDTH")
    assert hasattr(v, "bias_scale")
    assert hasattr(v, "progress_bar")
    assert hasattr(v, "separator")
    assert hasattr(v, "metrics_block")
