"""P-15 equity curve analytics.

Reads state/p15_equity.jsonl and computes:
  - Cumulative PnL over time
  - Trades per stage (OPEN, HARVEST, CLOSE)
  - Realized PnL per direction (long/short)
  - Worst/best trade
  - Win rate (profitable HARVEST + CLOSE events)

Run: python scripts/p15_equity_report.py [days]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EQUITY = ROOT / "state" / "p15_equity.jsonl"


def main(days: int = 30) -> int:
    if not EQUITY.exists():
        print(f"[p15-equity] {EQUITY} not yet (no closes/harvests recorded)")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = []
    with EQUITY.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
                ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    events.append(rec)
            except (ValueError, KeyError, json.JSONDecodeError):
                continue

    if not events:
        print(f"[p15-equity] no events in last {days}d")
        return 0

    print(f"[p15-equity] {len(events)} events in last {days}d\n")

    stage_counts = Counter(e.get("stage", "?") for e in events)
    print("By stage:")
    for s, c in stage_counts.most_common(): print(f"  {s}: {c}")

    # Realized PnL events (CLOSE + HARVEST)
    realized_events = [e for e in events if e.get("stage") in ("CLOSE", "HARVEST")]
    long_pnl = sum(float(e.get("realized_pnl_usd", 0) or 0) for e in realized_events
                   if e.get("direction") == "long")
    short_pnl = sum(float(e.get("realized_pnl_usd", 0) or 0) for e in realized_events
                    if e.get("direction") == "short")
    total = long_pnl + short_pnl
    print(f"\nRealized PnL ({len(realized_events)} events):")
    print(f"  LONG:  ${long_pnl:+.2f}")
    print(f"  SHORT: ${short_pnl:+.2f}")
    print(f"  TOTAL: ${total:+.2f}")

    if realized_events:
        pnls = [float(e.get("realized_pnl_usd", 0) or 0) for e in realized_events]
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        wr = (wins / len(pnls) * 100) if pnls else 0
        avg = sum(pnls) / len(pnls) if pnls else 0
        best = max(pnls)
        worst = min(pnls)
        print(f"\nTrade stats:")
        print(f"  Win rate: {wr:.1f}% ({wins} wins / {losses} losses / {len(pnls)} total)")
        print(f"  Avg: ${avg:+.2f}  Best: ${best:+.2f}  Worst: ${worst:+.2f}")

    # Per-day cumulative
    print(f"\nDaily cumulative PnL (last 14 days):")
    by_day: dict = {}
    for e in realized_events:
        try:
            ts = datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
            day = ts.strftime("%Y-%m-%d")
        except (ValueError, KeyError):
            continue
        by_day.setdefault(day, 0)
        by_day[day] += float(e.get("realized_pnl_usd", 0) or 0)
    days_sorted = sorted(by_day.keys())[-14:]
    cum = 0
    for d in days_sorted:
        cum += by_day[d]
        print(f"  {d}: day=${by_day[d]:+.2f}  cum=${cum:+.2f}")
    return 0


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    sys.exit(main(days))
