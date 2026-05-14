"""Deduplicate ginarea_live/snapshots.csv.

Removes:
  1. Garbage rows with non-ISO ts_utc (CSV parse artifacts from emoji in bot_name)
  2. Duplicate (ts_utc, bot_id) rows — keep='last' (last written = most recent API response)

Usage:
    python scripts/dedup_snapshots.py
    python scripts/dedup_snapshots.py --dry-run   # show stats without modifying file
    python scripts/dedup_snapshots.py --input PATH --output PATH
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

DEFAULT_INPUT = Path("ginarea_live/snapshots.csv")
DEFAULT_OUTPUT = DEFAULT_INPUT  # overwrite in-place by default


def dedup(
    input_path: Path,
    output_path: Path,
    *,
    dry_run: bool = False,
) -> dict:
    df = pd.read_csv(input_path, low_memory=False)
    total = len(df)

    # Step 1: remove garbage rows (non-ISO ts_utc from CSV parse errors)
    valid_ts_mask = df["ts_utc"].astype(str).str.match(_ISO_RE)
    n_garbage = (~valid_ts_mask).sum()
    df = df[valid_ts_mask].copy()

    # Step 2: deduplicate on (ts_utc, bot_id) — keep='last' for max recency
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["ts_utc", "bot_id"], keep="last")
    n_dupes = before_dedup - len(df)
    after = len(df)

    stats = {
        "total_before": total,
        "garbage_removed": int(n_garbage),
        "duplicates_removed": int(n_dupes),
        "total_after": after,
        "pct_removed": round((total - after) / total * 100, 2) if total else 0,
    }

    if not dry_run:
        df.to_csv(output_path, index=False)

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dedup ginarea_live/snapshots.csv")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup (not recommended)",
    )
    args = parser.parse_args(argv)

    input_path: Path = args.input
    output_path: Path = args.output or input_path  # default: overwrite in-place

    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    if not args.dry_run and not args.no_backup and input_path == output_path:
        today = date.today().strftime("%Y-%m-%d")
        backup = input_path.parent / f"snapshots_backup_{today}.csv"
        if not backup.exists():
            shutil.copy2(input_path, backup)
            print(f"Backup created: {backup}")
        else:
            print(f"Backup already exists: {backup}")

    stats = dedup(input_path, output_path, dry_run=args.dry_run)

    print(f"total_before:        {stats['total_before']:,}")
    print(f"garbage_removed:     {stats['garbage_removed']:,}")
    print(f"duplicates_removed:  {stats['duplicates_removed']:,}")
    print(f"total_after:         {stats['total_after']:,}")
    print(f"pct_removed:         {stats['pct_removed']:.1f}%")
    if args.dry_run:
        print("[dry-run] no changes written")
    else:
        print(f"Written to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
