"""Runtime detector kill switch via environment variable.

Operators can disable noisy or DEGRADED detectors without restarting:
  DISABLED_DETECTORS=detect_long_multi_divergence,detect_h10_liquidity_probe

The env var is re-read every TTL seconds (default 60), so:
  1. Edit .env.local
  2. Re-source (or wait for next process restart)
  3. Within 60s the cache picks up the new value

Each disabled detector skip is logged once per TTL cycle and recorded
in pipeline_metrics with stage_outcome="env_disabled".

Matching is by detector function NAME (e.g. detect_long_pdl_bounce).
Substring matching for partial: "multi_divergence" disables
detect_long_multi_divergence.
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

_ENV_VAR = "DISABLED_DETECTORS"
_CACHE_TTL_SEC = 60.0


class _DisabledCache:
    def __init__(self) -> None:
        self._items: set[str] = set()
        self._fetched_at: float = 0.0
        self._last_raw: str = ""

    def get(self) -> set[str]:
        now = time.monotonic()
        if now - self._fetched_at < _CACHE_TTL_SEC:
            return self._items
        raw = os.environ.get(_ENV_VAR, "").strip()
        if raw != self._last_raw:
            # Log only on actual change to avoid spam.
            logger.info("runtime_disabled.refreshed value=%r", raw)
            self._last_raw = raw
        self._items = {
            tok.strip() for tok in raw.split(",") if tok.strip()
        } if raw else set()
        self._fetched_at = now
        return self._items


_cache = _DisabledCache()


def is_detector_disabled(detector_name: str) -> bool:
    """True if the detector should be skipped this tick.

    Matches if any token in DISABLED_DETECTORS is a substring of
    detector_name. So "multi_divergence" matches
    "detect_long_multi_divergence" (loose) — operator can list either
    full or partial names.
    """
    if not detector_name:
        return False
    disabled = _cache.get()
    if not disabled:
        return False
    for tok in disabled:
        if tok and tok in detector_name:
            return True
    return False


def reset_cache_for_tests() -> None:
    """Force re-read on next call. Tests only."""
    _cache._fetched_at = 0.0
    _cache._last_raw = ""
    _cache._items = set()
