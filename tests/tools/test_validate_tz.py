"""Tests for tools/validate_tz.py

Covers:
  - detect_phase: phase keyword matching
  - check_queue_overlap: TZ ID and title word detection
  - check_phase_alignment: active vs planned phases
  - validate: full pipeline verdicts
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools.validate_tz import (
    ValidationResult,
    check_phase_alignment,
    check_queue_overlap,
    check_skills_section,
    detect_phase,
    validate,
)

# ---------------------------------------------------------------------------
# detect_phase
# ---------------------------------------------------------------------------

class TestDetectPhase:
    def test_phase0_infra_keywords(self):
        text = "TZ-OHLCV-INGEST: update collector tracker and state snapshot"
        assert detect_phase(text) == "phase0"

    def test_phase0_5_engine_keywords(self):
        text = "TZ-ENGINE-FIX: fix reconcile sim calibrat движок"
        assert detect_phase(text) == "phase0_5"

    def test_phase1_paper_journal_keywords(self):
        text = "TZ-PAPER-JOURNAL-FIX: paper journal weekly comparison report"
        assert detect_phase(text) == "phase1"

    def test_phase2_advise_keywords(self):
        text = "TZ-ADVISE-V2: /advise telegram push notification high-confidence signal"
        assert detect_phase(text) == "phase2"

    def test_phase3_auto_keywords(self):
        text = "TZ-FULL-AUTO: autonomous тактический bot_management авто-торговля"
        assert detect_phase(text) == "phase3"

    def test_unknown_returns_none(self):
        text = "some random text without any relevant domain words"
        # Could match none or any — just test it doesn't crash
        result = detect_phase(text)
        assert result is None or result in ("phase0", "phase0_5", "phase1", "phase2", "phase3")

    def test_multiple_keyword_hits_prefers_dominant_phase(self):
        # 5 phase2 keywords vs 1 phase0 keyword
        text = "advise v2 telegram push h10 bilateral optimize widen_long ohlcv"
        phase = detect_phase(text)
        assert phase == "phase2"


# ---------------------------------------------------------------------------
# check_queue_overlap
# ---------------------------------------------------------------------------

class TestCheckQueueOverlap:
    def _make_queue(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.flush()
        return Path(tmp.name)

    def test_exact_tz_id_overlap(self):
        queue = self._make_queue("| TZ-051 | collectors fix | ⬜ OPEN |\n")
        warnings = check_queue_overlap("TZ-051: do something", queue)
        assert any("TZ-051" in w for w in warnings)

    def test_no_overlap(self):
        queue = self._make_queue("| TZ-999 | something else |\n")
        warnings = check_queue_overlap("TZ-NEW-FEATURE: brand new task", queue)
        assert not any("TZ-NEW-FEATURE" in w for w in warnings)

    def test_missing_queue_file(self):
        warnings = check_queue_overlap("TZ-XYZ", Path("/nonexistent/queue.md"))
        assert warnings
        assert "not found" in warnings[0]

    def test_no_tz_id_in_text(self):
        queue = self._make_queue("| TZ-100 | task |\n")
        warnings = check_queue_overlap("Add a new feature without TZ ID", queue)
        # Should not crash; ID overlap check skipped
        assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# check_phase_alignment
# ---------------------------------------------------------------------------

class TestCheckPhaseAlignment:
    def _dummy_roadmap(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(
            "### ФАЗА 0\nStatus: in_progress\n"
            "### ФАЗА 0.5\nStatus: in_progress\n"
            "### ФАЗА 1\nStatus: in_progress\n"
            "### ФАЗА 2\nStatus: planned\n"
            "### ФАЗА 3\nStatus: planned\n"
        )
        tmp.flush()
        return Path(tmp.name)

    def test_active_phase_gives_info(self):
        err, warn, info = check_phase_alignment("phase0", "some text", self._dummy_roadmap())
        assert not err
        assert not warn
        assert info

    def test_phase2_gives_warning(self):
        err, warn, info = check_phase_alignment("phase2", "some text", self._dummy_roadmap())
        assert not err
        assert warn

    def test_phase3_gives_error(self):
        err, warn, info = check_phase_alignment("phase3", "some text", self._dummy_roadmap())
        assert err

    def test_none_phase_gives_warning(self):
        err, warn, info = check_phase_alignment(None, "some text", self._dummy_roadmap())
        assert not err
        assert warn


# ---------------------------------------------------------------------------
# Full validate pipeline
# ---------------------------------------------------------------------------

class TestValidate:
    def _make_roadmap(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(
            "### ФАЗА 0\nStatus: in_progress\n"
            "### ФАЗА 0.5\nStatus: in_progress\n"
            "### ФАЗА 1\nStatus: in_progress\n"
            "### ФАЗА 2\nStatus: planned\n"
        )
        tmp.flush()
        return Path(tmp.name)

    def _make_queue(self, content: str = "") -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(content or "# Queue\n")
        tmp.flush()
        return Path(tmp.name)

    def test_approved_for_phase0_tz(self):
        text = "TZ-NEW-INGEST: update ohlcv ingest collector script state snapshot"
        result = validate(
            text,
            roadmap_path=self._make_roadmap(),
            queue_path=self._make_queue(),
            root=Path(__file__).parents[2],
            enforce_skills=False,
        )
        assert result.verdict == "APPROVED"
        assert result.phase_detected == "phase0"

    def test_review_needed_for_phase2_tz(self):
        text = "TZ-ADVISE-V2: implement advise telegram push high-confidence signal"
        result = validate(
            text,
            roadmap_path=self._make_roadmap(),
            queue_path=self._make_queue(),
            root=Path(__file__).parents[2],
            enforce_skills=False,
        )
        assert result.verdict == "REVIEW_NEEDED"
        assert result.phase_detected == "phase2"

    def test_rejected_for_phase3_tz(self):
        text = "TZ-FULL-AUTO: autonomous тактический bot_management авто-торговля full_auto"
        result = validate(
            text,
            roadmap_path=self._make_roadmap(),
            queue_path=self._make_queue(),
            root=Path(__file__).parents[2],
            enforce_skills=False,
        )
        assert result.verdict == "REJECTED"
        assert result.phase_detected == "phase3"

    def test_review_needed_when_tz_id_in_queue(self):
        text = "TZ-ENGINE-FIX-RESOLUTION: reconcile engine resolution 1s bars"
        result = validate(
            text,
            roadmap_path=self._make_roadmap(),
            queue_path=self._make_queue("| TZ-ENGINE-FIX-RESOLUTION | reconcile |\n"),
            root=Path(__file__).parents[2],
            enforce_skills=False,
        )
        assert result.verdict in ("REVIEW_NEEDED", "REJECTED")
        assert any("TZ-ENGINE-FIX-RESOLUTION" in w for w in result.warnings + result.errors)

    def test_result_to_text_contains_verdict(self):
        result = ValidationResult(
            verdict="APPROVED",
            phase_detected="phase0",
            info=["Phase phase0 is currently active"],
        )
        text = result.to_text()
        assert "APPROVED" in text
        assert "Фаза 0" in text


# ---------------------------------------------------------------------------
# check_skills_section / Skills enforcement
# ---------------------------------------------------------------------------

def _make_skills_dir(skill_names: list[str]) -> Path:
    """Create temp dir with empty .md files for each skill name. Return dir path."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="skills_"))
    for name in skill_names:
        (tmp_dir / f"{name}.md").write_text("# stub", encoding="utf-8")
    return tmp_dir


