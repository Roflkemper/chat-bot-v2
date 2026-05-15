"""Volatility regime classifier — global filter для всех эмиттеров.

Считает realized volatility за окно (default 4h) и классифицирует:
- LOW:    realized < 33-pct (нижний терциль) — calm market, edges работают
- MEDIUM: 33-pct < realized < 67-pct — normal regime
- HIGH:   realized > 67-pct — chaotic, news, edges деградируют

Strategy filter:
- Range Hunter: ловит в LOW (mean-reversion в спокойствии)
- Cascade alert: в HIGH (большие liq events случаются в волатильности)
- Watchlist plays: variable per play

Все детекторы могут вызвать current_regime() для self-filter.
Per-asset поддержка: BTCUSDT, ETHUSDT, XRPUSDT.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

import numpy as np

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
MARKET_1M_CSV = ROOT / "market_live" / "market_1m.csv"
PRICE_2Y_CSV = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

RegimeLevel = Literal["low", "medium", "high"]

# Per-symbol пороги realized vol в % (annualized). Калиброваны на 2y данных:
# low = q33 (нижний терциль), high = q67 (верхний терциль).
# scripts/derivatives_edge_studies.py способ пересчитать через rolling 4h std.
VOL_THRESHOLDS = {
    "BTCUSDT": {"low": 29.0,  "high": 45.0},   # q33=28.7, q67=45.1 на 2y
    "ETHUSDT": {"low": 43.0,  "high": 65.0},   # q33=43.3, q67=65.0
    "XRPUSDT": {"low": 45.0,  "high": 74.0},   # q33=45.2, q67=73.5
}
DEFAULT_THRESHOLDS = {"low": 40.0, "high": 65.0}
WINDOW_HOURS = 4

# Защита от bad-data outliers: drop top 1% of |log_return| перед vol calc.
# Binance REST иногда отдаёт битый бар с price spike — нельзя позволить
# одному outlier сдвигать regime.
OUTLIER_PCT = 0.01


def _realized_vol_pct(closes: list[float]) -> Optional[float]:
    """Compute annualized realized volatility from close prices (1m bars).

    Annualization factor: 1m bars × sqrt(525600). Drops top OUTLIER_PCT% of
    |log_return| чтобы один bad bar не сместил regime.
    """
    if len(closes) < 30:
        return None
    arr = np.asarray(closes, dtype=float)
    if (arr <= 0).any():
        return None
    log_returns = np.diff(np.log(arr))
    if len(log_returns) < 30:
        return None
    # Outlier guard: drop top OUTLIER_PCT% of absolute moves
    abs_ret = np.abs(log_returns)
    cap = np.quantile(abs_ret, 1.0 - OUTLIER_PCT)
    filtered = log_returns[abs_ret <= cap]
    if len(filtered) < 30:
        filtered = log_returns
    sigma_per_minute = float(np.std(filtered, ddof=1))
    annualized = sigma_per_minute * np.sqrt(525_600) * 100.0
    return annualized


def _load_recent_closes_btc(window_hours: int = WINDOW_HOURS) -> Optional[list[float]]:
    """Read tail of market_live/market_1m.csv (BTC). Returns list of close floats."""
    if not MARKET_1M_CSV.exists():
        return None
    needed = window_hours * 60 + 10
    closes: list[float] = []
    try:
        with MARKET_1M_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    closes.append(float(row.get("close") or 0))
                except (ValueError, KeyError):
                    continue
    except OSError:
        return None
    if not closes:
        return None
    return closes[-needed:]


def current_regime(symbol: str = "BTCUSDT", window_hours: int = WINDOW_HOURS
                    ) -> tuple[RegimeLevel, Optional[float]]:
    """Return (regime, realized_vol_pct) for last `window_hours` of 1m data.

    Symbol="BTCUSDT" uses market_live/market_1m.csv (live).
    Other symbols fetch via core.data_loader.
    """
    if symbol.upper() == "BTCUSDT":
        closes = _load_recent_closes_btc(window_hours)
    else:
        try:
            from core.data_loader import load_klines
            df = load_klines(symbol=symbol.upper(), timeframe="1m",
                              limit=window_hours * 60 + 10)
            closes = df["close"].tolist() if df is not None else None
        except Exception:
            logger.exception("vol_regime.load_klines_failed symbol=%s", symbol)
            closes = None

    if not closes:
        return ("medium", None)  # graceful default

    vol_pct = _realized_vol_pct(closes)
    if vol_pct is None:
        return ("medium", None)

    thresholds = VOL_THRESHOLDS.get(symbol.upper(), DEFAULT_THRESHOLDS)
    if vol_pct < thresholds["low"]:
        return ("low", vol_pct)
    elif vol_pct < thresholds["high"]:
        return ("medium", vol_pct)
    else:
        return ("high", vol_pct)


def is_low_vol(symbol: str = "BTCUSDT") -> bool:
    """Quick boolean check для Range Hunter (любит LOW)."""
    regime, _ = current_regime(symbol)
    return regime == "low"


def is_high_vol(symbol: str = "BTCUSDT") -> bool:
    """Quick boolean check для cascade detectors (любят HIGH)."""
    regime, _ = current_regime(symbol)
    return regime == "high"
