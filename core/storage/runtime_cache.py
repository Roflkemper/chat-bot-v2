from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RuntimeCache:
    ttl_seconds: int = 45
    _lock: Lock = field(default_factory=Lock)
    _updated_at: float = 0.0
    _ranked: list[dict[str, Any]] = field(default_factory=list)

    def is_fresh(self) -> bool:
        if not self._ranked:
            return False
        return (time.time() - self._updated_at) <= self.ttl_seconds

    def get(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._ranked)

    def set(self, ranked: list[dict[str, Any]]) -> None:
        with self._lock:
            self._ranked = list(ranked)
            self._updated_at = time.time()

    def clear(self) -> None:
        with self._lock:
            self._ranked = []
            self._updated_at = 0.0

    def info(self) -> dict[str, Any]:
        with self._lock:
            age = time.time() - self._updated_at if self._updated_at else None
            return {
                "items": len(self._ranked),
                "updated_at": self._updated_at,
                "age_sec": round(age, 2) if age is not None else None,
                "ttl_seconds": self.ttl_seconds,
                "fresh": self.is_fresh(),
            }