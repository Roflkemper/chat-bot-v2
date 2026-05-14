"""Install bot7 git hooks: point core.hooksPath at .githooks/.

Idempotent: re-running is safe and exits 0 if hooks are already configured.

Usage:
    python tools/install_hooks.py
    python tools/install_hooks.py --check     # verify without changing config
"""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / ".githooks"
HOOK_NAMES = ("pre-commit",)
EXPECTED_HOOKS_PATH = ".githooks"


def _git(*args: str, cwd: Path = ROOT) -> tuple[int, str, str]:
    """Run git command, return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_current_hooks_path() -> str:
    """Return current core.hooksPath value (empty string if unset)."""
    code, out, _ = _git("config", "--get", "core.hooksPath")
    if code == 0:
        return out
    return ""  # unset → git uses default .git/hooks/


def set_hooks_path(value: str) -> None:
    """Set core.hooksPath to the given value."""
    code, _, err = _git("config", "core.hooksPath", value)
    if code != 0:
        raise RuntimeError(f"git config failed: {err}")


def make_hooks_executable() -> list[str]:
    """chmod +x every hook in .githooks/. Returns list of files made executable.

    On Windows the executable bit is irrelevant (Git for Windows runs hooks
    via bash regardless), but we still tag the bit so that POSIX clones work.
    """
    changed: list[str] = []
    for name in HOOK_NAMES:
        hook = HOOKS_DIR / name
        if not hook.exists():
            continue
        current = hook.stat().st_mode
        wanted = current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        if wanted != current:
            try:
                hook.chmod(wanted)
                changed.append(str(hook.relative_to(ROOT)))
            except (PermissionError, OSError):
                # Windows ignores chmod on some filesystems — not fatal.
                pass
    return changed


def install() -> dict:
    """Configure git to use .githooks/. Idempotent. Returns summary dict."""
    summary: dict = {
        "hooks_dir_exists": HOOKS_DIR.exists(),
        "hooks_present": [],
        "previous_hooks_path": get_current_hooks_path(),
        "new_hooks_path": EXPECTED_HOOKS_PATH,
        "made_executable": [],
        "already_configured": False,
    }

    if not HOOKS_DIR.exists():
        raise FileNotFoundError(f".githooks/ folder not found: {HOOKS_DIR}")

    summary["hooks_present"] = sorted(p.name for p in HOOKS_DIR.iterdir() if p.is_file())

    if summary["previous_hooks_path"] == EXPECTED_HOOKS_PATH:
        summary["already_configured"] = True

    set_hooks_path(EXPECTED_HOOKS_PATH)
    summary["made_executable"] = make_hooks_executable()

    # Verify
    after = get_current_hooks_path()
    summary["verified_hooks_path"] = after
    summary["ok"] = (after == EXPECTED_HOOKS_PATH)
    return summary


def check() -> dict:
    """Check current state without changing it."""
    return {
        "hooks_dir_exists": HOOKS_DIR.exists(),
        "current_hooks_path": get_current_hooks_path(),
        "expected_hooks_path": EXPECTED_HOOKS_PATH,
        "ok": get_current_hooks_path() == EXPECTED_HOOKS_PATH and HOOKS_DIR.exists(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install bot7 git hooks.")
    parser.add_argument("--check", action="store_true",
                        help="Report status without changing git config")
    args = parser.parse_args(argv)

    if args.check:
        result = check()
        print(f"hooks_dir_exists:    {result['hooks_dir_exists']}")
        print(f"current_hooks_path:  {result['current_hooks_path'] or '(unset)'}")
        print(f"expected_hooks_path: {result['expected_hooks_path']}")
        print(f"status:              {'OK' if result['ok'] else 'NOT INSTALLED'}")
        return 0 if result["ok"] else 1

    try:
        summary = install()
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"hooks_dir:           {HOOKS_DIR}")
    print(f"hooks_present:       {summary['hooks_present']}")
    print(f"previous_hooks_path: {summary['previous_hooks_path'] or '(unset)'}")
    print(f"new_hooks_path:      {summary['new_hooks_path']}")
    print(f"verified_hooks_path: {summary['verified_hooks_path']}")
    print(f"made_executable:     {summary['made_executable'] or '(none)'}")
    if summary["already_configured"]:
        print("(already configured — no change needed)")
    print(f"status:              {'OK' if summary['ok'] else 'FAILED'}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
