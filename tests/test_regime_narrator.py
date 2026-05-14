"""Unit tests for services.regime_narrator (no real API calls)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from services.regime_narrator import loop as nar


def test_read_json_missing(tmp_path):
    assert nar._read_json(tmp_path / "nope.json") is None


def test_read_json_valid(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert nar._read_json(p) == {"a": 1}


def test_read_json_corrupt(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("not json", encoding="utf-8")
    assert nar._read_json(p) is None


def test_read_last_jsonl_empty(tmp_path):
    assert nar._read_last_jsonl(tmp_path / "nope.jsonl") == []


def test_read_last_jsonl_returns_n_last(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text("\n".join(json.dumps({"i": i}) for i in range(10)) + "\n",
                 encoding="utf-8")
    out = nar._read_last_jsonl(p, n=3)
    assert len(out) == 3
    assert out[-1]["i"] == 9
    assert out[0]["i"] == 7


def test_recent_setups_filters_window(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    lines = [
        json.dumps({"setup_type": "old", "pair": "BTC",
                    "detected_at": (now - timedelta(hours=10)).isoformat(),
                    "strength": 5, "confidence_pct": 70}),
        json.dumps({"setup_type": "fresh", "pair": "BTC",
                    "detected_at": (now - timedelta(hours=2)).isoformat(),
                    "strength": 9, "confidence_pct": 80}),
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(nar, "SETUPS_PATH", p)
    out = nar._recent_setups(window_min=360)
    assert len(out) == 1
    assert out[0]["setup_type"] == "fresh"


def test_dl_event_counts(monkeypatch, tmp_path):
    p = tmp_path / "decisions.jsonl"
    now = datetime.now(timezone.utc)
    lines = [
        json.dumps({"rule_id": "M-3", "severity": "PRIMARY",
                    "ts": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}),
        json.dumps({"rule_id": "M-3", "severity": "PRIMARY",
                    "ts": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}),
        json.dumps({"rule_id": "R-2", "severity": "INFO",
                    "ts": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}),  # not PRIMARY
        json.dumps({"rule_id": "P-1", "severity": "PRIMARY",
                    "ts": (now - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")}),  # too old
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(nar, "DL_LOG_PATH", p)
    counts = nar._dl_event_counts(window_min=360)
    assert counts == {"M-3": 2}


def test_build_context_minimal(monkeypatch, tmp_path):
    """All paths point to non-existent files — context should still build with Nones."""
    monkeypatch.setattr(nar, "REGIME_A_PATH", tmp_path / "no.json")
    monkeypatch.setattr(nar, "REGIME_B_PATH", tmp_path / "no.jsonl")
    monkeypatch.setattr(nar, "DERIV_LIVE_PATH", tmp_path / "no.json")
    monkeypatch.setattr(nar, "SETUPS_PATH", tmp_path / "no.jsonl")
    monkeypatch.setattr(nar, "DL_LOG_PATH", tmp_path / "no.jsonl")
    # Stub _btc_6h_summary so we don't hit real network
    monkeypatch.setattr(nar, "_btc_6h_summary", lambda: {})

    ctx = nar._build_context()
    assert "now_utc" in ctx
    assert ctx["regime_a"] is None
    assert ctx["regime_b"] is None
    assert ctx["recent_setups_top5"] == []
    assert ctx["dl_primary_events_6h"] == {}


def test_build_prompt_includes_json():
    ctx = {"now_utc": "2026-05-09T12:00:00Z", "regime_a": "RANGE"}
    prompt = nar._build_prompt(ctx)
    assert "Снимок рынка" in prompt
    assert "RANGE" in prompt
    assert "regime_a" in prompt


def test_call_haiku_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert nar._call_haiku("system", "user") is None


def test_audit_append_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(nar, "AUDIT_PATH", tmp_path / "audit.jsonl")
    nar._audit_append({"a": 1})
    nar._audit_append({"b": 2})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}


def test_constants_safe():
    """Sanity guards on constants to prevent cost surprise."""
    assert nar.MIN_INTERVAL_SEC >= 1800   # at least 30 min between calls
    assert nar.MAX_TOKENS <= 1000          # output budget
    assert nar.DEFAULT_INTERVAL_SEC >= nar.MIN_INTERVAL_SEC
