from __future__ import annotations

from typing import Any

from advisors.range_detector import detect_range_context


def analyze_range(snapshot: dict[str, Any]) -> dict[str, Any]:
    return detect_range_context(snapshot)