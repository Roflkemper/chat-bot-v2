from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from services.setup_detector.setup_types import DetectionContext, PortfolioSnapshot

logger = logging.getLogger(__name__)

_OHLCV_COLS = ("open", "high", "low", "close", "volume")
_1M_WINDOW = 200   # 1m bars for indicators
_1H_WINDOW = 50    # 1h bars for RSI / regime


def _load_ohlcv(path: str | Path) -> pd.DataFrame:
    """Load OHLCV from parquet or CSV. Returns DataFrame with DatetimeIndex (UTC)."""
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    elif p.suffix == ".csv":
        df = pd.read_csv(p)
        # ts column may be Unix-ms integers (Binance export format)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts")
    else:
        raise ValueError(f"Unsupported format: {p.suffix} — use .parquet or .csv")

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    for col in _OHLCV_COLS:
        if col not in df.columns:
            raise ValueError(f"Missing column '{col}' in {p}")

    df = df[list(_OHLCV_COLS)].sort_index()
    return df


def _resample_to_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1m OHLCV to 1h bars."""
    return df_1m.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()


def _compute_rolling_regime(df_1h: pd.DataFrame) -> pd.Series:
    """Simple rolling regime label based on 20-bar trend direction."""
    close = df_1h["close"]
    ma20 = close.rolling(20, min_periods=5).mean()
    slope = ma20.diff(5)
    bb_std = close.rolling(20, min_periods=5).std()
    bb_width = (bb_std / close * 100).fillna(3.0)

    labels: list[str] = []
    for i in range(len(close)):
        s = float(slope.iloc[i]) if not pd.isna(slope.iloc[i]) else 0.0
        bw = float(bb_width.iloc[i]) if not pd.isna(bb_width.iloc[i]) else 3.0
        price_pct_slope = s / max(float(close.iloc[i]), 1.0) * 100.0
        if price_pct_slope > 0.3:
            labels.append("trend_up")
        elif price_pct_slope < -0.3:
            labels.append("trend_down")
        elif bw < 2.5:
            labels.append("consolidation")
        else:
            labels.append("range_wide")
    return pd.Series(labels, index=df_1h.index)


def _session_at(ts: datetime) -> str:
    """Compute session label from UTC timestamp."""
    try:
        from services.advise_v2.session_intelligence import compute_session_context
        ctx = compute_session_context(ts)
        return str(ctx.kz_active)
    except Exception:
        return "NONE"


class HistoricalContextBuilder:
    """Builds DetectionContext from historical OHLCV data at any given timestamp."""

    def __init__(self, frozen_path: str | Path, pair: str = "BTCUSDT") -> None:
        self.pair = pair
        logger.info("historical_context.loading path=%s", frozen_path)
        self._df_1m = _load_ohlcv(frozen_path)
        self._df_1h = _resample_to_1h(self._df_1m)
        self._regime_series = _compute_rolling_regime(self._df_1h)
        self._ts_index = self._df_1m.index
        logger.info(
            "historical_context.loaded bars=%d start=%s end=%s",
            len(self._df_1m),
            self._df_1m.index[0],
            self._df_1m.index[-1],
        )

    @property
    def start_ts(self) -> datetime:
        return self._df_1m.index[0].to_pydatetime().replace(tzinfo=timezone.utc)

    @property
    def end_ts(self) -> datetime:
        return self._df_1m.index[-1].to_pydatetime().replace(tzinfo=timezone.utc)

    def build_context_at(self, ts: datetime) -> DetectionContext | None:
        """Build DetectionContext for given UTC timestamp. Returns None if insufficient data."""
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_pd = pd.Timestamp(ts)

        # 1m window
        mask_1m = self._df_1m.index <= ts_pd
        df_1m = self._df_1m[mask_1m].iloc[-_1M_WINDOW:]
        if len(df_1m) < 30:
            return None

        current_price = float(df_1m["close"].iloc[-1])
        if current_price <= 0.0:
            return None

        # 1h window
        mask_1h = self._df_1h.index <= ts_pd
        df_1h = self._df_1h[mask_1h].iloc[-_1H_WINDOW:]
        if len(df_1h) < 6:
            return None

        # Regime at ts
        regime_mask = self._regime_series.index <= ts_pd
        if regime_mask.any():
            regime_label = str(self._regime_series[regime_mask].iloc[-1])
        else:
            regime_label = "unknown"

        session_label = _session_at(ts)

        return DetectionContext(
            pair=self.pair,
            current_price=current_price,
            regime_label=regime_label,
            session_label=session_label,
            ohlcv_1m=df_1m.copy(),
            ohlcv_1h=df_1h.copy(),
            portfolio=PortfolioSnapshot(),
        )
