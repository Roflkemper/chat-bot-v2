from __future__ import annotations

from pathlib import Path

from storage.json_store import load_json, save_json


class BotRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = load_json(self.path, {"active_bots": ["core", "countertrend", "range", "ginarea"]})

    def summary(self) -> dict:
        return self.data

    def save(self) -> None:
        save_json(self.path, self.data)
