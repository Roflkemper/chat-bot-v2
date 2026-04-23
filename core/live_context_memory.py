from __future__ import annotations

from typing import Any, Dict

from storage.json_store import load_json, save_json

STATE_FILE = "state/live_context_memory.json"


def _s(value: Any, default: str = "") -> str:
    return str(value or default).strip()


def build_live_context_memory(current: Dict[str, Any] | None = None) -> Dict[str, Any]:
    current = current or {}
    state = load_json(STATE_FILE, {})
    out = dict(state)

    classification = _s(current.get("fast_move_classification"), "BALANCED").upper()
    acceptance = _s(current.get("move_acceptance"), "UNDEFINED").upper()
    direction = _s(current.get("direction"), "НЕЙТРАЛЬНО").upper()
    tf = _s(current.get("timeframe"), "1h")

    if acceptance not in {"", "UNDEFINED"}:
        out["acceptance_memory"] = f"{tf}:{direction}:{acceptance}"

    if classification in {"LIKELY_FAKE_UP", "LIKELY_FAKE_DOWN"}:
        out["last_fake_signal"] = f"{tf}:{classification}"
    elif classification in {"CONTINUATION_UP", "CONTINUATION_DOWN"}:
        out["last_continuation_signal"] = f"{tf}:{classification}"

    save_json(STATE_FILE, out)
    return out
