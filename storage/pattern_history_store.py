from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Literal, Optional

Direction = Literal["LONG", "SHORT", "NEUTRAL"]
RangePosition = Literal["EDGE_TOP", "UPPER", "MID", "LOWER", "EDGE_BOT"]


@dataclass
class PatternRecord:
    ts: str
    tf: str
    market_regime: str
    range_position: RangePosition
    direction: Direction
    future_move_pct: float
    horizon_bars: int
    normalized_closes: List[float]
    similarity_features: Dict[str, float]
    meta: Optional[Dict[str, object]] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "PatternRecord":
        return cls(
            ts=str(payload["ts"]),
            tf=str(payload["tf"]),
            market_regime=str(payload["market_regime"]),
            range_position=str(payload["range_position"]),
            direction=str(payload["direction"]),
            future_move_pct=float(payload["future_move_pct"]),
            horizon_bars=int(payload["horizon_bars"]),
            normalized_closes=[float(x) for x in payload.get("normalized_closes", [])],
            similarity_features={k: float(v) for k, v in dict(payload.get("similarity_features", {})).items()},
            meta=dict(payload.get("meta", {})) if payload.get("meta") else None,
        )


class PatternHistoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, record: PatternRecord) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def extend(self, records: Iterable[PatternRecord]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def iter_records(self, tf: str | None = None) -> Iterator[PatternRecord]:
        with self.path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                payload = json.loads(raw)
                if tf and str(payload.get("tf")) != tf:
                    continue
                yield PatternRecord.from_dict(payload)

    def load(self, tf: str | None = None, limit: int | None = None) -> List[PatternRecord]:
        rows = list(self.iter_records(tf=tf))
        return rows[-limit:] if limit else rows
