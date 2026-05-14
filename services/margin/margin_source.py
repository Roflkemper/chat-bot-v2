"""Margin data source for Decision Layer M-* family.

Designed in TZ-MARGIN-COEFFICIENT-INPUT-WIRE (2026-05-06).

Why this exists:
  Decision Layer M-1..M-4 rules need margin_coefficient and
  distance_to_liquidation_pct to fire. Investigation (Phase 1 CP) showed
  the GinArea API exposes only bot-level operations — no account-wide
  wallet/balance/margin endpoints. ginarea_live/snapshots.csv has only
  per-bot balance, not the exchange-wallet total. state_latest.json
  exposure block has only liquidation prices and net_btc; distance_pct
  was never computed.

  Conclusion: there is no live automated source for account margin
  coefficient available in the current code base. The only way to get
  the operator's BitMEX 0.9693 figure into the bot is for the operator
  to provide it, until a future TZ wires an exchange-wallet feed.

Source resolution:

  Two possible source files; whichever record is newer (by ts) wins.

  1. state/manual_overrides/margin_overrides.jsonl — operator-supplied
     via Telegram /margin command. JSONL append-only. PRIMARY source
     in v1 (no automated feed exists).

  2. state/margin_automated.jsonl — reserved for a future
     TZ-EXCHANGE-WALLET-FEED that will publish margin computed from
     a direct exchange API. Not written by anything today; the reader
     handles the empty/missing case.

  When neither source has data, read_latest_margin() returns None.
  Decision Layer treats None as "M-* dormant" (rules short-circuit).

Schema (one JSONL line):
  {
    "ts": "2026-05-06T11:32:00Z",        # ISO8601 UTC
    "coefficient": 0.9693,                # float in [0.0, 1.0]
    "available_margin_usd": 20434.0,      # float >= 0
    "distance_to_liquidation_pct": 18.0,  # float in [0.0, 100.0]
    "source": "telegram_operator" | "exchange_api" | ...
  }
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_OVERRIDE_PATH = Path("state/manual_overrides/margin_overrides.jsonl")
DEFAULT_AUTOMATED_SOURCE_PATH = Path("state/margin_automated.jsonl")


@dataclass
class MarginRecord:
    ts: str
    coefficient: float
    available_margin_usd: float
    distance_to_liquidation_pct: float
    source: str

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "coefficient": self.coefficient,
            "available_margin_usd": self.available_margin_usd,
            "distance_to_liquidation_pct": self.distance_to_liquidation_pct,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "MarginRecord":
        return cls(
            ts=str(raw["ts"]),
            coefficient=float(raw["coefficient"]),
            available_margin_usd=float(raw["available_margin_usd"]),
            distance_to_liquidation_pct=float(raw["distance_to_liquidation_pct"]),
            source=str(raw.get("source") or "unknown"),
        )


def _last_record(path: Path) -> Optional[MarginRecord]:
    """Return the last valid JSONL record from path, or None."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("margin_source: cannot read %s: %s", path, exc)
        return None
    last: Optional[MarginRecord] = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = MarginRecord.from_dict(json.loads(line))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return last


def read_latest_margin(
    *,
    override_path: Path = DEFAULT_OVERRIDE_PATH,
    automated_path: Path = DEFAULT_AUTOMATED_SOURCE_PATH,
) -> Optional[MarginRecord]:
    """Return the newer of two records by ts; None if both unavailable."""
    a = _last_record(override_path)
    b = _last_record(automated_path)
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    # ISO8601 UTC strings sort lexicographically when normalized to Z form
    return a if a.ts >= b.ts else b


# ── /margin command parsing & validation ────────────────────────────────────


class MarginCommandError(ValueError):
    """Raised when /margin arguments are invalid; carries operator-readable message."""


