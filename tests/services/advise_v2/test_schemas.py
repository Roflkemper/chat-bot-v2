from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest
from pydantic import ValidationError

from services.advise_v2 import SignalEnvelope


def _payload() -> dict:
    return {
        "signal_id": "adv_2026-04-29_143000_001",
        "ts": "2026-04-29T14:30:45+02:00",
        "setup_id": "P-7",
        "setup_name": "Liquidity reclaim",
        "market_context": {
            "price_btc": 76200.0,
            "regime_label": "consolidation",
            "regime_modifiers": ["liquidity_sweep", "session_open"],
            "rsi_1h": 55.0,
            "rsi_5m": None,
            "price_change_5m_30bars_pct": -0.3,
            "price_change_1h_pct": 1.1,
            "nearest_liq_below": None,
            "nearest_liq_above": None,
        },
        "current_exposure": {
            "net_btc": 0.1,
            "shorts_btc": -0.2,
            "longs_btc": 0.3,
            "free_margin_pct": 42.0,
            "available_usd": 1800.0,
            "margin_coef_pct": 15.0,
        },
        "recommendation": {
            "primary_action": "increase_long_manual",
            "size_btc_equivalent": 0.05,
            "size_usd_inverse": None,
            "size_rationale": "Small add into support cluster.",
            "entry_zone": [76000.0, 76250.0],
            "invalidation": {
                "rule": "1h close below 75800",
                "reason": "Support sweep failed.",
            },
            "targets": [
                {"price": 76600.0, "size_pct": 40, "rationale": "TP1"},
                {"price": 77000.0, "size_pct": 60, "rationale": "TP2"},
            ],
            "max_hold_hours": 8,
        },
        "playbook_check": {
            "matched_pattern": "P-7",
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


def test_signal_envelope_valid_minimal():
    model = SignalEnvelope.model_validate(_payload())
    dumped = model.model_dump()
    assert dumped["setup_id"] == "P-7"


def test_signal_envelope_valid_full():
    payload = _payload()
    payload["market_context"]["rsi_5m"] = 48.5
    payload["market_context"]["nearest_liq_below"] = {"price": 75900.0, "size_usd": 500000.0}
    payload["market_context"]["nearest_liq_above"] = {"price": 76800.0, "size_usd": 750000.0}
    payload["playbook_check"]["similar_setups_last_30d"] = [
        {"date": "2026-04-10", "outcome": "tp1_hit", "realized_usd": 120.0}
    ]
    payload["playbook_check"]["note"] = "Recent sample is constructive."
    payload["recommendation"]["size_usd_inverse"] = 3800.0
    model = SignalEnvelope.model_validate(payload)
    assert model.market_context.nearest_liq_above is not None


def test_signal_envelope_extra_field_rejected():
    payload = _payload()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


def test_signal_id_format_invalid():
    payload = _payload()
    payload["signal_id"] = "bad_id"
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


def test_targets_size_pct_must_sum_to_100():
    payload = _payload()
    payload["recommendation"]["targets"][1]["size_pct"] = 50
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


def test_entry_zone_invalid_order():
    payload = _payload()
    payload["recommendation"]["entry_zone"] = [76300.0, 76200.0]
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


def test_market_context_invalid_regime():
    payload = _payload()
    payload["market_context"]["regime_label"] = "sideways"
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


@pytest.mark.parametrize("bad_rsi", [101, -1])
def test_rsi_out_of_range(bad_rsi: int):
    payload = _payload()
    payload["market_context"]["rsi_1h"] = bad_rsi
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


def test_current_exposure_signs():
    payload = _payload()
    payload["current_exposure"]["shorts_btc"] = 0.2
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


def test_recommendation_action_unknown():
    payload = _payload()
    payload["recommendation"]["primary_action"] = "flip_everything"
    with pytest.raises(ValidationError):
        SignalEnvelope.model_validate(payload)


def test_json_schema_generation():
    schema = SignalEnvelope.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "signal_id" in schema["properties"]
    assert "required" in schema


def test_round_trip_serialize_deserialize():
    model = SignalEnvelope.model_validate(_payload())
    raw = model.model_dump_json()
    restored = SignalEnvelope.model_validate_json(raw)
    assert restored == model
