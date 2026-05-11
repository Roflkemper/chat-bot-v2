"""Check app_runner restart frequency from state/app_runner_starts.jsonl.

If >RESTART_LIMIT in last RESTART_WINDOW_HOURS — alert via TG.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT = ROOT / "state" / "app_runner_starts.jsonl"
WATCHDOG_AUDIT = ROOT / "state" / "watchdog_audit.jsonl"
RESTART_LIMIT = 5
RESTART_WINDOW_HOURS = 1
# 2026-05-11 TODO-8: starts within this many seconds of a watchdog tick
# are likely operator-triggered (kill + immediate watchdog respawn).
# Don't count them toward the alert threshold.
OPERATOR_TRIGGER_WINDOW_SEC = 30


def _watchdog_tick_times(cutoff) -> list:
    """Read watchdog audit and return timestamps of 'started' events for
    app_runner. These are points where watchdog noticed NOT RUNNING and
    restarted — typically follow an operator kill or autonomous crash."""
    if not WATCHDOG_AUDIT.exists():
        return []
    out = []
    with WATCHDOG_AUDIT.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("event") != "started" or r.get("component") != "app_runner":
                    continue
                ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff: out.append(ts)
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
    return out


def main() -> int:
    if not AUDIT.exists():
        print("[restart-check] no audit yet"); return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RESTART_WINDOW_HOURS)
    starts = []
    with AUDIT.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    rec["_ts"] = ts
                    starts.append(rec)
            except (ValueError, KeyError, json.JSONDecodeError):
                continue

    # Classify: starts that align with a watchdog tick are operator-triggered.
    wd_ticks = _watchdog_tick_times(cutoff)
    autonomous = []
    operator = []
    for s in starts:
        ts = s["_ts"]
        aligned_with_wd = any(
            abs((ts - wd_ts).total_seconds()) <= OPERATOR_TRIGGER_WINDOW_SEC
            for wd_ts in wd_ticks
        )
        (operator if aligned_with_wd else autonomous).append(s)

    n = len(starts)
    n_auto = len(autonomous)
    n_op = len(operator)
    print(f"[restart-check] {n} starts in last {RESTART_WINDOW_HOURS}h "
          f"(autonomous={n_auto}, operator-triggered={n_op}, threshold={RESTART_LIMIT})")
    starts = autonomous  # only autonomous ones trigger the alert
    n = n_auto
    if n >= RESTART_LIMIT:
        msg = (f"[WARN] App_runner restarted {n} times in last {RESTART_WINDOW_HOURS}h "
               f"(threshold {RESTART_LIMIT}). Investigate watchdog or crashes.\n"
               f"Recent starts: " + ", ".join(s["ts"] for s in starts[-5:]))
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        print(msg)
        try:
            import requests
            from config import BOT_TOKEN, CHAT_ID
            chat_ids = [p.strip() for p in str(CHAT_ID or "").replace(";", ",").split(",") if p.strip()]
            for cid in chat_ids:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": cid, "text": msg}, timeout=10,
                    )
                except Exception:
                    pass
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
