from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.advise_v2 import CurrentExposure, LiqLevel, MarketContext, SignalEnvelope
from services.advise_v2.action_tracker import (
    ActionMatch,
    ActionTaken,
    FollowupHorizon,
    FollowupOutcome,
    aggregate_action_breakdown,
    get_followups_for_signal,
    get_match_for_signal,
    iter_followups,
    iter_matches,
    log_followup,
    log_match,
    signals_pending_followup,
    signals_without_match,
)
from services.advise_v2.schemas import (
    AlternativeAction,
    PlaybookCheck,
    Recommendation,
    RecommendationInvalidation,
    RecommendationTarget,
    TrendHandling,
)
from services.advise_v2.signal_logger import log_signal


def _market_context() -> MarketContext:
    return MarketContext(
        price_btc=76000.0,
        regime_label="trend_up",
        regime_modifiers=["volume_spike"],
        rsi_1h=58.0,
        rsi_5m=62.0,
        price_change_5m_30bars_pct=0.9,
        price_change_1h_pct=1.2,
        nearest_liq_below=LiqLevel(price=75500.0, size_usd=1_000_000.0),
        nearest_liq_above=LiqLevel(price=76500.0, size_usd=900_000.0),
    )


def _current_exposure() -> CurrentExposure:
    return CurrentExposure(
        net_btc=0.1,
        shorts_btc=0.0,
        longs_btc=0.1,
        free_margin_pct=70.0,
        available_usd=5000.0,
        margin_coef_pct=20.0,
    )


def _signal(signal_id: str, ts: datetime) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=signal_id,
        ts=ts,
        setup_id="P-2",
        setup_name="Reversal long after liq cascade",
        market_context=_market_context(),
        current_exposure=_current_exposure(),
        recommendation=Recommendation(
            primary_action="increase_long_manual",
            size_btc_equivalent=0.08,
            size_usd_inverse=6080.0,
            size_rationale="normal — confidence 0.80, free margin 70%",
            entry_zone=(75620.0, 76076.0),
            invalidation=RecommendationInvalidation(
                rule="5m close below 75468",
                reason="next major level breach, V failed",
            ),
            targets=[
                RecommendationTarget(price=76456.0, size_pct=30, rationale="first resistance"),
                RecommendationTarget(price=76760.0, size_pct=30, rationale="session VWAP"),
                RecommendationTarget(price=77140.0, size_pct=40, rationale="rally extension"),
            ],
            max_hold_hours=4,
        ),
        playbook_check=PlaybookCheck(
            matched_pattern="P-2",
            hard_ban_check="passed",
            similar_setups_last_30d=[],
            note="placeholder",
        ),
        alternatives_considered=[
            AlternativeAction(
                action="do_nothing",
                rationale="no other patterns matched above threshold",
                score=0.5,
            )
        ],
        trend_handling=TrendHandling(
            current_trend_strength=0.8,
            if_trend_continues_aligned="Hold.",
            if_trend_reverses_against="De-risk.",
            de_risking_rule="No active de-risking rule.",
        ),
    )


def _match(signal_id: str = "adv_2026-04-30_120000_001") -> ActionMatch:
    return ActionMatch(
        signal_id=signal_id,
        matched_at=datetime(2026, 4, 30, 12, 5, tzinfo=timezone.utc),
        action_taken=ActionTaken.YES_FULL,
        action_delay_seconds=300,
        actual_size_btc=0.08,
        actual_entry_price=75990.0,
        operator_note="manual follow-through",
    )


def _followup(
    signal_id: str = "adv_2026-04-30_120000_001",
    horizon: FollowupHorizon = FollowupHorizon.H1,
) -> FollowupOutcome:
    return FollowupOutcome(
        signal_id=signal_id,
        horizon=horizon,
        measured_at=datetime(2026, 4, 30, 13, 0, tzinfo=timezone.utc),
        price_at_measurement=76320.0,
        price_change_pct_from_signal=0.42,
        nearest_target_hit="tp1",
        invalidation_triggered=False,
        estimated_pnl_usd=22.0,
    )


def test_log_match_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    log_match(_match(), path)
    assert path.exists()


