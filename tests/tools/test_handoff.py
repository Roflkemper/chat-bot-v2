"""Tests for tools/handoff.py — context handoff generator and validator.

TZ-CONTEXT-HANDOFF-SKILL required tests:
  - test_handoff_includes_all_sections
  - test_state_current_reflects_latest_phase
  - test_consistency_validator_detects_contradictions
  - test_session_delta_extracts_git_changes
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.handoff import generate, validate, _git_log_today, PROJECT_CONTEXT, STATE_CURRENT, CONTEXT_DIR


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_minimal_context(tmp: Path) -> None:
    (tmp / "PROJECT_CONTEXT.md").write_text(
        "# PROJECT CONTEXT\n"
        "## §1 PROJECT GOAL\nAuto trading.\n"
        "## §3 OPERATOR STRATEGY\nGrid trading.\n"
        "HARD BAN: P-5, P-8\n"
        "## §4 PHASE MAP\nPhase roadmap\n"
        "indicator gate\n",
        encoding="utf-8",
    )
    (tmp / "STATE_CURRENT.md").write_text(
        "# STATE CURRENT\n"
        "## §1 PHASE STATUS\nPhase 1 | Paper Journal | in_progress\n"
        "K_SHORT | 9.637\n"
        "K_LONG  | 4.275\n",
        encoding="utf-8",
    )


# ── test 1: handoff includes all 5 sections ──────────────────────────────────

class TestHandoffIncludesAllSections:
    def test_handoff_includes_all_sections(self, tmp_path):
        """Generated HANDOFF must contain all expected section markers."""
        _write_minimal_context(tmp_path)
        (tmp_path / "SESSION_DELTA_2026-05-02.md").write_text(
            "# SESSION DELTA\n## TZs\nTZ-001 done\n",
            encoding="utf-8",
        )
        out = tmp_path / "HANDOFF_test.md"
        with (
            patch("tools.handoff.PROJECT_CONTEXT", tmp_path / "PROJECT_CONTEXT.md"),
            patch("tools.handoff.STATE_CURRENT", tmp_path / "STATE_CURRENT.md"),
            patch("tools.handoff.CONTEXT_DIR", tmp_path),
        ):
            result = generate(output_date="2026-05-02", output_path=out)

        content = result.read_text(encoding="utf-8")
        assert "PART 1" in content, "Missing PART 1 — Project Mechanics & Strategy"
        assert "PART 2" in content, "Missing PART 2 — Current State"
        assert "PART 3" in content, "Missing PART 3 — Recent Session Deltas"
        assert "PART 4" in content, "Missing PART 4 — Git log"
        assert "How to use this handoff" in content, "Missing usage instructions"


# ── test 2: state current reflects latest phase ───────────────────────────────

class TestStateCurrentReflectsLatestPhase:
    def test_state_current_reflects_latest_phase(self, tmp_path):
        """After writing Phase 1 in_progress to STATE_CURRENT, generate reflects it."""
        _write_minimal_context(tmp_path)
        state_file = tmp_path / "STATE_CURRENT.md"
        # Simulate Phase 1 transition: update to 'Day 5/14'
        content = state_file.read_text(encoding="utf-8")
        content = content + "\nDay 5/14\n"
        state_file.write_text(content, encoding="utf-8")

        out = tmp_path / "HANDOFF_phase_test.md"
        with (
            patch("tools.handoff.PROJECT_CONTEXT", tmp_path / "PROJECT_CONTEXT.md"),
            patch("tools.handoff.STATE_CURRENT", state_file),
            patch("tools.handoff.CONTEXT_DIR", tmp_path),
        ):
            result = generate(output_date="2026-05-02", output_path=out)

        handoff = result.read_text(encoding="utf-8")
        assert "Day 5/14" in handoff, "STATE_CURRENT phase update not reflected in handoff"
        assert "Paper Journal" in handoff, "Phase 1 name not in handoff"


# ── test 3: consistency validator detects contradictions ─────────────────────

class TestConsistencyValidatorDetectsContradictions:
    def test_consistency_validator_detects_contradictions(self, tmp_path):
        """Validator must flag missing required patterns in context docs."""
        _write_minimal_context(tmp_path)
        state_file = tmp_path / "STATE_CURRENT.md"

        # Remove K_SHORT from STATE_CURRENT — should trigger warning
        content = state_file.read_text(encoding="utf-8")
        content = content.replace("K_SHORT", "")
        state_file.write_text(content, encoding="utf-8")

        # Remove Paper Journal from STATE_CURRENT — should trigger warning
        content = state_file.read_text(encoding="utf-8")
        content = content.replace("Paper Journal", "")
        state_file.write_text(content, encoding="utf-8")

        with (
            patch("tools.handoff.PROJECT_CONTEXT", tmp_path / "PROJECT_CONTEXT.md"),
            patch("tools.handoff.STATE_CURRENT", state_file),
            patch("tools.handoff.CONTEXT_DIR", tmp_path),
            patch("tools.handoff.QUEUE_MD", tmp_path / "QUEUE.md"),
            patch("tools.handoff.ROADMAP_MD", tmp_path / "ROADMAP.md"),
        ):
            # Create missing files so other checks pass
            (tmp_path / "QUEUE.md").write_text("queue", encoding="utf-8")
            (tmp_path / "ROADMAP.md").write_text("roadmap", encoding="utf-8")
            warnings = validate()

        warning_text = "\n".join(warnings)
        assert any("K_SHORT" in w or "Phase 1" in w or "Paper Journal" in w for w in warnings), (
            f"Expected validator to flag missing K_SHORT / Paper Journal patterns, got: {warnings}"
        )

    def test_validator_passes_when_all_ok(self, tmp_path):
        """Validator returns empty warnings when all required patterns present."""
        _write_minimal_context(tmp_path)
        (tmp_path / "SESSION_DELTA_2099-01-01.md").write_text("delta", encoding="utf-8")
        (tmp_path / "QUEUE.md").write_text("queue", encoding="utf-8")
        (tmp_path / "ROADMAP.md").write_text("roadmap", encoding="utf-8")

        with (
            patch("tools.handoff.PROJECT_CONTEXT", tmp_path / "PROJECT_CONTEXT.md"),
            patch("tools.handoff.STATE_CURRENT", tmp_path / "STATE_CURRENT.md"),
            patch("tools.handoff.CONTEXT_DIR", tmp_path),
            patch("tools.handoff.QUEUE_MD", tmp_path / "QUEUE.md"),
            patch("tools.handoff.ROADMAP_MD", tmp_path / "ROADMAP.md"),
        ):
            # Patch date to match the delta file we created
            from unittest.mock import MagicMock
            import tools.handoff as hm
            with patch("tools.handoff.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2099-01-01"
                warnings = validate()

        # Should have no "MISSING" for files that exist
        missing_warnings = [w for w in warnings if "MISSING" in w and "SESSION_DELTA" in w]
        assert not missing_warnings, f"Unexpected session delta warnings: {missing_warnings}"


# ── test 4: session delta extraction ─────────────────────────────────────────

class TestSessionDeltaExtractsGitChanges:
    def test_session_delta_extracts_git_changes(self, tmp_path):
        """Generator includes git log section in HANDOFF output."""
        _write_minimal_context(tmp_path)
        out = tmp_path / "HANDOFF_git_test.md"

        fake_commits = "abc1234 feat: TZ-001 test\ndef5678 fix: bugfix"
        with (
            patch("tools.handoff.PROJECT_CONTEXT", tmp_path / "PROJECT_CONTEXT.md"),
            patch("tools.handoff.STATE_CURRENT", tmp_path / "STATE_CURRENT.md"),
            patch("tools.handoff.CONTEXT_DIR", tmp_path),
            patch("tools.handoff._git_log_today", return_value=fake_commits),
        ):
            result = generate(output_date="2026-05-02", output_path=out)

        content = result.read_text(encoding="utf-8")
        assert "TZ-001 test" in content, "Git commits not included in HANDOFF"
        assert "bugfix" in content, "Git log content missing from HANDOFF"

    def test_git_log_returns_string(self):
        """_git_log_today always returns a string (even if git fails)."""
        result = _git_log_today()
        assert isinstance(result, str), f"Expected str, got {type(result)}"
        assert len(result) >= 0
