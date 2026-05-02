"""Handoff CLI — generates, validates, and updates context documents.

Commands:
    python tools/handoff.py generate [--date YYYY-MM-DD] [--output PATH]
    python tools/handoff.py validate
    python tools/handoff.py update-state

Output: docs/CONTEXT/HANDOFF_YYYY-MM-DD.md (combine of 3 layers)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_DIR = ROOT / "docs" / "CONTEXT"
PROJECT_CONTEXT = CONTEXT_DIR / "PROJECT_CONTEXT.md"
STATE_CURRENT = CONTEXT_DIR / "STATE_CURRENT.md"
QUEUE_MD = ROOT / "docs" / "STATE" / "QUEUE.md"
ROADMAP_MD = ROOT / "docs" / "STATE" / "ROADMAP.md"


# ── helpers ──────────────────────────────────────────────────────────────────

def _read(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return fallback


def _latest_session_deltas(n: int = 2) -> list[tuple[str, str]]:
    """Return (date_str, content) for the most recent n SESSION_DELTA files."""
    deltas = sorted(CONTEXT_DIR.glob("SESSION_DELTA_*.md"), reverse=True)[:n]
    result = []
    for p in deltas:
        date_str = p.stem.replace("SESSION_DELTA_", "")
        result.append((date_str, _read(p)))
    return result


def _git_log_today() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=24 hours ago", "--no-walk=sorted"],
            capture_output=True, text=True, cwd=ROOT
        )
        return result.stdout.strip() or "(no commits in last 24h)"
    except Exception:
        return "(git unavailable)"


def _strip_frontmatter_comment(text: str) -> str:
    """Remove leading # comment lines (used as front-matter in context docs)."""
    lines = text.splitlines()
    out = []
    skip = True
    for line in lines:
        if skip and (line.startswith("# ") or line == ""):
            # Skip leading comment/blank lines that are front-matter
            if line.startswith("# ") and ("VERSION" in line.upper() or "ДАТА" in line.upper()
                                           or "СТАТУС" in line.upper() or "НАЗНАЧЕНИЕ" in line.upper()
                                           or "Версия" in line or "Дата" in line
                                           or "STATIC" in line or "TRANSIENT" in line):
                continue
        skip = False
        out.append(line)
    return "\n".join(out)


# ── generate ─────────────────────────────────────────────────────────────────

def generate(output_date: str | None = None, output_path: Path | None = None) -> Path:
    """Generate HANDOFF_YYYY-MM-DD.md combining all 3 layers."""
    today = output_date or date.today().isoformat()
    out = output_path or (CONTEXT_DIR / f"HANDOFF_{today}.md")

    project_ctx = _read(PROJECT_CONTEXT)
    state_text = _read(STATE_CURRENT)
    deltas = _latest_session_deltas(2)
    git_log = _git_log_today()

    lines: list[str] = [
        f"# Claude Session Handoff — {today}",
        "",
        "> Paste this into a new Claude chat as first message after a brief greeting.",
        "> Claude will immediately have full project context and can continue without onboarding.",
        "",
        "---",
        "",
        "## PART 1 — Project Mechanics & Strategy",
        "",
        project_ctx.strip(),
        "",
        "---",
        "",
        "## PART 2 — Current State",
        "",
        state_text.strip(),
        "",
        "---",
        "",
        "## PART 3 — Recent Session Deltas",
        "",
    ]

    if deltas:
        for date_str, delta_text in deltas:
            lines.append(f"### Delta {date_str}")
            lines.append("")
            lines.append(delta_text.strip())
            lines.append("")
    else:
        lines.append("*(no session deltas found)*")
        lines.append("")

    lines += [
        "---",
        "",
        "## PART 4 — Git log (last 24h)",
        "",
        "```",
        git_log,
        "```",
        "",
        "---",
        "",
        "## How to use this handoff",
        "",
        "Paste this document into a new Claude chat. Then say:",
        "",
        '> "Прочитай handoff. Подтверди в 5 строках: (1) главная цель проекта,'
        ' (2) текущий phase статус, (3) топ-3 open TZ, (4) последние calibration K-числа,'
        ' (5) что ты сделаешь первым делом."',
        "",
        "Не задавай оператору объяснять стратегию — всё в §2-§3 выше.",
    ]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ── validate ─────────────────────────────────────────────────────────────────

