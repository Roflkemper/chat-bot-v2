"""
main_morning_brief.py — MAIN coordinator morning brief generator.

Usage (week-based, legacy):
    python scripts/main_morning_brief.py --week docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md
    python scripts/main_morning_brief.py --week docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md --day 2026-05-05

Usage (multi-track roadmap, current):
    python scripts/main_morning_brief.py --roadmap docs/PLANS/MULTI_TRACK_ROADMAP.md
    python scripts/main_morning_brief.py --roadmap docs/PLANS/MULTI_TRACK_ROADMAP.md --day 2026-05-06

Common:
    --dry-run         Print to stdout instead of writing a file
    --top N           Number of TZs to surface in TODAY'S TZs (default 3)

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
# Roadmap-based dispatch (multi-track mode)
# ---------------------------------------------------------------------------

# Track priority order: track id -> rank (lower = higher priority).
# Falls through to default if track not listed (so new tracks degrade gracefully).
_TRACK_PRIORITY = {"P1": 1, "P4": 2, "P7": 3, "P5": 4, "P2": 5, "P8": 6, "P3": 7, "P6": 8}


def _parse_roadmap(roadmap_path: Path) -> dict:
    """Extract track-level info from MULTI_TRACK_ROADMAP.md.

    Returns:
        {
          "tracks": {"P1": {"title": ..., "pain": ..., "tzs": [{"id", "desc", "status"}]}, ...}
        }
    """
    text = roadmap_path.read_text(encoding="utf-8")
    tracks: dict = {}

    # Track headers look like "### P1 — Actionability layer ..." or "### P1 — Actionability ... (week 2)"
    track_header_re = re.compile(r"^###\s+(P\d)\s+[—-]\s+(.+?)$", re.MULTILINE)
    matches = list(track_header_re.finditer(text))

    for i, m in enumerate(matches):
        track_id = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]

        pain = ""
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("**Pain:**") or stripped.startswith("Pain:"):
                _, _, raw = stripped.partition(":")
                pain = raw.strip().strip("*").strip()
                break

        # TZ table rows: | TZ-FOO | Desc | Status |
        tz_rows: list[dict] = []
        for line in body.splitlines():
            if not line.strip().startswith("|"):
                continue
            if "TZ_ID" in line or "Description" in line or "---" in line:
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not cells or len(cells) < 2 or not cells[0].startswith("TZ-"):
                continue
            tz_rows.append({
                "id": cells[0],
                "desc": cells[1] if len(cells) >= 2 else "",
                "status": cells[2].upper() if len(cells) >= 3 else "OPEN",
            })

        tracks[track_id] = {"title": title, "pain": pain, "tzs": tz_rows}
    return {"tracks": tracks}


def _select_open_tzs(roadmap: dict, top_n: int = 3) -> list[dict]:
    """Pick the top-N OPEN TZs across tracks, ordered by track priority.

    Tracks ordered by _TRACK_PRIORITY; within each track, TZs in declared order.
    Skips DONE/CLOSED/DEFERRED/GATED statuses.
    """
    selected: list[dict] = []
    skip_statuses = {"DONE", "CLOSED", "DEFERRED", "GATED", "SUPERSEDED"}

    sorted_tracks = sorted(
        roadmap["tracks"].items(),
        key=lambda kv: _TRACK_PRIORITY.get(kv[0], 999),
    )

    for track_id, info in sorted_tracks:
        for tz in info["tzs"]:
            status = tz.get("status", "OPEN").upper()
            if any(s in status for s in skip_statuses):
                continue
            selected.append({
                "track": track_id,
                "track_title": info["title"],
                "id": tz["id"],
                "desc": tz["desc"],
                "status": status,
            })
            if len(selected) >= top_n:
                return selected
    return selected


def _highest_priority_track(roadmap: dict) -> tuple[str, str, str]:
    """Return (track_id, title, pain) of the highest-priority track with any OPEN TZ."""
    sorted_tracks = sorted(
        roadmap["tracks"].items(),
        key=lambda kv: _TRACK_PRIORITY.get(kv[0], 999),
    )
    skip = {"DONE", "CLOSED", "DEFERRED", "GATED", "SUPERSEDED"}
    for track_id, info in sorted_tracks:
        for tz in info["tzs"]:
            if not any(s in tz.get("status", "OPEN").upper() for s in skip):
                return track_id, info["title"], info["pain"]
    return "?", "no open tracks", ""


def generate_sprint_from_roadmap(
    roadmap_path: Path,
    target_date: date,
    top_n: int = 3,
) -> str:
    """Generate a SPRINT for target_date using a multi-track roadmap as input."""
    roadmap = _parse_roadmap(roadmap_path)
    blockers = _read_open_blockers()
    selected = _select_open_tzs(roadmap, top_n=top_n)
    track_id, track_title, track_pain = _highest_priority_track(roadmap)
    date_str = target_date.isoformat()

    if selected:
        goal_line = f"Advance {track_id} ({track_title}) — start with {selected[0]['id']}"
    else:
        goal_line = "[No OPEN TZs across roadmap — review backlog]"

    try:
        src_str = str(roadmap_path.relative_to(ROOT)) if roadmap_path.is_absolute() else str(roadmap_path)
    except ValueError:
        src_str = str(roadmap_path)
    lines = [
        f"# SPRINT — {date_str}",
        f"# Generated by main_morning_brief.py (--roadmap mode) at {datetime.now().strftime('%H:%M')}",
        f"# Source: {src_str}",
        "",
        "---",
        "",
        "## TODAY'S GOAL",
        "",
        goal_line,
        "",
        f"**Highest-priority track:** {track_id} — {track_title}",
    ]
    if track_pain:
        lines.append(f"**Pain it closes:** {track_pain}")
    lines.append("")

    if blockers:
        lines += ["## ⚠️ OPERATOR ACTIONS PENDING (check before starting)", ""]
        for b in blockers:
            lines.append(f"- [ ] {b}")
        lines.append("")

    lines += [
        "## TODAY'S TZs",
        "",
        "| # | Track | TZ_ID | Description | Status |",
        "|---|-------|-------|-------------|--------|",
    ]
    if selected:
        for i, tz in enumerate(selected, 1):
            lines.append(f"| {i} | {tz['track']} | {tz['id']} | {tz['desc']} | {tz['status']} |")
    else:
        lines.append("| — | — | _no open TZs found_ | — | — |")
    lines.append("")

    lines += [
        "## HARD DELIVERABLES",
        "",
        "_Spec each TZ separately when entering its block; populate this section from the TZ doc._",
        "",
        "---",
        "",
        "## ANTI-DRIFT REMINDERS",
        "",
        "- Run `anti_drift_validator` CHECK 1 before each TZ",
        "- If a deliverable takes >2x estimate → TIME DRIFT, notify operator",
        "- Do NOT add scope beyond TODAY'S TZs above",
        "- Roadmap is source of truth; do not invent priorities",
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
    parser = argparse.ArgumentParser(description="Generate daily SPRINT from week plan or multi-track roadmap")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--week", help="Path to WEEK_*.md plan file (legacy mode)")
    src.add_argument("--roadmap", help="Path to MULTI_TRACK_ROADMAP.md (current mode)")
    parser.add_argument("--day", default=None, help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--top", type=int, default=3, help="Top-N TZs in roadmap mode (default 3)")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, don't write file")
    args = parser.parse_args(argv)

    target_date = date.fromisoformat(args.day) if args.day else date.today()

    if args.week:
        path = Path(args.week)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            print(f"ERROR: week plan not found: {path}", file=sys.stderr)
            return 1
        content = generate_sprint(path, target_date, dry_run=args.dry_run)
    else:
        path = Path(args.roadmap)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            print(f"ERROR: roadmap not found: {path}", file=sys.stderr)
            return 1
        content = generate_sprint_from_roadmap(path, target_date, top_n=args.top)

    if args.dry_run:
        sys.stdout.buffer.write(content.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        return 0

    SPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SPRINTS_DIR / f"SPRINT_{target_date.isoformat()}.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"SPRINT written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