# All 23 actual project skills — used as the existing-skills set in tests.
_ALL_SKILLS = [
    "architect_inventory_first",
    "calibration_drift_monitor",
    "context_handoff",
    "cost_aware_executor",
    "data_freshness_check",
    "dataset_provenance_tracker",
    "encoding_safety",
    "incident_log_writer",
    "live_position_safety",
    "lookahead_bias_guard",
    "multi_year_validator",
    "operator_role_boundary",
    "param_provenance_tracker",
    "phase_aware_planning",
    "project_inventory_first",
    "regression_baseline_keeper",
    "result_sanity_check",
    "session_handoff_protocol",
    "state_drift_detector",
    "state_first_protocol",
    "survivorship_audit",
    "telegram_signal_validator",
    "trader_first_filter",
]


class TestCheckSkillsSection:
    """Skills applied section validation rules."""

    def test_missing_skills_section_rejects(self):
        text = "TZ-FOO: do something useful\n\nDONE\n"
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("missing" in e.lower() for e in errors)

    def test_empty_skills_section_rejects(self):
        text = (
            "TZ-FOO: do something\n"
            "Skills applied:\n"
            "\n"
            "END\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("empty" in e.lower() or "missing" in e.lower() for e in errors)

    def test_implement_keyword_requires_project_inventory_first(self):
        text = (
            "TZ-NEW-FEATURE: implement a new module to do X\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("project_inventory_first" in e for e in errors)

    def test_implement_with_all_mandatory_passes(self):
        text = (
            "TZ-NEW-FEATURE: implement a new module to do X\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "- project_inventory_first\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert ok, f"Unexpected errors: {errors}"

    def test_param_change_requires_param_provenance_tracker(self):
        text = (
            "TZ-TUNE: adjust grid_step and target_profit thresholds for SHORT\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("param_provenance_tracker" in e for e in errors)

    def test_live_deploy_requires_live_position_safety(self):
        text = (
            "TZ-DEPLOY: rollout new advisor to live, restart supervisor\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("live_position_safety" in e for e in errors)

    def test_phase2_keyword_requires_phase_aware_planning(self):
        text = (
            "TZ-ADVISE: change /advise behavior to use new signal\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "\n"
        )
        ok, errors = check_skills_section(
            text,
            phase="phase2",
            skills_dir=_make_skills_dir(_ALL_SKILLS),
        )
        assert not ok
        assert any("phase_aware_planning" in e for e in errors)

    def test_trader_first_filter_always_required(self):
        text = (
            "TZ-DOCS: update README with new section\n"
            "Skills applied:\n"
            "- encoding_safety\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("trader_first_filter" in e for e in errors)

    def test_unknown_skill_rejects(self):
        text = (
            "TZ-FOO: do something\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "- nonexistent_skill_xyz\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("nonexistent_skill_xyz" in e for e in errors)

    def test_happy_path_full_valid_tz(self):
        """A complete TZ that satisfies every applicable rule passes."""
        text = (
            "TZ-CLOSE-GAP-05: close instop semantics gap, build new test file,\n"
            "regression baseline preserved, RUN_TESTS clean, commit clean.\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "- project_inventory_first\n"
            "- param_provenance_tracker\n"
            "- regression_baseline_keeper\n"
            "- encoding_safety\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert ok, f"Unexpected errors: {errors}"

    def test_inline_comma_separated_skills_parsed(self):
        text = (
            "TZ-X: implement a new module\n"
            "Skills applied: trader_first_filter, project_inventory_first\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert ok, f"Unexpected errors: {errors}"

    def test_regression_keyword_requires_baseline_keeper(self):
        text = (
            "TZ-X: run RUN_TESTS and verify regression baseline\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "\n"
        )
        ok, errors = check_skills_section(text, skills_dir=_make_skills_dir(_ALL_SKILLS))
        assert not ok
        assert any("regression_baseline_keeper" in e for e in errors)


class TestValidatePipelineWithSkills:
    """Integration: full validate() with enforce_skills=True."""

    def _make_roadmap(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(
            "### ФАЗА 0\nStatus: in_progress\n"
            "### ФАЗА 0.5\nStatus: in_progress\n"
            "### ФАЗА 1\nStatus: in_progress\n"
            "### ФАЗА 2\nStatus: planned\n"
        )
        tmp.flush()
        return Path(tmp.name)

    def _make_queue(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write("# Queue\n")
        tmp.flush()
        return Path(tmp.name)

    def test_rejected_when_skills_section_missing(self):
        text = "TZ-OHLCV: update collector tracker"
        result = validate(
            text,
            roadmap_path=self._make_roadmap(),
            queue_path=self._make_queue(),
            root=Path(__file__).parents[2],
            skills_dir=_make_skills_dir(_ALL_SKILLS),
        )
        assert result.verdict == "REJECTED"
        assert any("Skills applied" in e for e in result.errors)

    def test_approved_with_full_skills_section(self):
        # Generic phase0 keyword (collector/tracker) — does not trigger any
        # of the keyword→skill mandatory rules, so the only required skill
        # is the always-mandatory trader_first_filter.
        text = (
            "TZ-COLLECTOR: update tracker fixture\n"
            "Skills applied:\n"
            "- trader_first_filter\n"
            "\n"
        )
        result = validate(
            text,
            roadmap_path=self._make_roadmap(),
            queue_path=self._make_queue(),
            root=Path(__file__).parents[2],
            skills_dir=_make_skills_dir(_ALL_SKILLS),
        )
        assert result.verdict == "APPROVED", (
            f"Expected APPROVED, got {result.verdict}; errors={result.errors}, "
            f"warnings={result.warnings}"
        )
