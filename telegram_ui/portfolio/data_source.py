"""Read portfolio data from snapshots.csv (primary) or GinArea API (fallback)."""
from __future__ import annotations

import csv
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .config import (
    BOT_ALIASES_JSON,
    GINAREA_ENV,
    SNAPSHOTS_CSV,
    STALE_CSV_SEC,
    WINDOW_24H_SEC,
    WINDOW_6H_SEC,
)

log = logging.getLogger(__name__)


@dataclass
class BotData:
    bot_id: str
    name: str
    alias: str
    status: str
    side: str           # "LONG", "SHORT", or "?"
    position: float

    profit_now: float
    profit_24h_ago: float

    current_profit: float

    in_filled_count: int
    in_filled_count_6h_ago: int

    trade_volume: float
    trade_volume_24h_ago: float

    balance: float
    balance_24h_ago: float

    average_price: float
    liquidation_price: float

    ts_latest: datetime
    source: str         # "csv" or "api"


def load_portfolio_data() -> list[BotData]:
    """Primary: snapshots.csv. Fallback: GinArea API."""
    result = _load_from_csv()
    if result is not None:
        return result
    log.warning("CSV unavailable or stale — using API fallback")
    return _load_from_api()


def _load_from_csv() -> Optional[list[BotData]]:
    path = SNAPSHOTS_CSV
    if not path.exists():
        log.warning("snapshots.csv not found: %s", path)
        return None

    now_utc = datetime.now(timezone.utc)
    rows_by_bot: dict[str, list[dict]] = {}

    try:
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                bid = row.get("bot_id", "")
                if bid:
                    rows_by_bot.setdefault(bid, []).append(row)
    except Exception as exc:
        log.error("Failed to read snapshots.csv: %s", exc)
        return None

    if not rows_by_bot:
        return None

    # Check freshness against the most recent timestamp across all bots
    most_recent: Optional[datetime] = None
    for rows in rows_by_bot.values():
        ts = _parse_ts(rows[-1].get("ts_utc", ""))
        if ts and (most_recent is None or ts > most_recent):
            most_recent = ts

    if most_recent is None:
        return None

    age_sec = (now_utc - most_recent).total_seconds()
    if age_sec > STALE_CSV_SEC:
        log.warning("CSV stale: %.0f seconds old", age_sec)
        return None

    aliases = _load_aliases()
    bots: list[BotData] = []

    for bid, rows in rows_by_bot.items():
        latest = rows[-1]
        ts_latest = _parse_ts(latest.get("ts_utc", ""))
        if ts_latest is None:
            continue

        target_24h = ts_latest - timedelta(seconds=WINDOW_24H_SEC)
        target_6h = ts_latest - timedelta(seconds=WINDOW_6H_SEC)

        row_24h = _find_closest_row(rows, target_24h)
        row_6h = _find_closest_row(rows, target_6h)

        alias = aliases.get(bid, latest.get("alias", ""))
        name = latest.get("bot_name", bid)
        position = _float(latest.get("position"))

        bots.append(BotData(
            bot_id=bid,
            name=name,
            alias=alias,
            status=latest.get("status", ""),
            side=_infer_side(position, name),
            position=position,
            profit_now=_float(latest.get("profit")),
            profit_24h_ago=_float(row_24h.get("profit") if row_24h else None),
            current_profit=_float(latest.get("current_profit")),
            in_filled_count=_int(latest.get("in_filled_count")),
            in_filled_count_6h_ago=_int(row_6h.get("in_filled_count") if row_6h else None),
            trade_volume=_float(latest.get("trade_volume")),
            trade_volume_24h_ago=_float(row_24h.get("trade_volume") if row_24h else None),
            balance=_float(latest.get("balance")),
            balance_24h_ago=_float(row_24h.get("balance") if row_24h else None),
            average_price=_float(latest.get("average_price")),
            liquidation_price=_float(latest.get("liquidation_price")),
            ts_latest=ts_latest,
            source="csv",
        ))

    return bots


def _load_from_api() -> list[BotData]:
    """Fallback: parallel fetch of all bot stats from GinArea API."""
    try:
        from dotenv import load_dotenv
        load_dotenv(GINAREA_ENV, override=False)
    except ImportError:
        pass

    api_url = os.getenv("GINAREA_API_URL", "")
    email = os.getenv("GINAREA_EMAIL", "")
    password = os.getenv("GINAREA_PASSWORD", "")
    totp_secret = os.getenv("GINAREA_TOTP_SECRET", "")

    if not all([api_url, email, password, totp_secret]):
        log.error("GinArea credentials missing — API fallback unavailable")
        return []

    try:
        import sys
        sys.path.insert(0, str(GINAREA_ENV.parent))
        from ginarea_client import GinAreaClient  # type: ignore[import]
    except ImportError:
        try:
            from ginarea_tracker.ginarea_client import GinAreaClient
        except ImportError:
            log.error("Cannot import GinAreaClient")
            return []

    try:
        client = GinAreaClient(api_url, email, password, totp_secret)
        client.login()
        bot_list = client.get_bots()
    except Exception as exc:
        log.error("API fallback login/list failed: %s", exc)
        return []

    aliases = _load_aliases()
    now_utc = datetime.now(timezone.utc)

    def _fetch(bot: dict) -> Optional[BotData]:
        bid = str(bot.get("id", ""))
        name = bot.get("name", bid)
        status = str(bot.get("status", ""))
        try:
            stat = client.get_bot_stat(bid)
        except Exception as exc:
            log.warning("stat failed for %s: %s", bid, exc)
            return None
        position = _float(stat.get("position"))
        return BotData(
            bot_id=bid,
            name=name,
            alias=aliases.get(bid, ""),
            status=status,
            side=_infer_side(position, name),
            position=position,
            profit_now=_float(stat.get("profit")),
            profit_24h_ago=0.0,
            current_profit=_float(stat.get("currentProfit")),
            in_filled_count=_int(stat.get("inFilledCount")),
            in_filled_count_6h_ago=0,
            trade_volume=_float(stat.get("tradeVolume")),
            trade_volume_24h_ago=0.0,
            balance=_float(stat.get("balance")),
            balance_24h_ago=0.0,
            average_price=_float(stat.get("averagePrice")),
            liquidation_price=_float(stat.get("liquidationPrice")),
            ts_latest=now_utc,
            source="api",
        )

    results: list[BotData] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_fetch, b) for b in bot_list]
        for fut in as_completed(futures):
            try:
                data = fut.result()
                if data is not None:
                    results.append(data)
            except Exception as exc:
                log.warning("Fetch future error: %s", exc)

    return results


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_aliases() -> dict[str, str]:
    try:
        return json.loads(BOT_ALIASES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_ts(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _find_closest_row(rows: list[dict], target: datetime) -> Optional[dict]:
    best: Optional[dict] = None
    best_delta: Optional[float] = None
    for row in rows:
        ts = _parse_ts(row.get("ts_utc", ""))
        if ts is None:
            continue
        delta = abs((ts - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best = row
            best_delta = delta
    return best


def _float(v: object) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _int(v: object) -> int:
    try:
        return int(float(v)) if v not in (None, "", "None") else 0
    except (ValueError, TypeError):
        return 0


def _infer_side(position: float, name: str) -> str:
    if position < 0:
        return "SHORT"
    if position > 0:
        return "LONG"
    name_up = name.upper()
    if "SHORT" in name_up or "ШОРТ" in name_up:
        return "SHORT"
    if "LONG" in name_up or "ЛОНГ" in name_up or "ЛОНГ" in name_up:
        return "LONG"
    return "?"
