"""Session breakout detector — 2026-05-11.

Backtest: docs/STRATEGIES/SESSION_BREAKOUT_BACKTEST.md
  - 2y BTC 1m, 320 combos sweep
  - Best ALL transitions (ew=30, buf=0, hold=4h): PF 1.52, N=2048, 4/4 folds positive
  - Best single: ny_pm_to_asia (ew=30, hold=4h) — PF 2.09, N=513, 4/4 folds positive

Strategy (from backtest):
  At each session change (asia/london/ny_am/ny_lunch/ny_pm transitions):
    - If price.high breaks prior_session.high within first 30 min → LONG entry
    - If price.low breaks prior_session.low within first 30 min → SHORT entry
    - Hold 4 hours, exit market.
  buffer 0% (touch is enough)
  One trade per transition.

Live integration:
  - Detector runs per-tick (every cycle ~60s in setup_detector loop)
  - Trigger fires when:
    a) we're inside a session AND time_in_session_min ≤ ENTRY_WINDOW_MIN
    b) prior session's high/low is known (from ICT context)
    c) current bar's high/low broke prior level
  - Dedup via setup_type + pair + transition: 1 trade per session boundary
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from .models import Setup, SetupBasis, SetupType, make_setup
from .scorer import compute_confidence, compute_strength

if TYPE_CHECKING:
    from .setup_types import DetectionContext


# Parameters from deep-dive backtest 2026-05-11 round 2:
#   ew=15 hold=3h: PF 1.73 across all transitions (best overall PnL+PF combo)
#   ew=15 hold=4h ny_pm_to_asia: PF 2.57 (strongest single)
# Tighter ew filters out half-hearted breaks → higher PF.
ENTRY_WINDOW_MIN = 15
BUFFER_PCT = 0.0           # 0% — touch is enough
HOLD_HOURS = 3             # 3h — broader sweet spot vs 1h-narrow / 4h-wider
DEFAULT_SL_PCT = 0.6       # stop = entry ± 0.6% (tighter than 0.8 to match shorter hold)
DEFAULT_TP_RATIO = 1.5     # TP = entry ± (SL × TP_RATIO)

# Order: prior → new
# Same as TRANS_MAP in tools/_backtest_session_breakout.py
_PRIOR_OF_NEW = {
    "asia": "ny_pm",        # ny_pm closes → asia opens
    "london": "asia",
    "ny_am": "london",
    "ny_lunch": "ny_am",
    "ny_pm": "ny_lunch",
}


def detect_session_breakout(ctx: "DetectionContext") -> Setup | None:
    """Fire LONG or SHORT when price breaks prior session's high/low.

    Requirements:
      - ctx.ict_context["session_active"] set to one of [asia, london, ny_am, ny_lunch, ny_pm]
      - ctx.ict_context["time_in_session_min"] ≤ ENTRY_WINDOW_MIN (within entry window)
      - ctx.ict_context[<prior_session>_high/_low] populated

    Returns LONG setup if recent 30-min high broke prior_session.high,
    SHORT setup if recent 30-min low broke prior_session.low,
    None otherwise.
    """
    ictx = ctx.ict_context or {}
    session = ictx.get("session_active")
    if not session or session == "dead":
        return None

    tis = ictx.get("time_in_session_min")
    if tis is None or tis > ENTRY_WINDOW_MIN:
        return None

    prior = _PRIOR_OF_NEW.get(str(session))
    if prior is None:
        return None

    prior_high = ictx.get(f"{prior}_high")
    prior_low = ictx.get(f"{prior}_low")
    if not prior_high or not prior_low or prior_high <= 0 or prior_low <= 0:
        return None

    # Look at recent price action within current session — use last `tis` 1m bars
    # to know if break already happened. If df1m too short, fall back to ctx.current_price.
    df1m = ctx.ohlcv_1m
    bars_in_session = min(int(tis) if tis else 1, len(df1m))
    if bars_in_session < 1 or len(df1m) < bars_in_session:
        recent_high = float(ctx.current_price)
        recent_low = float(ctx.current_price)
    else:
        recent = df1m.iloc[-bars_in_session:]
        recent_high = float(recent["high"].max())
        recent_low = float(recent["low"].min())

    target_high = float(prior_high) * (1 + BUFFER_PCT / 100.0)
    target_low = float(prior_low) * (1 - BUFFER_PCT / 100.0)

    side = None
    if recent_high >= target_high:
        side = "long"
    elif recent_low <= target_low:
        side = "short"
    else:
        return None

    # Build basis items
    basis_items: list[SetupBasis] = [
        SetupBasis(f"Session {session} (in {int(tis)}min)", str(session), 0.9),
        SetupBasis(f"Prior {prior}_high={prior_high:,.0f}", float(prior_high), 0.9),
        SetupBasis(f"Prior {prior}_low={prior_low:,.0f}", float(prior_low), 0.9),
        SetupBasis(
            f"Recent {'high' if side == 'long' else 'low'}="
            f"{recent_high if side == 'long' else recent_low:,.0f}",
            recent_high if side == "long" else recent_low,
            0.9,
        ),
    ]

    if side == "long":
        entry = ctx.current_price
        stop = entry * (1 - DEFAULT_SL_PCT / 100.0)
        tp1 = entry * (1 + DEFAULT_SL_PCT * DEFAULT_TP_RATIO / 100.0)
        tp2 = entry * (1 + DEFAULT_SL_PCT * DEFAULT_TP_RATIO * 1.6 / 100.0)
        setup_type = SetupType.LONG_SESSION_BREAKOUT
        cancel = (
            f"price drops below entry by 0.5% within first hour",
            f"hold window {HOLD_HOURS}h expired",
        )
    else:
        entry = ctx.current_price
        stop = entry * (1 + DEFAULT_SL_PCT / 100.0)
        tp1 = entry * (1 - DEFAULT_SL_PCT * DEFAULT_TP_RATIO / 100.0)
        tp2 = entry * (1 - DEFAULT_SL_PCT * DEFAULT_TP_RATIO * 1.6 / 100.0)
        setup_type = SetupType.SHORT_SESSION_BREAKOUT
        cancel = (
            f"price rallies above entry by 0.5% within first hour",
            f"hold window {HOLD_HOURS}h expired",
        )

    strength = compute_strength(tuple(basis_items))
    if strength < 6:
        return None
    confidence = compute_confidence(setup_type, tuple(basis_items),
                                    ctx.regime_label, ctx.session_label)

    risk_per_unit = abs(entry - stop)
    reward_per_unit = abs(tp1 - entry)
    rr = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0.0

    return make_setup(
        setup_type=setup_type,
        pair=ctx.pair,
        current_price=ctx.current_price,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        entry_price=entry,
        stop_price=stop,
        tp1_price=tp1,
        tp2_price=tp2,
        risk_reward=rr,
        strength=strength,
        confidence_pct=confidence,
        basis=tuple(basis_items),
        cancel_conditions=cancel,
        window_minutes=HOLD_HOURS * 60,
        portfolio_impact_note=(
            f"Session breakout {prior}->{session}: пробой "
            f"{'high' if side == 'long' else 'low'} предыдущей сессии"
        ),
        recommended_size_btc=0.05,
        ict_context=dict(ictx),
    )
