"""Market data collector process — OHLCV + liquidations + triggers.

Usage:
    cd c:/bot7
    python -m market_collector.collector
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_collector.config import MARKET_LIVE_DIR, PID_DIR
from market_collector.liquidations import start_liquidation_streams
from market_collector.ohlcv import OhlcvCollector
from market_collector.triggers import TriggerChecker

logger = logging.getLogger(__name__)
_stop = threading.Event()


def _acquire_pid_lock() -> object | None:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = PID_DIR / "collector.pid"
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
        return fd
    except ImportError:
        # Windows fallback
        try:
            existing = pid_path.read_text().strip() if pid_path.exists() else ""
            if existing:
                try:
                    os.kill(int(existing), 0)
                    return None
                except (ProcessLookupError, ValueError, PermissionError):
                    pass
            pid_path.write_text(str(os.getpid()))
            return pid_path
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


def _setup_logging() -> None:
    MARKET_LIVE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = MARKET_LIVE_DIR / "collector.log"
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[fh, sh])


def main() -> None:
    _setup_logging()
    logger.info("collector.starting pid=%d", os.getpid())

    lock = _acquire_pid_lock()
    if lock is None:
        logger.info("collector.already_running — exiting")
        sys.exit(0)

    signal.signal(signal.SIGTERM, lambda s, f: _stop.set())
    signal.signal(signal.SIGINT, lambda s, f: _stop.set())

    _root = Path(__file__).resolve().parents[1]
    params_csv = _root / "ginarea_tracker" / "ginarea_live" / "params.csv"

    try:
        ohlcv = OhlcvCollector(_stop)
        ohlcv_threads = ohlcv.start_all()

        liq_threads = start_liquidation_streams(_stop)

        checker = TriggerChecker(_stop, params_csv=params_csv if params_csv.exists() else None)
        trigger_thread = threading.Thread(
            target=checker.run, args=(30,), daemon=True, name="trigger-checker",
        )
        trigger_thread.start()

        logger.info(
            "collector.running ohlcv=%d liq=%d trigger=1",
            len(ohlcv_threads), len(liq_threads),
        )
        _stop.wait()
    finally:
        logger.info("collector.stopping")
        _release_pid_lock(lock)
        logger.info("collector.stopped")


if __name__ == "__main__":
    main()
