"""Integration: state_builder reads margin from state_latest.json["margin"]
and feeds Decision Layer M-* + D-4.

Live snapshot test reproduces the operator's BitMEX UI 2026-05-06 11:32 UTC+3
values: margin_coefficient=0.9693, distance_to_liq=18.0%.

Expected:
  - M-3 fires (margin >= 0.85)
  - M-4 fires (margin >= 0.95)
  - R-1 fires (regime stable)
  - D-4 does NOT fire when margin data is fresh
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.dashboard.state_builder import build_state


def _write_classifier_a_state(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "version": 1,
            "manual_blackout_until": None,
            "symbols": {
                "BTCUSDT": {
                    "current_primary": "RANGE",
                    "primary_since": "2026-05-06T05:00:00Z",
                    "regime_age_bars": 25,
                    "pending_primary": None,
                    "hysteresis_counter": 0,
                    "active_modifiers": {},
                    "atr_history_1h": [],
                    "bb_width_history_1h": [],
                },
            },
        }),
        encoding="utf-8",
    )


def _write_state_latest_with_margin(
    path: Path,
    *,
    coefficient: float = 0.9693,
    available: float = 20434.0,
    distance_pct: float = 18.0,
    margin_ts: str = "2026-05-06T08:30:00Z",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": "2026-05-06T08:30:00+00:00",
        "exposure": {
            "shorts_btc": -1.416,
            "longs_btc": 0.10,
            "net_btc": -1.316,
            "nearest_short_liq": {"price": 96311.0, "distance_pct": None},
            "nearest_long_liq": {"price": 22171.6, "distance_pct": None},
        },
        "margin": {
            "coefficient": coefficient,
            "available_margin_usd": available,
            "distance_to_liquidation_pct": distance_pct,
            "source": "telegram_operator",
            "updated_at": margin_ts,
            "data_age_minutes": 1.0,  # fresh
        },
        "bots": [
            {"live": {"unrealized_usd": -3572.0}},
            {"live": {"unrealized_usd": 33.0}},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_empty(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_paths(tmp_path: Path) -> dict:
    snap = tmp_path / "snapshots.csv"
    snap.write_text("bot_id,ts_utc,position,current_profit,alias\n", encoding="utf-8")
    return {
        "snapshots_path": snap,
        "state_latest_path": tmp_path / "state_latest.json",
        "signals_path": tmp_path / "advise_signals.jsonl",
        "null_signals_path": tmp_path / "null_signals.jsonl",
        "events_path": tmp_path / "events.jsonl",
        "liq_path": tmp_path / "liq_clusters.json",
        "competition_path": tmp_path / "competition.json",
        "engine_path": tmp_path / "engine_status.json",
        "regime_state_path": tmp_path / "regime_state.json",
    }


def test_live_snapshot_operator_bitmex_values(tmp_path: Path, monkeypatch) -> None:
    """Operator BitMEX UI 2026-05-06 11:32 UTC+3 values → M-3 + R-1.

    Original test (pre-2026-05-09) asserted M-4 also fires on coef=0.9693
    + dist=18%. That was BEFORE the safety override in commit 14bbd2e:
    high coef + safe distance (>=15%) no longer fires M-4 emergency
    because cross-margin running multiple bots routinely sits at
    coef 0.95-1.0 with comfortable distance.

    So with operator's values (coef=0.9693, dist=18%) M-4 should NOT
    fire. Below we verify the M-4 path is dormant on safe distance, and
    have a separate test for the dist-triggered branch.
    """
    monkeypatch.chdir(tmp_path)

    paths = _build_paths(tmp_path)
    _write_classifier_a_state(paths["regime_state_path"])
    _write_state_latest_with_margin(paths["state_latest_path"])
    # Empty placeholders for the rest
    paths["signals_path"].write_text("", encoding="utf-8")
    paths["null_signals_path"].write_text("", encoding="utf-8")
    paths["events_path"].write_text("", encoding="utf-8")
    (paths["liq_path"]).write_text("{}", encoding="utf-8")
    (paths["competition_path"]).write_text("{}", encoding="utf-8")
    (paths["engine_path"]).write_text(
        json.dumps({"bugs_detected": 2, "bugs_fixed": 2}), encoding="utf-8",
    )
    state = build_state(now=datetime(2026, 5, 6, 8, 32, tzinfo=timezone.utc), **paths)

    dl = state["decision_layer"]
    rules_emitted = [e["rule_id"] for e in dl["events_recent"]]
    # M-3 fires on 0.9693 coef (threshold 0.85)
    assert "M-3" in rules_emitted
    # M-4 must NOT fire: safety override (dist 18% >= 15% safe threshold)
    assert "M-4" not in rules_emitted
    # R-1 must fire on stable regime
    assert "R-1" in rules_emitted
    # D-4 must NOT fire — margin data is fresh
    assert "D-4" not in rules_emitted


def test_m4_fires_on_low_distance(tmp_path: Path, monkeypatch) -> None:
    """When distance_to_liq < 5%, M-4 emergency must fire regardless of coef."""
    monkeypatch.chdir(tmp_path)
    paths = _build_paths(tmp_path)
    _write_classifier_a_state(paths["regime_state_path"])
    _write_state_latest_with_margin(paths["state_latest_path"],
                                     coefficient=0.85, distance_pct=3.5)
    paths["signals_path"].write_text("", encoding="utf-8")
    paths["null_signals_path"].write_text("", encoding="utf-8")
    paths["events_path"].write_text("", encoding="utf-8")
    paths["liq_path"].write_text("{}", encoding="utf-8")
    paths["competition_path"].write_text("{}", encoding="utf-8")
    paths["engine_path"].write_text("{}", encoding="utf-8")
    state = build_state(now=datetime(2026, 5, 6, 8, 32, tzinfo=timezone.utc), **paths)
    dl = state["decision_layer"]
    rules_emitted = [e["rule_id"] for e in dl["events_recent"]]
    assert "M-4" in rules_emitted
    m4 = next(e for e in dl["events_recent"] if e["rule_id"] == "M-4")
    assert m4["payload"]["trigger"] == "distance_to_liq"


def test_no_margin_block_keeps_M_dormant(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    paths = _build_paths(tmp_path)
    _write_classifier_a_state(paths["regime_state_path"])
    # state_latest with no margin block at all
    paths["state_latest_path"].write_text(json.dumps({
        "exposure": {"net_btc": -0.5, "nearest_short_liq": {"price": 100000.0, "distance_pct": None}},
        "bots": [],
    }), encoding="utf-8")
    paths["signals_path"].write_text("", encoding="utf-8")
    paths["null_signals_path"].write_text("", encoding="utf-8")
    paths["events_path"].write_text("", encoding="utf-8")
    paths["liq_path"].write_text("{}", encoding="utf-8")
    paths["competition_path"].write_text("{}", encoding="utf-8")
    paths["engine_path"].write_text(
        json.dumps({"bugs_detected": 2, "bugs_fixed": 2}), encoding="utf-8",
    )
    state = build_state(now=datetime(2026, 5, 6, 8, 32, tzinfo=timezone.utc), **paths)
    rules = [e["rule_id"] for e in state["decision_layer"]["events_recent"]]
    # M-1..M-4 should not fire (margin_coefficient=None)
    assert not any(r in rules for r in ("M-1", "M-2", "M-3", "M-4"))
    # D-4 also doesn't fire (margin_data_age_min=None)
    assert "D-4" not in rules
