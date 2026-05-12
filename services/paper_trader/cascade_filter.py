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

# Эмпирически подобрано после audit_paper_trader_filters.py за 7 дней:
# - типичный фон ликвидаций (bybit + okx, обе стороны) ~250-500 BTC за 30 мин
# - реальные ликвидационные spike (как 12.05 в 16:46-18:46) дают 800-1500+
# - порог 50 BTC резал все winning trades; 200 BTC блокирует только настоящие spike
COOLDOWN_MIN = 30
THRESHOLD_BTC = 800.0

# OKX BTC-USDT-SWAP передаёт qty в контрактах, не в BTC.
# 1 контракт = 0.01 BTC (документация OKX, поле sz).
# market_collector/liquidations.py не нормализует — поэтому делаем
# конверсию здесь. Если когда-то collector нормализует — убрать
# этот словарь и просто читать qty as-is.
_EXCHANGE_QTY_MULTIPLIER = {
    "okx": 0.01,
    "bybit": 1.0,
}


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
                exchange = (row.get("exchange") or "").strip().lower()
                mult = _EXCHANGE_QTY_MULTIPLIER.get(exchange, 1.0)
                total += qty * mult
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


def should_block_entry(
    side: str,
    *,
    now: datetime | None = None,
    window_min: int = COOLDOWN_MIN,
    threshold_btc: float = THRESHOLD_BTC,
    csv_path: Path = LIQ_CSV,
) -> tuple[bool, float]:
    """Универсальный фильтр для обеих сторон.

    Симметричная логика: каскад любой стороны = рынок в разрядке.
    Не входим ни в LONG, ни в SHORT пока ликвидации не утихнут.
    Зеркальный кейс к LONG: 12.05 19:53 был SHORT-каскад 88 BTC —
    SHORT-сетап после него попал бы в squeeze и проиграл.
    """
    if side not in ("long", "short"):
        return False, 0.0
    return should_block_long_entry(
        now=now, window_min=window_min, threshold_btc=threshold_btc, csv_path=csv_path
    )
