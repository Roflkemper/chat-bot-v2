"""H10 liquidity map builder."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

DEFAULT_BIN_SIZE = 50.0
DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_TOP_N = 20
DEFAULT_MARKET_DATA_DIR = Path("market_live")
DEFAULT_SYMBOL = "BTCUSDT"

_BASE_COMPONENT_WEIGHTS = {
    "liquidations": 0.40,
    "structure": 0.30,
    "volume_profile": 0.20,
    "oi_density": 0.10,
}
_ROUND_NUMBER_BONUS = 0.15


@dataclass
class LiquidityZone:
    price_level: float
    price_range: tuple[float, float]
    weight: float
    side: Literal["long_stops", "short_stops"]
    components: dict[str, float] = field(default_factory=dict)


def build_liquidity_map(
    ts: datetime,
    ohlcv_1h: pd.DataFrame | None = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    *,
    market_data_dir: Path | str = DEFAULT_MARKET_DATA_DIR,
    bin_size: float = DEFAULT_BIN_SIZE,
    top_n: int = DEFAULT_TOP_N,
    symbol: str = DEFAULT_SYMBOL,
    oi_data: pd.DataFrame | None = None,
    liquidations: pd.DataFrame | None = None,
    current_price: float | None = None,
) -> list[LiquidityZone]:
    """Build weighted BTC liquidity zones around ``ts``."""
    ts_utc = _to_utc(ts)
    if ohlcv_1h is None:
        raise ValueError("ohlcv_1h is required for build_liquidity_map")

    window = _slice_lookback(ohlcv_1h, ts_utc, lookback_hours)
    if window.empty:
        return []

    if current_price is None:
        current_price = float(window["close"].iloc[-1])
    if current_price <= 0:
        return []

    bins = _build_bins(current_price=current_price, bin_size=bin_size)
    if len(bins) < 2:
        return []
    centers = (bins[:-1] + bins[1:]) / 2.0

    structure_score = _structure_score(window, centers, current_price, bin_size)
    volume_score = _volume_profile_score(window, bins)

    if liquidations is None:
        liquidations = _load_liquidations(
            market_data_dir=Path(market_data_dir),
            symbol=symbol,
            ts=ts_utc,
            lookback_hours=lookback_hours,
        )
    liq_score = _liquidation_score(liquidations, bins) if not liquidations.empty else np.zeros(len(centers))

    oi_window = _slice_lookback(oi_data, ts_utc, lookback_hours) if oi_data is not None else pd.DataFrame()
    oi_score = _oi_density_score(oi_window, window, bins) if not oi_window.empty else np.zeros(len(centers))

    component_scores = {
        "liquidations": liq_score,
        "structure": structure_score,
        "volume_profile": volume_score,
        "oi_density": oi_score,
    }
    active_weights = _normalize_component_weights(
        {
            name: weight
            for name, weight in _BASE_COMPONENT_WEIGHTS.items()
            if component_scores[name].max() > 0
        }
    )
    if not active_weights:
        return []

    composite = np.zeros(len(centers))
    for name, weight in active_weights.items():
        composite += component_scores[name] * weight
    composite = _apply_round_number_bonus(composite, centers)
    if composite.max() <= 0:
        return []
    composite = composite / composite.max()

    order = np.argsort(composite)[::-1]
    zones: list[LiquidityZone] = []
    for idx in order[:top_n]:
        weight = float(composite[idx])
        if weight <= 0:
            break
        price_level = float(centers[idx])
        zones.append(
            LiquidityZone(
                price_level=price_level,
                price_range=(float(bins[idx]), float(bins[idx + 1])),
                weight=weight,
                side="long_stops" if price_level < current_price else "short_stops",
                components={
                    name: float(component_scores[name][idx]) for name in component_scores
                },
            )
        )
    return zones


def _slice_lookback(
    df: pd.DataFrame | None,
    ts: pd.Timestamp,
    lookback_hours: int,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    start = ts - pd.Timedelta(hours=lookback_hours)
    out = df[(df.index >= start) & (df.index < ts)].copy()
    return out.sort_index()


def _build_bins(current_price: float, bin_size: float) -> np.ndarray:
    low = current_price * 0.97
    high = current_price * 1.03
    start = np.floor(low / bin_size) * bin_size
    stop = np.ceil(high / bin_size) * bin_size + bin_size
    return np.arange(start, stop, bin_size)


def _structure_score(
    window: pd.DataFrame,
    centers: np.ndarray,
    current_price: float,
    bin_size: float,
) -> np.ndarray:
    levels = set()
    levels.update(window["high"].tail(lookback_count_for_tf(len(window), 24)).tolist())
    levels.update(window["low"].tail(lookback_count_for_tf(len(window), 24)).tolist())

    if len(window) >= 4:
        range_4h = window.resample("4h", label="right", closed="right").agg(
            {"high": "max", "low": "min"}
        ).dropna()
        levels.update(range_4h["high"].tail(6).tolist())
        levels.update(range_4h["low"].tail(6).tolist())

    if not levels:
        return np.zeros(len(centers))

    radius = max(current_price * 0.02, bin_size)
    score = np.zeros(len(centers))
    for level in levels:
        distance = np.abs(centers - float(level))
        proximity = np.clip(1.0 - (distance / radius), 0.0, 1.0)
        score = np.maximum(score, proximity)
    return _normalize(score)


def lookback_count_for_tf(window_len: int, cap: int) -> int:
    return min(window_len, cap)


def _volume_profile_score(window: pd.DataFrame, bins: np.ndarray) -> np.ndarray:
    score = np.zeros(len(bins) - 1)
    for _, row in window.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        volume = float(row["volume"])
        if high <= low or volume <= 0:
            continue
        left = np.searchsorted(bins, low, side="right") - 1
        right = np.searchsorted(bins, high, side="left")
        for idx in range(max(left, 0), min(right + 1, len(score))):
            bin_low = bins[idx]
            bin_high = bins[idx + 1]
            overlap = min(high, bin_high) - max(low, bin_low)
            if overlap > 0:
                score[idx] += volume * (overlap / (high - low))
    return _normalize(score)


def _load_liquidations(
    market_data_dir: Path,
    symbol: str,
    ts: pd.Timestamp,
    lookback_hours: int,
) -> pd.DataFrame:
    start_day = (ts - pd.Timedelta(hours=lookback_hours)).normalize()
    end_day = ts.normalize()
    day = start_day
    frames: list[pd.DataFrame] = []
    datatype_dir = market_data_dir / "liquidations"
    if not datatype_dir.exists():
        return pd.DataFrame()

    while day <= end_day:
        date_str = day.strftime("%Y-%m-%d")
        pattern = f"{date_str}*.parquet"
        for exchange_dir in datatype_dir.iterdir():
            if not exchange_dir.is_dir():
                continue
            symbol_dir = exchange_dir / symbol
            candidate_dirs = [symbol_dir, exchange_dir]
            for candidate_dir in candidate_dirs:
                if not candidate_dir.exists():
                    continue
                for path in candidate_dir.glob(pattern):
                    try:
                        frames.append(pd.read_parquet(path))
                    except Exception:
                        continue
        day += pd.Timedelta(days=1)

    if not frames:
        return pd.DataFrame()

    liquidations = pd.concat(frames, ignore_index=True)
    if "ts_ms" not in liquidations.columns:
        return pd.DataFrame()
    liquidations["ts"] = pd.to_datetime(liquidations["ts_ms"], unit="ms", utc=True, errors="coerce")
    liquidations = liquidations.dropna(subset=["ts", "price", "value_usd"])
    start = ts - pd.Timedelta(hours=lookback_hours)
    liquidations = liquidations[(liquidations["ts"] >= start) & (liquidations["ts"] < ts)]
    return liquidations


def _liquidation_score(liquidations: pd.DataFrame, bins: np.ndarray) -> np.ndarray:
    score = np.zeros(len(bins) - 1)
    for _, row in liquidations.iterrows():
        price = float(row["price"])
        value = float(row["value_usd"])
        if price <= 0 or value <= 0:
            continue
        idx = np.searchsorted(bins, price, side="right") - 1
        if 0 <= idx < len(score):
            score[idx] += value
    return _normalize(score)


def _oi_density_score(
    oi_window: pd.DataFrame,
    ohlcv_window: pd.DataFrame,
    bins: np.ndarray,
) -> np.ndarray:
    if "oi_value" not in oi_window.columns:
        return np.zeros(len(bins) - 1)
    aligned = oi_window.reindex(ohlcv_window.index, method="ffill")
    if aligned["oi_value"].dropna().empty:
        return np.zeros(len(bins) - 1)

    mean_oi = float(aligned["oi_value"].mean())
    if mean_oi <= 0:
        return np.zeros(len(bins) - 1)

    score = np.zeros(len(bins) - 1)
    for ts, row in ohlcv_window.iterrows():
        oi_value = float(aligned.at[ts, "oi_value"]) if ts in aligned.index else np.nan
        if not np.isfinite(oi_value) or oi_value <= mean_oi:
            continue
        excess = (oi_value - mean_oi) / mean_oi
        mid_price = float((row["high"] + row["low"]) / 2.0)
        idx = np.searchsorted(bins, mid_price, side="right") - 1
        if 0 <= idx < len(score):
            score[idx] += excess
    return _normalize(score)


def _normalize_component_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {name: value / total for name, value in weights.items()}


def _apply_round_number_bonus(values: np.ndarray, centers: np.ndarray) -> np.ndarray:
    out = values.copy()
    for idx, center in enumerate(centers):
        round_level = round(center / 1000.0) * 1000.0
        if abs(center - round_level) <= 50.0:
            out[idx] += _ROUND_NUMBER_BONUS
    return out


def _normalize(values: np.ndarray) -> np.ndarray:
    max_value = float(np.nanmax(values)) if len(values) else 0.0
    if max_value <= 0:
        return np.zeros_like(values, dtype=float)
    return values / max_value


def _to_utc(ts: datetime) -> pd.Timestamp:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")
