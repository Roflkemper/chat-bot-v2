from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


TIMEFRAME_SUFFIXES = ('15M', '5M', '1H', '4H', '1D')


@dataclass(frozen=True)
class CommandCapabilities:
    requires_analysis: bool = False
    requires_journal: bool = False
    requires_position: bool = False
    requires_active_journal: bool = False
    requires_active_position: bool = False
    supports_timeframe: bool = False
    default_timeframe: str | None = None
    renderer: str = 'plain'
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommandEntry:
    name: str
    handler_name: str
    capabilities: CommandCapabilities


@dataclass(frozen=True)
class CommandResolution:
    entry: CommandEntry
    resolved_timeframe: str | None = None


class CommandRegistry:
    def __init__(self) -> None:
        self._exact: dict[str, CommandEntry] = {}
        self._prefix_rules: list[tuple[str, Callable[[str], bool], CommandEntry]] = []

    def register(self, name: str, handler_name: str, *, capabilities: CommandCapabilities | None = None) -> None:
        self._exact[name.upper()] = CommandEntry(
            name=name.upper(),
            handler_name=handler_name,
            capabilities=capabilities or CommandCapabilities(),
        )

    def register_many(
        self,
        names: list[str],
        handler_name: str,
        *,
        capabilities: CommandCapabilities | None = None,
    ) -> None:
        for name in names:
            self.register(name, handler_name, capabilities=capabilities)

    def register_prefix(
        self,
        label: str,
        matcher: Callable[[str], bool],
        handler_name: str,
        *,
        capabilities: CommandCapabilities | None = None,
    ) -> None:
        self._prefix_rules.append(
            (label, matcher, CommandEntry(name=label.upper(), handler_name=handler_name, capabilities=capabilities or CommandCapabilities()))
        )

    def resolve(self, command: str) -> CommandResolution | None:
        normalized = (command or '').strip().upper()
        entry = self._exact.get(normalized)
        if entry is not None:
            return CommandResolution(entry=entry, resolved_timeframe=_resolve_timeframe(normalized, entry.capabilities))
        for _label, matcher, prefix_entry in self._prefix_rules:
            if matcher(normalized):
                return CommandResolution(entry=prefix_entry, resolved_timeframe=_resolve_timeframe(normalized, prefix_entry.capabilities))
        return None


def ends_with_known_timeframe(text: str) -> bool:
    return any(text.endswith(suffix) for suffix in TIMEFRAME_SUFFIXES)


def extract_timeframe(text: str) -> str | None:
    normalized = (text or '').strip().upper()
    for suffix in TIMEFRAME_SUFFIXES:
        if normalized.endswith(suffix):
            return suffix.lower()
    return None


def _resolve_timeframe(command: str, capabilities: CommandCapabilities) -> str | None:
    if capabilities.supports_timeframe:
        extracted = extract_timeframe(command)
        if extracted:
            return extracted
    if capabilities.default_timeframe:
        return capabilities.default_timeframe
    return None
