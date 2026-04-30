from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterator, cast

from .models import CapturedEvent, ManualAnnotation, OutcomeRecord
from .schemas import annotation_from_dict, annotation_to_dict, event_from_dict, event_to_dict, outcome_from_dict, outcome_to_dict

EVENTS_PATH = Path("state/decision_log/events.jsonl")
ANNOTATIONS_PATH = Path("state/decision_log/annotations.jsonl")
OUTCOMES_PATH = Path("state/decision_log/outcomes.jsonl")
LAST_SEEN_PATH = Path("state/decision_log/_last_seen.json")
MAX_JSONL_BYTES = 100 * 1024 * 1024

_LOCKS: dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    lock = _LOCKS.get(key)
    if lock is None:
        lock = threading.Lock()
        _LOCKS[key] = lock
    return lock


def _rotate_if_needed(path: Path) -> None:
    if not path.exists() or path.stat().st_size <= MAX_JSONL_BYTES:
        return
    oldest = path.with_suffix(path.suffix + ".5")
    if oldest.exists():
        oldest.unlink()
    for idx in range(4, 0, -1):
        src = path.with_suffix(path.suffix + f".{idx}")
        dst = path.with_suffix(path.suffix + f".{idx + 1}")
        if src.exists():
            src.replace(dst)
    path.replace(path.with_suffix(path.suffix + ".1"))


def append_jsonl(path: Path, record: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_for(path)
    with lock:
        _rotate_if_needed(path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_last_seen(path: Path = LAST_SEEN_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return {}


def save_last_seen(state: dict[str, Any], path: Path = LAST_SEEN_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_event(event: CapturedEvent, path: Path = EVENTS_PATH) -> Path:
    return append_jsonl(path, event_to_dict(event))


def iter_events(path: Path = EVENTS_PATH) -> Iterator[CapturedEvent]:
    for row in iter_jsonl(path):
        yield event_from_dict(row)


def append_annotation(annotation: ManualAnnotation, path: Path = ANNOTATIONS_PATH) -> Path:
    return append_jsonl(path, annotation_to_dict(annotation))


def iter_annotations(path: Path = ANNOTATIONS_PATH) -> Iterator[ManualAnnotation]:
    for row in iter_jsonl(path):
        yield annotation_from_dict(row)


def append_outcome(outcome: OutcomeRecord, path: Path = OUTCOMES_PATH) -> Path:
    return append_jsonl(path, outcome_to_dict(outcome))


def iter_outcomes(path: Path = OUTCOMES_PATH) -> Iterator[OutcomeRecord]:
    for row in iter_jsonl(path):
        yield outcome_from_dict(row)
