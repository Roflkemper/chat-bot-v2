"""Runtime detector kill switch.

Two sources, both refreshed every TTL seconds (60s):

  1. Environment variable DISABLED_DETECTORS (comma-separated).
     Set in .env.local for permanent across restarts.

  2. State file state/disabled_detectors.json — runtime additions via
     TG `/disable <name>` command. Lives next to other state files,
     survives restart. Operator can clear via `/enable <name>` or by
     deleting the file.

Both sources are unioned. Either present → disabled.

Matching: substring of detector function name. Token "multi_divergence"
matches `detect_long_multi_divergence`.

Each disabled detector skip is recorded in pipeline_metrics with
stage_outcome="env_disabled".
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_VAR = "DISABLED_DETECTORS"
_CACHE_TTL_SEC = 60.0
_ROOT = Path(__file__).resolve().parents[2]
_STATE_PATH = _ROOT / "state" / "disabled_detectors.json"


def _read_state_file() -> set[str]:
    """Returns the set of tokens in state/disabled_detectors.json.

    Schema: {"tokens": ["short_pdh_rejection", "h10_liquidity"]}
    """
    if not _STATE_PATH.exists():
        return set()
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        toks = data.get("tokens") if isinstance(data, dict) else None
        if not isinstance(toks, list):
            return set()
        return {str(t).strip() for t in toks if str(t).strip()}
    except (OSError, ValueError, json.JSONDecodeError):
        logger.exception("runtime_disabled.state_read_failed")
        return set()


def _write_state_file(tokens: set[str]) -> None:
    """Atomic write of state file. Empty tokens → file deleted."""
    try:
        if not tokens:
            _STATE_PATH.unlink(missing_ok=True)
            return
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"tokens": sorted(tokens)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(_STATE_PATH)
    except OSError:
        logger.exception("runtime_disabled.state_write_failed")


class _DisabledCache:
    def __init__(self) -> None:
        self._items: set[str] = set()
        self._fetched_at: float = 0.0
        self._last_signature: str = ""

    def get(self) -> set[str]:
        now = time.monotonic()
        if now - self._fetched_at < _CACHE_TTL_SEC:
            return self._items
        env_raw = os.environ.get(_ENV_VAR, "").strip()
        env_set = {tok.strip() for tok in env_raw.split(",") if tok.strip()} if env_raw else set()
        state_set = _read_state_file()
        combined = env_set | state_set
        signature = f"{sorted(env_set)}|{sorted(state_set)}"
        if signature != self._last_signature:
            logger.info("runtime_disabled.refreshed env=%s state=%s",
                         sorted(env_set), sorted(state_set))
            self._last_signature = signature
        self._items = combined
        self._fetched_at = now
        return self._items


_cache = _DisabledCache()


def is_detector_disabled(detector_name: str) -> bool:
    """True if the detector should be skipped this tick."""
    if not detector_name:
        return False
    disabled = _cache.get()
    if not disabled:
        return False
    for tok in disabled:
        if tok and tok in detector_name:
            return True
    return False


def list_disabled() -> dict:
    """Return current disabled state for /status / /disable list commands."""
    env_raw = os.environ.get(_ENV_VAR, "").strip()
    env_set = {tok.strip() for tok in env_raw.split(",") if tok.strip()} if env_raw else set()
    state_set = _read_state_file()
    return {"env": sorted(env_set), "state_file": sorted(state_set)}


def add_runtime_disabled(token: str) -> bool:
    """Add a token to state/disabled_detectors.json. Returns True if added,
    False if already present."""
    token = (token or "").strip()
    if not token:
        return False
    current = _read_state_file()
    if token in current:
        return False
    current.add(token)
    _write_state_file(current)
    reset_cache_for_tests()  # next call sees fresh
    return True


def remove_runtime_disabled(token: str) -> bool:
    """Remove a token. Returns True if removed, False if not present."""
    token = (token or "").strip()
    if not token:
        return False
    current = _read_state_file()
    if token not in current:
        return False
    current.discard(token)
    _write_state_file(current)
    reset_cache_for_tests()
    return True


def reset_cache_for_tests() -> None:
    """Force re-read on next call. Tests only (also called internally
    after state mutation to make changes immediately visible)."""
    _cache._fetched_at = 0.0
    _cache._last_signature = ""
    _cache._items = set()
