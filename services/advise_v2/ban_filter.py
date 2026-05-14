from __future__ import annotations

from services.advise_v2.setup_matcher import SetupMatch

HARD_BAN_PATTERNS = frozenset({"P-5", "P-8", "P-10"})


def filter_banned_patterns(matches: list[SetupMatch]) -> list[SetupMatch]:
    """
    Remove HARD_BAN patterns from the match list.
    Pure function.
    """
    return [match for match in matches if match.pattern_id not in HARD_BAN_PATTERNS]


def is_banned(pattern_id: str) -> bool:
    """Single-pattern check."""
    return pattern_id in HARD_BAN_PATTERNS
