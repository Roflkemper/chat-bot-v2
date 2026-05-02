"""Tests for services/claude_bot/ — context loader and queue writer."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.claude_bot.context_loader import load_system_prompt
from services.claude_bot.queue_writer import append_if_tz, _looks_like_tz


# ── queue_writer tests ────────────────────────────────────────────────────────

class TestLooksLikeTZ:
    def test_tz_prefix_en(self):
        assert _looks_like_tz("TZ-001 do something") is True

    def test_tz_prefix_ru(self):
        assert _looks_like_tz("ТЗ: нужно сделать фичу") is True

    def test_tz_space_ru(self):
        assert _looks_like_tz("ТЗ на завтра") is True

    def test_regular_message(self):
        assert _looks_like_tz("как дела?") is False

    def test_status_message(self):
        assert _looks_like_tz("/status") is False


class TestAppendIfTZ:
    def test_appends_tz_to_queue(self, tmp_path):
        queue = tmp_path / "QUEUE.md"
        with patch("services.claude_bot.queue_writer._QUEUE_MD", queue):
            result = append_if_tz("TZ-TEST implement feature X", 12345)
        assert result is True
        content = queue.read_text(encoding="utf-8")
        assert "TZ-TEST" in content
        assert "implement feature X" in content
        assert "12345" in content

    def test_does_not_append_non_tz(self, tmp_path):
        queue = tmp_path / "QUEUE.md"
        with patch("services.claude_bot.queue_writer._QUEUE_MD", queue):
            result = append_if_tz("привет как дела", 12345)
        assert result is False
        assert not queue.exists()

    def test_appends_multiple(self, tmp_path):
        queue = tmp_path / "QUEUE.md"
        with patch("services.claude_bot.queue_writer._QUEUE_MD", queue):
            append_if_tz("TZ-001 first", 1)
            append_if_tz("TZ-002 second", 1)
        content = queue.read_text(encoding="utf-8")
        assert "TZ-001" in content
        assert "TZ-002" in content


# ── context_loader tests ──────────────────────────────────────────────────────

class TestContextLoader:
    def test_loads_handoff_when_present(self, tmp_path):
        handoff = tmp_path / "HANDOFF_2026-05-02.md"
        handoff.write_text("# HANDOFF\n## PART 1\nProject goal here.", encoding="utf-8")

        with (
            patch("services.claude_bot.context_loader._CONTEXT_DIR", tmp_path),
            patch("services.claude_bot.context_loader._STATE_CURRENT", tmp_path / "STATE.md"),
        ):
            prompt = load_system_prompt()

        assert "HANDOFF" in prompt or "Project goal here" in prompt
        assert "Claude" in prompt

    def test_falls_back_to_state_when_no_handoff(self, tmp_path):
        state = tmp_path / "STATE_CURRENT.md"
        state.write_text("Phase 1 in_progress K_SHORT 9.637", encoding="utf-8")

        with (
            patch("services.claude_bot.context_loader._CONTEXT_DIR", tmp_path),
            patch("services.claude_bot.context_loader._STATE_CURRENT", state),
        ):
            prompt = load_system_prompt()

        assert "K_SHORT" in prompt or "Phase 1" in prompt

    def test_truncates_large_handoff(self, tmp_path):
        handoff = tmp_path / "HANDOFF_2026-05-02.md"
        handoff.write_text("X" * 50_000, encoding="utf-8")

        with (
            patch("services.claude_bot.context_loader._CONTEXT_DIR", tmp_path),
            patch("services.claude_bot.context_loader._STATE_CURRENT", tmp_path / "STATE.md"),
        ):
            prompt = load_system_prompt()

        assert len(prompt) < 55_000
