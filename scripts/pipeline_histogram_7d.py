"""Pipeline 7-day histogram — daily breakdown of emits + drops.

Reads state/pipeline_metrics.jsonl + rotated archives. Groups events
by date (UTC), shows:
  - per-day total events
  - per-day emitted count
  - per-day drop categories

Useful for spotting trends: emit volume rising? Specific drop category
spiking?

Usage:
    python scripts/pipeline_histogram_7d.py [--days 7]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "state" / "pipeline_metrics.jsonl"
ARCHIVE_GLOB = "pipeline_metrics_*.jsonl"


def _read_all_sources(days: int) -> list[dict]:
    """Read current metrics + any rotated archives covering the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    sources = [METRICS] + sorted(METRICS.parent.glob(ARCHIVE_GLOB))
    for path in sources:
        if not path.exists(): continue
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
                        if dt >= cutoff:
                            rec["_date"] = dt.strftime("%Y-%m-%d")
                            out.append(rec)
                    except ValueError:
                        continue
        except OSError:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    metrics = _read_all_sources(args.days)
    if not metrics:
        print(f"[hist] no metrics in last {args.days}d")
        return 0

    # By-day breakdown
    by_day: dict[str, Counter] = defaultdict(Counter)
    for m in metrics:
        by_day[m["_date"]][m["stage_outcome"]] += 1

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    print(f"[hist] {len(metrics):,} events over {args.days}d, "
          f"{len(by_day)} unique days")
    print()

    # All stage types ever seen
    all_stages = sorted({s for day in by_day.values() for s in day})

    # Render table: rows = dates, columns = stage_outcomes
    print(f"{'date':<12} {'TOTAL':>6} | " +
          " ".join(f"{s[:11]:>11}" for s in all_stages))
    print("-" * (20 + 12 * len(all_stages)))

    for date in sorted(by_day):
        day = by_day[date]
        total = sum(day.values())
        cells = " ".join(f"{day.get(s, 0):>11}" for s in all_stages)
        print(f"{date:<12} {total:>6} | {cells}")

    # Trend: how does emit volume change?
    print()
    days_sorted = sorted(by_day)
    if len(days_sorted) >= 2:
        first_half = days_sorted[:len(days_sorted)//2]
        last_half = days_sorted[len(days_sorted)//2:]
        avg_first = sum(by_day[d].get("emitted", 0) for d in first_half) / len(first_half)
        avg_last = sum(by_day[d].get("emitted", 0) for d in last_half) / len(last_half)
        delta_pct = ((avg_last - avg_first) / avg_first * 100) if avg_first > 0 else 0
        print(f"Emit trend: first half avg {avg_first:.1f}/d, "
              f"last half avg {avg_last:.1f}/d ({delta_pct:+.0f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
