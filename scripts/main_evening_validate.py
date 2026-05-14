"""
main_evening_validate.py — MAIN coordinator evening deliverable validator.

Usage:
    python scripts/main_evening_validate.py --sprint docs/SPRINTS/SPRINT_2026-05-04.md
    python scripts/main_evening_validate.py --sprint docs/SPRINTS/SPRINT_2026-05-04.md --strict

Exit codes:
    0 — all deliverables validated
    1 — one or more deliverables failed or drift detected
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "docs" / "STATE" / "STATE_CURRENT.md"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DeliverableResult:
    text: str
    passed: bool
    reason: str = ""


@dataclass
class ValidationReport:
    sprint_path: Path
    date_str: str
    deliverables: list[DeliverableResult] = field(default_factory=list)
    verify_results: list[tuple[str, bool, str]] = field(default_factory=list)
    drift_detected: bool = False
    drift_type: str = ""
    drift_notes: list[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return (
            all(d.passed for d in self.deliverables)
            and all(ok for _, ok, _ in self.verify_results)
            and not self.drift_detected
        )


# ---------------------------------------------------------------------------
# Sprint parsing
# ---------------------------------------------------------------------------


def _parse_sprint(sprint_path: Path) -> dict:
    text = sprint_path.read_text(encoding="utf-8")
    data: dict = {
        "date": "",
        "deliverables": [],
        "verify_cmds": [],
        "tzs": [],
    }

    # Extract date from filename SPRINT_YYYY-MM-DD.md
    m = re.search(r"SPRINT_(\d{4}-\d{2}-\d{2})", sprint_path.name)
    if m:
        data["date"] = m.group(1)

    in_deliverables = False
    in_verify = False
    in_tz_table = False

    for line in text.splitlines():
        stripped = line.strip()

        if "## HARD DELIVERABLES" in stripped:
            in_deliverables = True
            in_verify = False
            in_tz_table = False
        elif "## VERIFY COMMANDS" in stripped:
            in_verify = True
            in_deliverables = False
            in_tz_table = False
        elif "## TODAY'S TZs" in stripped:
            in_tz_table = True
            in_deliverables = False
            in_verify = False
        elif stripped.startswith("##"):
            in_deliverables = False
            in_verify = False
            in_tz_table = False

        elif in_deliverables and stripped.startswith("- [ ]"):
            data["deliverables"].append(stripped[5:].strip())

        elif in_verify and stripped.startswith("python"):
            data["verify_cmds"].append(stripped)

        elif in_tz_table and "|" in stripped and "TZ-" in stripped and "---" not in stripped:
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) >= 2 and cells[1].startswith("TZ-"):
                data["tzs"].append(cells[1])

    return data


# ---------------------------------------------------------------------------
# Deliverable validation
# ---------------------------------------------------------------------------


def _validate_deliverable(text: str) -> DeliverableResult:
    """
    Heuristic validation of a deliverable description.
    Checks for file existence, test counts, or metric comparisons.
    """
    # File existence check: "D1: some/path/file.md"
    file_match = re.search(r"[\w/\\.-]+\.(md|py|csv|parquet|json|yaml|txt)", text)
    if file_match:
        rel_path = file_match.group(0)
        candidate = ROOT / rel_path
        if candidate.exists():
            return DeliverableResult(text=text, passed=True, reason=f"file exists: {rel_path}")
        # Try as absolute or partial match
        matches = list(ROOT.rglob(rel_path.lstrip("/\\")))
        if matches:
            return DeliverableResult(text=text, passed=True, reason=f"file found: {matches[0]}")
        # File not found but might be created during session — warn, don't fail
        return DeliverableResult(
            text=text, passed=False, reason=f"file not found: {rel_path}"
        )

    # Test count check: "45 tests green", "≥15 tests"
    test_match = re.search(r"(\d+)\s+tests?\s+(green|pass|ok)", text, re.IGNORECASE)
    if test_match:
        expected_count = int(test_match.group(1))
        return _check_test_count(text, expected_count)

    # Metric check: "Brier ≤0.22", "CV <5%"
    metric_match = re.search(r"(Brier|CV|F1|accuracy|WR)\s*[≤<=]\s*([\d.]+)", text, re.IGNORECASE)
    if metric_match:
        # Cannot auto-validate metrics — mark as needs manual check
        return DeliverableResult(
            text=text,
            passed=False,
            reason=f"metric deliverable '{metric_match.group(0)}' — verify manually",
        )

    # Commit check: "All open TZ committed"
    if "committed" in text.lower() or "commit" in text.lower():
        result = _check_recent_commit()
        return DeliverableResult(text=text, passed=result[0], reason=result[1])

    # Default: cannot auto-validate — flag for manual review
    return DeliverableResult(
        text=text, passed=False, reason="cannot auto-validate — check manually"
    )


def _check_test_count(text: str, expected: int) -> DeliverableResult:
    """Run pytest in collect-only mode to count available tests."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "core/tests/"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=30,
        )
        output = proc.stdout + proc.stderr
        m = re.search(r"(\d+) tests? collected", output)
        if m:
            found = int(m.group(1))
            if found >= expected:
                return DeliverableResult(
                    text=text, passed=True, reason=f"{found} tests collected (≥{expected})"
                )
            return DeliverableResult(
                text=text,
                passed=False,
                reason=f"only {found} tests collected, expected ≥{expected}",
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return DeliverableResult(
        text=text, passed=False, reason="could not run pytest --collect-only"
    )


def _check_recent_commit() -> tuple[bool, str]:
    """Check if there is a commit today."""
    try:
        proc = subprocess.run(
            ["git", "log", "--oneline", "--since=today", "-5"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=10,
        )
        commits = [l for l in proc.stdout.strip().splitlines() if l]
        if commits:
            return True, f"{len(commits)} commits today: {commits[0]}"
        return False, "no commits today — may need to commit"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "could not check git log"


# ---------------------------------------------------------------------------
# Verify command runner
# ---------------------------------------------------------------------------


def _run_verify_cmd(cmd: str) -> tuple[str, bool, str]:
    """Run a verify command and return (cmd, passed, output_summary)."""
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=60,
        )
        passed = proc.returncode == 0
        output = (proc.stdout + proc.stderr).strip()
        summary = output[-300:] if len(output) > 300 else output
        return cmd, passed, summary
    except subprocess.TimeoutExpired:
        return cmd, False, "TIMEOUT (60s)"
    except Exception as e:
        return cmd, False, str(e)


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def _detect_drift(sprint_data: dict, deliverable_results: list[DeliverableResult]) -> tuple[bool, str, list[str]]:
    """Simple drift detection based on deliverable outcomes."""
    notes = []
    failed = [d for d in deliverable_results if not d.passed]

    if not failed:
        return False, "", []

    # drift- : deliverables not done
    if len(failed) == len(deliverable_results):
        notes.append(f"ALL {len(failed)} deliverables incomplete")
        return True, "drift- (nothing completed)", notes

    if len(failed) >= 2:
        notes.append(f"{len(failed)}/{len(deliverable_results)} deliverables incomplete")
        return True, "drift- (multiple deliverables missed)", notes

    notes.append(f"{len(failed)}/{len(deliverable_results)} deliverable incomplete")
    return False, "", notes  # single miss — warning but not drift


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _format_report(report: ValidationReport, strict: bool) -> str:
    lines = [
        f"# EVENING VALIDATION — {report.date_str}",
        f"# Sprint: {report.sprint_path.name}",
        f"# Validated at: {datetime.now().strftime('%H:%M')}",
        "",
        "---",
        "",
    ]

    # Deliverables
    if report.deliverables:
        lines += ["## DELIVERABLES", ""]
        for d in report.deliverables:
            icon = "✅" if d.passed else "❌"
            lines.append(f"{icon} {d.text}")
            if d.reason:
                lines.append(f"   → {d.reason}")
        lines.append("")

    # Verify commands
    if report.verify_results:
        lines += ["## VERIFY COMMANDS", ""]
        for cmd, passed, out in report.verify_results:
            icon = "✅" if passed else "❌"
            lines.append(f"{icon} `{cmd}`")
            if out:
                lines.append(f"```\n{out}\n```")
        lines.append("")

    # Drift
    if report.drift_detected:
        lines += [
            f"## ⚠️ DRIFT DETECTED: {report.drift_type}",
            "",
        ]
        for note in report.drift_notes:
            lines.append(f"- {note}")
        lines += [
            "",
            "**Action required:**",
            "1. Update DRIFT TRACKING in week plan",
            "2. Add to docs/CONTEXT/DRIFT_HISTORY.md if new pattern",
            "3. Adjust tomorrow's plan",
            "",
        ]
    elif report.drift_notes:
        lines += ["## ⚠️ WARNINGS", ""]
        for note in report.drift_notes:
            lines.append(f"- {note}")
        lines.append("")

    # Summary
    status = "✅ ALL PASSED" if report.all_passed else "❌ VALIDATION FAILED"
    lines += ["---", "", f"## RESULT: {status}", ""]

    if not report.all_passed:
        lines += [
            "Next steps:",
            "1. Fix failing deliverables",
            "2. Re-run this script",
            "3. If drift: notify operator",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def validate_sprint(sprint_path: Path, strict: bool = False, run_verify: bool = True) -> ValidationReport:
    sprint_data = _parse_sprint(sprint_path)
    date_str = sprint_data.get("date") or date.today().isoformat()

    report = ValidationReport(sprint_path=sprint_path, date_str=date_str)

    # Validate deliverables
    for d_text in sprint_data.get("deliverables", []):
        result = _validate_deliverable(d_text)
        report.deliverables.append(result)

    # Run verify commands (optional — may be slow)
    if run_verify:
        for cmd in sprint_data.get("verify_cmds", []):
            report.verify_results.append(_run_verify_cmd(cmd))

    # Drift detection
    report.drift_detected, report.drift_type, report.drift_notes = _detect_drift(
        sprint_data, report.deliverables
    )

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate evening deliverables for a sprint")
    parser.add_argument("--sprint", required=True, help="Path to SPRINT_*.md file")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any warning")
    parser.add_argument("--no-verify", action="store_true", help="Skip running verify commands")
    args = parser.parse_args(argv)

    sprint_path = Path(args.sprint)
    if not sprint_path.is_absolute():
        sprint_path = ROOT / sprint_path
    if not sprint_path.exists():
        print(f"ERROR: sprint file not found: {sprint_path}", file=sys.stderr)
        return 1

    report = validate_sprint(sprint_path, strict=args.strict, run_verify=not args.no_verify)
    output = _format_report(report, strict=args.strict)
    sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
