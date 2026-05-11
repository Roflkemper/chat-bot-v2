"""Detailed process inspection for /inspect TG command.

Given a pid (from /status output), returns:
  - cmdline
  - age, RSS / VMS memory
  - CPU percent (1 sec sample)
  - n threads, n open files (best-effort)
  - parent process

If pid not given, lists all bot7 .venv processes with summary.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _format_process(p) -> str:
    import psutil
    pid = p.pid
    cl = " ".join(p.cmdline())[:200]
    age_sec = time.time() - p.create_time()
    age_min = age_sec / 60
    rss_mb = _safe(lambda: p.memory_info().rss / 1024**2, 0)
    vms_mb = _safe(lambda: p.memory_info().vms / 1024**2, 0)
    cpu = _safe(lambda: p.cpu_percent(interval=1.0), 0)
    n_threads = _safe(lambda: p.num_threads(), 0)
    n_files = _safe(lambda: len(p.open_files()), "n/a")
    ppid = _safe(lambda: p.ppid(), 0)
    try:
        parent_name = psutil.Process(ppid).name() if ppid else "?"
    except Exception:
        parent_name = "?"
    lines = [
        f"pid={pid}  ({p.name()})",
        f"  cmd: {cl}",
        f"  age: {age_min:.1f}min  (started {datetime.fromtimestamp(p.create_time(), tz=timezone.utc):%Y-%m-%d %H:%M UTC})",
        f"  mem: RSS={rss_mb:.0f}MB  VMS={vms_mb:.0f}MB",
        f"  cpu: {cpu:.1f}%  threads={n_threads}  open_files={n_files}",
        f"  parent: {parent_name}(pid={ppid})",
    ]
    return "\n".join(lines)


def build_inspect_report(pid: int | None = None) -> str:
    try:
        import psutil
    except ImportError:
        return "psutil not installed"

    if pid is not None:
        try:
            p = psutil.Process(pid)
            return _format_process(p)
        except psutil.NoSuchProcess:
            return f"pid={pid} not found"
        except psutil.AccessDenied:
            return f"pid={pid} access denied"

    # List all .venv bot7 processes
    out = ["[INSPECT] all bot7 .venv processes:"]
    found = []
    for p in psutil.process_iter(["pid", "cmdline", "name"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
            if ".venv" in cl and "bot7" in cl:
                found.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    found.sort(key=lambda p: p.create_time())
    for p in found:
        out.append("")
        out.append(_format_process(p))
    if not found:
        out.append("(none)")
    return "\n".join(out)
