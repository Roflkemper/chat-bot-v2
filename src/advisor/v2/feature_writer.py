"""Live feature writer for ADVISOR v2.

Computes a lightweight feature row from live 1h candles every 60 seconds
and appends it to features_out/{SYMBOL}/{YYYY-MM-DD}.parquet.

Features written (superset of what cascade.evaluate needs):
  ts_utc, symbol, price,
  delta_1h_pct, consec_1h_up, consec_1h_down,
  momentum_exhausted, momentum_proxy (double_neutral_streak proxy),
  range_low, range_high, range_mid, range_position_pct,
  distance_to_upper_edge, distance_to_lower_edge,
  active_block
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
_OUTPUT_DIR = _ROOT / "features_out"

# Lock so concurrent writes (unlikely but safe) don't corrupt the parquet file.
_write_lock = threading.Lock()

# TTL cache for read_latest_features: {symbol: (monotonic_ts, features_dict)}
_READ_CACHE: dict[str, tuple[float, dict]] = {}
_READ_CACHE_TTL = 30.0  # seconds


def compute_live_features(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Fetch live 1h candles and compute lightweight features row."""
    from market_data.ohlcv import get_klines
    from market_data.price_feed import get_price
    from features.forecast import short_term_forecast, session_forecast
    from services.timeframe_aggregator import aggregate_to_4h

    candles_1h = get_klines(symbol=symbol, interval="1h", limit=200)
    candles_1h = [{**c, "volume": float(c.get("volume") or 0)} for c in candles_1h]

    try:
        price = get_price(symbol)
    except Exception:
        price = float(candles_1h[-1]["close"]) if candles_1h else 0.0

    now_utc = datetime.now(timezone.utc)

    # ── delta_1h_pct ─────────────────────────────────────────────────────────
    delta_1h_pct: float | None = None
    if len(candles_1h) >= 2:
        c_now = float(candles_1h[-1].get("close") or 0)
        c_prev = float(candles_1h[-2].get("close") or 0)
        if c_prev:
            delta_1h_pct = round((c_now - c_prev) / c_prev * 100.0, 4)

    # ── consec_1h bars ───────────────────────────────────────────────────────
    consec_up = consec_dn = 0
    for bar in reversed(candles_1h[-20:]):
        o, c = float(bar.get("open") or 0), float(bar.get("close") or 0)
        if c > o:
            if consec_dn > 0:
                break
            consec_up += 1
        elif c < o:
            if consec_up > 0:
                break
            consec_dn += 1
        else:
            break

    # ── momentum proxy via short+session forecasts ────────────────────────────
    momentum_exhausted = False
    double_neutral_streak = 0
    try:
        candles_4h = aggregate_to_4h(candles_1h)
        short_fc = short_term_forecast(candles_1h)
        session_fc = session_forecast(candles_4h)
        short_side = str((short_fc or {}).get("direction") or "NEUTRAL").upper()
        session_side = str((session_fc or {}).get("direction") or "NEUTRAL").upper()
        if short_side == "NEUTRAL" and session_side == "NEUTRAL":
            double_neutral_streak = 1
            momentum_exhausted = True
    except Exception:
        pass

    # ── range (last 48 bars) ─────────────────────────────────────────────────
    window = candles_1h[-48:] if len(candles_1h) >= 48 else candles_1h
    range_low = min(float(b["low"]) for b in window) if window else 0.0
    range_high = max(float(b["high"]) for b in window) if window else 0.0
    range_mid = (range_low + range_high) / 2.0
    range_size = max(range_high - range_low, 1e-9)
    range_position_pct = ((price - range_low) / range_size) * 100.0 if price else 0.0

    active_block = "SHORT" if price >= range_mid else "LONG"
    distance_to_upper = round(range_high - price, 2) if price else 0.0
    distance_to_lower = round(price - range_low, 2) if price else 0.0

    return {
        "ts_utc":                  now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbol":                  symbol,
        "price":                   round(price, 2),
        "delta_1h_pct":            delta_1h_pct,
        "consec_1h_up":            consec_up,
        "consec_1h_down":          consec_dn,
        "momentum_exhausted":      momentum_exhausted,
        "double_neutral_streak":   double_neutral_streak,
        "range_low":               round(range_low, 2),
        "range_high":              round(range_high, 2),
        "range_mid":               round(range_mid, 2),
        "range_position_pct":      round(range_position_pct, 2),
        "distance_to_upper_edge":  distance_to_upper,
        "distance_to_lower_edge":  distance_to_lower,
        "active_block":            active_block,
    }


