from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

SNAPSHOTS_CSV = _ROOT / "ginarea_live" / "snapshots.csv"
BOT_ALIASES_JSON = _ROOT / "ginarea_tracker" / "bot_aliases.json"
GINAREA_ENV = _ROOT / "ginarea_tracker" / ".env"

WINDOW_24H_SEC: int = 86400
WINDOW_6H_SEC: int = 6 * 3600
STALE_CSV_SEC: int = 300

DD_ALERT_PCT: float = 3.5
LIQ_ALERT_PCT: float = 25.0

MSG_CHAR_LIMIT: int = 3800
