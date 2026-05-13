"""Live-config tracker для GinArea ботов.

Хранит снапшоты запущенных в live конфигов: какие параметры, когда стартовал,
ожидаемый profit/vol по backtest. Через неделю/месяц можно сравнить с
реальной PnL — если расхождение >30%, режим рынка отличается от backtest.

Файл: state/ginarea_live_configs.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_PATH = Path("state/ginarea_live_configs.json")


@dataclass
class LiveConfig:
    bot_id: str
    name: str
    side: str
    gs: float
    thresh: float
    td: float
    mult: float
    tp: str
    max_size: str
    started_at: str
    expected_profit_3mo_usd: float
    expected_vol_3mo_musd: float
    expected_peak_usd: float
    note: str = ""
    stopped_at: Optional[str] = None


def _read_state(path: Path = STATE_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _write_state(rows: list[dict], path: Path = STATE_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("live_config_tracker.write_failed path=%s", path)


def add_config(cfg: LiveConfig, *, path: Path = STATE_PATH) -> None:
    rows = _read_state(path)
    rows.append(asdict(cfg))
    _write_state(rows, path)


def mark_stopped(bot_id: str, *, path: Path = STATE_PATH) -> bool:
    rows = _read_state(path)
    now = datetime.now(timezone.utc).isoformat()
    updated = False
    for r in rows:
        if r.get("bot_id") == bot_id and not r.get("stopped_at"):
            r["stopped_at"] = now
            updated = True
    if updated:
        _write_state(rows, path)
    return updated


def active_configs(*, path: Path = STATE_PATH) -> list[dict]:
    return [r for r in _read_state(path) if not r.get("stopped_at")]


def days_since(iso_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 86400
    except (ValueError, TypeError):
        return 0.0


def expected_so_far_usd(cfg: dict) -> float:
    """Линейная экстраполяция: ожидаемый profit за фактический срок live."""
    days = days_since(cfg.get("started_at", ""))
    return cfg.get("expected_profit_3mo_usd", 0.0) * days / 90.0
