"""OHLCV gap-fill ingest from Binance public REST API.

Fills the gap in existing backtests/frozen/ CSV files from the last stored
timestamp up to a target end time.

Usage:
    python scripts/ohlcv_ingest.py
    python scripts/ohlcv_ingest.py --target-end 2026-04-29T23:00:00Z
    python scripts/ohlcv_ingest.py --symbol BTCUSDT --target-end 2026-04-29T23:00:00Z
    python scripts/ohlcv_ingest.py --dry-run

Output:
    Appends rows to existing backtests/frozen/{SYMBOL}_1m_2y.csv
    Updates backtests/frozen/{SYMBOL}_1h_2y.csv (resample from 1m)
    Appends entry to docs/STATE/ohlcv_ingest_log.jsonl
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# encoding_safety: stdout UTF-8 for Windows terminal
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and \
        sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8bom"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "backtests" / "frozen"
LOG_PATH = ROOT / "docs" / "STATE" / "ohlcv_ingest_log.jsonl"

_API_URL = "https://api.binance.com/api/v3/klines"
_BATCH_BARS = 1000
_BAR_MS = 60_000
_SLEEP_BETWEEN_BATCHES = 0.12   # ~8 req/s, well under 1200/min Binance limit

log = logging.getLogger(__name__)


def _utc_now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _ms_to_dt(ms: int) -> datetime:
    return datetime.utcfromtimestamp(ms / 1000).replace(tzinfo=timezone.utc)


def _parse_target(s: str) -> int:
    """Parse ISO-8601 string → epoch ms."""
    s = s.rstrip("Z")
    dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fetch_klines(symbol: str, start_ms: int, interval: str = "1m",
                  limit: int = _BATCH_BARS, retries: int = 6) -> list:
    url = (
        f"{_API_URL}?symbol={symbol}&interval={interval}"
        f"&startTime={start_ms}&limit={limit}"
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(
                    f"Binance fetch failed {symbol} start={start_ms}: {exc}"
                ) from exc
            wait = min(2 ** attempt * 0.5, 30)
            log.warning("Retry %d/%d (%s): %s", attempt + 1, retries, url, exc)
            time.sleep(wait)
    return []


def _read_csv_last_ts(path: Path) -> int | None:
    """Return last ts (ms) in CSV without loading all rows into RAM."""
    if not path.exists():
        return None
    last_line = b""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        read_back = min(512, size)
        f.seek(-read_back, 2)
        tail = f.read()
    lines = tail.split(b"\n")
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith(b"ts"):
            last_line = stripped
            break
    if not last_line:
        return None
    try:
        return int(last_line.split(b",")[0])
    except (IndexError, ValueError):
        return None


def _append_rows_to_csv(path: Path, rows: list[list]) -> None:
    """Append rows [[ts_ms, o, h, l, c, v], ...] to existing CSV."""
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)


def _validate(path: Path, last_ts_before: int, target_end_ms: int) -> dict:
    """Read CSV, validate continuity/sanity/volume. Return result dict."""
    df = pd.read_csv(path, dtype={"ts": "int64"})
    # Only look at new portion
    new = df[df["ts"] > last_ts_before].copy()
    result: dict = {
        "total_rows": len(df),
        "new_rows": len(new),
        "last_ts": int(df["ts"].iloc[-1]) if len(df) else 0,
        "last_ts_dt": _ms_to_dt(int(df["ts"].iloc[-1])).isoformat() if len(df) else "",
        "pass": True,
        "issues": [],
    }

    if new.empty:
        result["issues"].append("no new rows appended")
        result["pass"] = False
        return result

    # 1. Last bar >= min(target_end, now) - 5min
    # If target_end is in the future, compare against current time instead
    effective_target_ms = min(target_end_ms, _utc_now_ms())
    last_bar_ms = int(new["ts"].iloc[-1])
    if last_bar_ms < effective_target_ms - 5 * 60_000:
        result["issues"].append(
            f"last bar {_ms_to_dt(last_bar_ms).isoformat()} < effective target "
            f"{_ms_to_dt(effective_target_ms).isoformat()} - 5min"
        )
        result["pass"] = False

    # 2. Gaps > 5 min in new portion
    ts_sorted = new["ts"].sort_values()
    diffs = ts_sorted.diff().dropna()
    big_gaps = diffs[diffs > 5 * 60_000]
    if not big_gaps.empty:
        result["issues"].append(
            f"{len(big_gaps)} gap(s) >5min in new bars"
        )
        # Not a hard fail — Binance sometimes returns sparse bars

    # 3. Sanity: no nan, no zero prices
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        if new[col].isna().any() or (new[col] == 0).any():
            result["issues"].append(f"nan/zero in {col}")
            result["pass"] = False

    # 4. Volume not all zero
    if (new["volume"] == 0).all():
        result["issues"].append("volume all zero in new bars — exchange offline?")
        result["pass"] = False

    result["gaps_gt5m"] = len(big_gaps)
    return result


def fill_gap(
    symbol: str,
    interval: str,
    target_end_ms: int,
    frozen_dir: Path,
    dry_run: bool = False,
) -> dict:
    """Fill gap in {symbol}_{interval}_2y.csv up to target_end_ms."""
    csv_path = frozen_dir / f"{symbol}_{interval}_2y.csv"
    if not csv_path.exists():
        log.warning("No file %s — skipping %s %s", csv_path, symbol, interval)
        return {"skipped": True, "reason": "file not found"}

    last_ts = _read_csv_last_ts(csv_path)
    if last_ts is None:
        return {"skipped": True, "reason": "cannot read last ts"}

    next_start_ms = last_ts + _BAR_MS  # first missing bar
    if next_start_ms >= target_end_ms:
        log.info("%s %s already up to date (last=%s)", symbol, interval,
                 _ms_to_dt(last_ts).isoformat())
        return {"skipped": False, "already_uptodate": True, "bars_fetched": 0}

    gap_bars = (target_end_ms - last_ts) // _BAR_MS
    log.info(
        "%s %s: filling %d bars from %s → %s",
        symbol, interval,
        gap_bars,
        _ms_to_dt(last_ts).isoformat(),
        _ms_to_dt(target_end_ms).isoformat(),
    )

    all_rows: list[list] = []
    cursor = next_start_ms
    batch_num = 0
    while cursor < target_end_ms:
        if not dry_run:
            raw = _fetch_klines(symbol, cursor, interval)
            rows = [
                [int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                 float(k[4]), float(k[5])]
                for k in raw
            ]
            all_rows.extend(rows)
            log.debug("Batch %d: %d bars fetched (start=%s)",
                      batch_num, len(rows), _ms_to_dt(cursor).isoformat())
            if rows:
                cursor = rows[-1][0] + _BAR_MS
            else:
                break  # exchange returned nothing, stop
        else:
            log.info("[dry-run] would fetch batch from %s",
                     _ms_to_dt(cursor).isoformat())
            cursor += _BATCH_BARS * _BAR_MS

        batch_num += 1
        if cursor < target_end_ms:
            time.sleep(_SLEEP_BETWEEN_BATCHES)

    # Filter to not exceed target_end
    all_rows = [r for r in all_rows if r[0] <= target_end_ms]

    if dry_run:
        return {"dry_run": True, "expected_bars": gap_bars, "batches": batch_num}

    if all_rows:
        _append_rows_to_csv(csv_path, all_rows)
        log.info("Appended %d rows to %s", len(all_rows), csv_path)
    else:
        log.warning("No rows returned for %s %s", symbol, interval)

    validation = _validate(csv_path, last_ts, target_end_ms)
    return {
        "bars_fetched": len(all_rows),
        "batches": batch_num,
        "validation": validation,
    }


def fill_1h_from_1m(symbol: str, frozen_dir: Path, dry_run: bool = False) -> dict:
    """Resample 1m CSV → 1h, append missing hours to 1h CSV."""
    csv_1m = frozen_dir / f"{symbol}_1m_2y.csv"
    csv_1h = frozen_dir / f"{symbol}_1h_2y.csv"
    if not csv_1m.exists() or not csv_1h.exists():
        return {"skipped": True, "reason": "file not found"}

    last_1h_ts = _read_csv_last_ts(csv_1h)
    last_1m_ts = _read_csv_last_ts(csv_1m)
    if last_1h_ts is None or last_1m_ts is None:
        return {"skipped": True, "reason": "cannot read timestamps"}

    # Need to resample from last_1h_ts + 1h onward
    resample_from_ms = last_1h_ts + 3_600_000

    if resample_from_ms > last_1m_ts:
        log.info("%s 1h already up to date", symbol)
        return {"skipped": False, "already_uptodate": True, "hours_added": 0}

    log.info("%s 1h: resampling from %s", symbol,
             _ms_to_dt(resample_from_ms).isoformat())

    df_1m = pd.read_csv(csv_1m, dtype={"ts": "int64"})
    df_new = df_1m[df_1m["ts"] >= resample_from_ms].copy()
    if df_new.empty:
        return {"skipped": False, "hours_added": 0, "note": "no new 1m data"}

    df_new.index = pd.to_datetime(df_new["ts"], unit="ms", utc=True)
    df_1h_new = df_new[["open", "high", "low", "close", "volume"]].resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])
    df_1h_new = df_1h_new[~df_1h_new.index.isna()]

    # Filter: only complete hours (last bar of 1h may be incomplete)
    cutoff_dt = _ms_to_dt(last_1m_ts - 3_600_000)
    df_1h_new = df_1h_new[df_1h_new.index.tz_convert("UTC") <= pd.Timestamp(cutoff_dt)]

    if dry_run:
        return {"dry_run": True, "hours_to_add": len(df_1h_new)}

    rows = [
        [int(idx.timestamp() * 1000), row["open"], row["high"],
         row["low"], row["close"], row["volume"]]
        for idx, row in df_1h_new.iterrows()
    ]
    if rows:
        _append_rows_to_csv(csv_1h, rows)
        log.info("Appended %d 1h rows to %s", len(rows), csv_1h)

    return {"hours_added": len(rows), "last_1h_ts": _ms_to_dt(rows[-1][0]).isoformat() if rows else ""}


def _write_log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OHLCV gap-fill ingest")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--target-end", default="2026-04-29T23:00:00Z",
                   help="ISO-8601 UTC end timestamp")
    p.add_argument("--frozen-dir", default=str(FROZEN_DIR))
    p.add_argument("--dry-run", action="store_true",
                   help="Simulate only, do not write files")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    frozen_dir = Path(args.frozen_dir)
    target_end_ms = _parse_target(args.target_end)
    symbol = args.symbol

    print(f"OHLCV ingest: {symbol} → {args.target_end}")
    print(f"frozen_dir:   {frozen_dir}")
    if args.dry_run:
        print("DRY RUN — no files will be modified")

    ts_run = datetime.now(tz=timezone.utc).isoformat()

    # Fill 1m gap
    result_1m = fill_gap(symbol, "1m", target_end_ms, frozen_dir, args.dry_run)
    print(f"\n1m result: {result_1m}")

    # Derive 1h from updated 1m
    result_1h = fill_1h_from_1m(symbol, frozen_dir, args.dry_run)
    print(f"1h result: {result_1h}")

    # Validation summary
    val = result_1m.get("validation", {})
    if val:
        if val["pass"]:
            print(f"\nVALIDATION PASS  last bar: {val.get('last_ts_dt', '?')}  "
                  f"new_rows: {val.get('new_rows', '?')}  gaps>5m: {val.get('gaps_gt5m', 0)}")
        else:
            print(f"\nVALIDATION FAIL  issues: {val.get('issues', [])}")

    # Log
    if not args.dry_run:
        log_entry = {
            "ts_run": ts_run,
            "source": "binance_public_rest",
            "symbol": symbol,
            "target_end": args.target_end,
            "result_1m": result_1m,
            "result_1h": result_1h,
        }
        if val:
            log_entry["range_filled"] = {
                "from": _ms_to_dt(_read_csv_last_ts(frozen_dir / f"{symbol}_1m_2y.csv") or 0
                                   - (result_1m.get("bars_fetched", 0) * _BAR_MS)).isoformat(),
                "to": val.get("last_ts_dt", ""),
            }
            log_entry["bars_count"] = val.get("new_rows", 0)
            log_entry["gaps_found"] = val.get("gaps_gt5m", 0)
        _write_log(log_entry)
        print(f"\nLogged to {LOG_PATH}")

    return 0 if (not val or val.get("pass")) else 1


if __name__ == "__main__":
    sys.exit(main())
