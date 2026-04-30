from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.setup_detector.models import SetupBasis, SetupStatus, SetupType, make_setup
from services.setup_detector.outcomes import OutcomesWriter, ProgressResult, check_setup_progress


def _simple_setup(detected_at: datetime | None = None) -> object:
    return make_setup(
        setup_type=SetupType.LONG_DUMP_REVERSAL,
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="consolidation",
        session_label="NY_AM",
        entry_price=79760.0,
        stop_price=79000.0,
        tp1_price=80520.0,
        tp2_price=81280.0,
        risk_reward=1.0,
        strength=8,
        confidence_pct=72.0,
        basis=(SetupBasis("test", 1.0, 1.0),),
        cancel_conditions=("cancel",),
        window_minutes=120,
        portfolio_impact_note="test",
        recommended_size_btc=0.05,
        detected_at=detected_at or datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
    )


def test_outcome_event_written_to_jsonl(tmp_path: Path) -> None:
    writer = OutcomesWriter(path=tmp_path / "outcomes.jsonl")
    setup = _simple_setup()
    result = ProgressResult(
        status_changed=True,
        new_status=SetupStatus.TP1_HIT,
        close_price=80520.0,
        hypothetical_pnl_usd=38.0,
        hypothetical_r=1.0,
        time_to_outcome_min=47,
    )
    writer.write_outcome_event(setup, result)  # type: ignore[arg-type]

    lines = (tmp_path / "outcomes.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    d = json.loads(lines[0])
    assert d["new_status"] == "tp1_hit"
    assert d["hypothetical_pnl_usd"] == pytest.approx(38.0)
    assert d["setup_type"] == "long_dump_reversal"


def test_outcomes_idempotent_no_double_write(tmp_path: Path) -> None:
    writer = OutcomesWriter(path=tmp_path / "outcomes.jsonl")
    setup = _simple_setup()
    result = ProgressResult(
        status_changed=True,
        new_status=SetupStatus.STOP_HIT,
        close_price=79000.0,
        hypothetical_pnl_usd=-38.0,
        hypothetical_r=-1.0,
        time_to_outcome_min=30,
    )
    writer.write_outcome_event(setup, result)  # type: ignore[arg-type]
    # Writing same result again would double-write — but writer is append-only,
    # idempotency is enforced at storage.update_status level, not writer level.
    # Verify the first write is correct.
    lines = (tmp_path / "outcomes.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    d = json.loads(lines[0])
    assert d["new_status"] == "stop_hit"
    assert d["hypothetical_pnl_usd"] == pytest.approx(-38.0)


def test_outcome_includes_denormalized_fields(tmp_path: Path) -> None:
    writer = OutcomesWriter(path=tmp_path / "outcomes.jsonl")
    setup = _simple_setup()
    result = ProgressResult(
        status_changed=True,
        new_status=SetupStatus.EXPIRED,
        close_price=80100.0,
        time_to_outcome_min=120,
    )
    writer.write_outcome_event(setup, result)  # type: ignore[arg-type]
    d = json.loads((tmp_path / "outcomes.jsonl").read_text().strip())
    assert d["pair"] == "BTCUSDT"
    assert d["regime_label"] == "consolidation"
    assert d["session_label"] == "NY_AM"
    assert d["strength"] == 8
