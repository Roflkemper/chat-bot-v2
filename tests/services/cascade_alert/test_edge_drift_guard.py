"""Tests for edge_drift_guard."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from services.cascade_alert.edge_drift_guard import (
    evaluate_drift,
    is_drifted,
    get_status_summary,
)


def _summary_fn(by_bucket: dict):
    def fn(*, min_samples=5):
        return {"total": sum(s.get("n", 0) for h in by_bucket.values() for s in h.values()),
                "by_bucket": by_bucket}
    return fn


def test_no_drift_when_accuracy_above_threshold(tmp_path: Path) -> None:
    sp = tmp_path / "drift.json"
    send = MagicMock()
    summary = _summary_fn({
        "long": {"12h": {"n": 15, "accuracy": 73.0}},
        "short": {"24h": {"n": 12, "accuracy": 65.0}},
    })
    statuses = evaluate_drift(summary_fn=summary, send_fn=send, state_path=sp)
    assert all(not s.drifted for s in statuses)
    send.assert_not_called()


def test_drift_detected_when_below_60pct(tmp_path: Path) -> None:
    sp = tmp_path / "drift.json"
    send = MagicMock()
    summary = _summary_fn({
        "long": {"12h": {"n": 15, "accuracy": 53.3}},
    })
    statuses = evaluate_drift(summary_fn=summary, send_fn=send, state_path=sp)
    assert any(s.drifted for s in statuses)
    send.assert_called_once()
    msg = send.call_args[0][0]
    assert "EDGE DRIFT" in msg
    assert "53.3" in msg
    assert "long" in msg


def test_drift_alert_idempotent(tmp_path: Path) -> None:
    """Повторный eval с тем же drift → send_fn не зовётся снова."""
    sp = tmp_path / "drift.json"
    send = MagicMock()
    summary = _summary_fn({
        "long": {"12h": {"n": 15, "accuracy": 53.3}},
    })
    evaluate_drift(summary_fn=summary, send_fn=send, state_path=sp)
    send.reset_mock()
    evaluate_drift(summary_fn=summary, send_fn=send, state_path=sp)
    send.assert_not_called()


def test_n_below_min_samples_skipped(tmp_path: Path) -> None:
    sp = tmp_path / "drift.json"
    send = MagicMock()
    summary = _summary_fn({
        "long": {"12h": {"n": 5, "accuracy": 40.0}},  # too few samples
    })
    statuses = evaluate_drift(summary_fn=summary, send_fn=send, state_path=sp)
    assert statuses == []
    send.assert_not_called()


def test_recovery_clears_drift_flag(tmp_path: Path) -> None:
    """Если accuracy восстановилась — drifted=False, detected_at очищен."""
    sp = tmp_path / "drift.json"
    send = MagicMock()
    # first: drift
    evaluate_drift(
        summary_fn=_summary_fn({"long": {"12h": {"n": 15, "accuracy": 53.0}}}),
        send_fn=send, state_path=sp,
    )
    assert is_drifted("long", 5.0, state_path=sp)
    # then: recovery
    evaluate_drift(
        summary_fn=_summary_fn({"long": {"12h": {"n": 20, "accuracy": 75.0}}}),
        send_fn=send, state_path=sp,
    )
    assert not is_drifted("long", 5.0, state_path=sp)


def test_is_drifted_lookup_by_threshold(tmp_path: Path) -> None:
    sp = tmp_path / "drift.json"
    evaluate_drift(
        summary_fn=_summary_fn({
            "long": {"12h": {"n": 15, "accuracy": 50.0}},          # drifted
            "mega_long": {"12h": {"n": 12, "accuracy": 80.0}},     # healthy
        }),
        state_path=sp,
    )
    assert is_drifted("long", 5.0, state_path=sp) is True
    assert is_drifted("long", 10.0, state_path=sp) is False  # mega bucket


def test_status_summary_counts(tmp_path: Path) -> None:
    sp = tmp_path / "drift.json"
    evaluate_drift(
        summary_fn=_summary_fn({
            "long": {"12h": {"n": 15, "accuracy": 50.0}},
            "short": {"12h": {"n": 12, "accuracy": 70.0}},
        }),
        state_path=sp,
    )
    summary = get_status_summary(state_path=sp)
    assert summary["drifted_count"] == 1
    assert summary["healthy_count"] == 1
    assert "long_12h" in summary["drifted"]
