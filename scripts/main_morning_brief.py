"""
main_morning_brief.py — MAIN coordinator morning brief generator.

Usage:
    python scripts/main_morning_brief.py --week docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md
    python scripts/main_morning_brief.py --week docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md --day 2026-05-05
    python scripts/main_morning_brief.py --week docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md --dry-run

Output: docs/SPRINTS/SPRINT_YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPRINTS_DIR = ROOT / "docs" / "SPRINTS"
STATE_FILE = ROOT / "docs" / "STATE" / "STATE_CURRENT.md"
PENDING_TZ_FILE = ROOT / "docs" / "STATE" / "PENDING_TZ.md"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_week_plan(plan_path: Path) -> dict:
    """Extract structured data from a WEEK plan markdown file."""
    text = plan_path.read_text(encoding="utf-8")
    result: dict = {
        "period": "",
        "primary_goal": "",
        "phase_focus": "",
        "days": {},
    }

    # Header fields
    for line in text.splitlines():
        if line.startswith("**Period:**"):
            result["period"] = line.split(":", 1)[1].strip().strip("*")
        elif line.startswith("**Primary goal:**"):
            result["primary_goal"] = line.split(":", 1)[1].strip().strip("*")
        elif line.startswith("**Phase focus:**"):
            result["phase_focus"] = line.split(":", 1)[1].strip().strip("*")

    # Day sections — find "### DAY N — DayName YYYY-MM-DD"
    day_pattern = re.compile(
        r"### DAY \d+ — \w+ (\d{4}-\d{2}-\d{2})(.*?)(?=### DAY|\Z)", re.DOTALL
    )
    for m in day_pattern.finditer(text):
        day_date = m.group(1)
        day_text = m.group(2)
        result["days"][day_date] = _parse_day_section(day_text)

    return result


def _parse_day_section(text: str) -> dict:
    """Extract goal, TZ table, deliverables, verify commands from a day section."""
    day = {"goal": "", "tzs": [], "deliverables": [], "verify_cmds": [], "gate": ""}

    lines = text.splitlines()
    in_tz_table = False
    in_deliverables = False
    in_verify = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("**Goal:**"):
            day["goal"] = stripped.split(":", 1)[1].strip().strip("*")

        elif stripped.startswith("**Gate:**"):
            day["gate"] = stripped.split(":", 1)[1].strip().strip("*")

        elif "|" in stripped and "TZ_ID" in stripped:
            in_tz_table = True
            in_deliverables = False
            in_verify = False
            continue

        elif in_tz_table and stripped.startswith("|") and not stripped.startswith("|---"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) >= 4 and cells[1].startswith("TZ-"):
                day["tzs"].append(
                    {"num": cells[0], "id": cells[1], "desc": cells[2], "est": cells[3]}
                )

        elif stripped.startswith("**Hard deliverables:**"):
            in_deliverables = True
            in_tz_table = False
            in_verify = False

        elif in_deliverables and stripped.startswith("- [ ]"):
            day["deliverables"].append(stripped[5:].strip())

        elif stripped.startswith("**Verify commands:**"):
            in_verify = True
            in_deliverables = False
            in_tz_table = False

        elif in_verify and stripped.startswith("python"):
            day["verify_cmds"].append(stripped)

        elif stripped.startswith("---") or stripped.startswith("**"):
            if not stripped.startswith("**Verify") and not stripped.startswith("**Hard") and not stripped.startswith("**Goal") and not stripped.startswith("**Gate") and not stripped.startswith("**Drift"):
                in_tz_table = False
                in_deliverables = False
                in_verify = False

    return day


def _read_open_blockers() -> list[str]:
    """Read operator pending actions from STATE_CURRENT.md §5."""
    if not STATE_FILE.exists():
        return []
    text = STATE_FILE.read_text(encoding="utf-8")
    blockers = []
    in_section = False
    for line in text.splitlines():
        if "§5 OPERATOR PENDING" in line:
            in_section = True
        elif in_section and line.startswith("##"):
            break
        elif in_section and "|" in line and "---" not in line and "Действие" not in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if cells and cells[0]:
                blockers.append(cells[0])
    return blockers


def _read_open_tzs_from_pending() -> list[str]:
    """Read open TZs from PENDING_TZ.md if it exists."""
    if not PENDING_TZ_FILE.exists():
        return []
    text = PENDING_TZ_FILE.read_text(encoding="utf-8")
    tzs = []
    for line in text.splitlines():
        if line.startswith("| TZ-") or ("|" in line and "TZ-" in line and "DONE" not in line and "done" not in line.lower()):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if cells and cells[0].startswith("TZ-"):
                tzs.append(cells[0])
    return tzs[:10]  # cap at 10


# ---------------------------------------------------------------------------
# Sprint generation
# ---------------------------------------------------------------------------


def generate_sprint(week_plan_path: Path, target_date: date, dry_run: bool = False) -> str:
    """Generate a SPRINT.md for target_date from the week plan."""
    plan = _parse_week_plan(week_plan_path)
    date_str = target_date.isoformat()
    day_data = plan["days"].get(date_str, {})

    blockers = _read_open_blockers()
    open_tzs_pending = _read_open_tzs_from_pending()

    lines = [
        f"# SPRINT — {date_str}",
        f"# Generated by main_morning_brief.py at {datetime.now().strftime('%H:%M')}",
        f"# Week: {plan['period']}",
        "",
        "---",
        "",
        "## TODAY'S GOAL",
        "",
        day_data.get("goal") or "[No goal defined for this date — check week plan]",
        "",
        f"**Primary week goal:** {plan['primary_goal']}",
        f"**Phase focus:** {plan['phase_focus']}",
        "",
    ]

    # Blockers section
    if blockers:
        lines += [
            "## ⚠️ OPERATOR ACTIONS PENDING (check before starting)",
            "",
        ]
        for b in blockers:
            lines.append(f"- [ ] {b}")
        lines.append("")

    # TZ plan
    tzs = day_data.get("tzs", [])
    if tzs:
        lines += [
            "## TODAY'S TZs",
            "",
            "| # | TZ_ID | Description | Est. |",
            "|---|-------|-------------|------|",
        ]
        for tz in tzs:
            lines.append(f"| {tz['num']} | {tz['id']} | {tz['desc']} | {tz['est']} |")
        lines.append("")
    else:
        lines += [
            "## TODAY'S TZs",
            "",
            "_No TZs defined for this date in the week plan._",
            "",
        ]

    # Hard deliverables
    deliverables = day_data.get("deliverables", [])
    if deliverables:
        lines += [
            "## HARD DELIVERABLES",
            "",
        ]
        for d in deliverables:
            lines.append(f"- [ ] {d}")
        lines.append("")

    # Gate
    gate = day_data.get("gate", "")
    if gate:
        lines += [
            f"## GATE: {gate}",
            "",
            "> If gate fails → STOP, notify operator, await replan.",
            "",
        ]

    # Verify commands
    verify_cmds = day_data.get("verify_cmds", [])
    if verify_cmds:
        lines += [
            "## VERIFY COMMANDS",
            "",
            "```bash",
        ]
        lines.extend(verify_cmds)
        lines += ["```", ""]

    # Anti-drift reminder
    lines += [
        "---",
        "",
        "## ANTI-DRIFT REMINDERS",
        "",
        "- Run `anti_drift_validator` CHECK 1 before each TZ",
        "- If a deliverable takes >2x estimate → TIME DRIFT, notify operator",
        "- Do NOT add scope beyond what is listed in TODAY'S TZs above",
        "- At TZ end: verify ALL hard deliverables before marking ✅ DONE",
        "",
        "---",
        "",
        "## END OF DAY",
        "",
        "Run evening validator:",
        "```bash",
        f"python scripts/main_evening_validate.py --sprint docs/SPRINTS/SPRINT_{date_str}.md",
        "```",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate daily SPRINT from week plan")
    parser.add_argument("--week", required=True, help="Path to WEEK_*.md plan file")
    parser.add_argument("--day", default=None, help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, don't write file")
    args = parser.parse_args(argv)

    week_path = Path(args.week)
    if not week_path.is_absolute():
        week_path = ROOT / week_path
    if not week_path.exists():
        print(f"ERROR: week plan not found: {week_path}", file=sys.stderr)
        return 1

    target_date = date.fromisoformat(args.day) if args.day else date.today()
    content = generate_sprint(week_path, target_date, dry_run=args.dry_run)

    if args.dry_run:
        print(content)
        return 0

    SPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SPRINTS_DIR / f"SPRINT_{target_date.isoformat()}.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"SPRINT written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
