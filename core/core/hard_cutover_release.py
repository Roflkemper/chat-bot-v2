from __future__ import annotations

from typing import Any, Dict

from core.execution_snapshot import build_execution_snapshot
from renderers.hard_cutover_renderer import render_hard_cutover


def apply_hard_cutover(payload: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = build_execution_snapshot(payload)
    return {
        'execution_snapshot': snapshot,
        'telegram_text': render_hard_cutover(snapshot),
        'legacy_disabled': True,
        'source_of_truth': 'execution_snapshot',
    }
