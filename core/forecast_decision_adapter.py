from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Agreement = Literal["HIGH", "MID", "LOW", "CONFLICT"]
Direction = Literal["LONG", "SHORT", "NEUTRAL"]
State = Literal["MID_RANGE", "SEARCH_TRIGGER", "PRE_ACTIVATION", "CONFIRMED", "MANAGE", "OVERRUN"]


@dataclass
class DecisionAdjustment:
    confidence_delta: int
    block_aggressive_entry: bool
    block_new_entry: bool
    note: str


@dataclass
class ConsensusInput:
    dominant: Direction
    agreement: Agreement
    confidence_adjustment: int = 0
    veto_note: str = ""
    conflict_note: str = ""


@dataclass
class PatternInput:
    direction: Direction
    meaningful: bool
    strength: int
    note: str = ""


def apply_forecast_to_decision(
    state: State,
    action_side: Direction,
    base_confidence: int,
    consensus: ConsensusInput,
    pattern_1h: Optional[PatternInput] = None,
    pattern_4h: Optional[PatternInput] = None,
    pattern_1d: Optional[PatternInput] = None,
) -> DecisionAdjustment:
    confidence_delta = consensus.confidence_adjustment
    block_aggressive_entry = False
    block_new_entry = False
    notes = []

    if consensus.agreement == "HIGH" and consensus.dominant == action_side and state in {"PRE_ACTIVATION", "CONFIRMED", "MANAGE"}:
        confidence_delta += 1
        notes.append("forecast aligned across layers")
    elif consensus.agreement == "CONFLICT":
        confidence_delta -= 2
        block_aggressive_entry = True
        notes.append(consensus.conflict_note or "forecast conflict")
    elif consensus.agreement == "LOW":
        confidence_delta -= 1
        block_aggressive_entry = True
        notes.append("forecast alignment weak")

    if consensus.veto_note:
        confidence_delta -= 1
        block_aggressive_entry = True
        notes.append(consensus.veto_note)

    for label, pattern in (("1h", pattern_1h), ("4h", pattern_4h), ("1d", pattern_1d)):
        if not pattern:
            continue
        if pattern.meaningful and pattern.direction == action_side:
            confidence_delta += 1 if label == "1h" else 0
            notes.append(f"{label} pattern supports setup")
        elif pattern.meaningful and pattern.direction not in {action_side, "NEUTRAL"}:
            confidence_delta -= 1
            notes.append(f"{label} pattern conflicts with setup")

    final_conf = max(0, min(100, base_confidence + confidence_delta * 10))
    if state == "CONFIRMED" and final_conf < 50:
        block_new_entry = True
        notes.append("final confidence too low for confirmed entry")
    if state in {"SEARCH_TRIGGER", "PRE_ACTIVATION"} and final_conf < 40:
        block_aggressive_entry = True

    return DecisionAdjustment(
        confidence_delta=confidence_delta,
        block_aggressive_entry=block_aggressive_entry,
        block_new_entry=block_new_entry,
        note="; ".join(dict.fromkeys(notes)) if notes else "no forecast adjustment",
    )
