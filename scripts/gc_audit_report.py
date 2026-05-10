"""GC-confirmation audit reporter.

Reads state/gc_confirmation_audit.jsonl and reports:
  - Total decisions per detector (aligned/misaligned/neutral/blocked)
  - Distribution of confidence changes
  - Hit-rate of aligned vs misaligned (cross-ref with paper_trader outcomes)
  - Suggested adjustments to HARD_BLOCK list based on observed misalignment

Run on demand or via cron weekly to inform calibration decisions.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "state" / "gc_confirmation_audit.jsonl"
PAPER_LOG = ROOT / "state" / "paper_trades.jsonl"


def main(days: int = 30) -> int:
    if not AUDIT.exists():
        print(f"[gc-audit] {AUDIT} not found yet — let GC-confirmation run for a few hours")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records = []
    with AUDIT.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                r = json.loads(line)
                ts = datetime.fromisoformat(str(r.get("ts", "")).replace("Z", "+00:00"))
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff: continue
                records.append(r)
            except (json.JSONDecodeError, ValueError):
                continue

    if not records:
        print(f"[gc-audit] no audit records in last {days}d")
        return 0

    print(f"[gc-audit] {len(records)} decisions in last {days}d\n")

    # Per-detector stats
    per_det = defaultdict(lambda: Counter())
    for r in records:
        det = r.get("setup_type", "?")
        decision = r.get("decision", "?")
        per_det[det][decision] += 1
        per_det[det]["TOTAL"] += 1

    print(f"{'Detector':<35} {'Total':>6} {'Aligned':>9} {'Misalign':>9} {'Blocked':>9} {'Neutral':>9}")
    print("-" * 80)
    for det, c in sorted(per_det.items(), key=lambda x: -x[1]["TOTAL"]):
        total = c["TOTAL"]
        aligned = sum(v for k, v in c.items() if "boost" in k)
        misaligned_pen = sum(v for k, v in c.items() if "penalty" in k)
        blocked = sum(v for k, v in c.items() if "block" in k)
        neutral = c.get("pass-through", 0)
        print(f"{det:<35} {total:>6} {aligned:>9} {misaligned_pen:>9} {blocked:>9} {neutral:>9}")

    # Aggregate
    total = len(records)
    blocked_total = sum(1 for r in records if "block" in str(r.get("decision", "")))
    aligned_total = sum(1 for r in records if "boost" in str(r.get("decision", "")))
    print(f"\nAggregate: {total} decisions | {aligned_total} aligned | {blocked_total} blocked")
    print(f"  Suppression rate: {blocked_total/total*100:.1f}%")
    print(f"  Boost rate: {aligned_total/total*100:.1f}%")

    # Suggest adjustments: detectors with high misalignment rate not in HARD_BLOCK
    print("\n--- Suggestion: candidates for HARD_BLOCK ---")
    for det, c in per_det.items():
        total_d = c["TOTAL"]
        if total_d < 20: continue  # need enough samples
        misalign = sum(v for k, v in c.items() if "penalty" in k or "block" in k)
        misalign_rate = misalign / total_d * 100
        if misalign_rate > 30:
            print(f"  {det}: {misalign_rate:.1f}% misaligned ({misalign}/{total_d}) — consider adding to HARD_BLOCK")
    return 0


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    sys.exit(main(days))
