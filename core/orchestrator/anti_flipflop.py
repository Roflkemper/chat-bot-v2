"""Anti-flip-flop filter для orchestrator-changes.

Проблема (13.05 03:18-03:28):
  03:18  RUN→REDUCE  (TREND_UP)
  03:22  REDUCE→RUN  (COMPRESSION)
  03:28  RUN→REDUCE  (TREND_UP)
Три переключения за 10 минут на weekend low-vol. Каждое = 8 TG-сообщений.

Защита: после любого change блокируем повторные изменения той же категории
на MIN_DWELL_SECONDS. State хранится в state/orchestrator_dwell.json для
переживания рестартов.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_PATH = Path("state/orchestrator_dwell.json")
MIN_DWELL_SECONDS = 30 * 60  # 30 min — анти-flip-flop, но всё ещё реактивно


def _read_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict, path: Path = STATE_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("anti_flipflop.write_failed path=%s", path)


def should_suppress(
    category_key: str,
    *,
    now: datetime | None = None,
    min_dwell_sec: int = MIN_DWELL_SECONDS,
    state_path: Path = STATE_PATH,
) -> tuple[bool, float]:
    """Returns (suppress, seconds_since_last_change).

    Если для category_key прошло меньше min_dwell_sec — глушим.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    state = _read_state(state_path)
    last_iso = state.get(category_key, {}).get("ts")
    if not last_iso:
        return False, float("inf")
    try:
        last_ts = datetime.fromisoformat(last_iso)
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False, float("inf")
    elapsed = (now - last_ts).total_seconds()
    return elapsed < min_dwell_sec, elapsed


def record_change(
    category_key: str,
    from_action: str,
    to_action: str,
    *,
    now: datetime | None = None,
    state_path: Path = STATE_PATH,
) -> None:
    """Запомнить факт смены — для последующих should_suppress проверок."""
    if now is None:
        now = datetime.now(timezone.utc)
    state = _read_state(state_path)
    state[category_key] = {
        "ts": now.isoformat(),
        "from_action": from_action,
        "to_action": to_action,
    }
    _write_state(state, state_path)
