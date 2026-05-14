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
PID_DIR: Path = Path(__file__).parent / "run"
PARAMS_FORCE_SEC: int = 4 * 3600  # force params write every 4h regardless of change

_stop = threading.Event()


# ── PID lock ──────────────────────────────────────────────────────────────────

def _acquire_pid_lock() -> object | None:
    """Return a lock handle if acquired, None if another instance is running.

    Uses fcntl.flock on Unix/Mac (safe across crashes — kernel releases on exit).
    Falls back to a simple PID-file check on Windows.
    """
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = PID_DIR / "tracker.pid"

    try:
        import fcntl
        fd = os.open(str(pid_path), os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        return fd  # keep fd open — lock held as long as process lives
    except ImportError:
        # Windows: best-effort PID file (not race-safe, but good enough for our use)
        try:
            existing = pid_path.read_text().strip() if pid_path.exists() else ""
            if existing:
                try:
                    # Check if that process is alive
                    os.kill(int(existing), 0)
                    return None  # process alive
                except (ProcessLookupError, ValueError, PermissionError):
                    pass  # process dead, stale file
            pid_path.write_text(str(os.getpid()))
            return pid_path  # return path as handle; cleaned up on exit
        except Exception:
            return None


def _release_pid_lock(handle: object) -> None:
    try:
        import fcntl
        if isinstance(handle, int):
            os.close(handle)
    except ImportError:
        if isinstance(handle, Path):
            try:
                handle.unlink(missing_ok=True)
            except OSError:
                pass


# ── Aliases ───────────────────────────────────────────────────────────────────

def _load_aliases(path: Path) -> dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.getLogger(__name__).warning("Cannot load aliases from %s: %s", path, exc)
        return {}


def _aliases_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# ── Logging ───────────────────────────────────────────────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _filter_bots(bots: list[dict]) -> list[dict]:
    if TRACK_ALL or not BOT_FILTER:
        return bots
    return [b for b in bots if str(b.get("id", "")) in BOT_FILTER or b.get("name", "") in BOT_FILTER]


def _build_params_row(params: dict, ts: str, bot_id: str, bot_name: str) -> dict:
    gap = params.get("gap", {}) if isinstance(params.get("gap"), dict) else {}
    border = params.get("border", {}) if isinstance(params.get("border"), dict) else {}
    slp = params.get("slp", {}) if isinstance(params.get("slp"), dict) else {}
    in_ = params.get("in", {}) if isinstance(params.get("in"), dict) else {}
    return {
        "ts_utc": ts,
        "bot_id": bot_id,
        "bot_name": bot_name,
        "strategy_id": params.get("strategyId", ""),
        "side": params.get("side", ""),
        "grid_step": params.get("gs", ""),
        "grid_step_ratio": params.get("gsr", ""),
        "max_opened_orders": params.get("maxOp", ""),
        "border_top": border.get("top", ""),
        "border_bottom": border.get("bottom", ""),
        "instop": gap.get("isg", ""),
        "minstop": gap.get("minS", ""),
        "maxstop": gap.get("maxS", ""),
        "target": gap.get("tog", ""),
        "total_sl": slp.get("tp", ""),
        "total_tp": params.get("ttp", ""),
        "leverage": params.get("leverage", ""),
        "otc": in_.get("otc", ""),
        "dsblin": params.get("dsblin", ""),
        "raw_params_json": json.dumps(params, ensure_ascii=False),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)

    lock_handle = _acquire_pid_lock()
    if lock_handle is None:
        logger.info("Another tracker instance is already running — exiting")
        sys.exit(0)

    logger.info("Tracker starting — interval=%ds output=%s pid=%d", INTERVAL, OUTPUT_DIR, os.getpid())

    signal.signal(signal.SIGTERM, lambda s, f: _stop.set())
    signal.signal(signal.SIGINT, lambda s, f: _stop.set())

    client = GinAreaClient(API_URL, EMAIL, PASSWORD, TOTP_SECRET)
    client.login()

    storage = StorageManager(OUTPUT_DIR)
    aliases = _load_aliases(ALIASES_PATH)
    aliases_mtime = _aliases_mtime(ALIASES_PATH)

    # {bot_id: {"prev_stat": dict, "prev_params_hash": str, "params_written_at": float}}
    state: dict[str, dict] = {}

    try:
        while not _stop.is_set():
            cycle_start = time.monotonic()

            # Hot-reload aliases on mtime change
            mtime = _aliases_mtime(ALIASES_PATH)
            if mtime != aliases_mtime:
                aliases = _load_aliases(ALIASES_PATH)
                aliases_mtime = mtime
                logger.info("Aliases reloaded (mtime changed)")

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
                })

                if bot_id in state:
                    for ev in detect_events(state[bot_id].get("prev_stat", {}), stat):
                        storage.write_event({
                            "ts_utc": ts,
                            "bot_id": bot_id,
                            "bot_name": bot_name,
                            "alias": alias,
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
                    now_mono = time.monotonic()
                    since_write = now_mono - state[bot_id].get("params_written_at", 0)
                    changed = state[bot_id].get("prev_params_hash") != params_hash
                    force = since_write >= PARAMS_FORCE_SEC

                    if changed or force:
                        row = _build_params_row(params, ts, bot_id, bot_name)
                        row["alias"] = alias
                        storage.write_params(row)
                        state[bot_id]["prev_params_hash"] = params_hash
                        state[bot_id]["params_written_at"] = now_mono
                        reason = "changed" if changed else "4h-force"
                        logger.info("Params snapshot bot=%s (%s)", bot_id, reason)
                except Exception as exc:
                    logger.error("Failed params for bot %s: %s", bot_id, exc)

            storage.fsync_all()
            _wait(cycle_start)

    finally:
        storage.close()
        _release_pid_lock(lock_handle)
        logger.info("Tracker stopped cleanly")


def _wait(cycle_start: float) -> None:
    """Sleep the remainder of INTERVAL, interruptible by stop event."""
    elapsed = time.monotonic() - cycle_start
    remaining = max(0.0, INTERVAL - elapsed)
    _stop.wait(timeout=remaining)


if __name__ == "__main__":
    main()