def write_features_row(
    features: dict[str, Any],
    symbol: str = "BTCUSDT",
    output_dir: Path | None = None,
) -> None:
    """Append a single feature row to today's parquet partition."""
    import pandas as pd

    out_dir = (output_dir or _OUTPUT_DIR) / symbol
    out_dir.mkdir(parents=True, exist_ok=True)

    ts_str = features.get("ts_utc", "")
    try:
        day = datetime.strptime(ts_str[:10], "%Y-%m-%d").date()
    except Exception:
        day = datetime.now(timezone.utc).date()

    parquet_path = out_dir / f"{day}.parquet"

    new_row = pd.DataFrame([features])
    new_row["ts_utc"] = pd.to_datetime(new_row["ts_utc"], utc=True)

    with _write_lock:
        if parquet_path.exists():
            try:
                existing = pd.read_parquet(parquet_path)
                combined = pd.concat([existing, new_row], ignore_index=True)
                # Deduplicate by ts_utc (keep last) to survive restart replays.
                combined = combined.drop_duplicates(subset=["ts_utc"], keep="last")
                combined = combined.sort_values("ts_utc").reset_index(drop=True)
            except Exception:
                combined = new_row
        else:
            combined = new_row

        combined.to_parquet(parquet_path, index=False)
    logger.debug("[FW] wrote row ts=%s → %s (%d rows)", ts_str[:16], parquet_path.name, len(combined))


def run_once(symbol: str = "BTCUSDT", output_dir: Path | None = None) -> dict[str, Any]:
    """Compute and write one feature row. Returns the computed features dict."""
    features = compute_live_features(symbol)
    write_features_row(features, symbol=symbol, output_dir=output_dir)
    return features


def read_latest_features(
    symbol: str = "BTCUSDT",
    output_dir: Path | None = None,
    max_age_sec: float = 300.0,
) -> dict[str, Any] | None:
    """Return the most recent feature row for symbol from today's parquet, or None.

    Result is cached for _READ_CACHE_TTL seconds to avoid re-reading parquet
    on every cascade tick.  Returns None if file doesn't exist or row is older
    than max_age_sec.
    """
    import time

    now_mono = time.monotonic()
    cached = _READ_CACHE.get(symbol)
    if cached is not None:
        cached_ts, cached_val = cached
        if now_mono - cached_ts < _READ_CACHE_TTL:
            return cached_val  # may be None — negative cache also TTL-cached

    out_dir = (output_dir or _OUTPUT_DIR) / symbol
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parquet_path = out_dir / f"{today}.parquet"

    result: dict[str, Any] | None = None
    if parquet_path.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(parquet_path)
            if len(df):
                row = df.iloc[-1].to_dict()
                ts_raw = row.get("ts_utc")
                if ts_raw is not None:
                    try:
                        ts = pd.Timestamp(ts_raw).to_pydatetime()
                        if ts.tzinfo is None:
                            from datetime import timezone as _tz
                            ts = ts.replace(tzinfo=_tz.utc)
                        age_sec = (datetime.now(timezone.utc) - ts).total_seconds()
                        if age_sec <= max_age_sec:
                            # Re-serialise ts_utc as string for _check_stale compatibility
                            row["ts_utc"] = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                            result = {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
                    except Exception:
                        pass
        except Exception:
            pass

    _READ_CACHE[symbol] = (now_mono, result)
    return result
