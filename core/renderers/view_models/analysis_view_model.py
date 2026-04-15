from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AnalysisViewModel:
    title: str
    timeframe: str
    price: float
    bias: str
    regime: str
    location: str
    upper_block: str
    lower_block: str
    movement_state: str
    movement_quality: str
    reaction_status: str
    where_to_watch: str
    analysis_note: str
