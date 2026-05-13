"""Tests for R-2 + R-3 merge in telegram_emitter."""
from __future__ import annotations

from services.decision_layer.telegram_emitter import _merge_r2_r3


def _ev(rule_id: str, ts: str, payload: dict | None = None) -> dict:
    return {
        "rule_id": rule_id,
        "event_type": "regime_change" if rule_id == "R-2" else "regime_instability",
        "severity": "PRIMARY",
        "ts": ts,
        "payload": payload or {},
        "recommendation": f"{rule_id} fired.",
    }


def test_merges_r2_r3_within_window() -> None:
    events = [
        _ev("R-2", "2026-05-13T01:12:14+00:00", {"old_regime": "RANGE", "new_regime": "MARKUP"}),
        _ev("R-3", "2026-05-13T01:12:14+00:00", {"stability": 0.08}),
    ]
    merged = _merge_r2_r3(events)
    assert len(merged) == 1
    assert merged[0]["rule_id"] == "R-2+3"
    assert merged[0]["payload"]["stability"] == 0.08
    assert "0.08" in merged[0]["recommendation"]


def test_keeps_r2_alone_when_no_r3() -> None:
    events = [_ev("R-2", "2026-05-13T01:12:14+00:00")]
    merged = _merge_r2_r3(events)
    assert len(merged) == 1
    assert merged[0]["rule_id"] == "R-2"


def test_keeps_r3_alone_when_no_r2() -> None:
    events = [_ev("R-3", "2026-05-13T01:12:14+00:00", {"stability": 0.08})]
    merged = _merge_r2_r3(events)
    assert len(merged) == 1
    assert merged[0]["rule_id"] == "R-3"


def test_does_not_merge_if_too_far_apart() -> None:
    """R-2 and R-3 more than 60s apart → no merge."""
    events = [
        _ev("R-2", "2026-05-13T01:12:00+00:00"),
        _ev("R-3", "2026-05-13T01:15:00+00:00", {"stability": 0.08}),
    ]
    merged = _merge_r2_r3(events)
    assert len(merged) == 2
    assert {m["rule_id"] for m in merged} == {"R-2", "R-3"}


def test_handles_empty_list() -> None:
    assert _merge_r2_r3([]) == []


def test_multiple_r2_r3_pairs() -> None:
    """Несколько переходов в журнале — каждая пара мерджится отдельно."""
    events = [
        _ev("R-2", "2026-05-13T01:12:00+00:00"),
        _ev("R-3", "2026-05-13T01:12:00+00:00", {"stability": 0.08}),
        _ev("R-2", "2026-05-13T05:00:00+00:00"),
        _ev("R-3", "2026-05-13T05:00:00+00:00", {"stability": 0.10}),
    ]
    merged = _merge_r2_r3(events)
    assert len(merged) == 2
    assert all(m["rule_id"] == "R-2+3" for m in merged)
