"""Daily change log — recap what happened in the last 24h.

Renders a markdown summary in docs/CHANGELOG_DAILY.md combining:
  - Git commits in last 24h with one-line subject
  - Setup_precision tracker status changes (new DEGRADED, INSUFFICIENT→EVALUATING, etc)
  - KPI alerts that fired
  - Bot restart count
  - Top emitted detector types

Output: docs/CHANGELOG_DAILY.md (overwritten each run; persistent
history is git log itself).

Cron: bot7-daily-change-log-09am (runs after daily KPI).
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "CHANGELOG_DAILY.md"
WINDOW_H = 24


def _git_commits_last_24h() -> list[tuple[str, str]]:
    """Returns list of (hash, subject) commits in last WINDOW_H hours."""
    try:
        result = subprocess.run(
            ["git", "log", f"--since={WINDOW_H} hours ago",
             "--pretty=format:%h|%s"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        out = []
        for line in result.stdout.splitlines():
            if "|" not in line: continue
            h, subject = line.split("|", 1)
            out.append((h.strip(), subject.strip()))
        return out
    except Exception:
        return []


def _read_jsonl_window(path: Path, hours: int) -> list[dict]:
    if not path.exists(): return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
    out = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("ts")
                if not ts: continue
                try:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                    if dt.timestamp() >= cutoff:
                        out.append(rec)
                except ValueError:
                    continue
        return out
    except OSError:
        return []


def main() -> int:
    now = datetime.now(timezone.utc)
    lines = []
    lines.append(f"# Daily change log — {now:%Y-%m-%d}")
    lines.append("")
    lines.append(f"_Auto-generated {now.strftime('%H:%M UTC')} covering last {WINDOW_H}h_")
    lines.append("")

    # ── Commits ────────────────────────────────────────────────────────────
    commits = _git_commits_last_24h()
    lines.append(f"## Commits ({len(commits)})")
    lines.append("")
    if commits:
        for h, subject in commits:
            lines.append(f"- `{h}` {subject}")
    else:
        lines.append("- (none)")
    lines.append("")

    # ── Pipeline metrics summary ──────────────────────────────────────────
    metrics = _read_jsonl_window(ROOT / "state" / "pipeline_metrics.jsonl", WINDOW_H)
    if metrics:
        stage_counts = Counter(m.get("stage_outcome") for m in metrics)
        emitted = sum(1 for m in metrics if m.get("stage_outcome") == "emitted")
        lines.append(f"## Pipeline ({len(metrics)} events, {emitted} setups emitted)")
        lines.append("")
        for stage, n in stage_counts.most_common():
            lines.append(f"- {stage}: {n}")
        lines.append("")

    # ── Restarts ──────────────────────────────────────────────────────────
    restarts = _read_jsonl_window(ROOT / "state" / "app_runner_starts.jsonl", WINDOW_H)
    if restarts:
        lines.append(f"## app_runner restarts: {len(restarts)}")
        if len(restarts) > 20:
            lines.append("")
            lines.append("[WARN] elevated restart count — check watchdog audit")
        lines.append("")

    # ── P-15 equity ───────────────────────────────────────────────────────
    p15_events = _read_jsonl_window(ROOT / "state" / "p15_equity.jsonl", WINDOW_H)
    if p15_events:
        pnl_total = sum(float(e.get("realized_pnl_usd") or 0) for e in p15_events)
        opens = sum(1 for e in p15_events if e.get("stage") == "OPEN")
        closes = sum(1 for e in p15_events if e.get("stage") == "CLOSE")
        harvests = sum(1 for e in p15_events if e.get("stage") == "HARVEST")
        lines.append("## P-15 lifecycle")
        lines.append("")
        lines.append(f"- realized PnL: ${pnl_total:+.2f}")
        lines.append(f"- OPEN: {opens}, HARVEST: {harvests}, CLOSE: {closes}")
        lines.append("")

    # ── GC audit ──────────────────────────────────────────────────────────
    audit = _read_jsonl_window(ROOT / "state" / "gc_confirmation_audit.jsonl", WINDOW_H)
    if audit:
        decisions = Counter(str(r.get("decision", "")).split("(")[0].strip() for r in audit)
        lines.append("## GC decisions")
        lines.append("")
        for d, n in decisions.most_common():
            lines.append(f"- {d}: {n}")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[change-log] wrote {OUT}")
    print("\n".join(lines[:30]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
