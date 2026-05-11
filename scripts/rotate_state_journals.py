"""Daily rotation of growing jsonl state files.

Schedule via Windows Task Scheduler at 06:00 local. Each journal is
rotated independently when it exceeds its own size threshold:

  state/setups.jsonl                10MB
  state/gc_confirmation_audit.jsonl  5MB
  state/p15_equity.jsonl             2MB
  state/setup_outcomes.jsonl        10MB
  state/setup_precision_outcomes.jsonl  5MB
  state/pipeline_metrics.jsonl       5MB (also rotated in-place by writer)
  logs/watchdog.log                  5MB
  state/app_runner_starts.jsonl      2MB

Archives kept 30 days, then deleted.

Run manually:
    python scripts/rotate_state_journals.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.common.rotation import rotate_if_large  # noqa: E402

JOURNALS = [
    (ROOT / "state" / "setups.jsonl",                       10 * 1024 * 1024),
    (ROOT / "state" / "gc_confirmation_audit.jsonl",         5 * 1024 * 1024),
    (ROOT / "state" / "p15_equity.jsonl",                    2 * 1024 * 1024),
    (ROOT / "state" / "setup_outcomes.jsonl",               10 * 1024 * 1024),
    (ROOT / "state" / "setup_precision_outcomes.jsonl",      5 * 1024 * 1024),
    (ROOT / "state" / "pipeline_metrics.jsonl",              5 * 1024 * 1024),
    (ROOT / "logs"  / "watchdog.log",                        5 * 1024 * 1024),
    (ROOT / "state" / "app_runner_starts.jsonl",             2 * 1024 * 1024),
]
KEEP_DAYS = 30


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Report sizes without rotating")
    args = ap.parse_args()

    print(f"[rotate] checking {len(JOURNALS)} journals (keep_days={KEEP_DAYS})")
    for path, max_bytes in JOURNALS:
        if not path.exists():
            print(f"  {path.name:<45} (missing)")
            continue
        size_mb = path.stat().st_size / (1024 * 1024)
        threshold_mb = max_bytes / (1024 * 1024)
        if size_mb < threshold_mb:
            print(f"  {path.name:<45} {size_mb:>6.2f}MB  / {threshold_mb:.0f}MB  ok")
            continue
        if args.dry_run:
            print(f"  {path.name:<45} {size_mb:>6.2f}MB  WOULD ROTATE")
            continue
        result = rotate_if_large(path, max_bytes=max_bytes, keep_days=KEEP_DAYS)
        print(f"  {path.name:<45} {size_mb:>6.2f}MB  -> {result}")
    print("[rotate] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
