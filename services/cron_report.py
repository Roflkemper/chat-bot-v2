"""Read-only summary of Windows Task Scheduler bot7-* tasks for /cron command.

Calls schtasks.exe via subprocess (no PowerShell needed). Renders compact
list of registered tasks with state, last run, last result, next run.
"""
from __future__ import annotations

import subprocess
from datetime import datetime


def _query_tasks() -> list[dict]:
    """Returns list of {name, state, last_run, last_result, next_run} for
    bot7-* tasks. Empty list on any error.

    Uses schtasks /Query /FO CSV /V which produces verbose CSV per task.
    We filter to TaskName starting with bot7-.
    """
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/FO", "CSV", "/V", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    import csv
    import io
    out = []
    # Header columns (schtasks /V /NH still has implicit ordering — we use known indices)
    # Columns in /V /NH: HostName, TaskName, NextRunTime, Status, LogonMode,
    #   LastRunTime, LastResult, Author, TaskToRun, StartIn, Comment, ...
    reader = csv.reader(io.StringIO(result.stdout))
    for row in reader:
        if len(row) < 7: continue
        name = row[1].strip().lstrip("\\")
        if not name.startswith("bot7-"): continue
        out.append({
            "name": name,
            "next_run": row[2].strip(),
            "state": row[3].strip(),
            "last_run": row[5].strip(),
            "last_result": row[6].strip(),
        })
    # dedupe by name (some tasks repeat per trigger)
    seen = {}
    for r in out:
        if r["name"] not in seen:
            seen[r["name"]] = r
    return list(seen.values())


def build_cron_report() -> str:
    tasks = _query_tasks()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"[CRON] bot7-* scheduled tasks  ({now})"]
    if not tasks:
        lines.append("(none — schtasks query returned empty)")
        return "\n".join(lines)

    # Sort by name for readability
    tasks.sort(key=lambda t: t["name"])
    lines.append("")
    lines.append(f"{'task':<35} {'state':<10} {'last':<20} {'result':<10} next")
    lines.append("-" * 100)
    for t in tasks:
        # last_run/next_run can be 'N/A' or 'Disabled'.
        last = t["last_run"][:19] if t["last_run"] not in ("N/A", "") else "n/a"
        nxt = t["next_run"][:19] if t["next_run"] not in ("N/A", "") else "n/a"
        result = t["last_result"]
        if result == "267011":
            result = "never"
        elif result == "0":
            result = "ok"
        lines.append(
            f"{t['name']:<35} {t['state']:<10} {last:<20} {result:<10} {nxt}"
        )

    lines.append("")
    lines.append(f"Total: {len(tasks)} tasks")
    return "\n".join(lines)
