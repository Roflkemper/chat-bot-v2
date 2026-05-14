from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .signal_logger import iter_signals

DEFAULT_MATCH_LOG = Path("state/advise_action_match.jsonl")
DEFAULT_FOLLOWUP_LOG = Path("state/advise_followup.jsonl")


class ActionTaken(str, Enum):
    YES_FULL = "yes_full"
    YES_PARTIAL = "yes_partial"
    NO_IGNORED = "no_ignored"
    OPPOSITE = "opposite"
    NO_MARKET_MOVED = "no_market_moved"
    UNKNOWN = "unknown"


class FollowupHorizon(str, Enum):
    H1 = "1h"
    H4 = "4h"
    H24 = "24h"


class ActionMatch(BaseModel):
    """Mapping of signal_id to the operator action taken after the signal."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    signal_id: str = Field(..., pattern=r"^adv_\d{4}-\d{2}-\d{2}_\d{6}_\d{3}$")
    matched_at: datetime
    action_taken: ActionTaken
    action_delay_seconds: int | None = Field(None, ge=0)
    actual_size_btc: float | None = None
    actual_entry_price: float | None = Field(None, ge=0)
    operator_note: str | None = Field(None, max_length=500)


class FollowupOutcome(BaseModel):
    """Observed follow-up outcome for a signal at a fixed horizon."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    signal_id: str = Field(..., pattern=r"^adv_\d{4}-\d{2}-\d{2}_\d{6}_\d{3}$")
    horizon: FollowupHorizon
    measured_at: datetime
    price_at_measurement: float = Field(..., ge=0)
    price_change_pct_from_signal: float
    nearest_target_hit: Literal["tp1", "tp2", "tp3", "none"] | None = None
    invalidation_triggered: bool = False
    estimated_pnl_usd: float | None = None


def log_match(match: ActionMatch, log_path: Path | None = None) -> Path:
    """Append ActionMatch as a single JSONL line."""
    path = log_path or DEFAULT_MATCH_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(match.model_dump_json() + "\n")
    return path


def log_followup(outcome: FollowupOutcome, log_path: Path | None = None) -> Path:
    """Append FollowupOutcome as a single JSONL line."""
    path = log_path or DEFAULT_FOLLOWUP_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(outcome.model_dump_json() + "\n")
    return path


def iter_matches(log_path: Path | None = None) -> Iterator[ActionMatch]:
    """Yield action matches lazily, skipping malformed lines."""
    path = log_path or DEFAULT_MATCH_LOG
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield ActionMatch.model_validate_json(line)
            except Exception:
                continue


def iter_followups(log_path: Path | None = None) -> Iterator[FollowupOutcome]:
    """Yield follow-up outcomes lazily, skipping malformed lines."""
    path = log_path or DEFAULT_FOLLOWUP_LOG
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield FollowupOutcome.model_validate_json(line)
            except Exception:
                continue


def get_match_for_signal(signal_id: str, log_path: Path | None = None) -> ActionMatch | None:
    """Return the first ActionMatch for signal_id, or None if absent."""
    for match in iter_matches(log_path):
        if match.signal_id == signal_id:
            return match
    return None


def get_followups_for_signal(
    signal_id: str,
    log_path: Path | None = None,
) -> list[FollowupOutcome]:
    """Return all follow-ups for a signal, sorted by 1h, 4h, 24h."""
    horizon_order = {
        FollowupHorizon.H1: 1,
        FollowupHorizon.H4: 2,
        FollowupHorizon.H24: 3,
    }
    found = [followup for followup in iter_followups(log_path) if followup.signal_id == signal_id]
    return sorted(found, key=lambda followup: horizon_order.get(followup.horizon, 999))


def signals_without_match(
    signals_log: Path | None = None,
    matches_log: Path | None = None,
) -> list[str]:
    """Return signal_ids present in the signal log that have no ActionMatch."""
    matched_ids = {match.signal_id for match in iter_matches(matches_log)}
    return [
        envelope.signal_id
        for envelope in iter_signals(signals_log)
        if envelope.signal_id not in matched_ids
    ]


def signals_pending_followup(
    horizon: FollowupHorizon,
    signals_log: Path | None = None,
    followup_log: Path | None = None,
) -> list[str]:
    """Return due signal_ids that do not yet have a follow-up for the given horizon."""
    horizon_deltas = {
        FollowupHorizon.H1: timedelta(hours=1),
        FollowupHorizon.H4: timedelta(hours=4),
        FollowupHorizon.H24: timedelta(hours=24),
    }
    now = datetime.now(timezone.utc)
    delta = horizon_deltas[horizon]
    existing = {
        followup.signal_id
        for followup in iter_followups(followup_log)
        if followup.horizon == horizon
    }

    pending: list[str] = []
    for envelope in iter_signals(signals_log):
        if envelope.signal_id in existing:
            continue
        if envelope.ts + delta > now:
            continue
        pending.append(envelope.signal_id)
    return pending


def aggregate_action_breakdown(log_path: Path | None = None) -> dict[str, int]:
    """Count matches per ActionTaken value."""
    counts: dict[str, int] = {}
    for match in iter_matches(log_path):
        key = match.action_taken.value
        counts[key] = counts.get(key, 0) + 1
    return counts
