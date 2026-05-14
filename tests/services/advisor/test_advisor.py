"""Tests for services.advisor.advisor."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.advisor import build_advisor_text
from services.advisor.advisor import (
    RECONCILED_GROUP,
    _funding_percentile_label,
    _project_3state,
)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_project_3state() -> None:
    assert _project_3state("RANGE") == "RANGE"
    assert _project_3state("COMPRESSION") == "RANGE"
    assert _project_3state("TREND_UP") == "MARKUP"
    assert _project_3state("CASCADE_DOWN") == "MARKDOWN"
    assert _project_3state(None) == "?"


def test_funding_label_deeply_negative() -> None:
    label = _funding_percentile_label(-8.2e-5)
    assert "deeply" in label.lower()


def test_funding_label_positive() -> None:
    label = _funding_percentile_label(7e-5)
    assert "positive" in label.lower()


def test_funding_label_none() -> None:
    assert _funding_percentile_label(None) == "n/a"


def test_advisor_returns_string_with_required_sections(tmp_path: Path) -> None:
    state_latest = tmp_path / "state_latest.json"
    regime_state = tmp_path / "regime_state.json"
    _write(state_latest, {
        "ts": "2026-05-06T20:00:00Z",
        "exposure": {
            "shorts_btc": -1.434, "longs_btc": 0.0, "net_btc": -1.434,
            "nearest_short_liq": {"price": 96400, "distance_pct": 18.0},
        },
        "margin": {
            "coefficient": 0.97,
            "available_margin_usd": 20434.0,
            "distance_to_liquidation_pct": 18.0,
            "source": "telegram_operator",
            "updated_at": "2026-05-06T19:00:00Z",
            "data_age_minutes": 60.0,
        },
        "bots": [{"name": "TestBot", "live": {"position": -0.5, "position_unit": "BTC", "unrealized_usd": -100, "mark": 81500}}],
        "current_price_btc": 81500,
    })
    _write(regime_state, {
        "symbols": {
            "BTCUSDT": {
                "current_primary": "RANGE",
                "primary_since": "2026-05-06T15:00:00Z",
                "regime_age_bars": 5,
                "pending_primary": None,
                "hysteresis_counter": 0,
                "active_modifiers": {"WEEKEND_LOW_VOL": {}},
            }
        }
    })

    text = build_advisor_text(
        state_latest_path=state_latest,
        regime_path=regime_state,
        now=datetime(2026, 5, 6, 20, 0, tzinfo=timezone.utc),
    )

    # Required sections present
    assert "ADVISOR v0.1" in text
    assert "РЫНОК" in text
    assert "ПОЗИЦИЯ" in text
    assert "ИСТОРИЧЕСКИЙ КОНТЕКСТ" in text
    assert "БОТЫ" in text
    assert "WATCH-LIST" in text
    assert "Foundation gaps" in text
    # Regime classification
    assert "RANGE" in text
    # Reconciled foundation numbers visible
    assert str(RECONCILED_GROUP["n"]) in text
    assert "46.2" in text
    assert "53.8" in text
    # Mark price formatted
    assert "81,500" in text


def test_advisor_handles_missing_regime_file(tmp_path: Path) -> None:
    state_latest = tmp_path / "state.json"
    _write(state_latest, {"current_price_btc": 80000, "exposure": {}})
    text = build_advisor_text(
        state_latest_path=state_latest,
        regime_path=tmp_path / "missing.json",
        now=datetime(2026, 5, 6, 20, 0, tzinfo=timezone.utc),
    )
    assert "ADVISOR v0.1" in text
    assert "нет данных" in text or "?" in text


def test_advisor_handles_missing_state_file(tmp_path: Path) -> None:
    text = build_advisor_text(
        state_latest_path=tmp_path / "missing.json",
        regime_path=tmp_path / "missing2.json",
        now=datetime(2026, 5, 6, 20, 0, tzinfo=timezone.utc),
    )
    assert "ADVISOR v0.1" in text


def test_advisor_flags_stale_margin_data(tmp_path: Path) -> None:
    state_latest = tmp_path / "state.json"
    _write(state_latest, {
        "exposure": {"shorts_btc": -1.4, "net_btc": -1.4},
        "margin": {
            "coefficient": 0.97,
            "available_margin_usd": 20000,
            "distance_to_liquidation_pct": 18.0,
            "data_age_minutes": 800.0,  # >12h
            "source": "telegram_operator",
        },
        "bots": [],
        "current_price_btc": 81500,
    })
    text = build_advisor_text(state_latest_path=state_latest, regime_path=tmp_path / "no.json")
    assert "D-4 PRIMARY" in text


def test_advisor_marks_pending_regime_change(tmp_path: Path) -> None:
    state_latest = tmp_path / "state.json"
    regime = tmp_path / "regime.json"
    _write(state_latest, {"exposure": {}, "bots": [], "current_price_btc": 81500})
    _write(regime, {
        "symbols": {
            "BTCUSDT": {
                "current_primary": "RANGE",
                "regime_age_bars": 10,
                "pending_primary": "TREND_UP",
                "hysteresis_counter": 1,
                "active_modifiers": {},
            }
        }
    })
    text = build_advisor_text(state_latest_path=state_latest, regime_path=regime)
    assert "Pending: TREND_UP" in text
