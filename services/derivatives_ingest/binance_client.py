"""Thin Binance Futures REST client with rate-limiting, retry, and pagination.

Public endpoints only — no API key required for history data.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.parse
from typing import Any, Generator, Optional

log = logging.getLogger(__name__)

FAPI_BASE = "https://fapi.binance.com"
DAPI_BASE = "https://dapi.binance.com"         # coin-margined (not used here)
FUTURES_DATA_BASE = "https://fapi.binance.com"  # /futures/data/* lives here too

# Binance public endpoint limits:
#   /fapi/v1/openInterestHist   → 500 max per request
#   /fapi/v1/fundingRate        → 1000 max per request
#   /futures/data/*Ratio        → 500 max per request
# We stay well under 1200 req/min: default 0.12 s between requests.
_REQUEST_INTERVAL_S = 0.12


class BinanceFuturesClient:
    """Stateless HTTP client for Binance Futures public data endpoints."""

    def __init__(self, request_interval_s: float = _REQUEST_INTERVAL_S) -> None:
        self._interval = request_interval_s
        self._last_call_at: float = 0.0

    # ------------------------------------------------------------------ #
    # core                                                                  #
    # ------------------------------------------------------------------ #

    def get(self, path: str, params: dict[str, Any], retries: int = 6) -> Any:
        """GET request with rate-limit throttle + exponential backoff."""
        base = FUTURES_DATA_BASE if path.startswith("/futures/data") else FAPI_BASE
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{base}{path}?{qs}"

        for attempt in range(retries):
            self._throttle()
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    # respect Retry-After if present, else 60 s
                    wait = int(exc.headers.get("Retry-After", "60"))
                    log.warning("Rate-limited (429); sleeping %ds", wait)
                    time.sleep(wait)
                    continue
                if exc.code >= 500 and attempt < retries - 1:
                    wait = min(2 ** attempt, 30)
                    log.warning("Server error %d, retry %d/%d in %.0fs", exc.code, attempt + 1, retries, wait)
                    time.sleep(wait)
                    continue
                raise
            except Exception as exc:
                if attempt == retries - 1:
                    raise RuntimeError(f"GET {url} failed: {exc}") from exc
                wait = min(2 ** attempt * 0.5, 30)
                log.warning("Request error (retry %d/%d): %s", attempt + 1, retries, exc)
                time.sleep(wait)
        return []

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_call_at = time.monotonic()

    # ------------------------------------------------------------------ #
    # paginated iterators                                                   #
    # ------------------------------------------------------------------ #

    def paginate_oi_hist(
        self,
        symbol: str,
        period: str,
        start_ms: int,
        end_ms: int,
        limit: int = 500,
    ) -> Generator[list[dict], None, None]:
        """Yield batches of OI history rows between start_ms..end_ms."""
        cursor = start_ms
        while cursor < end_ms:
            batch = self.get(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "startTime": cursor, "endTime": end_ms, "limit": limit},
            )
            if not batch:
                break
            yield batch
            last_ts = int(batch[-1]["timestamp"])
            if last_ts <= cursor:
                break          # safety: no progress
            cursor = last_ts + 1

    def paginate_funding_rate(
        self,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 1000,
    ) -> Generator[list[dict], None, None]:
        """Yield batches of funding rate rows."""
        cursor = start_ms
        while cursor < end_ms:
            batch = self.get(
                "/fapi/v1/fundingRate",
                {"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": limit},
            )
            if not batch:
                break
            yield batch
            last_ts = int(batch[-1]["fundingTime"])
            if last_ts <= cursor:
                break
            cursor = last_ts + 1

    def paginate_ls_ratio(
        self,
        endpoint: str,
        symbol: str,
        period: str,
        start_ms: int,
        end_ms: int,
        limit: int = 500,
    ) -> Generator[list[dict], None, None]:
        """Yield batches for any /futures/data/*Ratio endpoint."""
        cursor = start_ms
        while cursor < end_ms:
            batch = self.get(
                endpoint,
                {"symbol": symbol, "period": period, "startTime": cursor, "endTime": end_ms, "limit": limit},
            )
            if not batch:
                break
            yield batch
            last_ts = int(batch[-1]["timestamp"])
            if last_ts <= cursor:
                break
            cursor = last_ts + 1