def test_log_match_appends(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    log_match(_match("adv_2026-04-30_120000_001"), path)
    log_match(_match("adv_2026-04-30_120000_002"), path)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_log_match_creates_parent_dir(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "match.jsonl"
    log_match(_match(), path)
    assert path.parent.exists()


def test_log_followup_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "followup.jsonl"
    log_followup(_followup(), path)
    assert path.exists()


def test_iter_matches_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    assert list(iter_matches(path)) == []


def test_iter_matches_yields_validated(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    log_match(_match(), path)
    records = list(iter_matches(path))
    assert len(records) == 1
    assert isinstance(records[0], ActionMatch)


def test_iter_matches_skips_malformed(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    path.write_text('{"bad": 1}\nnot json\n', encoding="utf-8")
    assert list(iter_matches(path)) == []


def test_iter_followups_yields_validated(tmp_path: Path) -> None:
    path = tmp_path / "followup.jsonl"
    log_followup(_followup(), path)
    records = list(iter_followups(path))
    assert len(records) == 1
    assert isinstance(records[0], FollowupOutcome)


def test_get_match_for_signal_found(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    log_match(_match(), path)
    found = get_match_for_signal("adv_2026-04-30_120000_001", path)
    assert found is not None
    assert found.action_taken is ActionTaken.YES_FULL


def test_get_match_for_signal_not_found(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    log_match(_match(), path)
    assert get_match_for_signal("adv_2026-04-30_120000_999", path) is None


def test_get_followups_sorted_by_horizon(tmp_path: Path) -> None:
    path = tmp_path / "followup.jsonl"
    log_followup(_followup(horizon=FollowupHorizon.H24), path)
    log_followup(_followup(horizon=FollowupHorizon.H1), path)
    log_followup(_followup(horizon=FollowupHorizon.H4), path)
    found = get_followups_for_signal("adv_2026-04-30_120000_001", path)
    assert [item.horizon for item in found] == [
        FollowupHorizon.H1,
        FollowupHorizon.H4,
        FollowupHorizon.H24,
    ]


def test_signals_without_match_returns_unmatched_ids(tmp_path: Path) -> None:
    signals_path = tmp_path / "signals.jsonl"
    matches_path = tmp_path / "matches.jsonl"
    ts = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    log_signal(_signal("adv_2026-04-30_120000_001", ts), signals_path)
    log_signal(_signal("adv_2026-04-30_120500_002", ts + timedelta(minutes=5)), signals_path)
    log_match(_match("adv_2026-04-30_120000_001"), matches_path)
    assert signals_without_match(signals_path, matches_path) == ["adv_2026-04-30_120500_002"]


def test_signals_pending_followup_h1_in_past(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc)

    signals_path = tmp_path / "signals.jsonl"
    signal_ts = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    log_signal(_signal("adv_2026-04-30_120000_001", signal_ts), signals_path)
    monkeypatch.setattr("services.advise_v2.action_tracker.datetime", _FrozenDatetime)
    assert signals_pending_followup(FollowupHorizon.H1, signals_path) == ["adv_2026-04-30_120000_001"]


def test_signals_pending_followup_h1_not_yet_due(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 30, 12, 30, tzinfo=timezone.utc)

    signals_path = tmp_path / "signals.jsonl"
    signal_ts = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    log_signal(_signal("adv_2026-04-30_120000_001", signal_ts), signals_path)
    monkeypatch.setattr("services.advise_v2.action_tracker.datetime", _FrozenDatetime)
    assert signals_pending_followup(FollowupHorizon.H1, signals_path) == []


def test_aggregate_action_breakdown_counts_correctly(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    log_match(_match("adv_2026-04-30_120000_001"), path)
    log_match(
        ActionMatch(
            signal_id="adv_2026-04-30_120001_002",
            matched_at=datetime(2026, 4, 30, 12, 6, tzinfo=timezone.utc),
            action_taken=ActionTaken.NO_IGNORED,
        ),
        path,
    )
    log_match(
        ActionMatch(
            signal_id="adv_2026-04-30_120002_003",
            matched_at=datetime(2026, 4, 30, 12, 7, tzinfo=timezone.utc),
            action_taken=ActionTaken.YES_FULL,
        ),
        path,
    )
    assert aggregate_action_breakdown(path) == {"yes_full": 2, "no_ignored": 1}


def test_action_match_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionMatch.model_validate(
            {
                "signal_id": "adv_2026-04-30_120000_001",
                "matched_at": "2026-04-30T12:05:00Z",
                "action_taken": "yes_full",
                "unexpected": True,
            }
        )


def test_followup_outcome_invalid_horizon_rejected() -> None:
    with pytest.raises(ValidationError):
        FollowupOutcome.model_validate(
            {
                "signal_id": "adv_2026-04-30_120000_001",
                "horizon": "2h",
                "measured_at": "2026-04-30T13:00:00Z",
                "price_at_measurement": 76320.0,
                "price_change_pct_from_signal": 0.42,
            }
        )
