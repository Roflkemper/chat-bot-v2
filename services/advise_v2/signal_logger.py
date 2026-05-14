from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import SignalEnvelope

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SIGNALS_PATH: Path = _ROOT / "state" / "advise_signals.jsonl"
DEFAULT_NULL_SIGNALS_PATH: Path = _ROOT / "state" / "advise_null_signals.jsonl"


def _append_line(path: Path | str, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, ensure_ascii=False, default=str)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def log_signal(
    envelope: SignalEnvelope,
    path: Path | str = DEFAULT_SIGNALS_PATH,
) -> None:
    """Append a SignalEnvelope as one JSONL line."""
    _append_line(path, json.loads(envelope.model_dump_json()))


def log_null_signal(
    reason: str,
    context: dict[str, Any] | None = None,
    path: Path | str = DEFAULT_NULL_SIGNALS_PATH,
) -> None:
    """Append a null-signal record (no trade signal generated)."""
    record: dict[str, Any] = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "reason": reason,
        "context": context,
    }
    _append_line(path, record)


def iter_signals(
    path: Path | str = DEFAULT_SIGNALS_PATH,
) -> Iterator[SignalEnvelope]:
    """Yield SignalEnvelope objects from a JSONL file, skipping malformed lines."""
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield SignalEnvelope.model_validate_json(line)
            except Exception:
                continue


def iter_null_signals(
    path: Path | str = DEFAULT_NULL_SIGNALS_PATH,
) -> Iterator[dict[str, Any]]:
    """Yield raw null-signal dicts from a JSONL file, skipping malformed lines."""
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def count_signals(path: Path | str = DEFAULT_SIGNALS_PATH) -> int:
    """Return number of valid SignalEnvelope records in the file."""
    return sum(1 for _ in iter_signals(path))


def signals_by_pattern(
    setup_id: str,
    path: Path | str = DEFAULT_SIGNALS_PATH,
) -> list[SignalEnvelope]:
    """Return all signals whose setup_id matches the given pattern (e.g. 'P-2')."""
    return [s for s in iter_signals(path) if s.setup_id == setup_id]
