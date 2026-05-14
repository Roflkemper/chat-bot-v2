"""Regime classifier v2 — pure logic, 10 states, no I/O.

Designed in TZ-REGIME-V2-EXTENDED 2026-05-06 after operator showed the v1
classifier marking a clear 6-day bull drift (75,200 → 82,500, +9.7%) as
RANGE/COMPRESSION because v1 ADX>25 strict criterion failed inside short
pullbacks. v2 introduces SLOW_UP/DOWN and DRIFT_UP/DOWN states which catch
exactly this case (calibration confirmed: operator window 4-6 May = 100%
SLOW_UP under v2 rules).

All inputs explicit; no live state reads here. Caller (regime adapter or
Telegram command) provides indicator values.

Backward compatibility: project_3state() projects 10 states → 3 states
(MARKUP/MARKDOWN/RANGE) for Decision Layer R-rules which still expect 3-state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Order: cascade > strong > slow > drift > compression > range
# Cascade is the only state that bypasses hysteresis (per regime_classifier.py:415).
STATES = (
    "CASCADE_UP",
    "CASCADE_DOWN",
    "STRONG_UP",
    "STRONG_DOWN",
    "SLOW_UP",
    "SLOW_DOWN",
    "DRIFT_UP",
    "DRIFT_DOWN",
    "COMPRESSION",
    "RANGE",
)

# Thresholds — derived from v1 logic + calibration on 1y data.
# See docs/ANALYSIS/REGIME_V2_CALIBRATION_2026-05-06.md.
CASCADE_15M_PCT = 3.0
CASCADE_1H_PCT = 5.0
CASCADE_4H_PCT = 8.0
STRONG_ADX_THRESHOLD = 25.0
SLOW_DIST_EMA200_PCT = 1.5
DRIFT_24H_PCT = 2.0
DRIFT_ATR_PCT_MAX = 1.5
COMPRESSION_ATR_PCT_MAX = 0.8
RANGE_ATR_PCT_MAX = 1.5


@dataclass
class ClassifierInputs:
    """All inputs needed to classify one bar.

    Caller computes these from OHLCV + indicators.
    """

    close: float
    ema50: Optional[float]
    ema200: Optional[float]
    ema50_slope_pct: Optional[float]   # % change of ema50 over last 12h
    adx_proxy: Optional[float]          # 0-100, proxy or real ADX
    atr_pct_1h: Optional[float]         # ATR as % of price
    bb_width_pct: Optional[float]       # Bollinger Band width as % of mid
    bb_width_p20_30d: Optional[float]   # 20th percentile of bb_width over rolling 30d
    move_15m_pct: Optional[float]       # % move over last 15 min (or 1h on 1h frame)
    move_1h_pct: Optional[float]
    move_4h_pct: Optional[float]
    move_24h_pct: Optional[float]
    dist_to_ema200_pct: Optional[float]


def classify_bar(inp: ClassifierInputs) -> str:
    """Classify one bar into one of STATES."""
    # 1. CASCADE — fast moves bypass hysteresis
    if inp.move_15m_pct is not None and inp.move_15m_pct > CASCADE_15M_PCT:
        return "CASCADE_UP"
    if inp.move_15m_pct is not None and inp.move_15m_pct < -CASCADE_15M_PCT:
        return "CASCADE_DOWN"
    if inp.move_1h_pct is not None and inp.move_1h_pct > CASCADE_1H_PCT:
        return "CASCADE_UP"
    if inp.move_1h_pct is not None and inp.move_1h_pct < -CASCADE_1H_PCT:
        return "CASCADE_DOWN"
    if inp.move_4h_pct is not None and inp.move_4h_pct > CASCADE_4H_PCT:
        return "CASCADE_UP"
    if inp.move_4h_pct is not None and inp.move_4h_pct < -CASCADE_4H_PCT:
        return "CASCADE_DOWN"

    # 2. Need ema200 for trend states
    if inp.ema200 is None or inp.ema50 is None:
        return "RANGE"

    ema_stack_up = inp.ema50 > inp.ema200
    ema_stack_down = inp.ema50 < inp.ema200
    slope = inp.ema50_slope_pct or 0
    adx = inp.adx_proxy or 0
    dist_ema200 = inp.dist_to_ema200_pct or 0
    atr = inp.atr_pct_1h or 0
    move_24h = inp.move_24h_pct or 0

    # 3. STRONG trend — high ADX + EMA stack + slope + on-side of EMA200
    if ema_stack_up and slope > 0 and adx > STRONG_ADX_THRESHOLD and dist_ema200 > 0:
        return "STRONG_UP"
    if ema_stack_down and slope < 0 and adx > STRONG_ADX_THRESHOLD and dist_ema200 < 0:
        return "STRONG_DOWN"

    # 4. SLOW trend — EMA stack + slope, dist > 1.5% from EMA200
    if ema_stack_up and slope > 0 and dist_ema200 > SLOW_DIST_EMA200_PCT:
        return "SLOW_UP"
    if ema_stack_down and slope < 0 and dist_ema200 < -SLOW_DIST_EMA200_PCT:
        return "SLOW_DOWN"

    # 5. DRIFT — net 24h directional move with low ATR (slow grind)
    if move_24h > DRIFT_24H_PCT and atr < DRIFT_ATR_PCT_MAX:
        return "DRIFT_UP"
    if move_24h < -DRIFT_24H_PCT and atr < DRIFT_ATR_PCT_MAX:
        return "DRIFT_DOWN"

    # 6. COMPRESSION — low BB width + low ATR
    if (
        inp.bb_width_pct is not None
        and inp.bb_width_p20_30d is not None
        and inp.bb_width_pct < inp.bb_width_p20_30d
        and atr < COMPRESSION_ATR_PCT_MAX
    ):
        return "COMPRESSION"

    # 7. Default
    return "RANGE"


def project_3state(state: str) -> str:
    """Project v2 10-state into Decision Layer 3-state for R-rules compat."""
    if state in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP"):
        return "MARKUP"
    if state in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN"):
        return "MARKDOWN"
    return "RANGE"
