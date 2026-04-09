from __future__ import annotations

from pathlib import Path

from storage.json_store import load_json, save_json


class PositionManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.state = load_json(self.path, {})

    def get(self, key: str) -> dict:
        return self.state.get(key, {"state": "CANDIDATE"})

    def set(self, key: str, value: dict) -> None:
        self.state[key] = value
        save_json(self.path, self.state)

    def all_states(self) -> dict:
        return self.state
