"""Double top / Double bottom detector.

Algorithm:
  1. Find swing highs/lows on 1h frame (ZigZag style: pivot if N=3 bars on
     each side are lower/higher).
  2. Double top: two swing highs within ±0.3% of each other, separated by
     a valley ≥1.5% below them.
  3. Double bottom: mirror.
  4. Setup fires when current price is near the neckline (valley high for
     double top, peak low for double bottom) ±0.2%.

Returns Setup object with entry/sl/tp computed from the pattern geometry.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from services.setup_detector.models import Setup, SetupBasis, SetupType, make_setup
from services.setup_detector.candle_patterns import candle_confirmation

logger = logging.getLogger(__name__)

# Pattern parameters
SWING_LOOKBACK_BARS = 3       # bars on each side for pivot
TOP_TOLERANCE_PCT = 0.3       # max % difference between two swing highs
VALLEY_DEPTH_MIN_PCT = 1.5    # valley must be at least this much below tops
NECKLINE_PROXIMITY_PCT = 0.2  # current price must be this close to neckline
MAX_PATTERN_AGE_BARS = 80     # ignore patterns older than 80h


def _find_swing_highs(df: pd.DataFrame, lookback: int = SWING_LOOKBACK_BARS) -> list[tuple[int, float]]:
    """Return list of (bar_index, high_value) for confirmed pivot highs."""
    out = []
    if "high" not in df.columns:
        return out
    highs = df["high"].values
    for i in range(lookback, len(highs) - lookback):
        center = highs[i]
        left = highs[i - lookback : i]
        right = highs[i + 1 : i + 1 + lookback]
        if all(center > l for l in left) and all(center > r for r in right):
            out.append((i, float(center)))
    return out


def _find_swing_lows(df: pd.DataFrame, lookback: int = SWING_LOOKBACK_BARS) -> list[tuple[int, float]]:
    out = []
    if "low" not in df.columns:
        return out
    lows = df["low"].values
    for i in range(lookback, len(lows) - lookback):
        center = lows[i]
        left = lows[i - lookback : i]
        right = lows[i + 1 : i + 1 + lookback]
        if all(center < l for l in left) and all(center < r for r in right):
            out.append((i, float(center)))
    return out


def _find_valley_min(df: pd.DataFrame, idx_a: int, idx_b: int) -> Optional[float]:
    """Min of `low` between two indices (exclusive of endpoints)."""
    if idx_a >= idx_b - 1:
        return None
    return float(df.iloc[idx_a + 1 : idx_b]["low"].min())


def _find_peak_max(df: pd.DataFrame, idx_a: int, idx_b: int) -> Optional[float]:
    """Max of `high` between two indices (exclusive of endpoints)."""
    if idx_a >= idx_b - 1:
        return None
    return float(df.iloc[idx_a + 1 : idx_b]["high"].max())


# 2026-05-10: breakout-confirmed entry variant.
# After double bottom forms + price closes ABOVE neckline (peak between bottoms),
# wait for pullback >=0.3% toward neckline. Entry on pullback gives realistic
# RR target and avoids the "predict the bounce" entry that gave 87% timeout.
BREAKOUT_PULLBACK_MIN_PCT = 0.3  # min pullback from breakout peak before entry
BREAKOUT_LOOKBACK_BARS = 12       # how many recent 1h bars to scan for breakout


def detect_double_bottom_breakout(ctx) -> Setup | None:
    """Double bottom + neckline breakout + pullback entry.

    Sequence required:
      1. Two swing lows within tolerance separated by peak (depth >=1.5%)
      2. Price breaks ABOVE neckline (peak) at some bar in last 12h
      3. Price pulls back >=0.3% from breakout high but stays >= neckline
      4. Entry at current pullback price; stop below 2nd swing low; TP1 at
         breakout high + 1.0 × pattern depth
    """
    df = ctx.ohlcv_1h
    if df is None or len(df) < 30:
        return None
    if not all(col in df.columns for col in ("high", "low", "open", "close")):
        return None

    swings = _find_swing_lows(df)
    if len(swings) < 2:
        return None

    n = len(df)
    last_close = float(df["close"].iloc[-1])

    # Find double-bottom + neckline confirmed broken
    for j in range(len(swings) - 1, 0, -1):
        for i in range(j - 1, -1, -1):
            idx_a, val_a = swings[i]
            idx_b, val_b = swings[j]
            avg = (val_a + val_b) / 2
            if abs(val_a - val_b) / avg * 100 > TOP_TOLERANCE_PCT:
                continue
            peak = _find_peak_max(df, idx_a, idx_b)
            if peak is None:
                continue
            depth_pct = (peak - avg) / avg * 100
            if depth_pct < VALLEY_DEPTH_MIN_PCT:
                continue
            if (n - 1 - idx_b) > MAX_PATTERN_AGE_BARS:
                return None

            # CHECK BREAKOUT: did highs in last BREAKOUT_LOOKBACK_BARS exceed peak?
            recent_lookback = min(BREAKOUT_LOOKBACK_BARS, n - 1 - idx_b)
            if recent_lookback <= 0:
                continue
            recent = df.iloc[-recent_lookback:]
            breakout_high = float(recent["high"].max())
            if breakout_high <= peak * 1.001:  # need >=0.1% above neckline to confirm
                continue

            # CHECK PULLBACK: current price pulled back from breakout_high,
            # but still above neckline.
            pullback_pct = (breakout_high - last_close) / breakout_high * 100
            if pullback_pct < BREAKOUT_PULLBACK_MIN_PCT:
                continue
            if last_close < peak * 0.998:  # broke back below neckline = pattern failed
                continue

            entry = last_close
            stop = val_b * 0.997  # below 2nd swing low
            tp1 = breakout_high + (peak - avg) * 0.5
            tp2 = breakout_high + (peak - avg) * 1.0
            rr = abs(tp1 - entry) / max(abs(entry - stop), 1e-6)

            confirmation = candle_confirmation(df, side="long", idx=-1)
            strength = 8
            if confirmation:
                strength = min(10, strength + 1)
            confidence_pct = 70.0 if confirmation else 60.0

            basis_items = [
                SetupBasis("double_bottom_low_1", round(val_a, 2), 0.3),
                SetupBasis("double_bottom_low_2", round(val_b, 2), 0.3),
                SetupBasis("neckline", round(peak, 2), 0.2),
                SetupBasis("breakout_high", round(breakout_high, 2), 0.3),
                SetupBasis("pullback_pct", round(pullback_pct, 2), 0.2),
                SetupBasis("depth_pct", round(depth_pct, 2), 0.2),
            ]
            if confirmation:
                basis_items.append(SetupBasis("candle_confirmation", confirmation, 0.3))

            return make_setup(
                setup_type=SetupType.LONG_DOUBLE_BOTTOM_BREAKOUT,
                pair=ctx.pair,
                current_price=last_close,
                regime_label=ctx.regime_label,
                session_label=ctx.session_label,
                entry_price=entry,
                stop_price=stop,
                tp1_price=tp1,
                tp2_price=tp2,
                risk_reward=round(rr, 2),
                strength=strength,
                confidence_pct=confidence_pct,
                basis=tuple(basis_items),
                cancel_conditions=(
                    f"close below {peak:.0f} (neckline retest fail)",
                    f"new low below {val_b:.0f}",
                ),
                window_minutes=240,
                portfolio_impact_note=(
                    f"Double bottom breakout {val_a:.0f}/{val_b:.0f} → {peak:.0f} → "
                    f"pullback to {last_close:.0f}"
                ),
            )

    return None


def detect_double_top_setup(ctx) -> Setup | None:
    """Double top: two swing highs within tolerance + valley + price near neckline."""
    df = ctx.ohlcv_1h
    if df is None or len(df) < 30:
        return None
    if not all(col in df.columns for col in ("high", "low", "open", "close")):
        return None

    swings = _find_swing_highs(df)
    if len(swings) < 2:
        return None

    n = len(df)
    last_close = float(df["close"].iloc[-1])

    # Iterate from most recent backwards, find two close-enough swing highs
    for j in range(len(swings) - 1, 0, -1):
        for i in range(j - 1, -1, -1):
            idx_a, val_a = swings[i]
            idx_b, val_b = swings[j]
            # Tolerance check
            avg = (val_a + val_b) / 2
            if abs(val_a - val_b) / avg * 100 > TOP_TOLERANCE_PCT:
                continue
            # Valley depth
            valley = _find_valley_min(df, idx_a, idx_b)
            if valley is None:
                continue
            depth_pct = (avg - valley) / avg * 100
            if depth_pct < VALLEY_DEPTH_MIN_PCT:
                continue
            # Pattern age
            if (n - 1 - idx_b) > MAX_PATTERN_AGE_BARS:
                return None  # too old; further pairs even older
            # Current price near neckline (valley)?
            dist_to_neckline_pct = abs(last_close - valley) / valley * 100
            if dist_to_neckline_pct > NECKLINE_PROXIMITY_PCT:
                # Pattern detected but price not near trigger zone
                continue
            # Optional candle confirmation
            confirmation = candle_confirmation(df, side="short", idx=-1)

            # Pattern geometry → setup levels
            entry = last_close
            stop = avg * 1.003   # 0.3% above the pattern tops
            tp1 = valley - (avg - valley) * 0.5  # half the pattern height down
            tp2 = valley - (avg - valley) * 1.0  # full pattern height down
            rr = abs(tp1 - entry) / max(abs(stop - entry), 1e-6)

            strength = 7
            if confirmation:
                strength = min(10, strength + 2)
            confidence_pct = 60.0
            if confirmation:
                confidence_pct = 75.0

            basis_items = [
                SetupBasis("double_top_high_1", round(val_a, 2), 0.3),
                SetupBasis("double_top_high_2", round(val_b, 2), 0.3),
                SetupBasis("valley_low", round(valley, 2), 0.2),
                SetupBasis("depth_pct", round(depth_pct, 2), 0.2),
            ]
            if confirmation:
                basis_items.append(SetupBasis("candle_confirmation", confirmation, 0.3))

            return make_setup(
                setup_type=SetupType.SHORT_DOUBLE_TOP,
                pair=ctx.pair,
                current_price=last_close,
                regime_label=ctx.regime_label,
                session_label=ctx.session_label,
                entry_price=entry,
                stop_price=stop,
                tp1_price=tp1,
                tp2_price=tp2,
                risk_reward=round(rr, 2),
                strength=strength,
                confidence_pct=confidence_pct,
                basis=tuple(basis_items),
                cancel_conditions=(
                    f"close above {avg:.0f} invalidates double top",
                    f"pattern age > {MAX_PATTERN_AGE_BARS}h",
                ),
                window_minutes=180,
                portfolio_impact_note=f"Double top {val_a:.0f}/{val_b:.0f}, neckline {valley:.0f}",
            )

    return None


def detect_double_bottom_setup(ctx) -> Setup | None:
    """Double bottom: two swing lows within tolerance + peak + price near neckline."""
    df = ctx.ohlcv_1h
    if df is None or len(df) < 30:
        return None
    if not all(col in df.columns for col in ("high", "low", "open", "close")):
        return None

    swings = _find_swing_lows(df)
    if len(swings) < 2:
        return None

    n = len(df)
    last_close = float(df["close"].iloc[-1])

    for j in range(len(swings) - 1, 0, -1):
        for i in range(j - 1, -1, -1):
            idx_a, val_a = swings[i]
            idx_b, val_b = swings[j]
            avg = (val_a + val_b) / 2
            if abs(val_a - val_b) / avg * 100 > TOP_TOLERANCE_PCT:
                continue
            peak = _find_peak_max(df, idx_a, idx_b)
            if peak is None:
                continue
            depth_pct = (peak - avg) / avg * 100
            if depth_pct < VALLEY_DEPTH_MIN_PCT:
                continue
            if (n - 1 - idx_b) > MAX_PATTERN_AGE_BARS:
                return None
            dist_to_neckline_pct = abs(last_close - peak) / peak * 100
            if dist_to_neckline_pct > NECKLINE_PROXIMITY_PCT:
                continue
            confirmation = candle_confirmation(df, side="long", idx=-1)

            entry = last_close
            stop = avg * 0.997
            # 2026-05-10 SETUP_FILTER_RESEARCH: попытка перенести TP1 на peak дала
            # WR 4.7% (TP касается, но slippage съедает). Возвращаем оригинал.
            # Реальная проблема: entry=last_close возле peak, нужен новый детектор
            # который входит ПОСЛЕ прорыва neckline (breakout-confirmed) — TODO.
            tp1 = peak + (peak - avg) * 0.5
            tp2 = peak + (peak - avg) * 1.0
            rr = abs(tp1 - entry) / max(abs(entry - stop), 1e-6)

            strength = 7
            if confirmation:
                strength = min(10, strength + 2)
            confidence_pct = 60.0
            if confirmation:
                confidence_pct = 75.0

            basis_items = [
                SetupBasis("double_bottom_low_1", round(val_a, 2), 0.3),
                SetupBasis("double_bottom_low_2", round(val_b, 2), 0.3),
                SetupBasis("peak_high", round(peak, 2), 0.2),
                SetupBasis("depth_pct", round(depth_pct, 2), 0.2),
            ]
            if confirmation:
                basis_items.append(SetupBasis("candle_confirmation", confirmation, 0.3))

            return make_setup(
                setup_type=SetupType.LONG_DOUBLE_BOTTOM,
                pair=ctx.pair,
                current_price=last_close,
                regime_label=ctx.regime_label,
                session_label=ctx.session_label,
                entry_price=entry,
                stop_price=stop,
                tp1_price=tp1,
                tp2_price=tp2,
                risk_reward=round(rr, 2),
                strength=strength,
                confidence_pct=confidence_pct,
                basis=tuple(basis_items),
                cancel_conditions=(
                    f"close below {avg:.0f} invalidates double bottom",
                    f"pattern age > {MAX_PATTERN_AGE_BARS}h",
                ),
                window_minutes=180,
                portfolio_impact_note=f"Double bottom {val_a:.0f}/{val_b:.0f}, neckline {peak:.0f}",
            )

    return None
