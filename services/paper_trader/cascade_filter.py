"""Cascade liquidation filter — блокирует вход в LONG-сетапы сразу после
крупного каскада ликвидаций.

Эмпирика 2026-05-12: 6 paper-LONG-сделок подряд закрылись по SL когда
сетапы входили во время или сразу после каскадов >50 BTC/мин. Сигналы
oversold/divergence/double-bottom срабатывают на правильных уровнях, но
истинное дно ещё не сформировано — нужен буфер на разрядку.

Фильтр читает market_live/liquidations.csv (тот же источник что
cascade_alert), агрегирует ликвидации за окно COOLDOWN_MIN минут и
блокирует open_paper_trade если суммарный объём ≥ THRESHOLD_BTC.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"

COOLDOWN_MIN = 30
THRESHOLD_BTC = 50.0


def recent_cascade_volume_btc(
    *,
    now: datetime | None = None,
    window_min: int = COOLDOWN_MIN,
    csv_path: Path = LIQ_CSV,
) -> float:
    """Сумма BTC ликвидаций за последние `window_min` минут.

    Считаем обе стороны (long+short) — paper_trader блокирует только LONG-входы,
    но любой крупный каскад означает что рынок ещё в разрядке.
    """
    if not csv_path.exists():
        return 0.0
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_min)
    total = 0.0
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_str = row.get("ts_utc", "").strip()
                qty_str = row.get("qty", "").strip()
                if not ts_str or not qty_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
                try:
                    qty = float(qty_str)
                except ValueError:
                    continue
                total += qty
    except OSError:
        logger.exception("cascade_filter.read_failed path=%s", csv_path)
        return 0.0
    return total


def should_block_long_entry(
    *,
    now: datetime | None = None,
    window_min: int = COOLDOWN_MIN,
    threshold_btc: float = THRESHOLD_BTC,
    csv_path: Path = LIQ_CSV,
) -> tuple[bool, float]:
    """Returns (blocked, recent_volume_btc).

    Блокируем LONG-вход если за последние `window_min` минут было
    суммарно ≥ `threshold_btc` BTC ликвидаций.
    """
    vol = recent_cascade_volume_btc(now=now, window_min=window_min, csv_path=csv_path)
    return vol >= threshold_btc, vol
