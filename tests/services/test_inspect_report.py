"""Tests for inspect_report."""
from __future__ import annotations

from services.inspect_report import build_inspect_report


def test_no_pid_returns_listing():
    """Without pid returns a string mentioning bot7 .venv processes."""
    text = build_inspect_report()
    assert "[INSPECT]" in text
    # Either lists processes or says (none)
    assert "bot7" in text or "(none)" in text


def test_invalid_pid_returns_not_found():
    """Non-existent pid → graceful message."""
    text = build_inspect_report(pid=999999999)
    assert "not found" in text or "access denied" in text


def test_current_pid_returns_details():
    """Inspect own process — works because we own it."""
    import os
    text = build_inspect_report(pid=os.getpid())
    assert "pid=" in text
    assert "cmd:" in text
    assert "mem:" in text
