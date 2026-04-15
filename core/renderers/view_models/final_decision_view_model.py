from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FinalDecisionViewModel:
    price: float
    decision_label: str
    market_bias: str
    primary_action: str
    mode: str
    confidence_or_strength: str
    why: str
    not_now: str
    warning: str
