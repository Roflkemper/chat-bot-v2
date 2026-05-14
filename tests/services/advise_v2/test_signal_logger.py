from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.advise_v2 import SignalEnvelope
from services.advise_v2.signal_logger import (
    count_signals,
    iter_null_signals,
    iter_signals,
    log_null_signal,
    log_signal,
    signals_by_pattern,
)


def _envelope_payload(
    signal_id: str = "adv_2026-04-29_143000_001",
    setup_id: str = "P-7",
    ts: str | None = None,
) -> dict:
    # derive ts from signal_id so the model_validator passes
    if ts is None:
        import re
        m = re.match(r"adv_(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})_\d{3}", signal_id)
        if m:
            date, hh, mm, ss = m.groups()
            ts = f"{date}T{hh}:{mm}:{ss}+00:00"
        else:
            ts = "2026-04-29T14:30:00+00:00"
    return {
        "signal_id": signal_id,
        "ts": ts,
        "setup_id": setup_id,
        "setup_name": "Liquidity reclaim",
        "market_context": {
            "price_btc": 76200.0,
            "regime_label": "consolidation",
            "regime_modifiers": [],
            "rsi_1h": 55.0,
            "rsi_5m": None,
            "price_change_5m_30bars_pct": -0.3,
            "price_change_1h_pct": 1.1,
            "nearest_liq_below": None,
            "nearest_liq_above": None,
        },
        "current_exposure": {
            "net_btc": 0.0,
            "shorts_btc": 0.0,
            "longs_btc": 0.0,
            "free_margin_pct": 50.0,
            "available_usd": 2000.0,
            "margin_coef_pct": 15.0,
        },
        "recommendation": {
            "primary_action": "increase_long_manual",
            "size_btc_equivalent": 0.05,
            "size_usd_inverse": None,
            "size_rationale": "Small add into support.",
            "entry_zone": [76000.0, 76250.0],
            "invalidation": {"rule": "1h close below 75800", "reason": "Support sweep failed."},
            "targets": [
                {"price": 76600.0, "size_pct": 50, "rationale": "TP1"},
                {"price": 77000.0, "size_pct": 50, "rationale": "TP2"},
            ],
            "max_hold_hours": 8,
        },
        "playbook_check": {
            "matched_pattern": setup_id,
            "hard_ban_check": "passed",
            "similar_setups_last_30d": [],
            "note": None,
        },
        "alternatives_considered": [
            {"action": "do_nothing", "rationale": "Wait for confirmation.", "score": 0.4}
        ],
        "trend_handling": {
            "current_trend_strength": 0.55,
            "if_trend_continues_aligned": "Trail after TP1.",
            "if_trend_reverses_against": "Reduce 50% on failed reclaim.",
            "de_risking_rule": "Flat before macro release.",
        },
    }


@pytest.fixture
def signals_file(tmp_path: Path) -> Path:
    return tmp_path / "signals.jsonl"


@pytest.fixture
def null_file(tmp_path: Path) -> Path:
    return tmp_path / "null_signals.jsonl"


@pytest.fixture
def envelope() -> SignalEnvelope:
    return SignalEnvelope.model_validate(_envelope_payload())


# --- log_signal ---


def test_log_signal_creates_file(signals_file: Path, envelope: SignalEnvelope) -> None:
    assert not signals_file.exists()
    log_signal(envelope, path=signals_file)
    assert signals_file.exists()


def test_log_signal_writes_valid_json(signals_file: Path, envelope: SignalEnvelope) -> None:
    log_signal(envelope, path=signals_file)
    lines = signals_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["signal_id"] == envelope.signal_id


def test_log_signal_appends(signals_file: Path, envelope: SignalEnvelope) -> None:
    log_signal(envelope, path=signals_file)
    log_signal(envelope, path=signals_file)
    lines = signals_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_log_signal_accepts_str_path(tmp_path: Path, envelope: SignalEnvelope) -> None:
    p = tmp_path / "s.jsonl"
    log_signal(envelope, path=str(p))
    assert p.exists()


# --- log_null_signal ---


def test_log_null_signal_creates_file(null_file: Path) -> None:
    assert not null_file.exists()
    log_null_signal("no setup matched", path=null_file)
    assert null_file.exists()


def test_log_null_signal_contains_reason(null_file: Path) -> None:
    log_null_signal("ban filter blocked", path=null_file)
    record = json.loads(null_file.read_text(encoding="utf-8").strip())
    assert record["reason"] == "ban filter blocked"


