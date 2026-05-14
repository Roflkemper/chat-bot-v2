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


def _load_skills() -> list[tuple[str, str]]:
    """Return (filename_stem, content) for all .md files in .claude/skills/."""
    skills_dir = ROOT / ".claude" / "skills"
    if not skills_dir.exists():
        return []
    result = []
    for p in sorted(skills_dir.glob("*.md")):
        result.append((p.stem, _read(p)))
    return result


_ARCHITECTURE_GAPS = """
### GAP-01: Dashboard HTTP Server

- `services/dashboard/http_server.py` — РЕАЛИЗОВАН и подключён в `app_runner.py`
- Служит `docs/dashboard.html` на `http://127.0.0.1:8765/` (или 8766/8767)
- Запускается вместе с ботом через `python app_runner.py`
- `state/dashboard_state.json` пересобирается каждые 5 минут через `state_builder.py`
- Инструмент открытия: `tools/dashboard_open.py`
- Статус: **РАБОТАЕТ** при запущенном app_runner.py

### GAP-02: Param Sweep Infrastructure

- `tools/sweep_runner.py` — CLI runner для sweep конфигураций
- `tools/klod_impulse_grid_search.py` — 96-combo trigger param search (TZ-KLOD-IMPULSE-GRID-SEARCH)
- `services/coordinated_grid/grid_search.py` — 256 конфигураций coordinated grid
- `services/coordinated_grid/trim_analyzer.py` — инструментированный wrapper, захватывает trim events
- Статус: инфраструктура есть. Следующие sweep: TZ-057/065/066 (ждут H10 backtest overnight)

### GAP-03: _recovery/restored/ модули

- `_recovery/restored/` содержит 34 модуля из прошлой сессии восстановления
- Статус каждого: задокументирован в `docs/STATE/RESTORED_FEATURES_AUDIT_*.json`
- НЕ реактивировать cascade.py — известный дубликат
- Перед реактивацией любого: прочитать audit + пройти skill `project_inventory_first`

### GAP-04: DEBT-04 — 91 collection errors

- Split plan готов: `reports/debt_04_split_plan_2026-05-02.md`
- TZ-DEBT-04-A..E в backlog
- Приоритет: FIX-BEFORE-PHASE-2

### GAP-05: Instop semantics для LONG (operator action needed)

- TZ-ENGINE-FIX-INSTOP-SEMANTICS-B открыт
- Нужно подтверждение оператора: Semant A или B для LONG_C/D
- Блокирует полную reconcile v3
"""


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
    """Generate HANDOFF_YYYY-MM-DD.md combining all 3 layers + skills + gaps."""
    today = output_date or date.today().isoformat()
    out = output_path or (CONTEXT_DIR / f"HANDOFF_{today}.md")

    project_ctx = _read(PROJECT_CONTEXT)
    state_text = _read(STATE_CURRENT)
    deltas = _latest_session_deltas(2)
    git_log = _git_log_today()
    skills = _load_skills()

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
        "## PART 5 — Skills Inventory (.claude/skills/)",
        "",
        "> ОБЯЗАТЕЛЬНО для нового Claude: каждый TZ должен завершаться секцией",
        '> "Skills applied: <list>". Без этой секции TZ некорректен.',
        "",
    ]

    if skills:
        lines.append(f"Всего skills: {len(skills)}\n")
        for stem, content in skills:
            lines.append(f"### Skill: {stem}")
            lines.append("")
            lines.append(content.strip())
            lines.append("")
            lines.append("---")
            lines.append("")
    else:
        lines.append("*(skills directory not found or empty)*")
        lines.append("")

    lines += [
        "---",
        "",
        "## PART 6 — Architecture Gaps & Known State",
        "",
        _ARCHITECTURE_GAPS.strip(),
        "",
        "---",
        "",
        "## How to use this handoff",
        "",
        "Paste this document into a new Claude chat. Then say:",
        "",
        '> "Прочитай handoff. Подтверди в 7 строках:',
        '> 1. Главная цель проекта',
        '> 2. Что построено в последней сессии (из SESSION_DELTA)',
        '> 3. Year backtest BTCUSDT — главные числа',
        '> 4. ВСЕ skills из PART 5 — назови каждый с trigger condition (одной строкой)',
        '> 5. Known gaps из PART 6 — что из них blocking',
        '> 6. Operator feedback — что НЕ делать (из SESSION_DELTA decisions)',
        '> 7. Что считаешь next critical TZ"',
        "",
        "Не задавай оператору объяснять стратегию — всё в §2-§3 выше.",
        "Не создавай новые модули без прохождения skill `project_inventory_first`.",
        "Каждый TZ завершается: `Skills applied: <list>`.",
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
