from __future__ import annotations


def rank_candidates(items: list[dict]) -> list[dict]:
    def _score(x: dict) -> float:
        return (
            float(x.get("confidence", 0.0)) * 0.40
            + float(x.get("urgency", 0.0)) * 0.25
            + float(x.get("execution_quality", 0.0)) * 0.15
            + float(x.get("winrate", 0.0)) * 0.10
            + float(x.get("reentry_score", 0.0)) * 0.10
        )

    for item in items:
        item["ranking_score"] = round(_score(item), 2)
    return sorted(items, key=lambda x: x["ranking_score"], reverse=True)
