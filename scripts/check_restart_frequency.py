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
RESTART_LIMIT = 5
RESTART_WINDOW_HOURS = 1


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
                    starts.append(rec)
            except (ValueError, KeyError, json.JSONDecodeError):
                continue

    n = len(starts)
    print(f"[restart-check] {n} app_runner starts in last {RESTART_WINDOW_HOURS}h "
          f"(threshold: {RESTART_LIMIT})")
    if n >= RESTART_LIMIT:
        msg = (f"⚠ App_runner restarted {n} times in last {RESTART_WINDOW_HOURS}h "
               f"(threshold {RESTART_LIMIT}). Investigate watchdog or crashes.\n"
               f"Recent starts: " + ", ".join(s["ts"] for s in starts[-5:]))
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
