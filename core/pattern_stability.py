from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Iterable, Literal, Optional

Direction = Literal["LONG", "SHORT", "NEUTRAL"]


@dataclass
class PatternSnapshot:
    direction: Direction
    strength: int
    confidence: float
    meaningful: bool
    ts: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class StablePatternResult:
    direction: Direction
    strength: int
    confidence: float
    stability_state: str
    flipped: bool
    note: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _opp(a: Direction, b: Direction) -> bool:
    return {a, b} == {"LONG", "SHORT"}


def stabilize_pattern_signal(
    current: PatternSnapshot,
    previous: Optional[PatternSnapshot] = None,
    *,
    flip_threshold: float = 0.15,
    min_persistence_bars: int = 2,
    persistence_bars_seen: int = 0,
    same_zone: bool = True,
    same_regime: bool = True,
) -> StablePatternResult:
    if previous is None:
        return StablePatternResult(
            direction=current.direction,
            strength=current.strength,
            confidence=current.confidence,
            stability_state="FRESH",
            flipped=False,
            note=current.note or "first pattern snapshot",
        )

    if current.direction == previous.direction:
        merged_conf = round((current.confidence + previous.confidence) / 2.0, 4)
        merged_strength = int(round((current.strength + previous.strength) / 2.0))
        return StablePatternResult(
            direction=current.direction,
            strength=merged_strength,
            confidence=merged_conf,
            stability_state="STABLE",
            flipped=False,
            note=current.note or "pattern direction stable",
        )

    # Weak / not meaningful opposite signal must not instantly flip.
    if _opp(current.direction, previous.direction):
        delta = abs(float(current.confidence) - float(previous.confidence))
        unstable_context = same_zone and same_regime

        if not current.meaningful:
            return StablePatternResult(
                direction=previous.direction,
                strength=previous.strength,
                confidence=previous.confidence,
                stability_state="LOCKED_PREVIOUS",
                flipped=False,
                note="new pattern not meaningful; keep previous direction",
            )

        if unstable_context and delta < flip_threshold:
            return StablePatternResult(
                direction="NEUTRAL",
                strength=min(previous.strength, current.strength),
                confidence=max(previous.confidence, current.confidence),
                stability_state="CONFLICT_SOFT",
                flipped=False,
                note="recent opposite pattern too weak to flip; downgrade to neutral/low",
            )

        if persistence_bars_seen < min_persistence_bars:
            return StablePatternResult(
                direction=previous.direction,
                strength=max(previous.strength - 5, 0),
                confidence=max(previous.confidence - 0.05, 0.0),
                stability_state="WAIT_PERSISTENCE",
                flipped=False,
                note=f"opposite pattern needs persistence >= {min_persistence_bars} bars",
            )

        return StablePatternResult(
            direction=current.direction,
            strength=current.strength,
            confidence=current.confidence,
            stability_state="CONFIRMED_FLIP",
            flipped=True,
            note="opposite pattern persisted; flip accepted",
        )

    # If one of them is neutral, prefer meaningful non-neutral side.
    if current.direction == "NEUTRAL" and previous.direction != "NEUTRAL":
        return StablePatternResult(
            direction=previous.direction if previous.meaningful else "NEUTRAL",
            strength=previous.strength,
            confidence=previous.confidence,
            stability_state="NEUTRALIZED",
            flipped=False,
            note="current signal neutral; preserve previous side if still meaningful",
        )

    return StablePatternResult(
        direction=current.direction,
        strength=current.strength,
        confidence=current.confidence,
        stability_state="FALLBACK",
        flipped=False,
        note=current.note or "fallback stability path",
    )
