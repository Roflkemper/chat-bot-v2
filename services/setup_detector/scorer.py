from __future__ import annotations

from .models import SetupBasis, SetupType

_LONG_TYPES = {
    SetupType.LONG_DUMP_REVERSAL,
    SetupType.LONG_PDL_BOUNCE,
    SetupType.LONG_OVERSOLD_RECLAIM,
    SetupType.LONG_LIQ_MAGNET,
}
_SHORT_TYPES = {
    SetupType.SHORT_RALLY_FADE,
    SetupType.SHORT_PDH_REJECTION,
    SetupType.SHORT_OVERBOUGHT_FADE,
    SetupType.SHORT_LIQ_MAGNET,
}

_SESSION_BOOSTS: dict[str, float] = {
    "NY_AM": 8.0,
    "LONDON": 5.0,
    "NY_PM": 3.0,
    "NY_LUNCH": -3.0,
    "ASIA": -5.0,
    "NONE": 0.0,
}


def compute_strength(basis: tuple[SetupBasis, ...]) -> int:
    """Map basis weights to a wider 1..10 integer strength distribution."""
    if not basis:
        return 1
    total = sum(max(0.0, min(1.0, b.weight)) for b in basis)
    max_possible = float(len(basis))
    ratio = total / max_possible if max_possible > 0 else 0.0

    # Non-linear mapping prevents 0.8-1.0 weight clusters from collapsing
    # into 9-10 for almost every setup in historical replay.
    base = 1.0 + (ratio ** 1.8) * 7.0
    count_bonus = min(2, len(basis) // 2)
    weak_count = sum(1 for b in basis if b.weight < 0.5)
    weak_penalty = min(2, weak_count)

    strength = int(round(base + count_bonus - weak_penalty))
    return max(1, min(10, strength))


def compute_confidence(
    setup_type: SetupType,
    basis: tuple[SetupBasis, ...],
    regime: str,
    session: str,
) -> float:
    """Returns 0.0..100.0 confidence score."""
    base = 50.0 + compute_strength(basis) * 3.0

    if setup_type in _LONG_TYPES:
        if regime in ("trend_down", "impulse_down"):
            base -= 10.0
        elif regime == "impulse_down_exhausting":
            base -= 3.0
        elif regime in ("trend_up", "impulse_up"):
            base += 5.0
    elif setup_type in _SHORT_TYPES:
        if regime in ("trend_up", "impulse_up"):
            base -= 10.0
        elif regime == "impulse_up_exhausting":
            base -= 3.0
        elif regime in ("trend_down", "impulse_down"):
            base += 5.0

    base += _SESSION_BOOSTS.get(session, 0.0)

    return max(0.0, min(100.0, base))
