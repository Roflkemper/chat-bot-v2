"""TZ-CLAUDE-TZ-VALIDATOR: Validate TZ proposals against ROADMAP and QUEUE.

Checks a proposed TZ (from stdin or --text) for:
  1. Phase alignment — keywords in the TZ text map to a roadmap phase
  2. QUEUE overlap  — TZ ID or title substring already in QUEUE.md
  3. Dependencies   — referenced files/modules exist in the repo
  4. Phase prerequisites — required prior phases are complete/in_progress

Verdicts:
  APPROVED        — all checks pass, TZ is safe to add to queue
  REVIEW_NEEDED   — warnings found, operator should review before queuing
  REJECTED        — blocking issues found (phase not reached, hard dependency missing)

Usage (from c:\\bot7):
    echo "TZ text here" | python tools/validate_tz.py
    python tools/validate_tz.py --text "TZ-MY-FEATURE: do something"
    python tools/validate_tz.py --file path/to/tz.md
    python tools/validate_tz.py --text "..." --roadmap docs/STATE/ROADMAP.md
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROADMAP = ROOT / "docs" / "STATE" / "ROADMAP.md"
DEFAULT_QUEUE   = ROOT / "docs" / "STATE" / "QUEUE.md"

# ---------------------------------------------------------------------------
# Phase keyword mapping
# ---------------------------------------------------------------------------

PHASE_KEYWORDS: dict[str, list[str]] = {
    "phase0": [
        "infra", "infrastructure", "инфраструктур", "гигиена", "conflict",
        "calendar", "cascade", "pre-commit", "hook", "pre_commit",
        "memory", "defense", "guard", "test", "тест", "fixture",
        "collector", "tracker", "snapshot", "watchdog", "scheduler",
        "ohlcv", "ingest", "taskkill", "pid", "leak", "rotation",
        "state", "state_latest", "naming", "sync", "debt", "долг",
        "queue", "roadmap", "handoff",
    ],
    "phase0_5": [
        "reconcile", "engine", "движок", "backtest", "бэктест", "calibrat",
        "калибр", "sim", "симул", "engine_v2", "engine_fix", "engine_bug",
        "resolution", "instop", "combo_stop", "group.py", "contracts.py",
        "indicator", "k_factor", "k_realized", "k_volume", "ground_truth",
    ],
    "phase1": [
        "paper", "journal", "paper_journal", "paper journal", "бумажн",
        "weekly", "comparison", "report", "отчёт", "отчет",
        "advise", "адвайс", "signal", "сигнал", "phase1", "phase 1",
    ],
    "phase2": [
        "advise_v2", "advise v2", "/advise", "telegram", "телеграм",
        "push notif", "пуш", "notification", "high-confidence", "confidence",
        "operator augment", "операт", "recommend", "рекоменд",
        "h10", "h1", "h2", "bilateral", "dedup", "optimize", "оптим",
        "optimize_short", "optimize_long", "widen", "widen_long", "widen_short",
        "regime", "adaptive", "adaptive_grid", "grid_search", "coordinated",
    ],
    "phase3": [
        "auto", "авто", "full_auto", "semi.auto", "tactic", "тактич",
        "bot_management", "size_reduction", "dd_management", "amplifier",
        "усилитель", "pause bot", "start bot", "stop bot",
        "autonomous", "авто.торг",
    ],
}

PHASE_ORDER = ["phase0", "phase0_5", "phase1", "phase2", "phase3"]

PHASE_NAMES = {
    "phase0":   "Фаза 0 — Infrastructure & гигиена",
    "phase0_5": "Фаза 0.5 — Engine validation",
    "phase1":   "Фаза 1 — Paper Journal Launch",
    "phase2":   "Фаза 2 — Operator Augmentation",
    "phase3":   "Фаза 3 — Tactical Bot Management",
}

# Phases currently active (in_progress) per ROADMAP
ACTIVE_PHASES = {"phase0", "phase0_5", "phase1"}

# Phase 3 pre-requisites (from ROADMAP)
PHASE3_PREREQS = [
    "Reconcile GREEN",
    "30+ days Phase 2 reports",
    "GinArea API automation tested",
]


# ---------------------------------------------------------------------------
# Skills enforcement rules
# ---------------------------------------------------------------------------

DEFAULT_SKILLS_DIR = ROOT / ".claude" / "skills"

# Always-required skills (apply to every TZ)
ALWAYS_REQUIRED_SKILLS = ("trader_first_filter",)

# (lowercase keyword tokens, required skill name)
# If any keyword token appears in TZ text → required skill must be in Skills applied.
SKILL_KEYWORD_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("new module", "implement", "create new", "build", "add feature"),
        "project_inventory_first",
    ),
    (
        ("thresholds", "tp/sl", "grid_step", "target_profit", "instop", "constants"),
        "param_provenance_tracker",
    ),
    (
        ("live", "rollout", "deploy", "restart", "kill", "supervisor"),
        "live_position_safety",
    ),
    (
        ("run_tests", "regression", "commit"),
        "regression_baseline_keeper",
    ),
    # New trading-research integrity rules (TZ-ADD-TRADING-SKILLS):
    (
        ("k_short", "k_long", "k_factor", "calibration constant",
         "expected_pnl", "/advise"),
        "calibration_drift_monitor",
    ),
    (
        ("best config", "winning", "champion config", "top params",
         "оптимальн", "лучшая комбинация", "grid search", "sweep"),
        "survivorship_audit",
    ),
    (
        ("backtest", "reconcile", "replay", "simulate", "sim",
         "бэктест"),
        "lookahead_bias_guard",
    ),
    (
        ("$/year", "% apy", "annualized", "expected edge",
         "годовая доходность"),
        "multi_year_validator",
    ),
    (
        ("ohlcv", "frozen csv", "ground_truth", "snapshots.csv",
         "_2y.csv", "_1y_full"),
        "dataset_provenance_tracker",
    ),
]

# Phase 2/3/4 trigger keywords — enforce phase_aware_planning
PHASE_AWARE_TRIGGERS: tuple[str, ...] = (
    "/advise",
    "auto bot management",
    "ginarea api write",
    "phase 2",
    "phase 3",
    "phase 4",
)


_SKILLS_HEADER_RE = re.compile(
    r"Skills\s+applied\s*:\s*(.*?)(?:\n\s*\n|\Z|^=+\s*$|^---\s*$)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_SKILL_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def _keyword_in_text(keyword: str, text_lower: str) -> bool:
    """Check if keyword appears in text, with word-boundary for single tokens.

    Multi-word phrases use plain substring match.
    Single-word tokens use a leading word-boundary so e.g. 'kill' does not
    match inside 'Skills'.
    """
    if " " in keyword or "/" in keyword:
        return keyword in text_lower
    return re.search(r"\b" + re.escape(keyword), text_lower) is not None


def _list_existing_skills(skills_dir: Path = DEFAULT_SKILLS_DIR) -> set[str]:
    """Return set of skill stems (filename without .md) present in skills dir."""
    if not skills_dir.exists():
        return set()
    return {p.stem for p in skills_dir.glob("*.md")}


def _parse_skills_block(tz_text: str) -> tuple[bool, list[str]]:
    """Extract Skills applied block. Returns (header_found, skill_names_list).

    Handles both bullet list (lines starting with '-') and inline comma-separated.
    Stops at blank line, divider line (=== or ---), or end of text.
    """
    m = _SKILLS_HEADER_RE.search(tz_text)
    if not m:
        return False, []

    block = m.group(1)
    skills: list[str] = []

    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            break  # blank line ends the block
        if line.startswith("=") or line.startswith("---"):
            break

        # Strip leading bullet marker
        if line.startswith(("- ", "* ", "• ")):
            line = line[2:].strip()

        # Some lines have "skill_name — description" — keep only the part before
        # the separator. Inline-comma format (skill1, skill2) must be preserved,
        # so we split on " — " / " - " / "—" but not on bare ":" (which would
        # mangle URLs or sub-headers).
        for sep in (" — ", " - ", "—"):
            if sep in line:
                line = line.split(sep, 1)[0].strip()
                break

        # Comma- or whitespace-separated multiple skills on one line
        for token in _SKILL_TOKEN_RE.findall(line):
            tl = token.lower()
            if tl not in skills and tl not in ("skills", "applied"):
                skills.append(tl)

    return True, skills


def check_skills_section(
    tz_text: str,
    phase: str | None = None,
    skills_dir: Path = DEFAULT_SKILLS_DIR,
) -> tuple[bool, list[str]]:
    """Validate the Skills applied section of a TZ.

    Returns (ok, errors). `ok=True` only when no blocking issue found.

    Rules:
      1. "Skills applied:" header must be present
      2. List must be non-empty
      3. Every skill name listed must exist as .claude/skills/<name>.md
      4. ALWAYS_REQUIRED_SKILLS must always be present
      5. SKILL_KEYWORD_RULES — keyword in text → required skill must be present
      6. Phase 2/3/4 keyword OR detected phase in {phase2, phase3} → require
         phase_aware_planning
    """
    errors: list[str] = []
    text_lower = tz_text.lower()
    existing = _list_existing_skills(skills_dir)

    header_found, listed = _parse_skills_block(tz_text)
    if not header_found:
        errors.append("Skills applied: section is missing")
        return False, errors

    if not listed:
        errors.append("Skills applied: section is empty (no skill names found)")
        return False, errors

    listed_set = set(listed)

    # Rule 3: every listed skill must exist as a file
    if existing:
        for skill in listed:
            if skill not in existing:
                errors.append(
                    f"Skill '{skill}' referenced but not found in {skills_dir.name}/"
                )

    # Rule 4: always-required skills
    for required in ALWAYS_REQUIRED_SKILLS:
        if required not in listed_set:
            errors.append(
                f"Mandatory skill '{required}' missing (always-required for every TZ)"
            )

    # Rule 5: keyword-triggered required skills.
    # Strip the Skills applied block from the search text so keyword tokens
    # like "kill" don't false-match against substrings of "Skills" itself.
    text_for_keyword_match = _SKILLS_HEADER_RE.sub("", tz_text).lower()

    for keywords, required in SKILL_KEYWORD_RULES:
        triggered = next(
            (kw for kw in keywords if _keyword_in_text(kw, text_for_keyword_match)),
            None,
        )
        if triggered and required not in listed_set:
            errors.append(
                f"Skill '{required}' missing — required by keyword '{triggered}' in TZ"
            )

    # Rule 6: phase_aware_planning enforcement
    phase_triggered = next(
        (kw for kw in PHASE_AWARE_TRIGGERS
         if _keyword_in_text(kw, text_for_keyword_match)),
        None,
    )
    needs_phase_skill = phase_triggered is not None or phase in ("phase2", "phase3")
    if needs_phase_skill and "phase_aware_planning" not in listed_set:
        reason = (
            f"keyword '{phase_triggered}'" if phase_triggered
            else f"detected phase {phase}"
        )
        errors.append(
            f"Skill 'phase_aware_planning' missing — required by {reason}"
        )

    return (not errors), errors


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    verdict: str  # APPROVED | REVIEW_NEEDED | REJECTED
    phase_detected: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [f"VERDICT: {self.verdict}"]
        if self.phase_detected:
            lines.append(f"Phase detected: {PHASE_NAMES.get(self.phase_detected, self.phase_detected)}")
        if self.errors:
            lines.append("\nERRORS (blocking):")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            lines.append("\nWARNINGS (review needed):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if self.info:
            lines.append("\nINFO:")
            for i in self.info:
                lines.append(f"  • {i}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase detection
# ---------------------------------------------------------------------------

def detect_phase(text: str) -> str | None:
    """Return the highest-priority phase whose keywords appear in text."""
    text_lower = text.lower()
    hits: dict[str, int] = {}
    for phase, keywords in PHASE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            hits[phase] = count

    if not hits:
        return None
    # Among phases with hits, prefer the one with most keyword matches;
    # break ties by phase order (earlier phase wins).
    return max(hits, key=lambda p: (hits[p], -PHASE_ORDER.index(p)))


# ---------------------------------------------------------------------------
# QUEUE overlap check
# ---------------------------------------------------------------------------

def _extract_tz_id(text: str) -> str | None:
    """Extract TZ-XXX identifier from text (first match)."""
    m = re.search(r'\bTZ-[A-Z0-9][A-Z0-9\-_]{1,40}\b', text)
    return m.group(0) if m else None


def check_queue_overlap(tz_text: str, queue_path: Path) -> list[str]:
    """Return list of overlap warnings (TZ ID or similar title found in QUEUE)."""
    if not queue_path.exists():
        return [f"QUEUE file not found: {queue_path}"]

    queue_content = queue_path.read_text(encoding="utf-8")
    warnings: list[str] = []

    tz_id = _extract_tz_id(tz_text)
    if tz_id and tz_id in queue_content:
        warnings.append(f"TZ ID '{tz_id}' already exists in QUEUE.md")

    # Title substring check: extract first non-blank line of TZ text
    first_line = next((l.strip() for l in tz_text.splitlines() if l.strip()), "")
    title_words = re.findall(r'[A-Za-zА-Яа-я0-9]{4,}', first_line)
    for word in title_words:
        if word.upper() in queue_content.upper() and len(word) >= 6:
            warnings.append(f"Title keyword '{word}' found in QUEUE.md — possible duplicate")
            break  # one warning is enough

    return warnings


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

_FILE_REF_PATTERN = re.compile(
    r'[`"\']([a-zA-Z0-9_\-./\\]+\.(py|json|yaml|yml|csv|md|txt))[`"\']'
)
_MODULE_REF_PATTERN = re.compile(
    r'\b(services|tools|src|tests|scripts|config|bot7|ginarea_tracker)'
    r'[./\\][a-zA-Z0-9_./\\-]{3,}'
)


def check_dependencies(tz_text: str, root: Path) -> tuple[list[str], list[str]]:
    """Check if referenced files exist. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    file_refs: set[str] = set()
    for m in _FILE_REF_PATTERN.finditer(tz_text):
        file_refs.add(m.group(1))
    for m in _MODULE_REF_PATTERN.finditer(tz_text):
        # Normalise path separators
        ref = m.group(0).replace("\\", "/")
        # Strip trailing punctuation
        ref = ref.rstrip(".,;:)>\"'")
        file_refs.add(ref)

    for ref in file_refs:
        # Skip generic words that match the pattern but aren't real paths
        if any(ref.startswith(skip) for skip in ("src/main", "src/com", "services/v")):
            continue
        candidate = root / Path(ref.replace("/", "\\"))
        if not candidate.exists():
            # Check relative without root-level component
            parts = Path(ref).parts
            if len(parts) > 1:
                candidate2 = root / Path(*parts[1:])
                if candidate2.exists():
                    continue
            warnings.append(f"Referenced path not found: {ref}")

    return errors, warnings


