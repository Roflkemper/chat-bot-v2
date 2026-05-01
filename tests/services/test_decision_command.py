"""Tests for services/decision_command.py — TZ-DECISION-COMMAND-TG."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import services.decision_command as dc


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_record(**overrides) -> dict:
    base = {
        "id": "dec_2026-05-01T14-00-00",
        "ts": "2026-05-01T14:00:00Z",
        "action": "close_long",
        "notes": "test note",
        "price_btc": 78000.0,
        "price_eth": None,
        "price_xrp": None,
        "session_active": "ny_am",
        "dist_to_pdh_pct": 1.2,
        "dist_to_nearest_unmitigated_high_pct": 0.5,
        "dist_to_nearest_unmitigated_low_pct": -1.3,
        "bots_state": {"bot1": {"alias": "TEST_1", "unrealized_pnl": -23.5}},
        "total_unrealized_pnl": -23.5,
        "total_realized_pnl_24h": None,
        "related_param_changes": [],
    }
    base.update(overrides)
    return base


# ── test_decision_command_basic ───────────────────────────────────────────────

def test_decision_command_basic(tmp_path):
    """'/decision close_long test note' creates a record in JSONL."""
    jsonl_path = tmp_path / "manual_decisions.jsonl"

    with (
        patch.object(dc, "_DECISIONS_JSONL", jsonl_path),
        patch.object(dc, "_JOURNAL_DIR", tmp_path),
        patch("services.decision_command._load_prices", return_value={"price_btc": 78000.0, "price_eth": None, "price_xrp": None}),
        patch("services.decision_command._load_ict_context", return_value={"session_active": "ny_am"}),
        patch("services.decision_command._load_bots_state", return_value=({}, None, None)),
        patch("services.decision_command._load_recent_param_events", return_value=[]),
    ):
        action, notes, warning = dc.parse_decision_command("/decision close_long test note")
        assert action == "close_long"
        assert notes == "test note"
        assert warning is None

        record = dc.build_decision_record(action, notes)
        dc.append_decision(record)

    assert jsonl_path.exists()
    records = [json.loads(l) for l in jsonl_path.read_text().splitlines() if l.strip()]
    assert len(records) == 1
    assert records[0]["action"] == "close_long"
    assert records[0]["notes"] == "test note"


# ── test_decision_market_snapshot_attached ────────────────────────────────────

def test_decision_market_snapshot_attached():
    """Record contains price_btc and session_active from market snapshot."""
    with (
        patch("services.decision_command._load_prices", return_value={"price_btc": 77500.0, "price_eth": None, "price_xrp": None}),
        patch("services.decision_command._load_ict_context", return_value={
            "session_active": "london",
            "dist_to_pdh_pct": 0.8,
            "dist_to_nearest_unmitigated_high_pct": 1.1,
            "dist_to_nearest_unmitigated_low_pct": -2.0,
        }),
        patch("services.decision_command._load_bots_state", return_value=({}, None, None)),
        patch("services.decision_command._load_recent_param_events", return_value=[]),
    ):
        record = dc.build_decision_record("pause", "жду откат")

    assert record["price_btc"] == 77500.0
    assert record["session_active"] == "london"
    assert "dist_to_pdh_pct" in record
    assert record["action"] == "pause"
    assert record["notes"] == "жду откат"


# ── test_decision_no_overwrite ────────────────────────────────────────────────

def test_decision_no_overwrite(tmp_path):
    """Two /decision calls → two appended lines, file not overwritten."""
    jsonl_path = tmp_path / "manual_decisions.jsonl"

    with patch.object(dc, "_DECISIONS_JSONL", jsonl_path), patch.object(dc, "_JOURNAL_DIR", tmp_path):
        dc.append_decision(_make_record(id="dec_1", action="pause"))
        dc.append_decision(_make_record(id="dec_2", action="resume"))

    lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    rec1, rec2 = json.loads(lines[0]), json.loads(lines[1])
    assert rec1["id"] == "dec_1"
    assert rec2["id"] == "dec_2"


# ── test_decision_max_notes_length ────────────────────────────────────────────

def test_decision_max_notes_length():
    """Notes >500 chars → truncated to 500 with truncation warning returned."""
    long_notes = "x" * 600
    cmd = f"/decision manual {long_notes}"
    action, notes, warning = dc.parse_decision_command(cmd)
    assert action == "manual"
    assert len(notes) == dc.MAX_NOTES
    assert warning is not None
    assert "500" in warning


# ── test_decision_action_normalization ────────────────────────────────────────

def test_decision_action_normalization():
    """'/decision Close_Long' → action='close_long' (lowercase)."""
    action, notes, warning = dc.parse_decision_command("/decision Close_Long Some reasoning")
    assert action == "close_long"
    assert notes == "Some reasoning"
    assert warning is None

    # All-caps (happens when original_command is uppercased fallback)
    action2, notes2, _ = dc.parse_decision_command("/DECISION CLOSE_LONG TEST")
    assert action2 == "close_long"
    assert notes2 == "TEST"
