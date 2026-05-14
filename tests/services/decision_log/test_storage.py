from __future__ import annotations

import threading
from pathlib import Path

from services.decision_log.models import ManualAnnotation
from services.decision_log.storage import append_annotation, append_event, iter_annotations, iter_events, load_last_seen, save_last_seen


def test_jsonl_append_round_trip_utf8_with_russian(tmp_path: Path, sample_event) -> None:
    path = tmp_path / "events.jsonl"
    append_event(sample_event, path)
    loaded = list(iter_events(path))
    assert loaded == [sample_event]


def test_jsonl_concurrent_writes_no_corruption(tmp_path: Path) -> None:
    path = tmp_path / "annotations.jsonl"

    def _writer(idx: int) -> None:
        append_annotation(
            ManualAnnotation(
                event_id=f"evt-20260430-{idx:04d}",
                annotation_ts=sample_ts(),
                is_intentional=bool(idx % 2),
                reason=f"причина {idx}",
            ),
            path,
        )

    threads = [threading.Thread(target=_writer, args=(idx,)) for idx in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(list(iter_annotations(path))) == 10


def test_last_seen_state_persisted(tmp_path: Path) -> None:
    path = tmp_path / "_last_seen.json"
    state = {"event_counter": 3, "free_margin_pct": 28.0}
    save_last_seen(state, path)
    assert load_last_seen(path) == state


def test_last_seen_state_recovered_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "_last_seen.json"
    save_last_seen({"regime_label": "trend_up"}, path)
    recovered = load_last_seen(path)
    assert recovered["regime_label"] == "trend_up"


def sample_ts():
    from datetime import datetime, timezone

    return datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
