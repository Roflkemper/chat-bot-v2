"""H10 Liquidity Grid Probe → Setup adapter.

Bridges existing services/h10_detector.py and services/liquidity_map.py to
the unified Setup contract used by setup_detector loop.

Strategy: when an impulse (>=1.5% in 2-12h) is followed by tight consolidation
(6-48h corridor <=2.5%) AND there are bilateral liquidity zones above/below,
emit a Setup that probes the heavier zone.

Backtest verdict (TZ-056, 2-year frozen): 79.3% WR, $2.16 avg PnL/cycle on
150 detected setups with protective_stop=-0.8%, tp=0.5%, time_stop=2h.

The setup is one-direction (LONG_LIQ_MAGNET if target zone above current
price else SHORT_LIQ_MAGNET). Entry = current price (limit fill), TP = 0.5%
toward target, stop = -0.8% in opposite direction.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from services.h10_detector import detect_setup as _h10_detect_setup
from services.liquidity_map import build_liquidity_map
from services.setup_detector.models import (
    Setup,
    SetupBasis,
    SetupType,
    make_setup,
)

if TYPE_CHECKING:
    from services.setup_detector.setup_types import DetectionContext

logger = logging.getLogger(__name__)

# H10 trade params from TZ-056 best row (79.3% WR, +$324 / 150 cycles)
H10_TP_PCT = 0.5         # +0.5% to TP (each side)
H10_STOP_PCT = 0.8       # -0.8% protective stop
H10_TIME_STOP_MIN = 120  # 2 hours
H10_STRENGTH = 8         # high — backtested edge
H10_CONFIDENCE = 75.0


def detect_h10_liquidity_probe(ctx: "DetectionContext") -> Setup | None:
    """Detect H10 setup, return Setup or None."""
    df1h = getattr(ctx, "ohlcv_1h", None)
    if df1h is None or len(df1h) < 60:
        return None

    # Need DatetimeIndex for h10_detector to work efficiently
    if not hasattr(df1h.index, "tzinfo"):
        return None

    # Use last bar timestamp as `ts`
    try:
        last_ts = df1h.index[-1]
        if not hasattr(last_ts, "to_pydatetime"):
            return None
        ts = last_ts.to_pydatetime() if hasattr(last_ts, "to_pydatetime") else last_ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (IndexError, AttributeError):
        return None

    # Build liquidity map for this moment
    try:
        liq_map = build_liquidity_map(ts, ohlcv_1h=df1h)
    except Exception:
        logger.debug("h10_adapter.liq_map_build_failed", exc_info=True)
        return None
    if not liq_map:
        return None

    # Run H10 detection
    try:
        h10 = _h10_detect_setup(ts, df1h, liq_map)
    except Exception:
        logger.debug("h10_adapter.h10_detect_failed", exc_info=True)
        return None
    if h10 is None:
        return None

    current_price = float(df1h["close"].iloc[-1])
    target_price = h10.target_zone.price_level
    if h10.target_side == "long_probe":
        side = "long"
        entry = current_price
        tp1 = entry * (1 + H10_TP_PCT / 100)
        tp2 = entry * (1 + H10_TP_PCT * 2 / 100)
        stop = entry * (1 - H10_STOP_PCT / 100)
        setup_type = SetupType.LONG_LIQ_MAGNET
    else:
        side = "short"
        entry = current_price
        tp1 = entry * (1 - H10_TP_PCT / 100)
        tp2 = entry * (1 - H10_TP_PCT * 2 / 100)
        stop = entry * (1 + H10_STOP_PCT / 100)
        setup_type = SetupType.SHORT_LIQ_MAGNET

    rr = abs(tp1 - entry) / max(abs(entry - stop), 1e-6)

    basis = (
        SetupBasis(label="impulse_pct", value=round(h10.impulse_pct * 100, 2), weight=0.3),
        SetupBasis(label="impulse_window_h", value=h10.impulse_window_hours, weight=0.2),
        SetupBasis(label="consolidation_h", value=h10.consolidation_hours, weight=0.2),
        SetupBasis(label="zone_weight", value=round(h10.target_zone.weight, 2), weight=0.2),
        SetupBasis(label="zone_distance_pct",
                   value=round(abs(target_price - current_price) / current_price * 100, 2),
                   weight=0.1),
    )

    return make_setup(
        setup_type=setup_type,
        pair=ctx.pair,
        current_price=current_price,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        entry_price=entry,
        stop_price=stop,
        tp1_price=tp1,
        tp2_price=tp2,
        risk_reward=round(rr, 2),
        strength=H10_STRENGTH,
        confidence_pct=H10_CONFIDENCE,
        basis=basis,
        cancel_conditions=(
            f"price breaks consolidation [{h10.consolidation_low:.0f}, {h10.consolidation_high:.0f}]",
            f"time stop {H10_TIME_STOP_MIN} min",
        ),
        window_minutes=H10_TIME_STOP_MIN,
        portfolio_impact_note=(
            f"H10 liq-grid {side} probe to zone @{target_price:.0f} (w={h10.target_zone.weight:.2f})"
        ),
    )
