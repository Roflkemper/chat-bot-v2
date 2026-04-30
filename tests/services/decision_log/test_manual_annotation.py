from __future__ import annotations

from pathlib import Path

from services.decision_log.manual_annotation import handle_callback, handle_reason_message
from services.decision_log.storage import iter_annotations


def test_callback_intentional_records_annotation(tmp_path: Path) -> None:
    path = tmp_path / "annotations.jsonl"
    result = handle_callback(
        "decision_log:intentional:evt-20260430-0001",
        pending_reasons={},
        chat_id=1,
        annotations_path=path,
    )
    records = list(iter_annotations(path))
    assert result["status"] == "recorded"
    assert records[0].is_intentional is True


def test_callback_not_intentional_records_annotation(tmp_path: Path) -> None:
    path = tmp_path / "annotations.jsonl"
    result = handle_callback(
        "decision_log:automatic:evt-20260430-0001",
        pending_reasons={},
        chat_id=1,
        annotations_path=path,
    )
    records = list(iter_annotations(path))
    assert result["status"] == "recorded"
    assert records[0].is_intentional is False


def test_callback_add_reason_starts_conversation(tmp_path: Path) -> None:
    pending: dict[int, str] = {}
    result = handle_callback(
        "decision_log:reason:evt-20260430-0001",
        pending_reasons=pending,
        chat_id=1,
        annotations_path=tmp_path / "annotations.jsonl",
    )
    assert result["status"] == "awaiting_reason"
    assert pending[1] == "evt-20260430-0001"


def test_reason_text_recorded_to_annotation(tmp_path: Path) -> None:
    pending = {1: "evt-20260430-0001"}
    path = tmp_path / "annotations.jsonl"
    result = handle_reason_message(1, "Это было моё решение", pending_reasons=pending, annotations_path=path)
    records = list(iter_annotations(path))
    assert result is not None
    assert records[0].reason == "Это было моё решение"


def test_callback_ignore_no_annotation_recorded(tmp_path: Path) -> None:
    pending: dict[int, str] = {}
    result = handle_callback(
        "decision_log:ignore:evt-20260430-0001",
        pending_reasons=pending,
        chat_id=1,
        annotations_path=tmp_path / "annotations.jsonl",
    )
    assert result["status"] == "ignored"
    assert list(iter_annotations(tmp_path / "annotations.jsonl")) == []
