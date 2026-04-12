from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storage.json_store import append_jsonl


class DecisionJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def log(self, payload: dict[str, Any]) -> None:
        row = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        append_jsonl(self.path, row)
