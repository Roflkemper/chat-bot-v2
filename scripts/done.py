"""Send a Telegram notification when a task is done.

Usage (from Claude or manually):
    python scripts/done.py "TZ-056 complete: 20 tests green, committed"
    python scripts/done.py  # sends generic "done" message
"""
from __future__ import annotations

import io
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# Windows terminal may use CP1251/CP866 — force UTF-8 output
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8bom"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config as _cfg


TG_LIMIT = 4000  # Telegram hard cap 4096; leave room for prefix/markup


def _send_chunk(token: str, chat_id: str, text: str) -> bool:
    """Send one text chunk. No HTML parse_mode — avoid escaping bugs on user content."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        print(f"[done.py] Telegram HTTPError {e.code}: {body[:300]}")
        return False
    except urllib.error.URLError as e:
        print(f"[done.py] Telegram URLError: {e}")
        return False


def _split_chunks(text: str, limit: int = TG_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text); break
        # Prefer splitting on newline
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


def notify(text: str) -> bool:
    token = _cfg.BOT_TOKEN
    chat_id = _cfg.CHAT_ID
    if not token or not chat_id:
        print("[done.py] No BOT_TOKEN/CHAT_ID configured — skipping notification")
        return False

    body = f"🤖 Claude Code\n{text}"
    chunks = _split_chunks(body)
    n = len(chunks)
    all_ok = True
    for i, chunk in enumerate(chunks, 1):
        prefix = f"({i}/{n}) " if n > 1 else ""
        ok = _send_chunk(token, chat_id, prefix + chunk)
        if not ok:
            all_ok = False

    if all_ok:
        print(f"[done.py] Sent ({n} chunk{'s' if n>1 else ''}): {text[:200]}{'...' if len(text)>200 else ''}")
    return all_ok


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Task complete"
    sys.exit(0 if notify(msg) else 1)
