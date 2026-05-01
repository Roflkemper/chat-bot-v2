from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .aggregates import add_session_aggregates
from .distances import add_distance_columns
from .mitigation import add_mitigation_columns
from .pivots import add_pivot_levels
from .reader import load_ohlcv_csv
from .sessions import add_session_columns

logger = logging.getLogger(__name__)

_INTERNAL_COLS = ("_kz_session_id",)


def build_ict_levels(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Full pipeline: load OHLCV → compute ICT levels → return (and optionally save) parquet.

    Args:
        input_path: Path to BTCUSDT_1m.csv (Unix-ms ts column).
        output_path: If provided, write result as parquet to this path.
        start: ISO date string filter (inclusive), e.g. '2025-04-25'.
        end: ISO date string filter (inclusive), e.g. '2026-04-30'.

    Returns:
        DataFrame with DatetimeIndex (UTC) and all ICT level columns.
    """
    logger.info("ict_levels.build loading %s", input_path)
    df = load_ohlcv_csv(input_path)

    if start:
        ts_start = pd.Timestamp(start, tz="UTC")
        df = df[df.index >= ts_start]
    if end:
        ts_end = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        df = df[df.index < ts_end]

    logger.info("ict_levels.build rows=%d  start=%s  end=%s", len(df), df.index[0], df.index[-1])

    # Pipeline stages
    logger.info("ict_levels.build stage=sessions")
    df = add_session_columns(df)

    logger.info("ict_levels.build stage=aggregates")
    df = add_session_aggregates(df)

    logger.info("ict_levels.build stage=pivots")
    df = add_pivot_levels(df)

    logger.info("ict_levels.build stage=mitigation")
    df = add_mitigation_columns(df)

    logger.info("ict_levels.build stage=distances")
    df = add_distance_columns(df)

    # Drop internal columns
    df = df.drop(columns=[c for c in _INTERNAL_COLS if c in df.columns])

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=True)
        logger.info("ict_levels.build saved rows=%d  path=%s", len(df), out)

    return df
