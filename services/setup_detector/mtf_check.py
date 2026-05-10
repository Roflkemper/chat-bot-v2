"""Multi-TF disagreement check (simplified from DESIGN/MTF_DISAGREEMENT_v1.md).

For a given DetectionContext, compute trend direction at 15m, 1h, 4h
and return agreement summary. Used as additional modifier in the
GC-confirmation pipeline:

  - 3/3 TFs agree on direction → confidence boost (high-confluence)
  - 2/3 with 1 flat → neutral (no penalty)
  - 1d direction opposite to 15m direction (when both non-flat) → penalty
    (top-down conflict — likely regime micro-flip)

Trend direction per TF (simple EMA spread):
  up    if EMA20 > EMA50 and slope_5bar > +0.1%
  down  if EMA20 < EMA50 and slope_5bar < -0.1%
  flat  otherwise

Used in setup_detector/loop.py as another confidence modifier alongside
GC-confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Direction = Literal["up", "down", "flat"]


@dataclass
class MTFView:
    dir_15m: Direction
    dir_1h: Direction
    dir_4h: Direction
    agreement_score: int   # 0..3 — count of TFs matching the *majority* direction
    majority: Direction    # majority direction across non-flat
    has_top_down_conflict: bool  # 1d/4h vs 15m opposite (when both non-flat)


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _trend_dir(df: pd.DataFrame, slope_threshold_pct: float = 0.1) -> Direction:
    """Compute trend direction from a single-TF OHLCV frame.

    Uses EMA20 vs EMA(min(50, len(df)//2)) — for short frames (e.g. 4h with
    15 bars resampled from 60h of 1h data), the long-EMA window scales down.
    """
    if df is None or len(df) < 12:
        return "flat"
    close = df["close"].astype(float)
    long_n = min(50, max(20, len(close) // 2))
    short_n = min(20, max(5, len(close) // 4))
    if short_n >= long_n:
        short_n = max(3, long_n // 2)
    ema_short = _ema(close, short_n).iloc[-1]
    ema_long = _ema(close, long_n).iloc[-1]
    last = close.iloc[-1]
    fifth_back = close.iloc[-6] if len(close) >= 6 else close.iloc[0]
    slope_pct = (last / fifth_back - 1) * 100 if fifth_back > 0 else 0.0

    if ema_short > ema_long and slope_pct > slope_threshold_pct:
        return "up"
    if ema_short < ema_long and slope_pct < -slope_threshold_pct:
        return "down"
    return "flat"


def _build_4h_from_1h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h to 4h."""
    if df_1h is None or len(df_1h) < 4:
        return pd.DataFrame()
    if not isinstance(df_1h.index, pd.DatetimeIndex):
        return pd.DataFrame()
    return df_1h.resample("4h").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


def compute_mtf_view(ctx) -> MTFView:
    """Compute multi-TF agreement view from DetectionContext."""
    dir_15m = _trend_dir(getattr(ctx, "ohlcv_15m", None))
    dir_1h = _trend_dir(getattr(ctx, "ohlcv_1h", None))
    df_4h = _build_4h_from_1h(getattr(ctx, "ohlcv_1h", None))
    dir_4h = _trend_dir(df_4h) if not df_4h.empty else "flat"

    dirs = [dir_15m, dir_1h, dir_4h]
    non_flat = [d for d in dirs if d != "flat"]
    if not non_flat:
        return MTFView(
            dir_15m=dir_15m, dir_1h=dir_1h, dir_4h=dir_4h,
            agreement_score=3, majority="flat",  # all flat = "agree" but no info
            has_top_down_conflict=False,
        )

    # Majority direction (most common non-flat)
    up_count = sum(1 for d in non_flat if d == "up")
    down_count = sum(1 for d in non_flat if d == "down")
    if up_count > down_count:
        majority: Direction = "up"
    elif down_count > up_count:
        majority = "down"
    else:
        majority = "flat"  # tie

    # Agreement score: count of TFs matching majority (flat counts as match if majority is flat)
    if majority == "flat":
        agreement_score = sum(1 for d in dirs if d == "flat")
    else:
        agreement_score = sum(1 for d in dirs if d == majority)

    # Top-down conflict: 4h direction OPPOSITE to 15m, both non-flat
    has_conflict = (
        dir_15m != "flat" and dir_4h != "flat" and dir_15m != dir_4h
    )

    return MTFView(
        dir_15m=dir_15m, dir_1h=dir_1h, dir_4h=dir_4h,
        agreement_score=agreement_score, majority=majority,
        has_top_down_conflict=has_conflict,
    )


def mtf_setup_alignment(setup_side: str, view: MTFView) -> Literal["aligned", "conflict", "neutral"]:
    """Decide if a setup side (long/short) matches MTF majority direction.

    aligned:  3/3 agreement on setup direction
    conflict: top-down conflict OR majority opposite to setup direction
    neutral:  partial / mixed / flat majority
    """
    if view.has_top_down_conflict:
        return "conflict"
    if view.majority == "flat":
        return "neutral"
    expected_for_long = view.majority == "up"
    expected_for_short = view.majority == "down"
    if setup_side == "long" and expected_for_long and view.agreement_score >= 3:
        return "aligned"
    if setup_side == "short" and expected_for_short and view.agreement_score >= 3:
        return "aligned"
    if setup_side == "long" and expected_for_short:
        return "conflict"
    if setup_side == "short" and expected_for_long:
        return "conflict"
    return "neutral"
