from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={"version": "1.0"},
    )


class LiqLevel(StrictModel):
    price: float = Field(gt=0)
    size_usd: float = Field(ge=0)


class MarketContext(StrictModel):
    price_btc: float = Field(gt=0)
    regime_label: Literal[
        "impulse_up",
        "impulse_down",
        "impulse_up_exhausting",
        "impulse_down_exhausting",
        "range_tight",
        "range_wide",
        "trend_up",
        "trend_down",
        "consolidation",
        "unknown",
    ]
    regime_modifiers: list[str] = Field(default_factory=list)
    rsi_1h: float = Field(ge=0, le=100)
    rsi_5m: float | None = Field(default=None, ge=0, le=100)
    price_change_5m_30bars_pct: float
    price_change_1h_pct: float
    nearest_liq_below: LiqLevel | None = None
    nearest_liq_above: LiqLevel | None = None

    @field_validator("regime_modifiers")
    @classmethod
    def validate_regime_modifiers(cls, value: list[str]) -> list[str]:
        pattern = re.compile(r"^[a-z_]+$")
        for item in value:
            if not pattern.fullmatch(item):
                raise ValueError("regime_modifiers items must match [a-z_]+")
        return value


class CurrentExposure(StrictModel):
    net_btc: float
    shorts_btc: float = Field(le=0)
    longs_btc: float = Field(ge=0)
    free_margin_pct: float = Field(ge=0, le=100)
    available_usd: float = Field(ge=0)
    margin_coef_pct: float = Field(ge=0, le=100)


class RecommendationTarget(StrictModel):
    price: float = Field(gt=0)
    size_pct: int = Field(ge=1, le=100)
    rationale: str = Field(min_length=1, max_length=200)


class RecommendationInvalidation(StrictModel):
    rule: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=200)


class Recommendation(StrictModel):
    primary_action: Literal[
        "increase_long_manual",
        "increase_short_manual",
        "close_long_partial",
        "close_short_partial",
        "do_nothing",
        "start_temporary_bot",
        "stop_bot",
    ]
    size_btc_equivalent: float = Field(ge=0)
    size_usd_inverse: float | None = Field(default=None, ge=0)
    size_rationale: str = Field(min_length=1, max_length=300)
    entry_zone: tuple[float, float]
    invalidation: RecommendationInvalidation
    targets: list[RecommendationTarget] = Field(min_length=1, max_length=5)
    max_hold_hours: int = Field(ge=1, le=72)

    @field_validator("entry_zone")
    @classmethod
    def validate_entry_zone(cls, value: tuple[float, float]) -> tuple[float, float]:
        low, high = value
        if low <= 0 or high <= 0:
            raise ValueError("entry_zone values must be > 0")
        if low > high:
            raise ValueError("entry_zone low must be <= high")
        return value

    @model_validator(mode="after")
    def validate_target_sum(self) -> "Recommendation":
        total = sum(target.size_pct for target in self.targets)
        if total != 100:
            raise ValueError("targets size_pct sum must equal 100")
        return self


class SimilarSetup(StrictModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    outcome: Literal["tp1_hit", "tp2_hit", "tp3_hit", "stop_hit", "timeout", "manual_close"]
    realized_usd: float


class PlaybookCheck(StrictModel):
    matched_pattern: str = Field(pattern=r"^P-\d+$")
    hard_ban_check: Literal["passed", "failed"]
    similar_setups_last_30d: list[SimilarSetup] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, min_length=1, max_length=500)


class AlternativeAction(StrictModel):
    action: str = Field(min_length=1, max_length=50)
    rationale: str = Field(min_length=1, max_length=200)
    score: float = Field(ge=0, le=1)


class TrendHandling(StrictModel):
    current_trend_strength: float = Field(ge=0, le=1)
    if_trend_continues_aligned: str = Field(min_length=1, max_length=300)
    if_trend_reverses_against: str = Field(min_length=1, max_length=300)
    de_risking_rule: str = Field(min_length=1, max_length=300)


class SignalEnvelope(StrictModel):
    signal_id: str = Field(pattern=r"^adv_\d{4}-\d{2}-\d{2}_\d{6}_\d{3}$")
    ts: datetime
    setup_id: str = Field(pattern=r"^P-\d+$")
    setup_name: str = Field(min_length=1, max_length=200)
    market_context: MarketContext
    current_exposure: CurrentExposure
    recommendation: Recommendation
    playbook_check: PlaybookCheck
    alternatives_considered: list[AlternativeAction] = Field(min_length=1, max_length=5)
    trend_handling: TrendHandling

    @field_validator("ts")
    @classmethod
    def validate_ts_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ts must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_signal_id_timestamp(self) -> "SignalEnvelope":
        match = re.fullmatch(r"adv_(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})_\d{3}", self.signal_id)
        if not match:
            return self
        date_part, hour, minute, _second = match.groups()
        expected_prefix = f"{date_part}_{hour}{minute}"
        actual_prefix = self.ts.strftime("%Y-%m-%d_%H%M")
        if expected_prefix != actual_prefix:
            raise ValueError("signal_id timestamp portion must match ts to the minute")
        return self
