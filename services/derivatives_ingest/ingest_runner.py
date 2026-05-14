"""Orchestrate historical derivatives ingest for BTC and XRP.

Data sources:
  - OI + Long-Short ratios: data.binance.vision daily zip files (5m granularity)
  - Funding rate: Binance fapi/v1/fundingRate live API (full history)

Usage:
    python -m services.derivatives_ingest.ingest_runner
    python -m services.derivatives_ingest.ingest_runner --smoke     # 3-day BTC only
    python -m services.derivatives_ingest.ingest_runner --symbols BTCUSDT
    python -m services.derivatives_ingest.ingest_runner --skip-funding

Output (backtests/frozen/derivatives_1y/):
    BTCUSDT_OI_5m_1y.parquet     — OI at 5m granularity
    BTCUSDT_funding_8h_1y.parquet — funding rate 8h settlements
    BTCUSDT_LS_5m_1y.parquet      — LS ratios at 5m granularity
    (same for XRPUSDT)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and \
        sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8bom"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
FROZEN_DIR = ROOT / "backtests" / "frozen" / "derivatives_1y"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("derivatives_runner")

from .binance_client import BinanceFuturesClient
from .data_portal_client import DataPortalClient
from .ingest_metrics import ingest_metrics
from .ingest_funding_rate import ingest_funding

START_DATE = date(2025, 5, 1)
END_DATE   = date(2026, 4, 30)

START_MS = int(datetime(2025, 5, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS   = int(datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

SMOKE_END_DATE = date(2025, 5, 3)   # 3 days for smoke test
SMOKE_END_MS = int(datetime(2025, 5, 3, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

SYMBOLS = ["BTCUSDT", "XRPUSDT"]


def run_symbol(
    symbol: str,
    start_date: date,
    end_date: date,
    start_ms: int,
    end_ms: int,
    skip_metrics: bool = False,
    skip_funding: bool = False,
) -> dict[str, int]:
    results: dict[str, int] = {}

    if not skip_metrics:
        t0 = time.monotonic()
        log.info("=== Metrics (OI+LS) %s: %s -> %s ===", symbol, start_date, end_date)
        portal = DataPortalClient()
        oi_df, ls_df = ingest_metrics(
            symbol,
            start_date,
            end_date,
            out_oi=FROZEN_DIR / f"{symbol}_OI_5m_1y.parquet",
            out_ls=FROZEN_DIR / f"{symbol}_LS_5m_1y.parquet",
            client=portal,
        )
        results["oi"] = len(oi_df)
        results["ls"] = len(ls_df)
        log.info("Metrics %s done: OI=%d LS=%d rows in %.1fs", symbol, len(oi_df), len(ls_df), time.monotonic() - t0)

    if not skip_funding:
        t0 = time.monotonic()
        log.info("=== Funding %s: %s -> %s ===", symbol, start_ms, end_ms)
        api = BinanceFuturesClient()
        funding_df = ingest_funding(
            symbol,
            start_ms,
            end_ms,
            out_path=FROZEN_DIR / f"{symbol}_funding_8h_1y.parquet",
            client=api,
        )
        results["funding"] = len(funding_df)
        log.info("Funding %s done: %d rows in %.1fs", symbol, len(funding_df), time.monotonic() - t0)

    return results


def estimate_requests(start_date: date, end_date: date, symbols: list[str]) -> tuple[int, float]:
    days = (end_date - start_date).days + 1
    # data portal: 1 req/day per symbol for metrics
    portal_req = days * len(symbols)
    # + S3 list calls: ~len(symbols) paginated calls (~2 each)
    list_req = len(symbols) * 3
    # funding: 365*3/1000 = ~2 reqs per symbol
    funding_req = len(symbols) * 3
    total = portal_req + list_req + funding_req
    # portal: 0.3s/req; funding: 0.12s/req
    runtime_s = portal_req * 0.3 + (list_req + funding_req) * 0.15
    return total, runtime_s


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance derivatives history ingest")
    parser.add_argument("--smoke", action="store_true", help="3-day smoke test (BTC only, OI+LS+funding)")
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    parser.add_argument("--skip-metrics", action="store_true", help="Skip OI+LS (data portal)")
    parser.add_argument("--skip-funding", action="store_true", help="Skip funding rate")
    parser.add_argument("--dry-run", action="store_true", help="Estimate only, no fetching")
    args = parser.parse_args()

    if args.smoke:
        symbols = ["BTCUSDT"]
        start_date, end_date = START_DATE, SMOKE_END_DATE
        start_ms, end_ms = START_MS, SMOKE_END_MS
        log.info("SMOKE MODE: BTC 3-day test")
    else:
        symbols = args.symbols
        start_date, end_date = START_DATE, END_DATE
        start_ms, end_ms = START_MS, END_MS

    n_req, est_s = estimate_requests(start_date, end_date, symbols)
    log.info("Estimate: ~%d requests, ~%.0f min runtime", n_req, est_s / 60)

    if args.dry_run:
        log.info("Dry-run: exiting.")
        return

    FROZEN_DIR.mkdir(parents=True, exist_ok=True)

    if args.smoke:
        result = run_symbol(
            "BTCUSDT", start_date, end_date, start_ms, end_ms,
            skip_metrics=args.skip_metrics,
            skip_funding=args.skip_funding,
        )
        log.info("Smoke result: %s", result)
        return

    wall_t0 = time.monotonic()
    all_results: dict[str, dict[str, int]] = {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(
                run_symbol,
                sym,
                start_date,
                end_date,
                start_ms,
                end_ms,
                args.skip_metrics,
                args.skip_funding,
            ): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                all_results[sym] = fut.result()
            except Exception as exc:
                log.error("FAILED %s: %s", sym, exc)
                all_results[sym] = {"error": str(exc)}

    elapsed = time.monotonic() - wall_t0
    log.info("All done in %.1f min:", elapsed / 60)
    for sym, res in all_results.items():
        log.info("  %s: %s", sym, res)


if __name__ == "__main__":
    main()
