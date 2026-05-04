"""Bot registry: stable UIDs + display layer for all bots.

See docs/DESIGN/BOT_ID_SCHEMA_v0_1.md for the spec.
"""
from .resolver import resolve_to_uid, get_display, list_bots, REGISTRY_PATH

__all__ = ["resolve_to_uid", "get_display", "list_bots", "REGISTRY_PATH"]
