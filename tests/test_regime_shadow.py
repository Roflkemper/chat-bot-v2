"""Unit tests for services.regime_shadow.loop."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from services.regime_shadow import loop as shadow


def test_read_prod_regime_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "PROD_REGIME_PATH", tmp_path / "missing.json")
    assert shadow._read_prod_regime() is None


def test_read_prod_regime_normalizes_classifier_a(monkeypatch, tmp_path):
    p = tmp_path / "regime.json"
    p.write_text(json.dumps({
        "symbols": {
            "BTCUSDT": {
                "current_primary": "RANGE",
                "active_modifiers": {"POST_FUNDING_HOUR": {"activated_at": "x"}},
                "regime_age_bars": 12,
            }
        }
    }), encoding="utf-8")
    monkeypatch.setattr(shadow, "PROD_REGIME_PATH", p)
    out = shadow._read_prod_regime()
    assert out is not None
    assert out["primary"] == "RANGE"
    assert out["regime_label"] == "RANGE"
    assert out["modifiers"] == ["POST_FUNDING_HOUR"]
    assert out["regime_age_bars"] == 12


def test_read_prod_regime_no_btc_section(monkeypatch, tmp_path):
    p = tmp_path / "regime.json"
    p.write_text(json.dumps({"symbols": {"ETHUSDT": {"current_primary": "RANGE"}}}),
                 encoding="utf-8")
    monkeypatch.setattr(shadow, "PROD_REGIME_PATH", p)
    assert shadow._read_prod_regime() is None


def test_verdicts_agree_range_match():
    assert shadow._verdicts_agree("RANGE", {"regime_label": "RANGE"}) is True
    assert shadow._verdicts_agree("RANGE", {"regime_label": "COMPRESSION"}) is True


def test_verdicts_agree_range_mismatch():
    assert shadow._verdicts_agree("RANGE", {"regime_label": "TREND_UP"}) is False


def test_verdicts_agree_trend_match():
    assert shadow._verdicts_agree("TREND", {"regime_label": "TREND_DOWN"}) is True
    assert shadow._verdicts_agree("TREND", {"regime_label": "CASCADE_UP"}) is True


def test_verdicts_agree_ambiguous_returns_none():
    assert shadow._verdicts_agree("AMBIGUOUS", {"regime_label": "RANGE"}) is None
    assert shadow._verdicts_agree("ERROR", {"regime_label": "RANGE"}) is None


def test_classify_b_handles_empty_data(monkeypatch):
    df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    verdict, feats = shadow._classify_b(df)
    assert verdict == "ERROR"
    assert feats == {}


def test_journal_append_writes_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "JOURNAL_PATH", tmp_path / "j.jsonl")
    shadow._journal_append({"a": 1})
    shadow._journal_append({"b": 2})
    lines = (tmp_path / "j.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}
