"""Archive a backtest result with timestamp + git hash for tracking.

Usage (manual or wrapped around a backtest):
    python tools/_backtest_detectors_honest.py > result.txt
    python scripts/archive_backtest_result.py result.txt detectors_honest

Or piped:
    python tools/_backtest_detectors_honest.py | python scripts/archive_backtest_result.py - detectors_honest

Archive location: data/backtest_archive/YYYY-MM-DD_HHMMSS_<name>_<gitsha>.txt

Why: backtests are research-grade scripts that print to stdout. Without
archiving, you lose the result the moment the terminal closes. With this,
every run gets a timestamped record next to the git commit it was based on.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = ROOT / "data" / "backtest_archive"


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _is_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=str(ROOT), capture_output=True, timeout=5,
        )
        return result.returncode != 0
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="File path or '-' for stdin")
    ap.add_argument("name", help="Short name for the archive (e.g. detectors_honest)")
    ap.add_argument("--note", default="", help="Optional note to prepend to archive")
    args = ap.parse_args()

    if args.source == "-":
        content = sys.stdin.read()
    else:
        try:
            content = Path(args.source).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[archive] read failed: {exc}", file=sys.stderr)
            return 1

    now = datetime.now(timezone.utc)
    sha = _git_sha()
    dirty = "_dirty" if _is_dirty() else ""
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in args.name)
    fname = f"{now:%Y-%m-%d_%H%M%S}_{safe_name}_{sha}{dirty}.txt"

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARCHIVE_DIR / fname

    header = (
        f"# Backtest archive\n"
        f"# Date: {now.isoformat()}\n"
        f"# Git: {sha}{dirty}\n"
        f"# Name: {args.name}\n"
    )
    if args.note:
        header += f"# Note: {args.note}\n"
    header += "# " + "-" * 60 + "\n\n"

    out_path.write_text(header + content, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"[archive] wrote {out_path}  ({size_kb:.1f}KB)")

    # Prune archives older than 90 days
    import time
    cutoff = time.time() - 90 * 86400
    for old in ARCHIVE_DIR.glob("*.txt"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
                print(f"[archive] pruned {old.name}")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
