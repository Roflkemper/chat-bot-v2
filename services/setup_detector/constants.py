"""Tunable constants for setup detectors.

Centralizes the magic numbers that were scattered across setup_types.py
in 9-15 places. One file = one tuning surface.

Conventions:
- RSI gates use the *_STRICT suffix when stricter than the default
  oversold/overbought definition. E.g., RSI_OVERSOLD = 35 (default for
  most fade detectors), RSI_OVERSOLD_STRICT = 30 (for high-confidence
  reclaim setups).
- Multipliers are expressed as fractions of price (1.003 = +0.3%) with
  named direction (LONG_ENTRY_PREMIUM, SHORT_STOP_BUFFER, etc).
- Each constant has a one-line rationale where the value isn't self-
  evident (e.g., why 72 vs 70).

Audit (2026-05-10): rsi/multiplier scattered values verified against
setup_types.py callsites. Refactor preserves existing detector behavior
exactly — same numbers, just centrally defined.
"""
from __future__ import annotations

# ─── RSI thresholds (1h) ─────────────────────────────────────────────────────
# Three pairs covering the spectrum: standard / strict / extreme.
RSI_OVERSOLD = 35.0           # default for fade-and-reclaim setups
RSI_OVERSOLD_STRICT = 30.0    # liq_reclaim — needs deep oversold for high-conf
RSI_OVERBOUGHT = 70.0         # default for short fade
RSI_OVERBOUGHT_STRICT = 72.0  # short_pdh_rejection — RSI≥72 hard-gate from
                              # 2026-05-10 calibration (PF 0.58→1.35 with this gate)

# Used as "neutral mid" — sometimes detectors require RSI to drift past midline
# (e.g., dump_reversal expects momentum past oversold cleanup zone).
RSI_NEUTRAL_LOW = 45.0
RSI_NEUTRAL_HIGH = 55.0
RSI_MID = 50.0

# Stronger momentum cutoff for RSI breakouts.
RSI_MOMENTUM_HIGH = 65.0

# ─── Slope / trend filters ──────────────────────────────────────────────────
# Used in short_pdh_rejection: must be in a trending-up day (slope_6h ≥ 1%)
# else the rejection isn't a real fade signal.
SLOPE_6H_MIN_FOR_SHORT = 1.0  # %

# ─── Confidence floors ──────────────────────────────────────────────────────
MIN_CONFIDENCE_DEFAULT = 70.0
MIN_CONFIDENCE_STRONG = 75.0  # used by mega-pair, p15, double-pattern
MIN_CONFIDENCE_VERY_STRONG = 85.0

# ─── Strength threshold ─────────────────────────────────────────────────────
# Below this, combo_filter blocks the setup. Data-driven from year backtest:
# strength=8 → 24.6% WR / +$384 (near-zero PnL); strength=9 → 38.4% WR / +$17k.
MIN_ALLOWED_STRENGTH = 9

# ─── Entry / stop multipliers (LONG side) ───────────────────────────────────
# Premium added to current_price for limit entries (so we don't enter at the
# tick that triggered the setup).
LONG_ENTRY_PREMIUM = 0.997    # current_price * 0.997 → entry just below market
LONG_ENTRY_NEAR_LEVEL = 0.998 # near a known level (PDL, liq)
LONG_STOP_BUFFER_BELOW = 0.995  # stop = level * 0.995 (below support)
LONG_STOP_BUFFER_DEEP = 0.993   # for breakout-confirmed long
LONG_STOP_FROM_LIQ = 0.997      # stop = liq * 0.997 (just below liq line)

# How far ABOVE the level the rejection close must be for valid PDL bounce.
LONG_REJECTION_TOLERANCE = 1.003  # close > pdl * 1.003 (cleared by 0.3%)

# Reclaim threshold — price must clear liq line by this margin.
LONG_RECLAIM_MIN = 1.003

# ─── Entry / stop multipliers (SHORT side) ──────────────────────────────────
SHORT_ENTRY_PREMIUM = 1.003   # current_price * 1.003 → entry just above market
SHORT_ENTRY_NEAR_LEVEL = 1.002
SHORT_STOP_BUFFER_ABOVE = 1.005
SHORT_STOP_BUFFER_DEEP = 1.007
SHORT_STOP_FROM_LIQ = 1.003

# How far BELOW the level the rejection close must be for valid PDH rejection.
SHORT_REJECTION_TOLERANCE = 0.997  # high >= pdh*0.997 AND close < pdh

# Reject threshold — price must drop below liq line by this margin.
SHORT_REJECT_MIN = 0.997

# Recent swing high / low buffer (small offset above/below extreme).
SWING_HIGH_BUFFER = 1.003
SWING_LOW_BUFFER = 0.997

# ─── Boundary / reference movement ──────────────────────────────────────────
# grid_raise_boundary: new_boundary = reference * 1.003.
GRID_BOUNDARY_PREMIUM = 1.003
# Trigger threshold: price must exceed reference by 0.1% to consider raising.
GRID_BOUNDARY_TRIGGER = 1.001
