"""Tests for main_morning_brief.py and main_evening_validate.py."""
from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers — minimal week plan fixture
# ---------------------------------------------------------------------------

WEEK_PLAN_CONTENT = textwrap.dedent(
    """\
    # WEEK PLAN — 2026-05-04 to 2026-05-10

    ## WEEK HEADER

    **Period:** 2026-05-04 (Mon) → 2026-05-10 (Sun)
    **Primary goal:** Phase 1 paper journal
    **Phase focus:** Phase 0.5 + Phase 1
    **Operator availability:** full

    ### DAY 1 — Monday 2026-05-04

    **Goal:** Close TZ-MAIN-COORDINATOR-INFRASTRUCTURE

    | # | TZ_ID | Description | Est. | Dependency |
    |---|-------|-------------|------|------------|
    | 1 | TZ-MAIN-COORDINATOR-INFRASTRUCTURE | Finish all deliverables | 2h | — |

    **Hard deliverables:**
    - [ ] D1: docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md exists
    - [ ] D2: ≥15 tests green

    **Verify commands:**
    ```
    python -m pytest core/tests/test_main_coordinator.py -v
    ```

    **Gate:** CP1 — ≥15 tests green

    ### DAY 2 — Tuesday 2026-05-05

    **Goal:** Engine fix

    | # | TZ_ID | Description | Est. | Dependency |
    |---|-------|-------------|------|------------|
    | 1 | TZ-ENGINE-FIX-RESOLUTION | 1s OHLCV | 4h | Operator |

    **Hard deliverables:**
    - [ ] D1: 1s OHLCV loaded

    **Verify commands:**
    ```
    python scripts/ohlcv_ingest.py --dry-run
    ```
    """
)


@pytest.fixture()
def week_plan(tmp_path: Path) -> Path:
    p = tmp_path / "WEEK_2026-05-04_to_2026-05-10.md"
    p.write_text(WEEK_PLAN_CONTENT, encoding="utf-8")
    return p


@pytest.fixture()
def sprint_content_full() -> str:
    return textwrap.dedent(
        """\
        # SPRINT — 2026-05-04

        ## TODAY'S GOAL

        Close TZ-MAIN-COORDINATOR-INFRASTRUCTURE

        ## TODAY'S TZs

        | # | TZ_ID | Description | Est. |
        |---|-------|-------------|------|
        | 1 | TZ-MAIN-COORDINATOR-INFRASTRUCTURE | Finish all deliverables | 2h |

        ## HARD DELIVERABLES

        - [ ] D1: docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md exists
        - [ ] D2: ≥15 tests green

        ## VERIFY COMMANDS

        ```bash
        python -m pytest core/tests/test_main_coordinator.py -v
        ```

        ## END OF DAY

        Run evening validator:
        ```bash
        python scripts/main_evening_validate.py --sprint docs/SPRINTS/SPRINT_2026-05-04.md
        ```
        """
    )


