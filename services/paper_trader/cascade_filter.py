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
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 60
_cache: dict[tuple, tuple[float, float]] = {}  # key -> (value, expires_at_ts)
_cache_lock = threading.Lock()

ROOT = Path(__file__).resolve().parents[2]
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"

# Эмпирически (после OKX qty normalization 2026-05-12):
# - типичный фон ликвидаций bybit+okx за 30 мин ~5-30 BTC
# - сильные spike (12.05 13:00-19:00) до ~80 BTC
# - порог 150 BTC ловит только настоящий кризис, фон не блокирует
COOLDOWN_MIN = 30
THRESHOLD_BTC = 150.0

# OKX BTC-USDT-SWAP передаёт `sz` в контрактах (1 контракт = 0.01 BTC).
# С 2026-05-12 нормализация делается на источнике в market_collector/liquidations.py
# (см. OKX_CONTRACT_SIZE_BTC). Существующие исторические строки приведены
# скриптом scripts/migrate_okx_liquidations_qty.py. Здесь qty читается as-is.


def _purge_cache(now_ts: float) -> None:
    """Drop expired cache entries. Called under _cache_lock."""
    expired = [k for k, (_, exp) in _cache.items() if exp <= now_ts]
    for k in expired:
        _cache.pop(k, None)


def clear_cache() -> None:
    """Test hook: forget all cached volumes."""
    with _cache_lock:
        _cache.clear()


def recent_cascade_volume_btc(
    *,
    now: datetime | None = None,
    window_min: int = COOLDOWN_MIN,
    csv_path: Path = LIQ_CSV,
    use_cache: bool = True,
) -> float:
    """Сумма BTC ликвидаций за последние `window_min` минут.

    Считаем обе стороны (long+short) — paper_trader блокирует только LONG-входы,
    но любой крупный каскад означает что рынок ещё в разрядке.

    Кеш: TTL 60s, ключ (now_minute, window_min, csv_path). За один tick loop'а
    проверок может быть несколько (по числу новых setup'ов) — кеш убирает
    повторное чтение всего CSV (~3000+ строк).
    """
    if not csv_path.exists():
        return 0.0
    if now is None:
        now = datetime.now(timezone.utc)
    if use_cache:
        # Квантуем now до минуты — иначе ключ всегда уникален и кеш бесполезен.
        now_min = now.replace(second=0, microsecond=0)
        key = (now_min, int(window_min), str(csv_path))
        wall = datetime.now(timezone.utc).timestamp()
        with _cache_lock:
            _purge_cache(wall)
            hit = _cache.get(key)
            if hit is not None:
                return hit[0]
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
                if ts < cutoff or ts > now:
                    # ts > now: защита для ретроспективных запросов (audit-скрипт
                    # передаёт now=момент_входа). Без этого фильтр учитывал бы
                    # ликвидации из «будущего», которых не было на момент решения.
                    continue
                try:
                    qty = float(qty_str)
                except ValueError:
                    continue
                total += qty
    except OSError:
        logger.exception("cascade_filter.read_failed path=%s", csv_path)
        return 0.0
    if use_cache:
        wall = datetime.now(timezone.utc).timestamp()
        with _cache_lock:
            _cache[key] = (total, wall + _CACHE_TTL_SEC)
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
    pair: str = "BTCUSDT",
    now: datetime | None = None,
    window_min: int = COOLDOWN_MIN,
    threshold_btc: float = THRESHOLD_BTC,
    csv_path: Path = LIQ_CSV,
) -> tuple[bool, float]:
    """Универсальный фильтр для обеих сторон.

    Симметричная логика: каскад любой стороны = рынок в разрядке.
    Не входим ни в LONG, ни в SHORT пока ликвидации не утихнут.

    `pair`: применяем фильтр только если pair = BTC*. Для ETH/XRP/SOL
    сетапов BTC-каскад не релевантен — у этих активов своя ликвидационная
    динамика, которую мы пока не собираем. Чтобы избежать ложных блокировок,
    pair != BTC* пропускаем мимо фильтра.
    """
    if side not in ("long", "short"):
        return False, 0.0
    p = (pair or "BTCUSDT").upper()
    if not (p.startswith("BTC") or p.startswith("XBT")):
        return False, 0.0
    return should_block_long_entry(
        now=now, window_min=window_min, threshold_btc=threshold_btc, csv_path=csv_path
    )
