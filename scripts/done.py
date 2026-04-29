"""Send a Telegram notification when a task is done.

Usage (from Claude or manually):
    python scripts/done.py "TZ-056 complete: 20 tests green, committed"
    python scripts/done.py  # sends generic "done" message
"""
from __future__ import annotations

import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config as _cfg


def notify(text: str) -> bool:
    token = _cfg.BOT_TOKEN
    chat_id = _cfg.CHAT_ID
    if not token or not chat_id:
        print("[done.py] No BOT_TOKEN/CHAT_ID configured — skipping notification")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": f"🤖 Claude Code\n{text}",
        "parse_mode": "HTML",
    }).encode()

    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as resp:
            ok = resp.status == 200
    except urllib.error.URLError as e:
        print(f"[done.py] Telegram error: {e}")
        return False

    if ok:
        print(f"[done.py] Sent: {text}")
    return ok


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Task complete"
    sys.exit(0 if notify(msg) else 1)
