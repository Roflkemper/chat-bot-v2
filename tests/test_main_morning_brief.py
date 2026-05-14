"""Tests for main_morning_brief.py — both --week (legacy) and --roadmap modes."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.main_morning_brief as mb


# ── Roadmap parsing ─────────────────────────────────────────────────────────

_ROADMAP_FIXTURE = """# MULTI-TRACK ROADMAP

### P1 — Actionability layer

**Pain:** Operator needs sizing decisions
**Goal:** forecast → multiplier

| TZ | Description | Status |
|----|-------------|--------|
| TZ-SETUP-DETECTION-WIRE | Connect setup to switcher | DONE |
| TZ-SIZING-MULTIPLIER-ENGINE | 0-2x scaling | OPEN |

### P4 — Dashboard

**Pain:** Operator can't see live state
**Goal:** browser view of forecast

| TZ | Description | Status |
|----|-------------|--------|
| TZ-DASHBOARD-PHASE-1 | Wire forecast | OPEN |

### P6 — Tooling

**Pain:** Cycle automation broken
**Goal:** fix scripts

| TZ | Description | Status |
|----|-------------|--------|
| TZ-MORNING-BRIEF-MULTITRACK-ADAPT | Fix sprint generator | OPEN |
"""


def test_parse_roadmap_finds_three_tracks(tmp_path):
    p = tmp_path / "ROADMAP.md"
    p.write_text(_ROADMAP_FIXTURE, encoding="utf-8")
    parsed = mb._parse_roadmap(p)
    assert set(parsed["tracks"].keys()) == {"P1", "P4", "P6"}
    assert parsed["tracks"]["P1"]["pain"].startswith("Operator needs")
    assert len(parsed["tracks"]["P1"]["tzs"]) == 2


def test_parse_roadmap_extracts_status(tmp_path):
    p = tmp_path / "ROADMAP.md"
    p.write_text(_ROADMAP_FIXTURE, encoding="utf-8")
    parsed = mb._parse_roadmap(p)
    p1_tzs = parsed["tracks"]["P1"]["tzs"]
    assert p1_tzs[0]["status"] == "DONE"
    assert p1_tzs[1]["status"] == "OPEN"


# ── _select_open_tzs prioritization ─────────────────────────────────────────

def test_select_skips_done():
    roadmap = {"tracks": {
        "P1": {"title": "Actionability", "pain": "x", "tzs": [
            {"id": "TZ-A", "desc": "a", "status": "DONE"},
            {"id": "TZ-B", "desc": "b", "status": "OPEN"},
        ]},
    }}
    out = mb._select_open_tzs(roadmap, top_n=3)
    assert len(out) == 1
    assert out[0]["id"] == "TZ-B"


def test_select_respects_track_priority():
    roadmap = {"tracks": {
        "P6": {"title": "Tooling", "pain": "", "tzs": [
            {"id": "TZ-LATE", "desc": "x", "status": "OPEN"},
        ]},
        "P1": {"title": "Actionability", "pain": "", "tzs": [
            {"id": "TZ-EARLY", "desc": "y", "status": "OPEN"},
        ]},
    }}
    out = mb._select_open_tzs(roadmap, top_n=3)
    # P1 (priority 1) should come before P6 (priority 8)
    assert out[0]["id"] == "TZ-EARLY"
    assert out[0]["track"] == "P1"
    assert out[1]["track"] == "P6"


def test_select_caps_at_top_n():
    roadmap = {"tracks": {
        "P1": {"title": "x", "pain": "", "tzs": [
            {"id": f"TZ-{i}", "desc": "", "status": "OPEN"} for i in range(10)
        ]},
    }}
    out = mb._select_open_tzs(roadmap, top_n=3)
    assert len(out) == 3


def test_select_skips_deferred_and_gated():
    roadmap = {"tracks": {
        "P1": {"title": "x", "pain": "", "tzs": [
            {"id": "TZ-D", "desc": "", "status": "DEFERRED"},
            {"id": "TZ-G", "desc": "", "status": "GATED on backtest"},
            {"id": "TZ-OK", "desc": "", "status": "OPEN"},
        ]},
    }}
    out = mb._select_open_tzs(roadmap, top_n=3)
    assert [tz["id"] for tz in out] == ["TZ-OK"]


# ── _highest_priority_track ──────────────────────────────────────────────────

def test_highest_priority_track_skips_all_done():
    roadmap = {"tracks": {
        "P1": {"title": "Actionability", "pain": "p1 pain", "tzs": [
            {"id": "TZ-X", "desc": "", "status": "DONE"},
        ]},
        "P4": {"title": "Dashboard", "pain": "p4 pain", "tzs": [
            {"id": "TZ-Y", "desc": "", "status": "OPEN"},
        ]},
    }}
    track_id, title, pain = mb._highest_priority_track(roadmap)
    assert track_id == "P4"
    assert pain == "p4 pain"


# ── End-to-end sprint generation (roadmap mode) ─────────────────────────────

def test_generate_sprint_from_roadmap_non_empty(tmp_path, monkeypatch):
    p = tmp_path / "ROADMAP.md"
    p.write_text(_ROADMAP_FIXTURE, encoding="utf-8")

    # Mock STATE_CURRENT.md and PENDING_TZ.md to be empty (forces fallback paths)
    fake_state = tmp_path / "STATE.md"
    fake_state.write_text("# empty\n", encoding="utf-8")
    fake_pending = tmp_path / "PENDING.md"
    fake_pending.write_text("# empty\n", encoding="utf-8")
    monkeypatch.setattr(mb, "STATE_FILE", fake_state)
    monkeypatch.setattr(mb, "PENDING_TZ_FILE", fake_pending)

    content = mb.generate_sprint_from_roadmap(p, date(2026, 5, 6), top_n=3)
    assert "[No goal defined" not in content
    assert "_No TZs defined" not in content
    assert "TODAY'S TZs" in content
    assert "TZ-SIZING-MULTIPLIER-ENGINE" in content  # P1 first OPEN TZ
    assert "TZ-DASHBOARD-PHASE-1" in content        # P4 next
    # Goal line mentions P1
    assert "P1" in content
    assert "Actionability" in content


def test_generate_sprint_from_roadmap_includes_blockers(tmp_path, monkeypatch):
    p = tmp_path / "ROADMAP.md"
    p.write_text(_ROADMAP_FIXTURE, encoding="utf-8")

    fake_state = tmp_path / "STATE.md"
    fake_state.write_text(
        "## §5 OPERATOR PENDING ACTIONS\n\n"
        "| Действие | Файл | Оценка |\n"
        "|---|---|---|\n"
        "| Confirm Semant A or B | TZ-INSTOP | 5 мин |\n\n"
        "## §6 next\n",
        encoding="utf-8",
    )
    fake_pending = tmp_path / "PENDING.md"
    fake_pending.write_text("# empty\n", encoding="utf-8")
    monkeypatch.setattr(mb, "STATE_FILE", fake_state)
    monkeypatch.setattr(mb, "PENDING_TZ_FILE", fake_pending)

    content = mb.generate_sprint_from_roadmap(p, date(2026, 5, 6), top_n=3)
    assert "OPERATOR ACTIONS PENDING" in content
    assert "Confirm Semant A or B" in content


def test_generate_sprint_from_roadmap_no_open_tzs(tmp_path, monkeypatch):
    """All-DONE roadmap → graceful empty signal in output."""
    all_done = """### P1 — x

