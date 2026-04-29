from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.advise_v2 import CurrentExposure, LiqLevel, MarketContext, SignalEnvelope
from services.advise_v2.action_tracker import (
    ActionMatch,
    ActionTaken,
    FollowupHorizon,
    FollowupOutcome,
    log_followup,
    log_match,
)
from services.advise_v2.schemas import (
    AlternativeAction,
    PlaybookCheck,
    Recommendation,
    RecommendationInvalidation,
    RecommendationTarget,
    SessionContext,
    TrendHandling,
)
from services.advise_v2.signal_logger import log_signal
from services.advise_v2.weekly_report import generate_weekly_report, report_to_markdown


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
        session=SessionContext(
            kz_active="NY_AM",
            kz_session_id="NY_AM_2026-04-30",
            minutes_into_session=15,
            dow_ny=5,
            is_weekend=False,
            is_friday_close=False,
        ),
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


def _signal_id(ts: datetime, counter: int) -> str:
    return f"adv_{ts.strftime('%Y-%m-%d_%H%M%S')}_{counter:03d}"


def _signal(signal_id: str, ts: datetime, setup_id: str = "P-2") -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=signal_id,
        ts=ts,
        setup_id=setup_id,
        setup_name="Setup",
        market_context=_market_context(),
        current_exposure=_current_exposure(),
        recommendation=Recommendation(
            primary_action="increase_long_manual",
            size_btc_equivalent=0.08,
            size_usd_inverse=6080.0,
            size_rationale="normal",
            entry_zone=(75620.0, 76076.0),
            invalidation=RecommendationInvalidation(
                rule="5m close below 75468",
                reason="next major level breach, V failed",
            ),
            targets=[
                RecommendationTarget(price=76456.0, size_pct=30, rationale="tp1"),
                RecommendationTarget(price=76760.0, size_pct=30, rationale="tp2"),
                RecommendationTarget(price=77140.0, size_pct=40, rationale="tp3"),
            ],
            max_hold_hours=4,
        ),
        playbook_check=PlaybookCheck(
            matched_pattern=setup_id,
            hard_ban_check="passed",
            similar_setups_last_30d=[],
            note="placeholder",
        ),
        alternatives_considered=[
            AlternativeAction(action="do_nothing", rationale="fallback", score=0.5)
        ],
        trend_handling=TrendHandling(
            current_trend_strength=0.8,
            if_trend_continues_aligned="Hold.",
            if_trend_reverses_against="De-risk.",
            de_risking_rule="No active de-risking rule.",
        ),
    )


def _match(signal_id: str, action: ActionTaken) -> ActionMatch:
    return ActionMatch(
        signal_id=signal_id,
        matched_at=datetime(2026, 4, 30, 12, 5, tzinfo=timezone.utc),
        action_taken=action,
    )


def _followup(signal_id: str, horizon: FollowupHorizon, pnl: float | None) -> FollowupOutcome:
    return FollowupOutcome(
        signal_id=signal_id,
        horizon=horizon,
        measured_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        price_at_measurement=76320.0,
        price_change_pct_from_signal=0.42,
        nearest_target_hit="tp1",
        invalidation_triggered=False,
        estimated_pnl_usd=pnl,
    )


def test_empty_window_returns_zero_report(tmp_path: Path) -> None:
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 8, tzinfo=timezone.utc)
    report = generate_weekly_report(start, end, tmp_path / "signals.jsonl", tmp_path / "matches.jsonl", tmp_path / "followups.jsonl")
    assert report.total_signals == 0
    assert report.coverage_rate == 0.0
    assert "no signals в window" in report.notes


