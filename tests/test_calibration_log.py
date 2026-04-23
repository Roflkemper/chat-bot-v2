from __future__ import annotations

from datetime import date, datetime, timezone
import json

from core.orchestrator.calibration_log import CalibrationLog
from utils.safe_io import atomic_append_line


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def test_atomic_append_line_appends_jsonl_rows(tmp_path):
    path = tmp_path / "state" / "calibration" / "2026-04-18.jsonl"
    atomic_append_line(str(path), '{"a":1}')
    atomic_append_line(str(path), '{"b":2}')
    assert path.read_text(encoding="utf-8").splitlines() == ['{"a":1}', '{"b":2}']


def test_calibration_log_writes_and_reads_events(tmp_path, monkeypatch):
    monkeypatch.setattr(CalibrationLog, "_instance", None)
    log = CalibrationLog.instance(tmp_path / "state" / "calibration")
    log.log_action_change(
        category_key="btc_short",
        from_action="RUN",
        to_action="PAUSE",
        regime="CASCADE_UP",
        modifiers=["VOLATILITY_SPIKE"],
        reason_ru="test",
        reason_en="TEST",
        affected_bots=["btc_short_l1"],
    )
    events = log.read_events(_utc_today())
    assert len(events) == 1
    assert events[0]["event_type"] == "ACTION_CHANGE"
    assert events[0]["affected_bots"] == ["btc_short_l1"]


def test_calibration_log_summary_groups_events(tmp_path, monkeypatch):
    monkeypatch.setattr(CalibrationLog, "_instance", None)
    log = CalibrationLog.instance(tmp_path / "state" / "calibration")
    day = date(2026, 4, 18)
    path = tmp_path / "state" / "calibration" / f"{day.isoformat()}.jsonl"
    rows = [
        {
            "ts": "2026-04-18T08:00:00+00:00",
            "event_type": "REGIME_SHIFT",
            "regime": "RANGE",
            "modifiers": [],
            "reason_ru": "shift",
            "triggered_by": "AUTO",
        },
        {
            "ts": "2026-04-18T08:10:00+00:00",
            "event_type": "ACTION_CHANGE",
            "category_key": "btc_long",
            "from_action": "RUN",
            "to_action": "PAUSE",
            "regime": "TREND_DOWN",
            "modifiers": [],
            "reason_ru": "pause",
            "triggered_by": "AUTO",
            "affected_bots": ["btc_long_l1"],
        },
        {
            "ts": "2026-04-18T08:20:00+00:00",
            "event_type": "MANUAL_COMMAND",
            "category_key": "btc_long",
            "to_action": "RESUME",
            "regime": "TREND_DOWN",
            "modifiers": [],
            "reason_ru": "Оператор: /resume btc_long",
            "triggered_by": "MANUAL",
        },
    ]
    for row in rows:
        atomic_append_line(str(path), json.dumps(row, ensure_ascii=False))
    summary = log.summarize_day(day)
    assert summary["total_events"] == 3
    assert summary["event_counts"]["ACTION_CHANGE"] == 1
    assert summary["categories_changed"] == ["btc_long"]
    assert summary["bots_touched"] == ["btc_long_l1"]
