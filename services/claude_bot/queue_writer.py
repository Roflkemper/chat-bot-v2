"""Appends incoming TZ proposals to docs/CONTEXT/QUEUE.md."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_QUEUE_MD = _ROOT / "docs" / "CONTEXT" / "QUEUE.md"


def _looks_like_tz(text: str) -> bool:
    """Heuristic: message looks like a TZ proposal."""
    upper = text.upper()
    triggers = ["TZ-", "ТЗ ", "ТЗ:", "TASK:", "ЗАДАЧА:", "TECHNICAL TASK"]
    return any(t in upper for t in triggers)


def append_if_tz(text: str, from_chat_id: int | str) -> bool:
    """If text looks like a TZ, append it to QUEUE.md. Returns True if appended."""
    if not _looks_like_tz(text):
        return False

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    header = f"\n---\n## TZ received {now} (chat {from_chat_id})\n\n"

    try:
        _QUEUE_MD.parent.mkdir(parents=True, exist_ok=True)
        with _QUEUE_MD.open("a", encoding="utf-8") as f:
            f.write(header + text.strip() + "\n")
        return True
    except Exception:
        return False
