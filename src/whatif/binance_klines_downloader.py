"""Download 1m klines from Binance Spot REST API with checkpoint + retry.

Usage:
    python -m src.whatif.binance_klines_downloader --symbol ETHUSDT --days 366
    python -m src.whatif.binance_klines_downloader --symbol XRPUSDT --days 366

Output: frozen/{SYMBOL}_1m.parquet  (UTC DatetimeIndex, cols: open high low close volume)
Checkpoint: frozen/.{SYMBOL}_1m_checkpoint.json  (resume after interruption)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

_API_URL = "https://api.binance.com/api/v3/klines"
_INTERVAL = "1m"
_BATCH_BARS = 1000       # bars per API call (Binance max)
_BAR_MS = 60_000         # 1 minute in ms
_BATCH_MS = _BAR_MS * _BATCH_BARS  # 1000 minutes per batch
_MIN_DELAY = 0.05        # 50 ms between batches → ~20 req/s, well under 1200/min limit


def _fetch_batch(symbol: str, start_ms: int, max_retries: int = 6) -> list:
    url = (
        f"{_API_URL}?symbol={symbol}&interval={_INTERVAL}"
        f"&startTime={start_ms}&limit={_BATCH_BARS}"
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed {symbol}@{start_ms} after {max_retries} retries: {exc}") from exc
            wait = min(2 ** attempt * 0.5, 30)
            log.warning("Retry %d/%d for %s@%d (%.1fs): %s", attempt + 1, max_retries, symbol, start_ms, wait, exc)
            time.sleep(wait)
    return []


def download_klines(
    symbol: str,
    days_back: int = 366,
    frozen_dir: Path | str = "frozen",
    workers: int = 4,
    verbose: bool = True,
) -> Path:
    """Download 1m klines, save to frozen/{symbol}_1m.parquet.

    Uses checkpoint to resume interrupted downloads.
    Merges with existing parquet if present.
    """
    frozen_dir = Path(frozen_dir)
    frozen_dir.mkdir(parents=True, exist_ok=True)
    out_path = frozen_dir / f"{symbol}_1m.parquet"
    ckpt_path = frozen_dir / f".{symbol}_1m_checkpoint.json"

    end_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days_back * 24 * 3600 * 1000

    all_batches = list(range(start_ms, end_ms, _BATCH_MS))
    log.info("symbol=%s  days=%d  batches=%d", symbol, days_back, len(all_batches))

    done_batches: set[int] = set()
    if ckpt_path.exists():
        try:
            done_batches = set(json.loads(ckpt_path.read_text()))
        except Exception:
            done_batches = set()
        if verbose:
            print(f"  Resuming {symbol}: {len(done_batches)}/{len(all_batches)} batches cached")

    pending = [b for b in all_batches if b not in done_batches]
    if not pending:
        if verbose:
            print(f"  {symbol}: already fully cached ({out_path})")
        return out_path

    if verbose:
        print(f"  {symbol}: downloading {len(pending)} batches (~{len(pending)//60}min)...")

    new_rows: list[list] = []
    t0 = time.time()

    # Rate-limit: stagger initial submissions slightly
    def _submit_with_delay(ex: ThreadPoolExecutor, batches: list[int]) -> dict:
        futures = {}
        for i, b in enumerate(batches):
            if i > 0 and i % workers == 0:
                time.sleep(_MIN_DELAY * workers)
            futures[ex.submit(_fetch_batch, symbol, b)] = b
        return futures

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = _submit_with_delay(ex, pending)
        completed = 0
        for fut in as_completed(futures):
            b_start = futures[fut]
            try:
                batch = fut.result()
                new_rows.extend(
                    [int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
                    for k in batch
                )
                done_batches.add(b_start)
            except Exception as exc:
                log.error("Batch %d failed for %s: %s (will retry on next run)", b_start, symbol, exc)
            completed += 1
            if completed % 100 == 0 or completed == len(pending):
                ckpt_path.write_text(json.dumps(sorted(done_batches)))
                if verbose:
                    elapsed = time.time() - t0
                    rate = completed / elapsed if elapsed > 0 else 1
                    eta = (len(pending) - completed) / rate
                    print(f"    {completed}/{len(pending)}  {rate:.1f} batch/s  ETA {eta/60:.1f}min")

    # Save checkpoint before merge
    ckpt_path.write_text(json.dumps(sorted(done_batches)))

    # Merge with existing parquet (if any) and deduplicate
    existing_rows: list[list] = []
    if out_path.exists() and not new_rows:
        return out_path  # nothing new
    if out_path.exists():
        try:
            _old = pd.read_parquet(out_path)
            _old_ms = (_old.index.astype("int64") // 1_000_000).tolist()
            opens = _old["open"].tolist()
            highs = _old["high"].tolist()
            lows = _old["low"].tolist()
            closes = _old["close"].tolist()
            vols = _old["volume"].tolist()
            existing_rows = [
                [ms, o, h, lo, c, v]
                for ms, o, h, lo, c, v in zip(_old_ms, opens, highs, lows, closes, vols)
            ]
        except Exception as exc:
            log.warning("Could not read existing parquet, overwriting: %s", exc)

    all_rows = existing_rows + new_rows
    df = pd.DataFrame(all_rows, columns=["ts_ms", "open", "high", "low", "close", "volume"])
    df["ts_ms"] = df["ts_ms"].astype("int64")
    df = df.sort_values("ts_ms").drop_duplicates("ts_ms")

    # Filter to requested window
    cutoff_ms = start_ms
    df = df[df["ts_ms"] >= cutoff_ms]

    df.index = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df.index.name = "ts"
    df = df.drop(columns=["ts_ms"])
    df.to_parquet(out_path, compression="zstd", compression_level=3)

    # Log gaps > 5 min
    gaps = df.index.to_series().diff()
    large_gaps = gaps[gaps > pd.Timedelta("5min")]
    if not large_gaps.empty:
        for ts, gap in large_gaps.items():
            log.warning("Gap in %s data: %s at %s", symbol, gap, ts)
        log.info("Total gaps >5min in %s: %d", symbol, len(large_gaps))

    log.info("Saved %d bars to %s", len(df), out_path)
    if verbose:
        mb = out_path.stat().st_size // 1024 // 1024
        print(f"  {symbol}: saved {len(df):,} bars to {out_path} ({mb}MB)")
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.whatif.binance_klines_downloader")
    p.add_argument("--symbol", required=True, help="e.g. ETHUSDT")
    p.add_argument("--days", type=int, default=366)
    p.add_argument("--frozen-dir", default="frozen")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    download_klines(args.symbol, args.days, Path(args.frozen_dir), args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