def _extract_numbers(text: str) -> list[float]:
    """Extract all numeric values from text, tolerantly.

    Понимает: 96, 0.96, 96%, 0,96 (запятая), $21000, 21k, 21,000, 21 000,
    <96>, [96], (96), '$21,000.50 USD'.

    k/K → ×1000. % символ — просто игнорируется (значение остаётся как есть).
    """
    import re
    # Normalize: убрать угловые скобки, $, USD, доллар - ловушки для regex
    cleaned = text
    for sym in ("<", ">", "[", "]", "(", ")", "$", "₽"):
        cleaned = cleaned.replace(sym, " ")
    # USD/usd/долл/доллар — словесные маркеры
    cleaned = re.sub(r"\b(?:USD|usd|долл\w*|dollar\w*|%)\b", " ", cleaned)
    # запятая как десятичный разделитель — конвертируем в точку, но только
    # внутри числа (типа "0,96"). Запятая как тысячный разделитель ("21,000")
    # — обрабатываем отдельно.
    # Эвристика: "1,234" (без точки и больше 1 цифры до и >=3 после) = тысячи → убрать запятую.
    cleaned = re.sub(r"(\d),(\d{3})\b", r"\1\2", cleaned)
    # Оставшиеся запятые — десятичные, заменим на точку
    cleaned = cleaned.replace(",", ".")
    # Удалить пробелы внутри чисел: "21 000" → "21000"
    cleaned = re.sub(r"(\d)\s+(\d{3})\b", r"\1\2", cleaned)

    # Найти все числа (с поддержкой k/K → ×1000)
    pattern = r"(-?\d+\.?\d*)([kK])?"
    out: list[float] = []
    for m in re.finditer(pattern, cleaned):
        try:
            val = float(m.group(1))
            if m.group(2):  # k/K suffix
                val *= 1000
            out.append(val)
        except ValueError:
            continue
    return out


def parse_override_command(text: str) -> MarginRecord:
    """Parse '/margin ...' into a MarginRecord with FLEXIBLE input parsing.

    Принимает много форматов:
      /margin 0.97 20434 18
      /margin <96> <21000> <18>
      /margin 96% $21,000 18%
      /margin coef=0.97 available=21000 liq=18
      /margin 0,97 21 000 18,5

    Логика для coefficient:
      • 0.0-1.0 → принимается как есть
      • 1.0-100.0 → интерпретируется как процент, делится на 100 (96 → 0.96)
      • >100 или <0 → ошибка

    Raises MarginCommandError with a user-facing message on bad input.
    """
    if not text or not text.strip():
        raise MarginCommandError("Пустая команда.")

    # Drop /margin prefix
    stripped = text.strip()
    lower = stripped.lower()
    if lower.startswith("/margin"):
        stripped = stripped[len("/margin"):].strip()

    if not stripped:
        raise MarginCommandError(
            "Использование: /margin <coefficient> <available_margin_usd> <distance_to_liq_pct>\n"
            "Пример: /margin 0.97 20434 18.0\n"
            "Или: /margin 96 21000 18 (96 будет понято как 96%)"
        )

    numbers = _extract_numbers(stripped)
    if len(numbers) < 3:
        raise MarginCommandError(
            f"Нужно 3 числа (нашёл {len(numbers)}: {numbers}).\n"
            "Использование: /margin <coefficient> <available_margin_usd> <distance_to_liq_pct>\n"
            "Пример: /margin 96 21000 18"
        )
    if len(numbers) > 3:
        # Берём первые 3, остальные игнорируем
        numbers = numbers[:3]

    coef_raw, avail, dist_raw = numbers

    # Coefficient: понимаем 0.0-1.0 как есть, 1-100 как процент
    if 0.0 <= coef_raw <= 1.0:
        coef = coef_raw
    elif 1.0 < coef_raw <= 100.0:
        coef = coef_raw / 100.0
    else:
        raise MarginCommandError(
            f"coefficient = {coef_raw} вне допустимого диапазона.\n"
            "Принимаются: 0.0-1.0 (как доля) или 1-100 (как проценты)."
        )

    if avail < 0:
        raise MarginCommandError(
            f"available_margin = {avail} отрицательное; ожидается >= 0."
        )

    # Distance: понимаем 0-100 как процент
    if 0.0 <= dist_raw <= 1.0:
        # Допускаем долю (0.18 = 18%), но это редко — переводим в проценты
        dist = dist_raw * 100.0
    elif 1.0 < dist_raw <= 100.0:
        dist = dist_raw
    else:
        raise MarginCommandError(
            f"distance_to_liquidation_pct = {dist_raw} вне диапазона [0, 100]."
        )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return MarginRecord(
        ts=ts,
        coefficient=coef,
        available_margin_usd=avail,
        distance_to_liquidation_pct=dist,
        source="telegram_operator",
    )


def append_override(record: MarginRecord, *, path: Path = DEFAULT_OVERRIDE_PATH) -> None:
    """Append a record as a single JSONL line, creating the file if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
