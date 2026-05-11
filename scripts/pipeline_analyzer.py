"""Analyze setup_detector pipeline efficiency over last N hours.

Reads state/pipeline_metrics.jsonl and produces a per-detector funnel:

   detector              fired   strength  combo   dedup   gc   emit  yield%
   long_dump_reversal      780      684      40      0     0     0     0.0%
   long_pdl_bounce          25        0       0      4    18     3    12.0%
   short_rally_fade          8        1       0      2     5     0     0.0%

`yield%` = emit / fired. Detectors with high `fired` but low `yield%`
are wasting CPU on candidates that get blocked downstream — candidates
for upstream gate tightening.

Run via `python scripts/pipeline_analyzer.py [--hours 24]`. Output is
markdown-friendly; can be piped to TG via /pipeline command (future).
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

# Map drop stage_outcomes to columns in the output table.
DROP_STAGES = (
    ("strength", {"below_strength"}),
    ("combo", {"combo_blocked"}),
    ("env_dis", {"env_disabled"}),
    ("dedup", {"semantic_dedup_skip", "type_pair_dedup_skip"}),
    ("gc_blk", {"gc_blocked"}),
)
ANY_DROP = {s for _, stages in DROP_STAGES for s in stages}
ANY_DROP |= {"detector_failed"}


def _read_window(hours: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out = []
    if not METRICS.exists():
        return out
    with METRICS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
                ts = rec.get("ts")
                if not ts: continue
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff: out.append(rec)
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _analyze(metrics: list[dict]) -> tuple[dict, dict, int]:
    """Returns (per_detector_funnel, totals_by_stage, n_metrics)."""
    per_det = defaultdict(lambda: {
        "fired": 0, "strength": 0, "combo": 0, "env_dis": 0,
        "dedup": 0, "gc_blk": 0, "emit": 0,
    })
    totals = Counter()

    # First pass — count drops by stage and by detector.
    for m in metrics:
        outcome = m.get("stage_outcome")
        totals[outcome] += 1
        # Drop events carry setup_type.
        st = m.get("setup_type")
        if outcome == "emitted" and st:
            per_det[st]["emit"] += 1
            per_det[st]["fired"] += 1
        elif outcome in ANY_DROP and st:
            per_det[st]["fired"] += 1
            for col, stages in DROP_STAGES:
                if outcome in stages:
                    per_det[st][col] += 1
                    break

    # env_disabled events don't always carry setup_type (extracted from
    # drop_reason like "detect_short_pdh_rejection"). Catch those.
    for m in metrics:
        if m.get("stage_outcome") != "env_disabled":
            continue
        if m.get("setup_type"):
            continue  # already counted above
        reason = str(m.get("drop_reason") or "")
        if not reason.startswith("detect_"):
            continue
        # detect_short_pdh_rejection -> short_pdh_rejection
        st = reason[len("detect_"):]
        per_det[st]["fired"] += 1
        per_det[st]["env_dis"] += 1

    return dict(per_det), dict(totals), len(metrics)


def _format_table(per_det: dict) -> str:
    headers = ["detector", "fired", "strength", "combo", "env_dis",
               "dedup", "gc_blk", "emit", "yield%"]
    rows = []
    for det, stats in per_det.items():
        fired = stats["fired"]
        emit = stats["emit"]
        yield_pct = emit / fired * 100 if fired else 0
        rows.append({
            "detector": det,
            "fired": fired,
            "strength": stats["strength"],
            "combo": stats["combo"],
            "env_dis": stats["env_dis"],
            "dedup": stats["dedup"],
            "gc_blk": stats["gc_blk"],
            "emit": emit,
            "yield%": yield_pct,
        })
    rows.sort(key=lambda r: -r["fired"])

    # Pretty-print
    widths = {h: max(len(h), max((len(str(r[h])) if h != "yield%" else len(f"{r[h]:.1f}") for r in rows), default=0)) for h in headers}
    out = []
    out.append("  ".join(h.ljust(widths[h]) for h in headers))
    out.append("  ".join("-" * widths[h] for h in headers))
    for r in rows:
        cells = []
        for h in headers:
            if h == "yield%":
                cells.append(f"{r[h]:.1f}".rjust(widths[h]))
            elif h == "detector":
                cells.append(str(r[h]).ljust(widths[h]))
            else:
                cells.append(str(r[h]).rjust(widths[h]))
        out.append("  ".join(cells))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24,
                    help="Lookback window in hours (default 24)")
    args = ap.parse_args()

    metrics = _read_window(args.hours)
    per_det, totals, n = _analyze(metrics)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    print(f"[pipeline] {n} events in last {args.hours}h")
    print()
    print(f"Stage totals:")
    for stage, count in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {stage:<24} {count:>6}")
    print()

    if per_det:
        print("Per-detector funnel:")
        print(_format_table(per_det))
        print()

        # Highlight inefficiencies
        wasteful = [(det, s) for det, s in per_det.items()
                    if s["fired"] >= 50 and s["emit"] == 0]
        if wasteful:
            print("[INSIGHT] high-volume detectors with 0 emits "
                  "(candidates for tighter upstream gate):")
            for det, s in sorted(wasteful, key=lambda x: -x[1]["fired"]):
                print(f"  - {det}: fired={s['fired']} all blocked "
                      f"(strength={s['strength']}, combo={s['combo']}, env={s['env_dis']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