@pytest.fixture()
def sprint_file(tmp_path: Path, sprint_content_full: str) -> Path:
    p = tmp_path / "SPRINT_2026-05-04.md"
    p.write_text(sprint_content_full, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# main_morning_brief — _parse_week_plan
# ---------------------------------------------------------------------------


def test_parse_week_plan_period(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    assert "2026-05-04" in plan["period"]
    assert "2026-05-10" in plan["period"]


def test_parse_week_plan_primary_goal(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    assert "paper journal" in plan["primary_goal"].lower()


def test_parse_week_plan_phase_focus(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    assert "0.5" in plan["phase_focus"] or "Phase" in plan["phase_focus"]


def test_parse_week_plan_days_found(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    assert "2026-05-04" in plan["days"]
    assert "2026-05-05" in plan["days"]


def test_parse_day_goal(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    day = plan["days"]["2026-05-04"]
    assert "TZ-MAIN" in day["goal"] or "Close" in day["goal"]


def test_parse_day_tzs(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    day = plan["days"]["2026-05-04"]
    assert len(day["tzs"]) >= 1
    assert day["tzs"][0]["id"] == "TZ-MAIN-COORDINATOR-INFRASTRUCTURE"


def test_parse_day_deliverables(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    day = plan["days"]["2026-05-04"]
    assert len(day["deliverables"]) == 2
    assert any("WEEK_2026" in d for d in day["deliverables"])


def test_parse_day_verify_cmds(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    day = plan["days"]["2026-05-04"]
    assert any("pytest" in c for c in day["verify_cmds"])


def test_parse_day_gate(week_plan: Path) -> None:
    from scripts.main_morning_brief import _parse_week_plan

    plan = _parse_week_plan(week_plan)
    day = plan["days"]["2026-05-04"]
    assert "CP1" in day["gate"] or "15" in day["gate"]


# ---------------------------------------------------------------------------
# main_morning_brief — generate_sprint
# ---------------------------------------------------------------------------


def test_generate_sprint_contains_goal(week_plan: Path) -> None:
    from scripts.main_morning_brief import generate_sprint

    content = generate_sprint(week_plan, date(2026, 5, 4))
    assert "TODAY'S GOAL" in content
    assert "TZ-MAIN" in content or "Close" in content


def test_generate_sprint_contains_date(week_plan: Path) -> None:
    from scripts.main_morning_brief import generate_sprint

    content = generate_sprint(week_plan, date(2026, 5, 4))
    assert "2026-05-04" in content


def test_generate_sprint_contains_deliverables(week_plan: Path) -> None:
    from scripts.main_morning_brief import generate_sprint

    content = generate_sprint(week_plan, date(2026, 5, 4))
    assert "HARD DELIVERABLES" in content
    assert "WEEK_2026" in content


def test_generate_sprint_contains_anti_drift(week_plan: Path) -> None:
    from scripts.main_morning_brief import generate_sprint

    content = generate_sprint(week_plan, date(2026, 5, 4))
    assert "ANTI-DRIFT" in content


def test_generate_sprint_missing_day_fallback(week_plan: Path) -> None:
    from scripts.main_morning_brief import generate_sprint

    # Date not in plan
    content = generate_sprint(week_plan, date(2026, 5, 9))
    assert "SPRINT" in content  # should still produce output, not crash


def test_generate_sprint_writes_file(week_plan: Path, tmp_path: Path, monkeypatch) -> None:
    from scripts import main_morning_brief

    monkeypatch.setattr(main_morning_brief, "SPRINTS_DIR", tmp_path)
    ret = main_morning_brief.main(["--week", str(week_plan), "--day", "2026-05-04"])
    assert ret == 0
    assert (tmp_path / "SPRINT_2026-05-04.md").exists()


def test_generate_sprint_dry_run_no_file(week_plan: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    from scripts import main_morning_brief

    monkeypatch.setattr(main_morning_brief, "SPRINTS_DIR", tmp_path)
    ret = main_morning_brief.main(["--week", str(week_plan), "--day", "2026-05-04", "--dry-run"])
    assert ret == 0
    out = capsys.readouterr().out
    assert "SPRINT" in out
    assert not (tmp_path / "SPRINT_2026-05-04.md").exists()


# ---------------------------------------------------------------------------
# main_evening_validate — _parse_sprint
# ---------------------------------------------------------------------------


def test_parse_sprint_date(sprint_file: Path) -> None:
    from scripts.main_evening_validate import _parse_sprint

    data = _parse_sprint(sprint_file)
    assert data["date"] == "2026-05-04"


def test_parse_sprint_deliverables(sprint_file: Path) -> None:
    from scripts.main_evening_validate import _parse_sprint

    data = _parse_sprint(sprint_file)
    assert len(data["deliverables"]) == 2
    assert any("WEEK_2026" in d for d in data["deliverables"])


def test_parse_sprint_verify_cmds(sprint_file: Path) -> None:
    from scripts.main_evening_validate import _parse_sprint

    data = _parse_sprint(sprint_file)
    assert any("pytest" in c for c in data["verify_cmds"])


def test_parse_sprint_tzs(sprint_file: Path) -> None:
    from scripts.main_evening_validate import _parse_sprint

    data = _parse_sprint(sprint_file)
    assert "TZ-MAIN-COORDINATOR-INFRASTRUCTURE" in data["tzs"]


# ---------------------------------------------------------------------------
# main_evening_validate — _validate_deliverable
# ---------------------------------------------------------------------------


def test_validate_deliverable_file_exists(tmp_path: Path, monkeypatch) -> None:
    from scripts import main_evening_validate

    # Point ROOT at tmp_path
    target = tmp_path / "docs" / "PLANS" / "WEEK_2026-05-04_to_2026-05-10.md"
    target.parent.mkdir(parents=True)
    target.write_text("exists", encoding="utf-8")
    monkeypatch.setattr(main_evening_validate, "ROOT", tmp_path)

    result = main_evening_validate._validate_deliverable(
        "D1: docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md exists"
    )
    assert result.passed


def test_validate_deliverable_file_missing(tmp_path: Path, monkeypatch) -> None:
    from scripts import main_evening_validate

    monkeypatch.setattr(main_evening_validate, "ROOT", tmp_path)
    result = main_evening_validate._validate_deliverable("D1: docs/PLANS/NONEXISTENT.md")
    assert not result.passed
    assert "not found" in result.reason


def test_validate_deliverable_metric_manual(tmp_path: Path, monkeypatch) -> None:
    from scripts import main_evening_validate

    monkeypatch.setattr(main_evening_validate, "ROOT", tmp_path)
    result = main_evening_validate._validate_deliverable("D2: Brier ≤0.22")
    assert not result.passed
    assert "manually" in result.reason


# ---------------------------------------------------------------------------
# main_evening_validate — _detect_drift
# ---------------------------------------------------------------------------


def test_detect_drift_all_passed_no_drift() -> None:
    from scripts.main_evening_validate import DeliverableResult, _detect_drift

    results = [DeliverableResult("D1", True, "ok"), DeliverableResult("D2", True, "ok")]
    detected, dtype, notes = _detect_drift({}, results)
    assert not detected


def test_detect_drift_all_failed_is_drift() -> None:
    from scripts.main_evening_validate import DeliverableResult, _detect_drift

    results = [
        DeliverableResult("D1", False, "missing"),
        DeliverableResult("D2", False, "missing"),
    ]
    detected, dtype, notes = _detect_drift({}, results)
    assert detected
    assert "drift-" in dtype


def test_detect_drift_two_failed_is_drift() -> None:
    from scripts.main_evening_validate import DeliverableResult, _detect_drift

    results = [
        DeliverableResult("D1", True, "ok"),
        DeliverableResult("D2", False, "missing"),
        DeliverableResult("D3", False, "missing"),
    ]
    detected, dtype, notes = _detect_drift({}, results)
    assert detected


def test_detect_drift_one_failed_warning_only() -> None:
    from scripts.main_evening_validate import DeliverableResult, _detect_drift

    results = [DeliverableResult("D1", True, "ok"), DeliverableResult("D2", False, "missing")]
    detected, dtype, notes = _detect_drift({}, results)
    assert not detected  # single miss = warning, not drift


# ---------------------------------------------------------------------------
# main_evening_validate — validate_sprint integration
# ---------------------------------------------------------------------------


def test_validate_sprint_missing_file_raises(tmp_path: Path) -> None:
    from scripts.main_evening_validate import main

    ret = main(["--sprint", str(tmp_path / "NONEXISTENT.md"), "--no-verify"])
    assert ret == 1


def test_validate_sprint_report_format(sprint_file: Path, tmp_path: Path, monkeypatch) -> None:
    from scripts import main_evening_validate

    monkeypatch.setattr(main_evening_validate, "ROOT", tmp_path)
    report = main_evening_validate.validate_sprint(sprint_file, run_verify=False)
    formatted = main_evening_validate._format_report(report, strict=False)
    assert "EVENING VALIDATION" in formatted
    assert "2026-05-04" in formatted
    assert "DELIVERABLES" in formatted
