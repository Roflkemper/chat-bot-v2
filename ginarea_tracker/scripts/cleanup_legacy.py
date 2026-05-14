"""One-time migration: convert v2 CSV files to schema v3.

Reads old snapshots.csv / events.csv / params.csv, filters invalid rows,
writes clean versions with schema_version=3.

Usage (from ginarea_tracker/ directory):
    python scripts/cleanup_legacy.py [--input-dir ginarea_live] [--output-dir ginarea_live_v3] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Allow running from any CWD
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage import (
    EVENTS_HEADERS,
    PARAMS_HEADERS,
    SCHEMA_VERSION,
    SNAPSHOTS_HEADERS,
)

_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _is_valid_row(row: dict) -> bool:
    ts = str(row.get("ts_utc", ""))
    bot_id = str(row.get("bot_id", ""))
    if not _ISO8601_RE.match(ts):
        return False
    try:
        int(bot_id)
    except (ValueError, TypeError):
        return False
    return True


def _migrate_file(
    src: Path,
    dst: Path,
    target_headers: list[str],
    dry_run: bool,
) -> tuple[int, int]:
    """Read src CSV, filter valid rows, write to dst with target schema.

    Returns (rows_read, rows_written).
    """
    if not src.exists():
        print(f"  SKIP {src.name} — not found")
        return 0, 0

    with src.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        src_headers = reader.fieldnames or []
        rows = list(reader)

    valid = [r for r in rows if _is_valid_row(r)]
    dropped = len(rows) - len(valid)

    print(f"  {src.name}: {len(rows)} rows read, {dropped} dropped, {len(valid)} valid")

    if dry_run:
        print(f"  DRY-RUN: would write {len(valid)} rows to {dst.name}")
        return len(rows), len(valid)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=target_headers, extrasaction="ignore")
        writer.writeheader()
        for row in valid:
            row["schema_version"] = SCHEMA_VERSION
            writer.writerow({h: row.get(h, "") for h in target_headers})

    print(f"  Written → {dst}")
    return len(rows), len(valid)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate tracker CSVs to schema v3")
    parser.add_argument("--input-dir", default="ginarea_live", help="Directory with existing CSV files")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as input, files named _v3.csv)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    dry_run: bool = args.dry_run

    print(f"Input:  {input_dir.resolve()}")
    print(f"Output: {output_dir.resolve()}")
    print(f"Mode:   {'DRY RUN' if dry_run else 'WRITE'}")
    print()

    files = [
        ("snapshots.csv", "snapshots_v3.csv", SNAPSHOTS_HEADERS),
        ("events.csv",    "events_v3.csv",    EVENTS_HEADERS),
        ("params.csv",    "params_v3.csv",    PARAMS_HEADERS),
    ]

    total_read = total_written = 0
    for src_name, dst_name, headers in files:
        src = input_dir / src_name
        dst = output_dir / dst_name if output_dir != input_dir else input_dir / dst_name
        r, w = _migrate_file(src, dst, headers, dry_run)
        total_read += r
        total_written += w

    print()
    print(f"Total: {total_read} rows read, {total_written} rows written to v3 files")
    if not dry_run:
        print("Done. Rename _v3 files to replace originals if satisfied.")


if __name__ == "__main__":
    main()
