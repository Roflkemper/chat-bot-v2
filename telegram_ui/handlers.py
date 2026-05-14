from __future__ import annotations

from pathlib import Path

from storage.json_store import load_json


def tail_jsonl(path: str | Path, limit: int = 5) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    items = []
    for line in lines[-limit:]:
        try:
            import json
            items.append(json.loads(line))
        except Exception:
            continue
    return items


def load_position_state(path: str | Path) -> dict:
    return load_json(path, {})
