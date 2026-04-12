from __future__ import annotations

from pathlib import Path

from storage.json_store import load_json, save_json


class WeightTuner:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.stats = load_json(self.path, {
            "wins": 0,
            "losses": 0,
            "setup_stats": {"A": 0, "B": 0, "C": 0},
            "execution_stats": {"A": 0, "B": 0, "C": 0},
        })

    def update_from_decision(self, payload: dict) -> None:
        result = payload.get("result")
        if result == "win":
            self.stats["wins"] += 1
        elif result == "loss":
            self.stats["losses"] += 1

        cd = payload.get("confidence_decomposition", {})
        sg = cd.get("setup_grade")
        eg = cd.get("execution_grade")
        if sg in self.stats["setup_stats"]:
            self.stats["setup_stats"][sg] += 1
        if eg in self.stats["execution_stats"]:
            self.stats["execution_stats"][eg] += 1
        save_json(self.path, self.stats)

    def summary(self) -> dict:
        total = self.stats["wins"] + self.stats["losses"]
        winrate = self.stats["wins"] / total * 100 if total else 0.0
        return {**self.stats, "total": total, "winrate": round(winrate, 2)}
