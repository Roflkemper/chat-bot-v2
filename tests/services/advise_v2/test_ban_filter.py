from __future__ import annotations

from services.advise_v2 import SetupMatch, filter_banned_patterns, is_banned


def _match(pattern_id: str, confidence: float = 0.5) -> SetupMatch:
    return SetupMatch(
        pattern_id=pattern_id,
        pattern_name=pattern_id,
        confidence=confidence,
        direction="neutral",
    )


def test_filter_removes_p5_p8_p10():
    matches = [_match("P-1"), _match("P-5"), _match("P-8"), _match("P-10")]
    filtered = filter_banned_patterns(matches)
    assert [match.pattern_id for match in filtered] == ["P-1"]


def test_filter_keeps_others():
    matches = [_match("P-1"), _match("P-2"), _match("P-9")]
    filtered = filter_banned_patterns(matches)
    assert [match.pattern_id for match in filtered] == ["P-1", "P-2", "P-9"]


def test_is_banned_correct():
    assert is_banned("P-5") is True
    assert is_banned("P-8") is True
    assert is_banned("P-10") is True
    assert is_banned("P-2") is False


def test_filter_empty_list_returns_empty():
    assert filter_banned_patterns([]) == []


def test_filter_preserves_order():
    matches = [_match("P-2"), _match("P-5"), _match("P-1"), _match("P-10"), _match("P-7")]
    filtered = filter_banned_patterns(matches)
    assert [match.pattern_id for match in filtered] == ["P-2", "P-1", "P-7"]
