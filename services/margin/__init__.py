"""Margin data source for Decision Layer M-* family.

See margin_source.py for the public API and design rationale.
"""
from services.margin.margin_source import (
    DEFAULT_AUTOMATED_SOURCE_PATH,
    DEFAULT_OVERRIDE_PATH,
    MarginCommandError,
    MarginRecord,
    append_override,
    parse_override_command,
    read_latest_margin,
)

__all__ = [
    "DEFAULT_AUTOMATED_SOURCE_PATH",
    "DEFAULT_OVERRIDE_PATH",
    "MarginCommandError",
    "MarginRecord",
    "append_override",
    "parse_override_command",
    "read_latest_margin",
]
