"""ICT levels context reader for setup_detector.

Loads the pre-built ICT levels parquet (from services/ict_levels) once at startup
and provides sub-millisecond per-bar lookups via binary search.

Usage in loop.py:
    reader = ICTContextReader.load(ict_parquet_path)
    ctx.ict_context = reader.lookup(now_utc)
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ICT columns exposed to setup_detector. Extended 2026-05-11 (session_breakout detector)
# to include per-session high/low fields — needed for "break of prior session high/low"
# trigger logic.
ICT_CONTEXT_COLS: tuple[str, ...] = (
    "session_active",
    "time_in_session_min",
    "dist_to_pdh_pct",
    "dist_to_pdl_pct",
    "dist_to_pwh_pct",
    "dist_to_pwl_pct",
    "dist_to_d_open_pct",
    "dist_to_kz_mid_pct",
    "dist_to_nearest_unmitigated_high_pct",
    "dist_to_nearest_unmitigated_low_pct",
    "nearest_unmitigated_high_above",
    "nearest_unmitigated_high_above_age_h",
    "nearest_unmitigated_low_below",
    "nearest_unmitigated_low_below_age_h",
    "unmitigated_count_7d",
    # 2026-05-11: per-session OHLC needed for session_breakout detector.
    "asia_high", "asia_low",
    "london_high", "london_low",
    "ny_am_high", "ny_am_low",
    "ny_lunch_high", "ny_lunch_low",
    "ny_pm_high", "ny_pm_low",
)

_LOOKUP_TOLERANCE_NS = int(5 * 60 * 1e9)  # 5 minutes in nanoseconds
_EMPTY: Dict[str, Any] = {}


class ICTContextReader:
    """Read ICT level features for any UTC timestamp from a pre-built parquet.

    Thread-safe for read-only access. Single-entry cache avoids repeated lookups
    within the same 5-minute detection tick.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self._ts_ns: np.ndarray = np.asarray(df.index.astype(np.int64))
        self._last_ts_ns: int = -1
        self._last_result: Dict[str, Any] = {}

    @classmethod
    def load(cls, parquet_path: str | Path) -> "ICTContextReader":
        """Load from parquet. Returns a no-op reader (empty lookups) if file absent."""
        p = Path(parquet_path)
        if not p.exists():
            logger.warning(
                "ict_context.parquet_missing path=%s — ICT context will be empty. "
                "Run: python -m services.ict_levels.runner to build it.",
                p,
            )
            return cls(_empty_frame())

        try:
            # Load only the 14 columns we need — faster than loading all ~78
            available = pd.read_parquet(p, columns=list(ICT_CONTEXT_COLS))
            logger.info(
                "ict_context.loaded rows=%d  path=%s",
                len(available),
                p,
            )
            return cls(available)
        except Exception:
            logger.exception("ict_context.load_failed path=%s — using empty reader", p)
            return cls(_empty_frame())

    def lookup(self, ts: datetime) -> Dict[str, Any]:
        """Return ICT context dict for the 1m bar nearest to *ts* (within 5 min).

        Returns empty dict if parquet is missing, ts is out of range, or no
        bar is found within the 5-minute tolerance.
        """
        if self._df.empty:
            return _EMPTY

        ts_ns = int(pd.Timestamp(ts).value)

        # Single-entry cache: same tick → same result
        if ts_ns == self._last_ts_ns:
            return self._last_result

        # Binary search: find the last bar at or before ts
        idx = int(np.searchsorted(self._ts_ns, ts_ns, side="right")) - 1
        if idx < 0:
            self._last_ts_ns = ts_ns
            self._last_result = {}
            return {}

        bar_ts_ns = self._ts_ns[idx]
        if abs(int(bar_ts_ns) - ts_ns) > _LOOKUP_TOLERANCE_NS:
            # Nearest bar is more than 5min away — outside coverage
            self._last_ts_ns = ts_ns
            self._last_result = {}
            return {}

        row = self._df.iloc[idx]
        result: Dict[str, Any] = {}
        for col in ICT_CONTEXT_COLS:
            if col not in self._df.columns:
                result[col] = None
                continue
            val = row[col]
            result[col] = None if (isinstance(val, float) and np.isnan(val)) else val

        self._last_ts_ns = ts_ns
        self._last_result = result
        return result

    def is_loaded(self) -> bool:
        return not self._df.empty


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=list(ICT_CONTEXT_COLS),
        index=pd.DatetimeIndex([], tz="UTC"),
    )
