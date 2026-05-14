from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Literal, Optional

Direction = Literal["LONG", "SHORT", "NEUTRAL"]
Agreement = Literal["HIGH", "MID", "LOW", "CONFLICT"]


@dataclass
class ForecastConsensus:
    dominant: Direction
    agreement: Agreement
    confidence_adjustment: int
    veto_note: str = ""
    conflict_note: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def build_consensus(short_vec: Direction, session_bias: Direction, medium_bias: Direction, medium_phase: str) -> ForecastConsensus:
    votes = [short_vec, session_bias, medium_bias]
    long_count = votes.count("LONG")
    short_count = votes.count("SHORT")

    dominant: Direction = "NEUTRAL"
    agreement: Agreement = "CONFLICT"
    confidence_adjustment = 0
    veto_note = ""
    conflict_note = ""

    if long_count == 3 or short_count == 3:
        dominant = "LONG" if long_count == 3 else "SHORT"
        agreement = "HIGH"
        confidence_adjustment = 1
    elif long_count >= 2 and short_count == 0:
        dominant = "LONG"
        agreement = "MID"
    elif short_count >= 2 and long_count == 0:
        dominant = "SHORT"
        agreement = "MID"
    elif long_count == short_count:
        agreement = "CONFLICT"
        dominant = "NEUTRAL"
        conflict_note = "forecast layers disagree"
    else:
        dominant = "LONG" if long_count > short_count else "SHORT"
        agreement = "LOW"
        conflict_note = "mixed alignment"

    if medium_phase == "DISTRIBUTION" and dominant == "LONG":
        confidence_adjustment -= 1
        veto_note = "1d distribution weakens long"
    elif medium_phase == "ACCUMULATION" and dominant == "SHORT":
        confidence_adjustment -= 1
        veto_note = "1d accumulation weakens short"

    return ForecastConsensus(
        dominant=dominant,
        agreement=agreement,
        confidence_adjustment=confidence_adjustment,
        veto_note=veto_note,
        conflict_note=conflict_note,
    )
