"""Predicts when state/pipeline_metrics.jsonl will hit the 5MB rotation
threshold based on growth rate over last 24h.

Saves daily checkpoint to state/pipeline_growth_log.jsonl so growth rate
is computed without re-walking the whole file each run.

Usage: cron hourly. If days_to_threshold < 2, alerts via done.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "state" / "pipeline_metrics.jsonl"
GROWTH_LOG = ROOT / "state" / "pipeline_growth_log.jsonl"

THRESHOLD_BYTES = 5 * 1024 * 1024  # matches pipeline_metrics rotation
ALERT_DAYS = 2


def _read_checkpoints() -> list[dict]:
    if not GROWTH_LOG.exists():
        return []
    out = []
    try:
        with GROWTH_LOG.open(encoding="utf-8") as f:
            for line in f:
                try: out.append(json.loads(line))
                except json.JSONDecodeError: continue
    except OSError:
        pass
    return out


def _append_checkpoint(rec: dict) -> None:
    try:
        GROWTH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with GROWTH_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError as exc:
        print(f"[growth] save failed: {exc}", file=sys.stderr)


def _send_tg_alert(msg: str) -> None:
    done = ROOT / "scripts" / "done.py"
    if not done.exists(): return
    try:
        subprocess.Popen(
            [sys.executable, str(done), msg],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"[growth] TG alert failed: {exc}", file=sys.stderr)


def main() -> int:
    if not METRICS.exists():
        print("[growth] pipeline_metrics.jsonl not yet — nothing to monitor")
        return 0

    now = datetime.now(timezone.utc)
    size = METRICS.stat().st_size
    cur = {"ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "size_bytes": size}
    _append_checkpoint(cur)

    cps = _read_checkpoints()
    if len(cps) < 2:
        print(f"[growth] first checkpoint saved (size={size/1024:.1f}KB). "
              f"Run again to compute growth rate.")
        return 0

    # Find a checkpoint from at least 12h ago (so the rate is meaningful)
    cutoff_ts = now.timestamp() - 12 * 3600
    older = [c for c in cps if datetime.fromisoformat(c["ts"].replace("Z", "+00:00")).timestamp() <= cutoff_ts]
    if not older:
        # use oldest available
        older = [cps[0]]

    ref = older[-1]
    ref_ts = datetime.fromisoformat(ref["ts"].replace("Z", "+00:00")).timestamp()
    hours_diff = (now.timestamp() - ref_ts) / 3600
    if hours_diff <= 0:
        print(f"[growth] not enough time passed")
        return 0

    bytes_diff = size - ref["size_bytes"]
    rate_per_hour = bytes_diff / hours_diff
    rate_per_day = rate_per_hour * 24

    print(f"[growth] current size: {size/1024:.1f}KB")
    print(f"[growth] window: {hours_diff:.1f}h, delta {bytes_diff/1024:+.1f}KB")
    print(f"[growth] rate: {rate_per_hour/1024:.1f}KB/h = {rate_per_day/1024:.1f}KB/day")

    if rate_per_hour <= 0:
        # File was rotated or shrunk. Nothing to alert on.
        print("[growth] file shrunk (rotation?) — skipping projection")
        return 0

    remaining = THRESHOLD_BYTES - size
    hours_to = remaining / rate_per_hour
    days_to = hours_to / 24
    print(f"[growth] projected to hit {THRESHOLD_BYTES/1024/1024:.0f}MB in "
          f"{hours_to:.1f}h ({days_to:.1f} days)")

    if days_to < ALERT_DAYS:
        msg = (f"[INFO] pipeline_metrics.jsonl will reach {THRESHOLD_BYTES/1024/1024:.0f}MB "
               f"rotation in ~{days_to:.1f} days (current {size/1024/1024:.2f}MB, "
               f"rate {rate_per_day/1024/1024:.2f}MB/day). Cron rotation is scheduled "
               f"daily 06:00 — should handle it without operator action.")
        _send_tg_alert(msg)
        print("[growth] alert sent")

    return 0


if __name__ == "__main__":
    sys.exit(main())
