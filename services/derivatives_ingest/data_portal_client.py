"""Binance data.binance.vision portal client for bulk daily metrics downloads.

Provides access to historical daily ZIP files containing 5-minute derivatives metrics:
- sum_open_interest / sum_open_interest_value
- count_toptrader_long_short_ratio / sum_toptrader_long_short_ratio  (top-trader LS)
- count_long_short_ratio                                              (global LS)
- sum_taker_long_short_vol_ratio                                      (taker volume)

Schema (CSV inside each zip):
  create_time, symbol, sum_open_interest, sum_open_interest_value,
  count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
  count_long_short_ratio, sum_taker_long_short_vol_ratio
"""
from __future__ import annotations

import io
import logging
import re
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

import pandas as pd

log = logging.getLogger(__name__)

_S3_BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
_DL_BASE = "https://data.binance.vision"

_METRICS_PREFIX = "data/futures/um/daily/metrics"

# Request throttle — data portal has no published limit; 0.3s is conservative
_INTERVAL_S = 0.3
_MAX_RETRIES = 5


class DataPortalClient:
    """Downloads and parses Binance data portal daily metric files."""

    def __init__(self, interval_s: float = _INTERVAL_S) -> None:
        self._interval = interval_s
        self._last = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last = time.monotonic()

    def _fetch(self, url: str, retries: int = _MAX_RETRIES) -> bytes:
        for attempt in range(retries):
            self._throttle()
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    return r.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise FileNotFoundError(f"Not found: {url}") from exc
                if exc.code == 403:
                    raise FileNotFoundError(f"Forbidden (file may not exist): {url}") from exc
                if attempt < retries - 1:
                    wait = min(2 ** attempt, 30)
                    log.warning("HTTP %d on %s, retry in %.0fs", exc.code, url, wait)
                    time.sleep(wait)
                    continue
                raise
            except Exception as exc:
                if attempt == retries - 1:
                    raise RuntimeError(f"Fetch failed: {url}: {exc}") from exc
                time.sleep(min(2 ** attempt * 0.5, 15))
        return b""

    def list_available_dates(self, symbol: str) -> list[date]:
        """Return sorted list of dates available in the data portal for this symbol."""
        prefix = f"{_METRICS_PREFIX}/{symbol}/"
        keys: list[str] = []
        marker = ""
        while True:
            qs = f"delimiter=/&prefix={prefix}"
            if marker:
                qs += f"&marker={marker}"
            raw = self._fetch(f"{_S3_BASE}?{qs}")
            text = raw.decode("utf-8", errors="replace")
            batch = re.findall(r"<Key>([^<]+)</Key>", text)
            keys.extend(batch)
            if "<IsTruncated>true</IsTruncated>" not in text or not batch:
                break
            marker = batch[-1]

        dates: list[date] = []
        for k in keys:
            fname = k.split("/")[-1]
            if not fname.endswith(".zip") or ".CHECKSUM" in fname:
                continue
            date_str = fname.replace(f"{symbol}-metrics-", "").replace(".zip", "")
            try:
                dates.append(datetime.strptime(date_str, "%Y-%m-%d").date())
            except ValueError:
                pass
        return sorted(dates)

    def fetch_metrics_day(self, symbol: str, day: date) -> pd.DataFrame:
        """Download and parse one day's 5m metrics CSV from the portal.

        Returns DataFrame with normalised columns:
          ts_ms, symbol, sum_open_interest, sum_open_interest_value,
          top_trader_ls_ratio, global_ls_ratio, taker_vol_ratio
        """
        fname = f"{symbol}-metrics-{day:%Y-%m-%d}.zip"
        url = f"{_DL_BASE}/{_METRICS_PREFIX}/{symbol}/{fname}"
        raw = self._fetch(url)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_name = zf.namelist()[0]
            content = zf.read(csv_name).decode("utf-8", errors="replace")

        df = pd.read_csv(io.StringIO(content))
        df.columns = [c.strip() for c in df.columns]

        # Parse timestamps
        df["ts_ms"] = pd.to_datetime(df["create_time"]).astype("int64") // 1_000_000

        out = pd.DataFrame({
            "ts_ms": df["ts_ms"],
            "symbol": symbol,
            "sum_open_interest": df["sum_open_interest"].astype(float),
            "sum_open_interest_value": df["sum_open_interest_value"].astype(float),
            "top_trader_ls_ratio": df["sum_toptrader_long_short_ratio"].astype(float),
            "global_ls_ratio": df["count_long_short_ratio"].astype(float),
            "taker_vol_ratio": df["sum_taker_long_short_vol_ratio"].astype(float),
        })
        return out

    def iter_metrics_range(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        resume_after: date | None = None,
    ) -> Iterator[tuple[date, pd.DataFrame]]:
        """Yield (day, df) for each day in [start_date, end_date].

        Skips days before resume_after (exclusive) if provided.
        Missing days (404) are logged and skipped.
        """
        available = set(self.list_available_dates(symbol))
        day = start_date
        while day <= end_date:
            if resume_after and day <= resume_after:
                day += timedelta(days=1)
                continue
            if day not in available:
                log.debug("No data portal file for %s %s — skipping", symbol, day)
                day += timedelta(days=1)
                continue
            try:
                df = self.fetch_metrics_day(symbol, day)
                yield day, df
            except FileNotFoundError:
                log.warning("Not found: %s %s — skipping", symbol, day)
            day += timedelta(days=1)
