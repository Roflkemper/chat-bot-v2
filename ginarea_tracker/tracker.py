"""GinArea bot tracker — 24/7 snapshot + event logger.

Usage:
    cd ginarea_tracker
    cp .env.example .env   # fill in credentials
    python tracker.py
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure local modules resolve when run as script from any CWD
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from ginarea_client import GinAreaClient
from events import detect_events
from storage import StorageManager

load_dotenv(Path(__file__).parent / ".env")

# --- Config (fail fast on missing required vars) ---
API_URL: str = os.environ["GINAREA_API_URL"]
EMAIL: str = os.environ["GINAREA_EMAIL"]
PASSWORD: str = os.environ["GINAREA_PASSWORD"]
TOTP_SECRET: str = os.environ["GINAREA_TOTP_SECRET"]
INTERVAL: int = int(os.getenv("SNAPSHOT_INTERVAL_SEC", "60"))
OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "ginarea_live"))
TRACK_ALL: bool = os.getenv("TRACK_ALL_BOTS", "true").lower() != "false"
_BOT_FILTER_RAW: str = os.getenv("BOT_FILTER", "")
BOT_FILTER: set[str] = (
    {x.strip() for x in _BOT_FILTER_RAW.split(",") if x.strip()}
    if _BOT_FILTER_RAW else set()
)

ALIASES_PATH: Path = Path(__file__).parent / "bot_aliases.json"
ALIASES_RELOAD_SEC: int = 600

_stop = threading.Event()


def _setup_logging() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / "tracker.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])


def _load_aliases(path: Path) -> dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.getLogger(__name__).warning("Cannot load aliases from %s: %s", path, exc)
        return {}


def _ts_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _filter_bots(bots: list[dict]) -> list[dict]:
    if TRACK_ALL or not BOT_FILTER:
        return bots
    return [b for b in bots if str(b.get("id", "")) in BOT_FILTER or b.get("name", "") in BOT_FILTER]


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Tracker starting — interval=%ds output=%s", INTERVAL, OUTPUT_DIR)

    signal.signal(signal.SIGTERM, lambda s, f: _stop.set())
    signal.signal(signal.SIGINT, lambda s, f: _stop.set())

    client = GinAreaClient(API_URL, EMAIL, PASSWORD, TOTP_SECRET)
    client.login()

    storage = StorageManager(OUTPUT_DIR)
    aliases = _load_aliases(ALIASES_PATH)
    aliases_loaded_at = time.monotonic()

    # {bot_id: {"prev_stat": dict, "prev_params_hash": str}}
    state: dict[str, dict] = {}

    try:
        while not _stop.is_set():
            cycle_start = time.monotonic()

            if time.monotonic() - aliases_loaded_at > ALIASES_RELOAD_SEC:
                aliases = _load_aliases(ALIASES_PATH)
                aliases_loaded_at = time.monotonic()
                logger.debug("Aliases reloaded")

            try:
                bots = client.get_bots()
                bots = _filter_bots(bots)
                logger.debug("Fetched %d bots", len(bots))
            except Exception as exc:
                logger.error("Failed to fetch bot list: %s", exc)
                _wait(cycle_start)
                continue

            ts = _ts_utc()

            for bot in bots:
                if _stop.is_set():
                    break

                bot_id = str(bot.get("id", ""))
                bot_name = str(bot.get("name", ""))
                alias = aliases.get(bot_id, "")

                try:
                    stat = client.get_bot_stat(bot_id)
                except Exception as exc:
                    logger.error("Failed stat for bot %s: %s", bot_id, exc)
                    continue

                storage.write_snapshot({
                    "ts_utc": ts,
                    "bot_id": bot_id,
                    "bot_name": bot_name,
                    "alias": alias,
                    "status": bot.get("status", ""),
                    "position": stat.get("position", ""),
                    "profit": stat.get("profit", ""),
                    "current_profit": stat.get("currentProfit", ""),
                    "in_filled_count": stat.get("inFilledCount", ""),
                    "in_filled_qty": stat.get("inFilledQty", ""),
                    "out_filled_count": stat.get("outFilledCount", ""),
                    "out_filled_qty": stat.get("outFilledQty", ""),
                    "trigger_count": stat.get("triggerCount", ""),
                    "trigger_qty": stat.get("triggerQty", ""),
                    "average_price": stat.get("averagePrice", ""),
                    "trade_volume": stat.get("tradeVolume", ""),
                    "balance": stat.get("balance", ""),
                    "liquidation_price": stat.get("liquidationPrice", ""),
                    "stat_updated_at": stat.get("statUpdatedAt", stat.get("updatedAt", "")),
                })

                if bot_id in state:
                    for ev in detect_events(state[bot_id].get("prev_stat", {}), stat):
                        storage.write_event({
                            "ts_utc": ts,
                            "bot_id": bot_id,
                            "bot_name": bot_name,
                            "event_type": ev.event_type,
                            "delta_count": ev.delta_count,
                            "delta_qty": ev.delta_qty,
                            "price_last": ev.price_last,
                            "position_after": ev.position_after,
                            "profit_after": ev.profit_after,
                        })
                        logger.info("Event %s bot=%s delta=%d", ev.event_type, bot_id, ev.delta_count)
                else:
                    state[bot_id] = {}

                state[bot_id]["prev_stat"] = stat

                try:
                    params = client.get_bot_params(bot_id)
                    params_hash = json.dumps(params, sort_keys=True)
                    if state[bot_id].get("prev_params_hash") != params_hash:
                        storage.write_params({
                            "ts_utc": ts,
                            "bot_id": bot_id,
                            "bot_name": bot_name,
                            "strategy_id": params.get("strategyId", ""),
                            "side": params.get("side", ""),
                            "grid_step": params.get("gs", ""),
                            "grid_step_ratio": params.get("gsr", ""),
                            "max_opened_orders": params.get("maxOp", ""),
                            "border_top": params.get("border", {}).get("top", ""),
                            "border_bottom": params.get("border", {}).get("bottom", ""),
                            "instop": params.get("gap", {}).get("isg", ""),
                            "minstop": params.get("gap", {}).get("minS", ""),
                            "maxstop": params.get("gap", {}).get("maxS", ""),
                            "target": params.get("target", ""),
                            "total_sl": params.get("slp", {}).get("tp", "") if isinstance(params.get("slp"), dict) else "",
                            "total_tp": params.get("ttp", ""),
                            "raw_params_json": json.dumps(params, ensure_ascii=False),
                        })
                        state[bot_id]["prev_params_hash"] = params_hash
                        logger.info("Params snapshot bot=%s", bot_id)
                except Exception as exc:
                    logger.error("Failed params for bot %s: %s", bot_id, exc)

            _wait(cycle_start)

    finally:
        storage.close()
        logger.info("Tracker stopped cleanly")


def _wait(cycle_start: float) -> None:
    """Sleep the remainder of INTERVAL, interruptible by stop event."""
    elapsed = time.monotonic() - cycle_start
    remaining = max(0.0, INTERVAL - elapsed)
    _stop.wait(timeout=remaining)


if __name__ == "__main__":
    main()
