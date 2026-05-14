"""bot7 supervisor CLI.

Usage:
    python -m bot7 start              # start all components
    python -m bot7 start app_runner   # start one
    python -m bot7 stop               # stop all
    python -m bot7 stop collectors    # stop one
    python -m bot7 restart tracker    # restart one
    python -m bot7 status             # table: component | PID | health | last_log
    python -m bot7 logs <component> [--tail N] [--follow]
    python -m bot7 logs all --grep ERROR
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.supervisor.process_config import ALL_COMPONENTS, COMPONENTS, RUN_DIR, log_path, pid_path
from src.supervisor.daemon import (
    DAEMON_PID_PATH, _pid_alive, _pid_alive_for, _read_pid, get_status_rows,
)

_CREATE_BREAKAWAY_FROM_JOB = 0x01000000  # not exported by subprocess in py3.10
DETACH_FLAGS = (
    subprocess.DETACHED_PROCESS
    | subprocess.CREATE_NEW_PROCESS_GROUP
    | _CREATE_BREAKAWAY_FROM_JOB  # so supervisor survives Task Scheduler's job ending
)


def _hidden_startupinfo() -> "subprocess.STARTUPINFO | None":
    """Return STARTUPINFO that hides the console window (Windows-only).

    DETACHED_PROCESS + CREATE_NO_WINDOW are mutually exclusive at the Win32
    layer; combining them is silently ignored. STARTUPINFO with SW_HIDE works
    reliably alongside DETACHED_PROCESS.
    """
    if not hasattr(subprocess, "STARTUPINFO"):
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return si


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_table(rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    sep    = "  ".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for row in rows:
        health = str(row.get("health", ""))
        icon = {"OK": "[OK]", "STALE": "[!!]", "DEAD": "[--]"}.get(health, "")
        line = "  ".join(str(row[c]).ljust(widths[c]) for c in cols)
        print(f"{line}  {icon}")


def _require_component(name: str) -> None:
    if name not in COMPONENTS and name != "supervisor":
        print(f"Unknown component: {name!r}. Valid: {ALL_COMPONENTS}", file=sys.stderr)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_start(components: list[str] | None) -> None:
    # Check if supervisor already running. Use cmdline-checked variant —
    # plain _pid_alive returns True on Windows PID-reuse (a stale supervisor
    # PID can match an unrelated new process). Without the cmdline check
    # cmd_start was returning early thinking supervisor was up, leaving the
    # actual daemon never started — keepalive then saw the stale PID dead
    # 2min later and looped on `bot7 start` every cycle.
    sup_pid = _read_pid(DAEMON_PID_PATH)
    if sup_pid and _pid_alive_for(sup_pid, "src.supervisor.daemon"):
        if not components:
            print(f"Supervisor already running (PID={sup_pid})")
            return
        # Start individual components via a one-shot sub-supervisor? For now just warn.
        print(f"Supervisor running (PID={sup_pid}). To add components, restart supervisor.")
        return

    args = [sys.executable, "-m", "src.supervisor.daemon"]
    if components:
        args += components

    proc = subprocess.Popen(
        args,
        cwd=str(ROOT),
        creationflags=DETACH_FLAGS,
        startupinfo=_hidden_startupinfo(),
        close_fds=True,
        stdin=subprocess.DEVNULL,   # без этого supervisor наследует stdin parent'а
        stdout=subprocess.DEVNULL,  # которое закрывается → EOF на любом I/O →
        stderr=subprocess.DEVNULL,  # silent exit. (handoff #7 watchdog post-mortem)
    )
    print(f"Supervisor started (PID={proc.pid})")
    # Give it a moment then show status
    time.sleep(2)
    cmd_status()


def _kill_pid(pid: int, name: str) -> None:
    try:
        import signal as _signal
        os.kill(pid, _signal.SIGTERM)
        print(f"Sent SIGTERM to {name} (PID={pid})")
    except Exception as exc:
        print(f"Could not stop {name} (PID={pid}): {exc}", file=sys.stderr)


def cmd_stop(components: list[str] | None) -> None:
    if not components:
        # Stop supervisor (which will stop all managed processes)
        sup_pid = _read_pid(DAEMON_PID_PATH)
        if sup_pid and _pid_alive(sup_pid):
            _kill_pid(sup_pid, "supervisor")
        else:
            print("Supervisor not running")
            # Kill any stray managed processes
            for name in ALL_COMPONENTS:
                pid = _read_pid(pid_path(name))
                if pid and _pid_alive(pid):
                    _kill_pid(pid, name)
    else:
        for name in components:
            _require_component(name)
            p = pid_path(name) if name != "supervisor" else DAEMON_PID_PATH
            pid = _read_pid(p)
            if pid and _pid_alive(pid):
                _kill_pid(pid, name)
                p.unlink(missing_ok=True)
            else:
                print(f"{name}: not running")


def cmd_restart(components: list[str]) -> None:
    cmd_stop(components)
    time.sleep(2)
    # If supervisor alive, it will auto-restart. Otherwise re-launch.
    sup_pid = _read_pid(DAEMON_PID_PATH)
    if not (sup_pid and _pid_alive(sup_pid)):
        cmd_start(components)
    else:
        print("Supervisor will auto-restart the component within 30s")
        time.sleep(5)
    cmd_status()


def cmd_status() -> None:
    rows = get_status_rows()
    _print_table(rows)


def cmd_logs(component: str, tail: int = 50, follow: bool = False, grep: str | None = None) -> None:
    if component == "all":
        components = ["supervisor"] + ALL_COMPONENTS
    else:
        _require_component(component)
        components = [component]

    for name in components:
        if name == "supervisor":
            from src.utils.logging_config import CURRENT_DIR
            lp = CURRENT_DIR / "supervisor.log"
        else:
            lp = log_path(name)

        if not lp.exists():
            print(f"[{name}] log not found: {lp}")
            continue

        if len(components) > 1:
            print(f"\n{'='*20} {name} {'='*20}")

        lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()

        if grep:
            lines = [l for l in lines if grep.lower() in l.lower()]

        for line in lines[-tail:]:
            print(line.encode("cp1251", errors="replace").decode("cp1251"))

        if follow and len(components) == 1:  # noqa
            print(f"--- following {lp} (Ctrl+C to stop) ---")
            with lp.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)  # end
                try:
                    while True:
                        line = f.readline()
                        if line:
                            if not grep or grep.lower() in line.lower():
                                print(line, end="")
                        else:
                            time.sleep(0.3)
                except KeyboardInterrupt:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bot7",
        description="bot7 supervisor CLI",
    )
    sub = p.add_subparsers(dest="command")

    # start
    s = sub.add_parser("start", help="Start all or named components")
    s.add_argument("components", nargs="*", default=None)

    # stop
    s = sub.add_parser("stop", help="Stop all or named components")
    s.add_argument("components", nargs="*", default=None)

    # restart
    s = sub.add_parser("restart", help="Restart named component(s)")
    s.add_argument("components", nargs="+")

    # status
    sub.add_parser("status", help="Show process status table")

    # logs
    s = sub.add_parser("logs", help="Show logs")
    s.add_argument("component", help="Component name or 'all'")
    s.add_argument("--tail", type=int, default=50)
    s.add_argument("--follow", "-f", action="store_true")
    s.add_argument("--grep", default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        cmd_start(args.components or None)
    elif args.command == "stop":
        cmd_stop(args.components or None)
    elif args.command == "restart":
        cmd_restart(args.components)
    elif args.command == "status":
        cmd_status()
    elif args.command == "logs":
        cmd_logs(args.component, args.tail, args.follow, args.grep)
    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
