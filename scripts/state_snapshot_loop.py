"""State snapshot loop — wraps scripts/state_snapshot.py main() in periodic loop.

Replaces bot7-state-snapshot scheduled task. Runs as managed process under
src/supervisor/daemon.py so it always restarts on crash and never gets
disabled by scheduled-task admin permissions.

Default interval: 300s (5 min). Same cadence as previous scheduled task.

Why not встроено в app_runner: state_snapshot uses heavy blocking I/O
(GinArea REST API calls, large parquet reads) которое мешало бы asyncio loop.
Отдельный процесс изолирует это.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | state_snapshot_loop | %(message)s",
)
logger = logging.getLogger("state_snapshot_loop")

_stop = False


def _on_signal(signum, _frame):
    global _stop
    logger.info("signal %s received — stopping after current iteration", signum)
    _stop = True


def main() -> int:
    parser = argparse.ArgumentParser(description="State snapshot periodic loop")
    parser.add_argument("--interval-sec", type=int, default=300,
                        help="Seconds between snapshots (default 300 = 5 min)")
    parser.add_argument("--no-api", action="store_true",
                        help="Pass through to state_snapshot")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    logger.info("state_snapshot_loop.start interval=%ds no_api=%s", args.interval_sec, args.no_api)

    iteration = 0
    while not _stop:
        iteration += 1
        t0 = time.time()
        try:
            # Re-import per iteration to pick up code changes без перезапуска
            # (для скрипта который мы будем дорабатывать).
            import importlib
            import scripts.state_snapshot as ss
            importlib.reload(ss)

            # state_snapshot.main() читает sys.argv — подменяем
            old_argv = sys.argv
            sys.argv = ["state_snapshot.py"]
            if args.no_api:
                sys.argv.append("--no-api")
            try:
                ss.main()
            finally:
                sys.argv = old_argv

            elapsed = time.time() - t0
            logger.info("iteration_done iter=%d elapsed=%.1fs", iteration, elapsed)
        except Exception:
            logger.exception("iteration_failed iter=%d", iteration)

        # Sleep до следующего тика, но останавливаемся раньше при SIGTERM
        sleep_left = max(0.0, args.interval_sec - (time.time() - t0))
        end = time.time() + sleep_left
        while time.time() < end and not _stop:
            time.sleep(min(1.0, end - time.time()))

    logger.info("state_snapshot_loop.stopped after iter=%d", iteration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
