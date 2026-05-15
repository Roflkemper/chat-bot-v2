"""Manual VPVR / key levels store — `state/manual_levels.json`.

Покрывает 2 источника:
1. Оператор через TG: `/levels BTCUSD poc=81500 vah=82200 val=80800`
2. TradingView Pro+ alerts (через TG-bridge или webhook): "LEVELS BTCUSD ..."

Уровни нужны для:
- Range Hunter: snap BUY к VAL, SELL к VAH (вместо ±0.10% от mid).
  Hypothesis: fill rate скачет с ~75% до ~85%+ т.к. VAH/VAL — реальные
  зоны бид/аск, а не случайные тики.
- Cascade alert entry plan: учитывать proximity к POC для расчёта stop.
- Pre-cascade alert: фильтр "не торговать если cascade происходит у POC"
  (рынок может застрять в зоне).

Schema (state/manual_levels.json):
{
  "BTCUSD": {
    "updated_at": "2026-05-15T20:30:00+00:00",
    "source": "tg_manual" | "tv_webhook" | "tv_tg_bridge",
    "poc": 81500.0,        // Point of Control
    "vah": 82200.0,        // Value Area High
    "val": 80800.0,        // Value Area Low
    "hvn": [82100, 81100], // High Volume Nodes (optional)
    "lvn": [81800],         // Low Volume Nodes (optional)
    "session_high": 82500.0,
    "session_low": 80300.0,
    "ttl_hours": 24        // через сколько часов считать stale
  },
  ...
}
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
LEVELS_PATH = ROOT / "state" / "manual_levels.json"

# Поля которые принимаем (key:value pairs в команде/alert)
SUPPORTED_KEYS = {"poc", "vah", "val", "session_high", "session_low"}
LIST_KEYS = {"hvn", "lvn"}  # comma-separated списки чисел
DEFAULT_TTL_H = 24


def _read_all() -> dict:
    if not LEVELS_PATH.exists():
        return {}
    try:
        return json.loads(LEVELS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("manual_levels.read_failed")
        return {}


def _write_all(data: dict) -> None:
    try:
        LEVELS_PATH.parent.mkdir(parents=True, exist_ok=True)
        LEVELS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        logger.exception("manual_levels.write_failed")


def get_levels(symbol: str = "BTCUSD") -> Optional[dict]:
    """Return current levels for symbol, or None if missing / stale."""
    data = _read_all()
    sym = symbol.upper()
    entry = data.get(sym)
    if not entry:
        return None
    try:
        updated = datetime.fromisoformat(entry.get("updated_at", ""))
    except (ValueError, TypeError):
        return None
    ttl_h = entry.get("ttl_hours", DEFAULT_TTL_H)
    if (datetime.now(timezone.utc) - updated) > timedelta(hours=ttl_h):
        return None  # stale
    return entry


def update_levels(symbol: str, levels: dict, *, source: str = "tg_manual",
                  now: Optional[datetime] = None) -> dict:
    """Merge new levels into store, set updated_at + source. Returns saved entry."""
    if now is None:
        now = datetime.now(timezone.utc)
    sym = symbol.upper()
    data = _read_all()
    entry = data.get(sym, {})
    # Clean: только supported keys
    for k, v in levels.items():
        k = k.lower()
        if k in SUPPORTED_KEYS:
            try:
                entry[k] = float(v)
            except (TypeError, ValueError):
                continue
        elif k in LIST_KEYS:
            if isinstance(v, str):
                items = [float(x.strip()) for x in v.split(",") if x.strip()]
            elif isinstance(v, (list, tuple)):
                items = [float(x) for x in v]
            else:
                continue
            entry[k] = items
        elif k == "ttl_hours":
            try:
                entry[k] = int(v)
            except (TypeError, ValueError):
                continue
    entry["updated_at"] = now.isoformat(timespec="seconds")
    entry["source"] = source
    data[sym] = entry
    _write_all(data)
    return entry


def clear_symbol(symbol: str) -> bool:
    """Remove symbol from store. Returns True if removed."""
    sym = symbol.upper()
    data = _read_all()
    if sym not in data:
        return False
    del data[sym]
    _write_all(data)
    return True


_CMD_RE = re.compile(r"(?i)(?:^|\s)(poc|vah|val|hvn|lvn|session_high|session_low|ttl_hours)\s*=\s*([\d.,\-eE]+)")
# Plain number — supports $79,100.5 / 79100 / 79100.5 / "79,100"
_NUMBER_RE = re.compile(r"\$?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def _parse_number(s: str) -> Optional[float]:
    s = s.replace("$", "").replace(",", "").replace(" ", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_levels_text(text: str) -> tuple[Optional[str], dict]:
    """Parse уровни в гибком формате. Понимает:

      1. Named: "LEVELS BTCUSD poc=81500 vah=82200 val=80800"
      2. Positional 3 числа: "LEVELS BTCUSD 79100 80500 78200" → poc,vah,val
         автоматически нормализуем: max=vah, min=val, средний=poc
      3. Positional 5 чисел: "LEVELS BTCUSD 79100 80500 78200 81000 78000"
         → poc, vah, val, session_high, session_low
      4. $ и запятые в числах: "$79,100 $80,500 $78,200" ОК
      5. Префиксы /levels, LEVELS, TV:LEVELS, VPVR — все съедаются

    Symbol — first all-caps token. Defaults to None (caller подставит "BTCUSD").
    """
    text = text.strip()
    parts = text.split(maxsplit=2)
    symbol = None
    rest = text
    if parts:
        first = parts[0].lstrip("/").upper().rstrip(":")
        # Strip leading prefix word (LEVELS, TV, VPVR, TV:LEVELS, etc.)
        if first in ("LEVELS", "TV", "VPVR") or first.startswith("TV"):
            text2 = text.split(maxsplit=1)
            rest = text2[1] if len(text2) > 1 else ""
        m = re.match(r"^\s*([A-Z][A-Z0-9]+)\s+(.*)$", rest)
        if m:
            symbol = m.group(1).upper()
            rest = m.group(2)

    # 1. Try named "key=value" pattern first
    levels: dict = {}
    for m in _CMD_RE.finditer(rest):
        levels[m.group(1).lower()] = m.group(2)
    if levels:
        return symbol, levels

    # 2. Positional fallback — извлекаем все числа в порядке появления
    numbers = []
    for m in _NUMBER_RE.finditer(rest):
        val = _parse_number(m.group(0))
        if val is not None and val > 0:
            numbers.append(val)

    if not numbers:
        return symbol, {}

    # Assign by count:
    #   3 → poc, vah, val (auto-normalized: max=vah, min=val, middle=poc)
    #   2 → vah, val (max,min)
    #   5+ → poc, vah, val, session_high, session_low
    if len(numbers) == 3:
        srt = sorted(numbers, reverse=True)
        levels = {"vah": srt[0], "poc": srt[1], "val": srt[2]}
    elif len(numbers) == 2:
        srt = sorted(numbers, reverse=True)
        levels = {"vah": srt[0], "val": srt[1]}
    elif len(numbers) >= 5:
        # explicit order: poc, vah, val, session_high, session_low
        levels = {
            "poc": numbers[0], "vah": numbers[1], "val": numbers[2],
            "session_high": numbers[3], "session_low": numbers[4],
        }
    elif len(numbers) == 4:
        # poc, vah, val + session_high (assume sorted descending session high > vah > poc > val)
        srt = sorted(numbers, reverse=True)
        levels = {"session_high": srt[0], "vah": srt[1], "poc": srt[2], "val": srt[3]}
    elif len(numbers) == 1:
        levels = {"poc": numbers[0]}

    return symbol, levels


def format_levels_summary(symbol: str = "BTCUSD") -> str:
    """Build human-readable text of current levels for TG response."""
    entry = get_levels(symbol)
    if entry is None:
        return f"❌ Уровней для {symbol} нет / устарели (>24ч). Обнови через /levels."
    lines = [f"📊 LEVELS {symbol}  (от {entry.get('source')}, обновлено {entry.get('updated_at')})"]
    for k in ("poc", "vah", "val", "session_high", "session_low"):
        v = entry.get(k)
        if v is not None:
            lines.append(f"  {k.upper():<14} ${v:,.0f}")
    for k in ("hvn", "lvn"):
        v = entry.get(k)
        if v:
            lines.append(f"  {k.upper():<14} {', '.join(f'${x:,.0f}' for x in v)}")
    return "\n".join(lines)