def test_signals_count_matches_logged(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    ts2 = start + timedelta(days=1)
    log_signal(_signal(_signal_id(ts1, 1), ts1), signals)
    log_signal(_signal(_signal_id(ts2, 2), ts2), signals)
    report = generate_weekly_report(start, end, signals)
    assert report.total_signals == 2


def test_coverage_rate_computed_correctly(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    ts2 = start + timedelta(hours=2)
    id1 = _signal_id(ts1, 1)
    id2 = _signal_id(ts2, 2)
    log_signal(_signal(id1, ts1), signals)
    log_signal(_signal(id2, ts2), signals)
    log_match(_match(id1, ActionTaken.YES_FULL), matches)
    report = generate_weekly_report(start, end, signals, matches)
    assert report.coverage_rate == pytest.approx(0.5)


def test_action_breakdown_aggregates(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    ts2 = start + timedelta(hours=2)
    id1 = _signal_id(ts1, 1)
    id2 = _signal_id(ts2, 2)
    log_signal(_signal(id1, ts1), signals)
    log_signal(_signal(id2, ts2), signals)
    log_match(_match(id1, ActionTaken.YES_FULL), matches)
    report = generate_weekly_report(start, end, signals, matches)
    assert report.overall_action_breakdown == {"yes_full": 1, "unmatched": 1}


def test_setup_breakdown_per_pattern(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    ts2 = start + timedelta(hours=2)
    log_signal(_signal(_signal_id(ts1, 1), ts1, "P-2"), signals)
    log_signal(_signal(_signal_id(ts2, 2), ts2, "P-9"), signals)
    report = generate_weekly_report(start, end, signals)
    by_id = {setup.pattern_id: setup for setup in report.setups}
    assert by_id["P-2"].signals_count == 1
    assert by_id["P-9"].signals_count == 1


def test_edge_computed_when_both_groups_present(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    followups = tmp_path / "followups.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    ts2 = start + timedelta(hours=2)
    id1 = _signal_id(ts1, 1)
    id2 = _signal_id(ts2, 2)
    log_signal(_signal(id1, ts1), signals)
    log_signal(_signal(id2, ts2), signals)
    log_match(_match(id1, ActionTaken.YES_FULL), matches)
    log_match(_match(id2, ActionTaken.NO_IGNORED), matches)
    log_followup(_followup(id1, FollowupHorizon.H24, 100.0), followups)
    log_followup(_followup(id2, FollowupHorizon.H24, 40.0), followups)
    report = generate_weekly_report(start, end, signals, matches, followups)
    setup = report.setups[0]
    assert setup.edge_followed_vs_ignored == pytest.approx(60.0)


def test_edge_none_when_one_group_empty(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    followups = tmp_path / "followups.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    id1 = _signal_id(ts1, 1)
    log_signal(_signal(id1, ts1), signals)
    log_match(_match(id1, ActionTaken.YES_FULL), matches)
    log_followup(_followup(id1, FollowupHorizon.H24, 100.0), followups)
    report = generate_weekly_report(start, end, signals, matches, followups)
    assert report.setups[0].edge_followed_vs_ignored is None


def test_blind_spots_detect_ignored_profitable_signals(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    followups = tmp_path / "followups.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    id1 = _signal_id(ts1, 1)
    log_signal(_signal(id1, ts1), signals)
    log_match(_match(id1, ActionTaken.NO_IGNORED), matches)
    log_followup(_followup(id1, FollowupHorizon.H24, 75.0), followups)
    report = generate_weekly_report(start, end, signals, matches, followups)
    assert report.blind_spots[0]["missed_pnl_usd"] == pytest.approx(75.0)


def test_hits_detect_followed_profitable_signals(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    followups = tmp_path / "followups.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    id1 = _signal_id(ts1, 1)
    log_signal(_signal(id1, ts1), signals)
    log_match(_match(id1, ActionTaken.YES_PARTIAL), matches)
    log_followup(_followup(id1, FollowupHorizon.H24, 55.0), followups)
    report = generate_weekly_report(start, end, signals, matches, followups)
    assert report.hits[0]["realized_pnl_usd"] == pytest.approx(55.0)


def test_window_boundary_inclusive_start_exclusive_end(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    log_signal(_signal("adv_2026-04-30_000000_001", start), signals)
    log_signal(_signal("adv_2026-05-07_000000_002", end), signals)
    report = generate_weekly_report(start, end, signals)
    assert report.total_signals == 1


def test_report_to_markdown_renders_all_sections(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    followups = tmp_path / "followups.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    id1 = _signal_id(ts1, 1)
    log_signal(_signal(id1, ts1), signals)
    log_match(_match(id1, ActionTaken.YES_FULL), matches)
    log_followup(_followup(id1, FollowupHorizon.H24, 50.0), followups)
    text = report_to_markdown(generate_weekly_report(start, end, signals, matches, followups))
    assert "## Overview" in text
    assert "## Action breakdown" in text
    assert "## Per-setup breakdown" in text
    assert "## Hits" in text


def test_low_coverage_note_when_threshold_breached(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    for idx in range(6):
        ts = start + timedelta(hours=idx + 1)
        signal_id = f"adv_2026-04-30_{(idx + 1):02d}0000_{idx+1:03d}"
        log_signal(_signal(signal_id, ts), signals)
    log_match(_match("adv_2026-04-30_010000_001", ActionTaken.YES_FULL), matches)
    report = generate_weekly_report(start, end, signals, matches)
    assert "low coverage rate" in report.notes


def test_period_naive_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        generate_weekly_report(datetime(2026, 4, 30), datetime(2026, 5, 7, tzinfo=timezone.utc), tmp_path / "signals.jsonl")


def test_period_inverted_raises(tmp_path: Path) -> None:
    start = datetime(2026, 5, 7, tzinfo=timezone.utc)
    end = datetime(2026, 4, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        generate_weekly_report(start, end, tmp_path / "signals.jsonl")


def test_report_pure_no_input_mutation(tmp_path: Path) -> None:
    signals = tmp_path / "signals.jsonl"
    matches = tmp_path / "matches.jsonl"
    followups = tmp_path / "followups.jsonl"
    start = datetime(2026, 4, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    ts1 = start + timedelta(hours=1)
    id1 = _signal_id(ts1, 1)
    log_signal(_signal(id1, ts1), signals)
    log_match(_match(id1, ActionTaken.YES_FULL), matches)
    log_followup(_followup(id1, FollowupHorizon.H24, 50.0), followups)
    before = {
        "signals": deepcopy(signals.read_text(encoding="utf-8")),
        "matches": deepcopy(matches.read_text(encoding="utf-8")),
        "followups": deepcopy(followups.read_text(encoding="utf-8")),
    }
    generate_weekly_report(start, end, signals, matches, followups)
    after = {
        "signals": signals.read_text(encoding="utf-8"),
        "matches": matches.read_text(encoding="utf-8"),
        "followups": followups.read_text(encoding="utf-8"),
    }
    assert after == before
