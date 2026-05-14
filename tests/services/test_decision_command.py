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


# ── test_decision_filters_operator_bots ──────────────────────────────────────

def test_decision_filters_operator_bots(tmp_path):
    """_load_bots_state() only returns bots listed in bot_aliases.json, not all 500+ public bots."""
    import json, pandas as pd
    from datetime import timezone

    # Fake snapshots.csv with 3 rows: 2 operator bots + 1 public bot
    rows = [
        {"ts_utc": "2026-05-01T10:00:00Z", "bot_id": 111.0, "bot_name": "OP_BOT_1", "alias": "OP_1",
         "status": "2", "position": "-0.5", "profit": 100.0, "current_profit": 50.0},
        {"ts_utc": "2026-05-01T10:00:00Z", "bot_id": 222.0, "bot_name": "OP_BOT_2", "alias": "OP_2",
         "status": "2", "position": "0.3", "profit": 200.0, "current_profit": -30.0},
        {"ts_utc": "2026-05-01T10:00:00Z", "bot_id": 999.0, "bot_name": "PUBLIC_BOT", "alias": "PUB",
         "status": "2", "position": "0.0", "profit": 999999.0, "current_profit": 888888.0},
    ]
    csv_path = tmp_path / "snapshots.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    # bot_aliases.json has only operator bots 111 + 222
    aliases_path = tmp_path / "bot_aliases.json"
    aliases_path.write_text(json.dumps({"111": "OP_1", "222": "OP_2"}), encoding="utf-8")

    with (
        patch.object(dc, "_SNAPSHOTS_CSV", csv_path),
        patch.object(dc, "_BOT_ALIASES_JSON", aliases_path),
    ):
        bots, total_upl, _ = dc._load_bots_state()

    assert "999" not in bots, "Public bot 999 should be filtered out"
    assert len(bots) == 2
    assert total_upl is not None
    assert abs(total_upl - 20.0) < 0.01, f"Expected 50 + (-30) = 20, got {total_upl}"


# ── test_ict_lookup_fallback_on_stale_parquet ─────────────────────────────────

def test_ict_lookup_fallback_on_stale_parquet(tmp_path):
    """When ICT parquet is stale (>5 min gap), _load_ict_context returns a valid session label."""
    from datetime import datetime, timezone

    # Point to non-existent parquet (simulates missing/stale data)
    with patch.object(dc, "_ICT_PARQUET", tmp_path / "nonexistent.parquet"):
        ts = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)  # 10:30 NYC EDT = ny_am
        ctx = dc._load_ict_context(ts)

    assert "session_active" in ctx
    session = ctx["session_active"]
    assert session in ("asia", "london", "ny_am", "ny_lunch", "ny_pm", "dead"), (
        f"Expected valid session label, got {session!r}"
    )
    assert session != "", "session_active must not be empty string"