| TZ | Description | Status |
|----|-------------|--------|
| TZ-A | a | DONE |
"""
    p = tmp_path / "ROADMAP.md"
    p.write_text(all_done, encoding="utf-8")
    fake = tmp_path / "empty.md"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(mb, "STATE_FILE", fake)
    monkeypatch.setattr(mb, "PENDING_TZ_FILE", fake)

    content = mb.generate_sprint_from_roadmap(p, date(2026, 5, 6))
    assert "no open TZs found" in content


# ── Backward compat: --week mode unchanged ──────────────────────────────────

_WEEK_FIXTURE = """# WEEK PLAN

**Period:** 2026-05-04 to 2026-05-10
**Primary goal:** Forecast pipeline closure
**Phase focus:** Phase 1

### DAY 1 — Mon 2026-05-05

**Goal:** Wire dashboard

| # | TZ_ID | Description | Est. |
|---|-------|-------------|------|
| 1 | TZ-DASH-1 | Wire forecast | 4h |

**Hard deliverables:**
- [ ] D1: regime renders
- [ ] D2: forecast renders

**Gate:** All 3 D met

**Verify commands:**
python -m pytest tests/

### DAY 2 — Tue 2026-05-06

**Goal:** Setup wire

| # | TZ_ID | Description | Est. |
|---|-------|-------------|------|
| 1 | TZ-SETUP | wire setup | 2h |
"""


def test_week_mode_still_works(tmp_path):
    """Backward compat: --week mode produces identical output as before this TZ."""
    p = tmp_path / "WEEK.md"
    p.write_text(_WEEK_FIXTURE, encoding="utf-8")
    content = mb.generate_sprint(p, date(2026, 5, 5))
    assert "TZ-DASH-1" in content
    assert "Wire dashboard" in content
    assert "regime renders" in content


def test_week_mode_unknown_date_returns_no_tzs_template(tmp_path):
    p = tmp_path / "WEEK.md"
    p.write_text(_WEEK_FIXTURE, encoding="utf-8")
    content = mb.generate_sprint(p, date(2026, 5, 30))  # date not in plan
    # legacy behavior: still produces a template, not an error
    assert "SPRINT —" in content
    assert "TZ-DASH-1" not in content


# ── CLI integration ──────────────────────────────────────────────────────────

def test_cli_requires_one_of_week_or_roadmap(capsys):
    with pytest.raises(SystemExit):
        mb.main([])  # neither --week nor --roadmap


def test_cli_roadmap_mode_writes_file(tmp_path, monkeypatch, capsys):
    p = tmp_path / "ROADMAP.md"
    p.write_text(_ROADMAP_FIXTURE, encoding="utf-8")

    sprint_dir = tmp_path / "SPRINTS"
    fake = tmp_path / "empty.md"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(mb, "SPRINTS_DIR", sprint_dir)
    monkeypatch.setattr(mb, "STATE_FILE", fake)
    monkeypatch.setattr(mb, "PENDING_TZ_FILE", fake)

    rc = mb.main(["--roadmap", str(p), "--day", "2026-05-06"])
    assert rc == 0
    out_path = sprint_dir / "SPRINT_2026-05-06.md"
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "TZ-SIZING-MULTIPLIER-ENGINE" in content
