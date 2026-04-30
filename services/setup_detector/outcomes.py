from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Setup, SetupStatus, setup_side

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTCOMES_JSONL = _ROOT / "state" / "setup_outcomes.jsonl"


@dataclass(frozen=True)
class ProgressResult:
    status_changed: bool
    new_status: SetupStatus
    close_price: float | None = None
    hypothetical_pnl_usd: float | None = None
    hypothetical_r: float | None = None
    time_to_outcome_min: int | None = None


@dataclass(frozen=True)
class SetupOutcome:
    setup_id: str
    ts: datetime
    old_status: SetupStatus
    new_status: SetupStatus
    close_price: float | None
    hypothetical_pnl_usd: float | None
    hypothetical_r: float | None
    time_to_outcome_min: int | None


def _calc_pnl_usd(
    setup: Setup,
    close_price: float,
    size_btc: float | None = None,
) -> tuple[float, float]:
    """Returns (pnl_usd, r_multiple)."""
    size = size_btc if size_btc is not None else setup.recommended_size_btc
    if setup.entry_price is None or setup.entry_price <= 0.0 or size <= 0.0:
        return (0.0, 0.0)
    entry = setup.entry_price
    side = setup_side(setup)
    if side == "long":
        pnl_usd = (close_price - entry) / entry * entry * size
        pnl_usd = close_price * size - entry * size  # simple: price delta × size
        stop = setup.stop_price
        risk_usd = (entry - stop) * size if stop is not None and stop > 0.0 else entry * size * 0.005
        r = pnl_usd / max(risk_usd, 1e-9)
    elif side == "short":
        pnl_usd = (entry - close_price) * size
        stop = setup.stop_price
        risk_usd = (stop - entry) * size if stop is not None and stop > 0.0 else entry * size * 0.005
        r = pnl_usd / max(risk_usd, 1e-9)
    else:
        return (0.0, 0.0)
    return (round(pnl_usd, 2), round(r, 3))


def check_setup_progress(
    setup: Setup,
    current_price: float,
    now: datetime | None = None,
) -> ProgressResult:
    """Determine if setup needs a status transition."""
    _now = now if now is not None else datetime.now(timezone.utc)
    side = setup_side(setup)

    # Expiry check (any active status)
    if setup.status in (SetupStatus.DETECTED, SetupStatus.ENTRY_HIT):
        if _now >= setup.expires_at:
            return ProgressResult(
                status_changed=True,
                new_status=SetupStatus.EXPIRED,
                close_price=current_price,
                time_to_outcome_min=int((_now - setup.detected_at).total_seconds() / 60),
            )

    # Entry fill check
    if setup.status == SetupStatus.DETECTED and setup.entry_price is not None:
        entry_hit = False
        if side == "long" and current_price <= setup.entry_price:
            entry_hit = True
        elif side == "short" and current_price >= setup.entry_price:
            entry_hit = True
        if entry_hit:
            return ProgressResult(
                status_changed=True,
                new_status=SetupStatus.ENTRY_HIT,
                close_price=current_price,
                time_to_outcome_min=int((_now - setup.detected_at).total_seconds() / 60),
            )

    # TP / Stop checks (only after entry)
    if setup.status == SetupStatus.ENTRY_HIT:
        # TP1
        if setup.tp1_price is not None:
            tp1_hit = (side == "long" and current_price >= setup.tp1_price) or (
                side == "short" and current_price <= setup.tp1_price
            )
            if tp1_hit:
                pnl, r = _calc_pnl_usd(setup, setup.tp1_price)
                return ProgressResult(
                    status_changed=True,
                    new_status=SetupStatus.TP1_HIT,
                    close_price=setup.tp1_price,
                    hypothetical_pnl_usd=pnl,
                    hypothetical_r=r,
                    time_to_outcome_min=int((_now - setup.detected_at).total_seconds() / 60),
                )

        # Stop
        if setup.stop_price is not None:
            stop_hit = (side == "long" and current_price <= setup.stop_price) or (
                side == "short" and current_price >= setup.stop_price
            )
            if stop_hit:
                pnl, r = _calc_pnl_usd(setup, setup.stop_price)
                return ProgressResult(
                    status_changed=True,
                    new_status=SetupStatus.STOP_HIT,
                    close_price=setup.stop_price,
                    hypothetical_pnl_usd=pnl,
                    hypothetical_r=r,
                    time_to_outcome_min=int((_now - setup.detected_at).total_seconds() / 60),
                )

    return ProgressResult(status_changed=False, new_status=setup.status)


class OutcomesWriter:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_OUTCOMES_JSONL
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write_outcome_event(self, setup: Setup, result: ProgressResult) -> None:
        outcome = SetupOutcome(
            setup_id=setup.setup_id,
            ts=datetime.now(timezone.utc),
            old_status=setup.status,
            new_status=result.new_status,
            close_price=result.close_price,
            hypothetical_pnl_usd=result.hypothetical_pnl_usd,
            hypothetical_r=result.hypothetical_r,
            time_to_outcome_min=result.time_to_outcome_min,
        )
        d: dict[str, Any] = {
            "setup_id": outcome.setup_id,
            "ts": outcome.ts.isoformat(),
            "old_status": outcome.old_status.value,
            "new_status": outcome.new_status.value,
            "close_price": outcome.close_price,
            "hypothetical_pnl_usd": outcome.hypothetical_pnl_usd,
            "hypothetical_r": outcome.hypothetical_r,
            "time_to_outcome_min": outcome.time_to_outcome_min,
            # denormalized for analytics
            "setup_type": setup.setup_type.value,
            "pair": setup.pair,
            "regime_label": setup.regime_label,
            "session_label": setup.session_label,
            "strength": setup.strength,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        logger.info(
            "setup_outcomes.write id=%s %s→%s pnl=%s",
            setup.setup_id,
            setup.status.value,
            result.new_status.value,
            result.hypothetical_pnl_usd,
        )
