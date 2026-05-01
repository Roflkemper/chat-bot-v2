from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class SetupType(Enum):
    LONG_DUMP_REVERSAL = "long_dump_reversal"
    LONG_PDL_BOUNCE = "long_pdl_bounce"
    LONG_OVERSOLD_RECLAIM = "long_oversold_reclaim"
    LONG_LIQ_MAGNET = "long_liq_magnet"
    SHORT_RALLY_FADE = "short_rally_fade"
    SHORT_PDH_REJECTION = "short_pdh_rejection"
    SHORT_OVERBOUGHT_FADE = "short_overbought_fade"
    SHORT_LIQ_MAGNET = "short_liq_magnet"
    GRID_RAISE_BOUNDARY = "grid_raise_boundary"
    GRID_PAUSE_ENTRIES = "grid_pause_entries"
    GRID_BOOSTER_ACTIVATE = "grid_booster"
    GRID_ADAPTIVE_TIGHTEN = "grid_adaptive"
    DEFENSIVE_LIQ_PROXIMITY = "def_liq_proximity"
    DEFENSIVE_MARGIN_LOW = "def_margin_low"


class SetupStatus(Enum):
    DETECTED = "detected"
    ENTRY_HIT = "entry_hit"
    TP1_HIT = "tp1_hit"
    TP2_HIT = "tp2_hit"
    STOP_HIT = "stop_hit"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class SetupBasis:
    label: str
    value: float | str
    weight: float  # [0.0 .. 1.0] contribution to strength score


@dataclass(frozen=True)
class Setup:
    setup_id: str
    setup_type: SetupType
    detected_at: datetime

    pair: str
    current_price: float
    regime_label: str
    session_label: str

    entry_price: float | None
    stop_price: float | None
    tp1_price: float | None
    tp2_price: float | None
    risk_reward: float | None

    grid_action: str | None
    grid_target_bots: tuple[str, ...]
    grid_param_change: dict[str, Any] | None

    strength: int            # 1..10
    confidence_pct: float    # 0..100
    basis: tuple[SetupBasis, ...]
    cancel_conditions: tuple[str, ...]

    window_minutes: int
    expires_at: datetime
    status: SetupStatus

    portfolio_impact_note: str
    recommended_size_btc: float

    # ICT context at detection time (14 fields from ict_levels parquet).
    # Empty dict when parquet is unavailable or not yet generated.
    ict_context: dict[str, Any] = field(default_factory=dict)


def make_setup(
    *,
    setup_type: SetupType,
    pair: str,
    current_price: float,
    regime_label: str,
    session_label: str,
    entry_price: float | None = None,
    stop_price: float | None = None,
    tp1_price: float | None = None,
    tp2_price: float | None = None,
    risk_reward: float | None = None,
    grid_action: str | None = None,
    grid_target_bots: tuple[str, ...] = (),
    grid_param_change: dict[str, Any] | None = None,
    strength: int,
    confidence_pct: float,
    basis: tuple[SetupBasis, ...],
    cancel_conditions: tuple[str, ...],
    window_minutes: int = 120,
    portfolio_impact_note: str = "",
    recommended_size_btc: float = 0.05,
    detected_at: datetime | None = None,
    ict_context: dict[str, Any] | None = None,
) -> Setup:
    now = detected_at if detected_at is not None else datetime.now(timezone.utc)
    setup_id = f"setup-{now.strftime('%Y-%m-%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    return Setup(
        setup_id=setup_id,
        setup_type=setup_type,
        detected_at=now,
        pair=pair,
        current_price=current_price,
        regime_label=regime_label,
        session_label=session_label,
        entry_price=entry_price,
        stop_price=stop_price,
        tp1_price=tp1_price,
        tp2_price=tp2_price,
        risk_reward=risk_reward,
        grid_action=grid_action,
        grid_target_bots=grid_target_bots,
        grid_param_change=grid_param_change,
        strength=strength,
        confidence_pct=confidence_pct,
        basis=basis,
        cancel_conditions=cancel_conditions,
        window_minutes=window_minutes,
        expires_at=now + timedelta(minutes=window_minutes),
        status=SetupStatus.DETECTED,
        portfolio_impact_note=portfolio_impact_note,
        recommended_size_btc=recommended_size_btc,
        ict_context=ict_context if ict_context is not None else {},
    )


def setup_side(setup: Setup) -> str:
    """Returns 'long', 'short', 'grid', or 'defensive'."""
    v = setup.setup_type.value
    if v.startswith("long_"):
        return "long"
    if v.startswith("short_"):
        return "short"
    if v.startswith("grid_"):
        return "grid"
    return "defensive"
