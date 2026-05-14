"""Bot UID resolver.

Reads data/bot_registry.json and provides three public functions:
  - resolve_to_uid(any_handle) -> uid | None
  - get_display(uid) -> str
  - list_bots(filter_side) -> list[dict]

A handle can be a GinArea numeric ID, an alias, or a display name.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = _ROOT / "data" / "bot_registry.json"

UID_RE = re.compile(r"^[a-z]+:(long|short|spot|hedge|test):[a-z0-9]+:\d{3}$")

_cache: Optional[dict] = None
_cache_path: Optional[Path] = None


def _load(path: Path = REGISTRY_PATH) -> dict:
    """Load registry JSON. Cached by path."""
    global _cache, _cache_path
    if _cache is not None and _cache_path == path:
        return _cache
    if not path.exists():
        _cache = {"bots": {}}
    else:
        _cache = json.loads(path.read_text(encoding="utf-8"))
    _cache_path = path
    return _cache


def _invalidate_cache() -> None:
    global _cache, _cache_path
    _cache = None
    _cache_path = None


def resolve_to_uid(handle: str, path: Path = REGISTRY_PATH) -> Optional[str]:
    """Resolve any handle (ginarea_id / alias / display_name) to a stable UID.

    Returns None if the handle isn't in the registry.
    """
    if not handle:
        return None
    handle_str = str(handle).strip()
    # Already a UID?
    if UID_RE.match(handle_str):
        return handle_str

    registry = _load(path)
    bots = registry.get("bots", {})

    # Strip trailing ".0" GinArea sometimes emits
    handle_clean = handle_str.rstrip(".0") if handle_str.endswith(".0") else handle_str

    for uid, info in bots.items():
        if str(info.get("ginarea_id", "")) == handle_clean:
            return uid
        if info.get("alias_short") == handle_str:
            return uid
        if info.get("display_name") == handle_str:
            return uid
    return None


def get_display(uid: str, path: Path = REGISTRY_PATH) -> str:
    """Operator-friendly label for the UID; falls back to UID if not found."""
    registry = _load(path)
    info = registry.get("bots", {}).get(uid, {})
    return info.get("alias_short") or info.get("display_name") or uid


def list_bots(filter_side: Optional[str] = None, path: Path = REGISTRY_PATH) -> list[dict]:
    """List all bots, optionally filtered by side."""
    registry = _load(path)
    out = []
    for uid, info in registry.get("bots", {}).items():
        if filter_side is not None and info.get("side") != filter_side:
            continue
        row = dict(info)
        row["bot_uid"] = uid
        out.append(row)
    return out
