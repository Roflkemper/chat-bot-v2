"""Read-only summary of scheduled tasks for /cron command.

On Windows: calls schtasks.exe and filters bot7-* tasks.
On Mac: calls launchctl list and filters com.bot7.* labels.
On Linux: empty (no implementation yet).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime


def _query_tasks_mac() -> list[dict]:
    """Returns list of bot7 tasks visible to launchctl on Mac.

    `launchctl list` output columns: PID, Status, Label.
    We don't have last/next run from this — would need launchctl print
    per-label which is slow. Return minimal: name + state.
    """
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    out = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.split("\t")
        if len(parts) < 3: continue
        label = parts[2].strip()
        if not label.startswith("com.bot7."):
            continue
        pid = parts[0].strip()
        status = parts[1].strip()
        state = "Running" if pid != "-" else ("Ready" if status == "0" else f"Status={status}")
        out.append({
            "name": label,
            "state": state,
            "last_run": "n/a",
            "last_result": status if status != "0" else "ok",
            "next_run": "n/a",
        })
    return out


def _query_tasks() -> list[dict]:
    """Returns list of {name, state, last_run, last_result, next_run} for
    bot7-* tasks. Empty list on any error.

    Uses schtasks /Query /FO CSV /V on Windows; launchctl on Mac.
    """
    if sys.platform == "darwin":
        return _query_tasks_mac()
    if sys.platform != "win32":
        return []  # Linux/other — no implementation

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
