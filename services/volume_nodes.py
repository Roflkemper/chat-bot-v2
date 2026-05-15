"""Volume nodes detector — local approximation TradingView VPVR.

Считает high-volume nodes (HVN) и low-volume nodes (LVN) из 1m OHLCV
за окно (default 24h):
- Бьём ценовой range на N price-bins (default 50)
- Per-bin: sum(volume × bar_present) = "time-volume profile"
- HVN: top quantile bins (high acceptance, support/resistance levels)
- LVN: bottom quantile (price moves through, weak zones)
- POC: bin with max volume = Point of Control

Output совместим с manual_levels store:
  {symbol: {poc, vah, val, hvn[], lvn[], ttl_hours, ...}}

Использование: вызывается раз в час, обновляет state/manual_levels.json
с source="local_vol_profile". При наличии TV-уровней (source="tv_*")
эти значения НЕ перезаписываются — TV приоритет.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
MARKET_1M_CSV = ROOT / "market_live" / "market_1m.csv"

WINDOW_HOURS = 24
N_BINS = 50
HVN_TOP_QUANTILE = 0.85   # bins above q85 = HVN
LVN_BOTTOM_QUANTILE = 0.15  # bins below q15 = LVN
VA_FRACTION = 0.70  # Value Area = 70% of total volume around POC


def _load_recent_btc_ohlcv(window_hours: int = WINDOW_HOURS) -> Optional[list[dict]]:
    """Read tail of market_1m.csv. Returns list of {ts, high, low, close, volume?}."""
    if not MARKET_1M_CSV.exists():
        return None
    needed = window_hours * 60 + 10
    rows = []
    try:
        with MARKET_1M_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rows.append({
                        "high": float(row.get("high") or row.get("close") or 0),
                        "low": float(row.get("low") or row.get("close") or 0),
                        "close": float(row.get("close") or 0),
                        "volume": float(row.get("volume") or 1.0),  # default 1 если volume нет
                    })
                except (ValueError, KeyError):
                    continue
    except OSError:
        return None
    return rows[-needed:]


def compute_volume_profile(bars: list[dict], n_bins: int = N_BINS) -> dict:
    """Build volume profile: price → volume distribution.

    Returns dict with:
      poc: price (center of POC bin)
      vah, val: Value Area High/Low (containing VA_FRACTION of total volume)
      hvn: list of top HVN prices (HVN_TOP_QUANTILE+ bins)
      lvn: list of LVN prices (LVN_BOTTOM_QUANTILE- bins)
      bin_edges, bin_volumes: raw distribution
    """
    if not bars:
        return {}
    highs = np.array([b["high"] for b in bars])
    lows = np.array([b["low"] for b in bars])
    closes = np.array([b["close"] for b in bars])
    volumes = np.array([b.get("volume", 1.0) for b in bars])

    price_min = float(np.min(lows))
    price_max = float(np.max(highs))
    if price_max <= price_min:
        return {}

    bin_edges = np.linspace(price_min, price_max, n_bins + 1)
    bin_volumes = np.zeros(n_bins)

    # Per bar: bar занимает диапазон [low, high]. Volume распределим
    # равномерно по бинам пересекающимся с диапазоном.
    for i in range(len(bars)):
        lo, hi, vol = lows[i], highs[i], volumes[i]
        if hi <= lo:
            # treat as point at close
            idx = min(int((closes[i] - price_min) / (price_max - price_min) * n_bins), n_bins - 1)
            bin_volumes[idx] += vol
            continue
        # bars touching bin if [bin_low, bin_high] overlaps [lo, hi]
        lo_idx = max(0, int((lo - price_min) / (price_max - price_min) * n_bins))
        hi_idx = min(n_bins - 1, int((hi - price_min) / (price_max - price_min) * n_bins))
        n_touched = hi_idx - lo_idx + 1
        if n_touched > 0:
            per_bin = vol / n_touched
            bin_volumes[lo_idx:hi_idx + 1] += per_bin

    # POC: bin with max volume
    poc_idx = int(np.argmax(bin_volumes))
    bin_width = (price_max - price_min) / n_bins
    poc_price = price_min + (poc_idx + 0.5) * bin_width

    # Value Area: expand from POC выбирая бины по убыванию volume пока не
    # покроет VA_FRACTION общего volume.
    total_vol = float(np.sum(bin_volumes))
    target = total_vol * VA_FRACTION
    in_va = np.zeros(n_bins, dtype=bool)
    in_va[poc_idx] = True
    acc = bin_volumes[poc_idx]
    lo_ptr = hi_ptr = poc_idx
    while acc < target and (lo_ptr > 0 or hi_ptr < n_bins - 1):
        next_lo_vol = bin_volumes[lo_ptr - 1] if lo_ptr > 0 else -1
        next_hi_vol = bin_volumes[hi_ptr + 1] if hi_ptr < n_bins - 1 else -1
        if next_hi_vol >= next_lo_vol and hi_ptr < n_bins - 1:
            hi_ptr += 1
            in_va[hi_ptr] = True
            acc += bin_volumes[hi_ptr]
        elif lo_ptr > 0:
            lo_ptr -= 1
            in_va[lo_ptr] = True
            acc += bin_volumes[lo_ptr]
        else:
            break
    val_price = price_min + lo_ptr * bin_width
    vah_price = price_min + (hi_ptr + 1) * bin_width

    # HVN / LVN
    if total_vol > 0:
        normalized = bin_volumes / total_vol
        hvn_threshold = float(np.quantile(normalized, HVN_TOP_QUANTILE))
        lvn_threshold = float(np.quantile(normalized, LVN_BOTTOM_QUANTILE))
        hvn_idx = np.where(normalized >= hvn_threshold)[0]
        lvn_idx = np.where(normalized <= lvn_threshold)[0]
        hvn_prices = [round(price_min + (i + 0.5) * bin_width, 1) for i in hvn_idx]
        lvn_prices = [round(price_min + (i + 0.5) * bin_width, 1) for i in lvn_idx]
    else:
        hvn_prices = []
        lvn_prices = []

    return {
        "poc": round(poc_price, 1),
        "vah": round(vah_price, 1),
        "val": round(val_price, 1),
        "hvn": hvn_prices[:5],  # top 5
        "lvn": lvn_prices[:5],
        "session_high": round(price_max, 1),
        "session_low": round(price_min, 1),
        "n_bars": len(bars),
        "window_hours": WINDOW_HOURS,
    }


def refresh_local_levels(*, symbol: str = "BTCUSDT", window_hours: int = WINDOW_HOURS
                          ) -> Optional[dict]:
    """Compute volume profile for symbol and write to manual_levels store
    ONLY if no fresh TV-sourced entry exists. TV приоритет."""
    sym_norm = symbol.upper()
    if sym_norm not in ("BTCUSDT", "BTCUSD"):
        # TODO: extend для ETH/XRP когда market_collector будет multi-symbol
        return None
    # manual_levels store uses "BTCUSD" convention (TV chart symbol).
    storage_sym = "BTCUSD"
    bars = _load_recent_btc_ohlcv(window_hours)
    if not bars or len(bars) < 60:
        return None
    profile = compute_volume_profile(bars)
    if not profile:
        return None
    # Check if TV-sourced entry is fresh
    try:
        from services.manual_levels import get_levels, update_levels
        existing = get_levels(storage_sym)
        if existing and (existing.get("source") or "").startswith("tv_"):
            # TV приоритет — не перезаписываем
            return None
        # Convert numpy floats → native floats для JSON-сериализации
        update_levels(storage_sym, {
            "poc": float(profile["poc"]),
            "vah": float(profile["vah"]),
            "val": float(profile["val"]),
            "hvn": [float(x) for x in profile["hvn"]],
            "lvn": [float(x) for x in profile["lvn"]],
            "session_high": float(profile["session_high"]),
            "session_low": float(profile["session_low"]),
            "ttl_hours": 6,  # local re-computed every hour, не TV-точность
        }, source="local_vol_profile")
        return profile
    except Exception:
        logger.exception("volume_nodes.refresh_failed")
        return None
