from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def make_request_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class RequestTrace:
    command: str
    chat_id: int | None = None
    request_id: str = field(default_factory=make_request_id)
    started_at: float = field(default_factory=time.time)
    marks: dict[str, int] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    def mark(self, name: str) -> int:
        ms = int((time.time() - self.started_at) * 1000)
        self.marks[name] = ms
        return ms

    def set(self, **kwargs: Any) -> None:
        self.context.update(kwargs)

    @property
    def total_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    def marks_text(self) -> str:
        if not self.marks:
            return '-'
        return ', '.join(f"{k}={v}ms" for k, v in self.marks.items())

    def as_metadata(self) -> dict[str, Any]:
        return {
            'request_id': self.request_id,
            'command': self.command,
            'chat_id': self.chat_id,
            'total_ms': self.total_ms,
            'marks': dict(self.marks),
            'context': dict(self.context),
        }
