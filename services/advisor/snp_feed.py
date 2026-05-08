"""S&P 500 futures feed + BTC↔SNP correlation.

Why ES=F (SP500 futures), not ^GSPC (SPX cash index):
  - ES=F trades nearly 24/5 (Sun 22:00 UTC → Fri 21:00 UTC), which matches
    the operator's BTC trading hours much better than ^GSPC (NY 13:30–20:00).
  - For crypto-equities correlation, futures are the right benchmark — that's
    what risk-on/risk-off flow trades against in real time.

The fetch is cached for 5 minutes — yfinance is free but not reliable
under burst load. Cache also makes /morning_brief return instantly when
called repeatedly.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_PATH = Path("state/snp_feed_cache.json")
CACHE_TTL_SECONDS = 300   # 5 minutes
SNP_TICKER = "ES=F"


@dataclass
class SnpSnapshot:
    last_close: float
    change_24h_pct: float | None
    change_1h_pct: float | None
    bars_count: int           # how many 1h bars in correlation window
    correlation_24h: float | None    # BTC vs SNP, last 24h, on 1h bars
    fetched_at: str           # iso timestamp
    is_stale: bool            # True if older than CACHE_TTL
    error: str | None = None


def _read_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        import json
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(data: dict) -> None:
    try:
        import json
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(data, default=str), encoding="utf-8")
    except Exception:
        logger.exception("snp_feed.cache_write_failed")


def _fetch_fresh() -> dict:
    """Fetch SNP futures + compute BTC-SNP correlation. Returns dict for cache."""
    import yfinance as yf
    import pandas as pd

    out: dict = {"fetched_at": datetime.now(timezone.utc).isoformat(), "error": None}

    try:
        es = yf.Ticker(SNP_TICKER)
        snp_hist = es.history(period="3d", interval="1h", prepost=False)
        if snp_hist.empty:
            out["error"] = "yfinance returned empty"
            return out

        snp_hist = snp_hist.tz_convert("UTC")
        last_close = float(snp_hist["Close"].iloc[-1])
        out["last_close"] = last_close

        # 1h change
        if len(snp_hist) >= 2:
            prev_close = float(snp_hist["Close"].iloc[-2])
            out["change_1h_pct"] = (last_close - prev_close) / prev_close * 100.0

        # 24h change — use bar from ~24h ago
        if len(snp_hist) >= 24:
            ago_24h = float(snp_hist["Close"].iloc[-24])
            out["change_24h_pct"] = (last_close - ago_24h) / ago_24h * 100.0

        # Correlation BTC↔SNP: take their hourly returns over last 24h, compute corr.
        from core.data_loader import load_klines
        btc = load_klines(symbol="BTCUSDT", timeframe="1h", limit=48)
        if btc is not None and not btc.empty and "open_time" in btc.columns:
            btc_idx = btc.set_index("open_time")["close"].astype(float)
            # Take last 24 hours of SNP, align with BTC by hour.
            snp_24h = snp_hist["Close"].iloc[-24:]
            btc_24h = btc_idx.iloc[-24:]
            # Use returns
            snp_ret = snp_24h.pct_change().dropna()
            btc_ret = btc_24h.pct_change().dropna()
            # Re-align by hour timestamp (both UTC tz-aware)
            joined = pd.concat([snp_ret.rename("snp"), btc_ret.rename("btc")], axis=1, join="inner").dropna()
            if len(joined) >= 8:
                out["correlation_24h"] = float(joined["snp"].corr(joined["btc"]))
                out["bars_count"] = int(len(joined))
            else:
                out["correlation_24h"] = None
                out["bars_count"] = int(len(joined))
        else:
            out["correlation_24h"] = None
            out["bars_count"] = 0

    except Exception as exc:
        logger.exception("snp_feed.fetch_failed")
        out["error"] = f"{type(exc).__name__}: {exc}"

    return out


def get_snp_snapshot(force_refresh: bool = False) -> SnpSnapshot:
    """Return cached or fresh SNP snapshot. Falls back to stale cache on fetch error."""
    cache = _read_cache()
    now = time.time()
    use_cache = False
    if cache and not force_refresh:
        cached_time = cache.get("_cached_unix_ts", 0)
        if now - cached_time < CACHE_TTL_SECONDS:
            use_cache = True

    if not use_cache:
        fresh = _fetch_fresh()
        if fresh.get("error") and cache:
            # On fetch failure, return stale cache marked as stale.
            data = cache
            is_stale = True
        else:
            fresh["_cached_unix_ts"] = now
            _write_cache(fresh)
            data = fresh
            is_stale = False
    else:
        data = cache
        is_stale = False

    return SnpSnapshot(
        last_close=data.get("last_close", 0.0),
        change_24h_pct=data.get("change_24h_pct"),
        change_1h_pct=data.get("change_1h_pct"),
        bars_count=data.get("bars_count", 0),
        correlation_24h=data.get("correlation_24h"),
        fetched_at=data.get("fetched_at", ""),
        is_stale=is_stale,
        error=data.get("error"),
    )