# ---------------------------------------------------------------------------
# Phase alignment check
# ---------------------------------------------------------------------------

def check_phase_alignment(
    phase: str | None,
    tz_text: str,
    roadmap_path: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Check phase alignment. Returns (errors, warnings, info)."""
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if phase is None:
        warnings.append(
            "Could not detect phase from TZ keywords. "
            "Add phase tag (e.g. 'Phase 0 / Phase 2') or relevant keywords."
        )
        return errors, warnings, info

    if phase in ACTIVE_PHASES:
        info.append(
            f"Phase {phase} is currently active (in_progress) — TZ is in scope"
        )
    elif phase == "phase2":
        warnings.append(
            "TZ appears to be Phase 2 (Operator Augmentation) work. "
            "Phase 2 is 'planned' — not yet active. "
            "Acceptable only if explicitly pre-staged or labeled IDEA."
        )
    elif phase == "phase3":
        errors.append(
            "TZ appears to be Phase 3 (Tactical Bot Management) work. "
            "Phase 3 pre-requisites not met: Reconcile GREEN, 30+ days Phase 2, "
            "GinArea API automation tested. Mark as IDEA or defer."
        )
    else:
        warnings.append(f"Unknown phase detected: {phase}")

    return errors, warnings, info


# ---------------------------------------------------------------------------
# Phase prerequisites check (for Phase 2+ TZs)
# ---------------------------------------------------------------------------

def check_prerequisites(phase: str | None, roadmap_path: Path) -> list[str]:
    """Return list of unmet prerequisite warnings."""
    warnings: list[str] = []
    if phase not in ("phase2", "phase3"):
        return warnings

    if not roadmap_path.exists():
        warnings.append(f"ROADMAP file not found: {roadmap_path}")
        return warnings

    roadmap = roadmap_path.read_text(encoding="utf-8")

    if phase == "phase2":
        # Phase 2 requires Phase 0, 0.5, 1 to be done or in_progress
        for req_phase in ("phase0", "phase0_5", "phase1"):
            name = PHASE_NAMES[req_phase]
            if "in_progress" not in roadmap.lower() and name not in roadmap:
                warnings.append(
                    f"Phase 2 pre-requisite check: confirm {name} is in_progress"
                )

    if phase == "phase3":
        for prereq in PHASE3_PREREQS:
            warnings.append(
                f"Phase 3 pre-requisite not verified: '{prereq}'"
            )

    return warnings


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

def validate(
    tz_text: str,
    roadmap_path: Path = DEFAULT_ROADMAP,
    queue_path: Path = DEFAULT_QUEUE,
    root: Path = ROOT,
    skills_dir: Path | None = None,
    enforce_skills: bool = True,
) -> ValidationResult:
    """Run all checks and return ValidationResult."""
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    phase = detect_phase(tz_text)

    # 1. Phase alignment
    p_err, p_warn, p_info = check_phase_alignment(phase, tz_text, roadmap_path)
    errors.extend(p_err)
    warnings.extend(p_warn)
    info.extend(p_info)

    # 2. QUEUE overlap
    q_warn = check_queue_overlap(tz_text, queue_path)
    warnings.extend(q_warn)

    # 3. Dependency check
    d_err, d_warn = check_dependencies(tz_text, root)
    errors.extend(d_err)
    warnings.extend(d_warn)

    # 4. Phase prerequisites
    pre_warn = check_prerequisites(phase, roadmap_path)
    warnings.extend(pre_warn)

    # 5. Skills applied section
    if enforce_skills:
        s_dir = skills_dir if skills_dir is not None else (root / ".claude" / "skills")
        s_ok, s_errors = check_skills_section(tz_text, phase=phase, skills_dir=s_dir)
        errors.extend(s_errors)

    # Determine verdict
    if errors:
        verdict = "REJECTED"
    elif warnings:
        verdict = "REVIEW_NEEDED"
    else:
        verdict = "APPROVED"

    return ValidationResult(
        verdict=verdict,
        phase_detected=phase,
        errors=errors,
        warnings=warnings,
        info=info,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate a TZ proposal against ROADMAP and QUEUE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--text",  "-t", help="TZ text inline")
    group.add_argument("--file",  "-f", help="Path to TZ markdown file")
    p.add_argument("--roadmap", default=str(DEFAULT_ROADMAP), help="Path to ROADMAP.md")
    p.add_argument("--queue",   default=str(DEFAULT_QUEUE),   help="Path to QUEUE.md")
    p.add_argument("--root",    default=str(ROOT),            help="Repo root for dep checks")
    p.add_argument("--json",    action="store_true",           help="Output as JSON")
    return p


def _setup_stdout_utf8() -> None:
    """encoding_safety: ensure stdout can emit non-ASCII (✗, ⚠, •, →, etc.)
    on Windows terminals where the default encoding is cp1251."""
    import io
    if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and \
            sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8bom"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )


def main(argv: list[str] | None = None) -> int:
    _setup_stdout_utf8()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.text:
        tz_text = args.text
    elif args.file:
        tz_text = Path(args.file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        tz_text = sys.stdin.read()
    else:
        parser.print_help()
        return 2

    result = validate(
        tz_text,
        roadmap_path=Path(args.roadmap),
        queue_path=Path(args.queue),
        root=Path(args.root),
    )

    if args.json:
        import json
        print(json.dumps({
            "verdict": result.verdict,
            "phase_detected": result.phase_detected,
            "errors": result.errors,
            "warnings": result.warnings,
            "info": result.info,
        }, ensure_ascii=False, indent=2))
    else:
        print(result.to_text())

    return 0 if result.verdict == "APPROVED" else 1


if __name__ == "__main__":
    sys.exit(main())
