#!/usr/bin/env python3
"""
Parse operator-dictated RANGE/TREND intervals into data/regime_truth/btc_1h_v1.json.

Usage — two modes:

  # Mode A: interactive — type intervals one per line, empty line to finish
  python tools/parse_regime_truth.py --interactive

  # Mode B: from text file
  python tools/parse_regime_truth.py --file intervals.txt

  # Mode C: from screenshots directory (reads screenshots, prompts for timestamps)
  python tools/parse_regime_truth.py --screenshots data/regime_truth/screenshots/

Line format (both modes A and B):
  RANGE 2026-01-09 00:00 → 2026-01-12 18:00  (Screenshot_134344)
  TREND 2026-01-13 14:00 → 2026-01-14 08:00  (Screenshot_134344)
  # comment lines are ignored
  (blank lines are ignored)

Arrow variants accepted: →, ->, -–, to
Timestamps accepted: "YYYY-MM-DD HH:MM", "YYYY-MM-DDTHH:MM", "YYYY-MM-DDTHH:MM:SSZ"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _ROOT / "data" / "regime_truth" / "btc_1h_v1.json"

_META = {
    "version": "v1",
    "asset": "BTCUSDT",
    "timeframe": "1h",
    "labelling_method": "operator_manual_screenshots",
    "labelled_period_start": "2026-01-09T00:00:00Z",
    "labelled_period_end": "2026-04-19T23:00:00Z",
    "holdout_period_start": "2026-04-22T00:00:00Z",
    "holdout_period_end": "2026-04-28T23:00:00Z",
    "notes": (
        "Binary TREND/RANGE labels from operator manual review of BTC 1H chart. "
        "Green boxes = TREND (displacement), red/purple boxes = RANGE (price band). "
        "Gaps between labelled intervals are OK — feature extractor uses only labelled bars."
    ),
}

# Regex patterns
_TS_PATTERN = r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2})?Z?"
_ARROW = r"(?:→|->|–>|to)\s*"
_LABEL = r"(RANGE|TREND)"
_SCREEN = r"(?:\(([^)]+)\))?"

_LINE_RE = re.compile(
    rf"^\s*{_LABEL}\s+{_TS_PATTERN}\s+{_ARROW}{_TS_PATTERN}\s*{_SCREEN}",
    re.IGNORECASE,
)


def _parse_ts(date: str, time: str) -> str:
    """Return ISO8601 UTC string from date+time strings."""
    dt_str = f"{date}T{time}:00"
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_line(line: str) -> dict | None:
    """Parse one line into an interval dict. Returns None if not parseable."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = _LINE_RE.match(line)
    if not m:
        return None
    label, d1, t1, d2, t2, screen = m.groups()
    return {
        "label": label.upper(),
        "start_ts": _parse_ts(d1, t1),
        "end_ts": _parse_ts(d2, t2),
        "source_screenshot": screen.strip() if screen else "",
    }


def build_json(intervals: list[dict]) -> dict:
    """Sort intervals chronologically, assign IDs, embed in full schema."""
    intervals = sorted(intervals, key=lambda x: x["start_ts"])
    range_n = trend_n = 0
    labelled: list[dict] = []
    for iv in intervals:
        label = iv["label"]
        if label == "RANGE":
            range_n += 1
            id_ = f"range_{range_n:03d}"
        else:
            trend_n += 1
            id_ = f"trend_{trend_n:03d}"
        labelled.append({
            "id": id_,
            "start_ts": iv["start_ts"],
            "end_ts": iv["end_ts"],
            "label": label,
            "source_screenshot": iv.get("source_screenshot", ""),
            "notes": iv.get("notes", ""),
        })
    return {**_META, "intervals": labelled}


def interactive_mode() -> list[dict]:
    print("Enter intervals (empty line to finish):")
    print("  Format: RANGE 2026-01-09 00:00 → 2026-01-12 18:00  (Screenshot_134344)")
    print("  Format: TREND 2026-01-13 14:00 → 2026-01-14 08:00")
    intervals = []
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            break
        iv = parse_line(line)
        if iv:
            intervals.append(iv)
            print(f"  ✓ {iv['label']} {iv['start_ts']} → {iv['end_ts']}")
        elif line.strip() and not line.startswith("#"):
            print(f"  ✗ Could not parse: {line!r}")
    return intervals


def file_mode(path: Path) -> list[dict]:
    intervals = []
    for line in path.read_text(encoding="utf-8").splitlines():
        iv = parse_line(line)
        if iv:
            intervals.append(iv)
    return intervals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse regime truth intervals into JSON")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--interactive", "-i", action="store_true")
    group.add_argument("--file", "-f", type=Path, help="Text file with intervals")
    parser.add_argument("--out", "-o", type=Path, default=_DEFAULT_OUT)
    parser.add_argument("--append", action="store_true", help="Append to existing JSON")
    args = parser.parse_args(argv)

    if args.file:
        intervals = file_mode(args.file)
    elif args.interactive or not sys.stdin.isatty():
        intervals = interactive_mode()
    else:
        intervals = interactive_mode()

    if not intervals:
        print("No intervals parsed. Exiting.")
        return 1

    # Merge with existing if appending
    existing: list[dict] = []
    if args.append and args.out.exists():
        data = json.loads(args.out.read_text(encoding="utf-8"))
        existing = data.get("intervals", [])
        for iv in existing:
            intervals.append({
                "label": iv["label"],
                "start_ts": iv["start_ts"],
                "end_ts": iv["end_ts"],
                "source_screenshot": iv.get("source_screenshot", ""),
                "notes": iv.get("notes", ""),
            })

    result = build_json(intervals)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    n_range = sum(1 for iv in result["intervals"] if iv["label"] == "RANGE")
    n_trend = sum(1 for iv in result["intervals"] if iv["label"] == "TREND")
    print(f"\nSaved {len(result['intervals'])} intervals → {args.out}")
    print(f"  RANGE: {n_range}  TREND: {n_trend}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
