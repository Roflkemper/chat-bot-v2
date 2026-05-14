"""Compact paper_trades.jsonl — drop unreferenced P-15 records.

paper_trades.jsonl was originally designed for traditional SL/TP trades:
each setup → OPEN, then later TP1/SL/EXPIRE close. The P-15 strategy
writes OPEN/REENTRY/CLOSE events but they're managed by its own state
machine, so the generic trader.update_open_trades() loop (now correctly
skips them — TZ-B5) treats them as orphans.

Over time these P-15 records pile up and confuse anyone reading the
journal manually (or any code that grep-counts opens vs closes).

This script:
  1. Reads the journal.
  2. Splits records into trad-trade (strategy != p15) and p15.
  3. For trad: keeps as-is.
  4. For p15: matches OPEN with CLOSE on the same trade_id. Drops OPEN
     records that have no CLOSE (they're managed elsewhere).
  5. Rewrites the file. Original backup at paper_trades.jsonl.bak_TZ.

Run with --dry-run to see what would be dropped without modifying.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "state" / "paper_trades.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would happen without writing")
    args = ap.parse_args()

    if not PATH.exists():
        print(f"[compact] {PATH} missing — nothing to do")
        return 0

    records = []
    with PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # Bucket by strategy
    p15_by_id: dict[str, list[dict]] = defaultdict(list)
    keep: list[dict] = []
    for r in records:
        is_p15 = (r.get("strategy") == "p15"
                   or str(r.get("setup_type") or "").startswith("p15_"))
        if is_p15:
            tid = r.get("trade_id") or "_no_id_"
            p15_by_id[tid].append(r)
        else:
            keep.append(r)

    # For each p15 trade_id: keep only if there's a CLOSE record
    p15_kept = 0
    p15_dropped = 0
    for tid, recs in p15_by_id.items():
        has_close = any((r.get("action") or "").upper() in ("CLOSE", "TP1", "SL", "TP2", "EXPIRE")
                         or (r.get("stage") or "").upper() == "CLOSE"
                         for r in recs)
        if has_close:
            keep.extend(recs)
            p15_kept += len(recs)
        else:
            p15_dropped += len(recs)

    print(f"[compact] total records read:    {len(records)}")
    print(f"[compact] trad trades kept:      {len(keep) - p15_kept}")
    print(f"[compact] p15 closed trades kept: {p15_kept}")
    print(f"[compact] p15 orphan records dropped: {p15_dropped}")
    print(f"[compact] final size:            {len(keep)} (was {len(records)})")

    if args.dry_run:
        print("[compact] dry-run — no changes written")
        return 0

    if p15_dropped == 0:
        print("[compact] nothing to drop — skip rewrite")
        return 0

    backup = PATH.with_suffix(".jsonl.bak_TZ")
    shutil.copy(PATH, backup)
    print(f"[compact] backup: {backup}")

    with PATH.open("w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[compact] wrote {PATH}: {len(keep)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