def validate() -> list[str]:
    """Run consistency checks. Returns list of warnings (empty = all OK)."""
    warnings: list[str] = []

    checks: list[tuple[str, Path, str]] = [
        ("PROJECT_CONTEXT exists", PROJECT_CONTEXT, r"."),
        ("STATE_CURRENT exists", STATE_CURRENT, r"."),
        ("Phase 1 mentioned in STATE_CURRENT", STATE_CURRENT, r"Paper Journal"),
        ("K_SHORT in STATE_CURRENT", STATE_CURRENT, r"K_SHORT"),
        ("indicator gate in PROJECT_CONTEXT", PROJECT_CONTEXT, r"indicator"),
        ("HARD BAN in PROJECT_CONTEXT", PROJECT_CONTEXT, r"HARD BAN"),
        ("Phase roadmap in PROJECT_CONTEXT", PROJECT_CONTEXT, r"Phase roadmap"),
        ("QUEUE.md exists", QUEUE_MD, r"."),
        ("ROADMAP.md exists", ROADMAP_MD, r"."),
    ]

    for desc, path, pattern in checks:
        if not path.exists():
            warnings.append(f"MISSING: {desc} — {path}")
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if not re.search(pattern, content):
            warnings.append(f"PATTERN NOT FOUND: {desc} (pattern={pattern!r})")

    # Check STATE_CURRENT is recent (modified in last 7 days)
    if STATE_CURRENT.exists():
        age_days = (datetime.now().timestamp() - STATE_CURRENT.stat().st_mtime) / 86400
        if age_days > 7:
            warnings.append(f"STALE: STATE_CURRENT.md last modified {age_days:.0f} days ago (>7)")

    # Check SESSION_DELTA exists for today
    today_delta = CONTEXT_DIR / f"SESSION_DELTA_{date.today().isoformat()}.md"
    if not today_delta.exists():
        warnings.append(f"MISSING: No SESSION_DELTA for today ({today_delta.name})")

    return warnings


# ── update-state ─────────────────────────────────────────────────────────────

def update_state() -> None:
    """Print instructions for manually updating STATE_CURRENT.md."""
    print("To update STATE_CURRENT.md:")
    print(f"  Edit: {STATE_CURRENT}")
    print()
    print("Sections to update:")
    print("  §1 PHASE STATUS — update 'Прогресс' column")
    print("  §2 ПОСЛЕДНИЕ RESULTS — add new TZ completions at top of 'Completed' list")
    print("  §3 CALIBRATION NUMBERS — update if calibration re-run")
    print("  §4 OPEN TZs — add/close/update tasks")
    print("  §5 OPERATOR PENDING ACTIONS — add/remove actions")
    print("  §6 CHANGELOG — add one line: 'YYYY-MM-DD | what changed'")
    print()
    print(f"Also create: docs/CONTEXT/SESSION_DELTA_{date.today().isoformat()}.md")
    print("Template available at: docs/CONTEXT/SESSION_DELTA_2026-05-02.md")


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Handoff CLI — generate/validate/update context documents"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen_p = sub.add_parser("generate", help="Generate HANDOFF_YYYY-MM-DD.md")
    gen_p.add_argument("--date", help="Override date (YYYY-MM-DD)")
    gen_p.add_argument("--output", type=Path, help="Override output path")
    gen_p.add_argument("--preview", action="store_true", help="Print first 50 lines to terminal")

    sub.add_parser("validate", help="Run consistency checks on context docs")
    sub.add_parser("update-state", help="Print instructions to update STATE_CURRENT.md")

    args = parser.parse_args(argv)

    if args.cmd == "generate":
        out = generate(args.date, args.output)
        lines = out.read_text(encoding="utf-8").splitlines()
        print(f"Generated: {out}")
        print(f"Lines: {len(lines)}")
        if args.preview:
            preview_text = "\n".join(lines[:50])
            if len(lines) > 50:
                preview_text += f"\n... ({len(lines) - 50} more lines)"
            sys.stdout.buffer.write((preview_text + "\n").encode("utf-8", errors="replace"))

    elif args.cmd == "validate":
        warnings = validate()
        if not warnings:
            print("All checks passed.")
        else:
            print(f"{len(warnings)} warning(s):")
            for w in warnings:
                print(f"  ⚠️  {w}")
        return 1 if warnings else 0

    elif args.cmd == "update-state":
        update_state()

    return 0


if __name__ == "__main__":
    sys.exit(main())