def test_log_null_signal_context_stored(null_file: Path) -> None:
    log_null_signal("low confidence", context={"confidence": 0.3}, path=null_file)
    record = json.loads(null_file.read_text(encoding="utf-8").strip())
    assert record["context"]["confidence"] == 0.3


def test_log_null_signal_has_ts(null_file: Path) -> None:
    log_null_signal("test", path=null_file)
    record = json.loads(null_file.read_text(encoding="utf-8").strip())
    assert "ts" in record and record["ts"]


def test_log_null_signal_no_context(null_file: Path) -> None:
    log_null_signal("empty context", path=null_file)
    record = json.loads(null_file.read_text(encoding="utf-8").strip())
    assert record["context"] is None


# --- iter_signals ---


def test_iter_signals_empty_file(signals_file: Path) -> None:
    signals_file.write_text("", encoding="utf-8")
    assert list(iter_signals(signals_file)) == []


def test_iter_signals_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"
    assert list(iter_signals(missing)) == []


def test_iter_signals_yields_envelope(signals_file: Path, envelope: SignalEnvelope) -> None:
    log_signal(envelope, path=signals_file)
    results = list(iter_signals(signals_file))
    assert len(results) == 1
    assert isinstance(results[0], SignalEnvelope)
    assert results[0].signal_id == envelope.signal_id


def test_iter_signals_skips_malformed(signals_file: Path, envelope: SignalEnvelope) -> None:
    log_signal(envelope, path=signals_file)
    with signals_file.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")
    results = list(iter_signals(signals_file))
    assert len(results) == 1


def test_iter_signals_multiple(signals_file: Path) -> None:
    ids = [
        "adv_2026-04-29_143000_001",
        "adv_2026-04-29_143100_002",
        "adv_2026-04-29_143200_003",
    ]
    for sid in ids:
        e = SignalEnvelope.model_validate(_envelope_payload(signal_id=sid))
        log_signal(e, path=signals_file)
    results = list(iter_signals(signals_file))
    assert len(results) == 3
    assert [r.signal_id for r in results] == ids


# --- iter_null_signals ---


def test_iter_null_signals_missing_file(tmp_path: Path) -> None:
    assert list(iter_null_signals(tmp_path / "nope.jsonl")) == []


def test_iter_null_signals_yields_dicts(null_file: Path) -> None:
    log_null_signal("r1", path=null_file)
    log_null_signal("r2", path=null_file)
    results = list(iter_null_signals(null_file))
    assert len(results) == 2
    assert results[0]["reason"] == "r1"
    assert results[1]["reason"] == "r2"


# --- count_signals ---


def test_count_signals_zero_missing(tmp_path: Path) -> None:
    assert count_signals(tmp_path / "nope.jsonl") == 0


def test_count_signals_correct(signals_file: Path, envelope: SignalEnvelope) -> None:
    for _ in range(5):
        log_signal(envelope, path=signals_file)
    assert count_signals(signals_file) == 5


def test_count_signals_excludes_malformed(signals_file: Path, envelope: SignalEnvelope) -> None:
    log_signal(envelope, path=signals_file)
    with signals_file.open("a", encoding="utf-8") as fh:
        fh.write("garbage\n")
    assert count_signals(signals_file) == 1


# --- signals_by_pattern ---


def test_signals_by_pattern_filters(signals_file: Path) -> None:
    for setup_id, sig_id in [
        ("P-2", "adv_2026-04-29_143000_001"),
        ("P-7", "adv_2026-04-29_143100_002"),
        ("P-2", "adv_2026-04-29_143200_003"),
    ]:
        e = SignalEnvelope.model_validate(_envelope_payload(signal_id=sig_id, setup_id=setup_id))
        e2 = e.model_copy(update={"playbook_check": e.playbook_check.model_copy(
            update={"matched_pattern": setup_id}
        )})
        log_signal(e2, path=signals_file)
    p2 = signals_by_pattern("P-2", path=signals_file)
    assert len(p2) == 2
    assert all(s.setup_id == "P-2" for s in p2)


def test_signals_by_pattern_empty_result(signals_file: Path, envelope: SignalEnvelope) -> None:
    log_signal(envelope, path=signals_file)
    assert signals_by_pattern("P-99", path=signals_file) == []


def test_signals_by_pattern_missing_file(tmp_path: Path) -> None:
    assert signals_by_pattern("P-2", path=tmp_path / "nope.jsonl") == []
