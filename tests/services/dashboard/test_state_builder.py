from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


from services.dashboard.state_builder import (
    PHASE_1_TOTAL_DAYS,
    build_and_save_state,
    build_state,
)


def _now() -> datetime:
    return datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_snapshots_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("bot_id,ts_utc,position,current_profit,alias,average_price\n")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _signal(setup_id: str = "P-3", regime: str = "trend_down", price: float = 76000.0, ts: str = "2026-04-30T08:45:05Z") -> dict:
    return {
        "signal_id": f"adv_{ts[:10]}",
        "ts": ts,
        "setup_id": setup_id,
        "market_context": {"price_btc": price, "regime_label": regime},
    }


def _snap_row(bot_id: str, position: float, profit: float) -> dict:
    return {
        "bot_id": bot_id,
        "ts_utc": "2026-04-30T12:00:00+00:00",
        "position": str(position),
        "current_profit": str(profit),
        "alias": f"BOT_{bot_id}",
        "average_price": "76000",
    }


def _build_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "snapshots_path": tmp_path / "snapshots.csv",
        "state_latest_path": tmp_path / "state_latest.json",
        "signals_path": tmp_path / "advise_signals.jsonl",
        "null_signals_path": tmp_path / "null_signals.jsonl",
        "events_path": tmp_path / "events.jsonl",
        "liq_path": tmp_path / "liq_clusters.json",
        "competition_path": tmp_path / "competition.json",
        "engine_path": tmp_path / "engine_status.json",
    }


# ── test_build_state_with_all_sources_present ─────────────────────────────────

def test_build_state_with_all_sources_present(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    _write_snapshots_csv(paths["snapshots_path"], [_snap_row("1", -0.1, -50.0)])
    _write_json(paths["state_latest_path"], {"exposure": {"net_btc": -0.1, "free_margin_pct": 50.0}})
    _write_jsonl(paths["signals_path"], [_signal()])
    _write_jsonl(paths["null_signals_path"], [{"ts": "2026-04-30T10:00:00Z", "reason": "low_margin", "context": {}}])
    _write_jsonl(paths["events_path"], [{"event_id": "evt-1", "event_type": "PARAM_CHANGE", "ts": "2026-04-30T12:00:00Z", "severity": "WARNING", "summary": "test"}])
    _write_json(paths["competition_path"], {"rank": 1, "pnl_total_usd": 1429})
    _write_json(paths["engine_path"], {"bugs_detected": 3, "bugs_fixed": 0})

    state = build_state(now=_now(), **paths)

    assert "last_updated_at" in state
    assert state["current_price_btc"] == 76000.0
    assert state["phase_1_paper_journal"]["advise_signals_count"] == 1
    assert state["phase_1_paper_journal"]["null_signals_count"] == 1
    assert state["competition"]["rank"] == 1
    assert state["engine_status"]["bugs_detected"] == 3
    assert len(state["boli_status"]) == 4
    assert len(state["recent_decisions"]) == 1
    assert "positions" in state


# ── test_build_state_with_missing_advise_signals_gracefully ──────────────────

def test_build_state_with_missing_advise_signals_gracefully(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    # signals_path does not exist
    state = build_state(now=_now(), **paths)
    pj = state["phase_1_paper_journal"]
    assert pj["advise_signals_count"] == 0
    assert pj["day_n"] == 0
    assert pj["dominant_setup"] is None


# ── test_build_state_with_missing_decision_log_gracefully ────────────────────

def test_build_state_with_missing_decision_log_gracefully(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    # events_path does not exist
    state = build_state(now=_now(), **paths)
    assert state["recent_decisions"] == []
    assert state["alerts_24h"] == []


# ── test_build_state_with_missing_liq_clusters_gracefully ───────────────────

def test_build_state_with_missing_liq_clusters_gracefully(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    state = build_state(now=_now(), **paths)
    assert state["active_liq_clusters"] == []


# ── test_state_includes_last_updated_at_iso ──────────────────────────────────

def test_state_includes_last_updated_at_iso(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    state = build_state(now=_now(), **paths)
    ts = state["last_updated_at"]
    assert ts == "2026-04-30T14:00:00Z"
    # Must parse as ISO datetime
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo is not None


# ── test_competition_calculation_correct ─────────────────────────────────────

def test_competition_calculation_correct(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    _write_json(paths["competition_path"], {
        "rank": 2,
        "pnl_total_usd": 850,
        "volume_total_usd": 1_500_000,
        "volume_target_usd": 10_500_000,
        "days_remaining": 18,
        "daily_volume_avg": 150_000,
        "projected_volume_30d": 4_500_000,
        "rebate_estimate": "900-1500",
    })
    state = build_state(now=_now(), **paths)
    comp = state["competition"]
    assert comp["rank"] == 2
    assert comp["pnl_total_usd"] == 850
    assert comp["volume_target_usd"] == 10_500_000
    assert comp["rebate_estimate"] == "900-1500"


# ── test_paper_journal_day_n_calculated_from_first_signal_ts ─────────────────

def test_paper_journal_day_n_calculated_from_first_signal_ts(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    # First signal 3 days before now
    first_ts = (_now() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(paths["signals_path"], [_signal(ts=first_ts), _signal()])
    state = build_state(now=_now(), **paths)
    assert state["phase_1_paper_journal"]["day_n"] == 4  # day 1 + 3 days elapsed


# ── test_phase_1_progress_bar_pct_correct ────────────────────────────────────

def test_phase_1_progress_bar_pct_correct(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    first_ts = (_now() - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(paths["signals_path"], [_signal(ts=first_ts)])
    state = build_state(now=_now(), **paths)
    pj = state["phase_1_paper_journal"]
    day_n = pj["day_n"]
    day_total = pj["day_total"]
    pct = day_n / day_total * 100
    assert 40 < pct < 60  # ~7/14 = 50%
    assert day_total == PHASE_1_TOTAL_DAYS


# ── test_build_and_save_state_writes_file ─────────────────────────────────────

def test_build_and_save_state_writes_file(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    output_path = tmp_path / "out" / "dashboard_state.json"
    build_and_save_state(output_path=output_path, now=_now(), **paths)
    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert "last_updated_at" in data
    assert "positions" in data


# ── test_alerts_24h_only_warning_or_critical ─────────────────────────────────

def test_alerts_24h_only_warning_or_critical(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    recent_ts = (_now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(paths["events_path"], [
        {"event_id": "1", "event_type": "BOUNDARY_BREACH", "ts": recent_ts, "severity": "INFO", "summary": "info event"},
        {"event_id": "2", "event_type": "MARGIN_ALERT", "ts": recent_ts, "severity": "WARNING", "summary": "warning event"},
        {"event_id": "3", "event_type": "MARGIN_ALERT", "ts": recent_ts, "severity": "CRITICAL", "summary": "critical event"},
    ])
    state = build_state(now=_now(), **paths)
    alerts = state["alerts_24h"]
    msgs = [a["msg"] for a in alerts]
    assert "warning event" in msgs
    assert "critical event" in msgs
    assert "info event" not in msgs


# ── Forecast block decommissioned (TZ-FORECAST-DECOMMISSION) ────────────────
# Tests for forecast staleness, usability bands, and Brier classification
# were removed when the forecast block was retired per
# FORECAST_CALIBRATION_DIAGNOSTIC_v1.md verdict (FUNDAMENTALLY WEAK).


def test_forecast_field_not_in_state(tmp_path: Path) -> None:
    """forecast field is absent from build_state output post-decommission."""
    paths = _build_paths(tmp_path)
    state = build_state(now=_now(), **paths)
    assert "forecast" not in state, "forecast field must be removed in TZ-FORECAST-DECOMMISSION"


# ── P1: regulation action card (preserved — independent of forecast) ────────

def _write_classifier_a_state(path: Path, primary: str = "RANGE") -> None:
    """Write a Classifier A-shape regime_state.json that the adapter consumes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "version": 1,
            "manual_blackout_until": None,
            "symbols": {
                "BTCUSDT": {
                    "current_primary": primary,
                    "primary_since": "2026-04-30T00:00:00Z",
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


def test_regulation_card_for_RANGE(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    regime_state_path = tmp_path / "regime_state.json"
    _write_classifier_a_state(regime_state_path, primary="RANGE")
    state = build_state(now=_now(), regime_state_path=regime_state_path, **paths)
    card = state["regulation_action_card"]
    assert card["regulation_version"] == "v0.1.1"
    assert card["regime_label"] == "RANGE"
    on_cfgs = {row["cfg_id"] for row in card["on"]}
    assert on_cfgs == {"CFG-L-RANGE", "CFG-L-FAR", "CFG-S-RANGE-DEFAULT"}
    off_cfgs = {row["cfg_id"] for row in card["off"]}
    assert off_cfgs == {"CFG-S-INDICATOR", "CFG-L-DEFAULT"}
    assert card["conditional"] == []


def test_regulation_card_for_MARKDOWN_has_conditionals(tmp_path: Path) -> None:
    paths = _build_paths(tmp_path)
    regime_state_path = tmp_path / "regime_state.json"
    _write_classifier_a_state(regime_state_path, primary="TREND_DOWN")
    state = build_state(now=_now(), regime_state_path=regime_state_path, **paths)
    card = state["regulation_action_card"]
    assert card["regime_label"] == "MARKDOWN"
    cond_cfgs = {row["cfg_id"] for row in card["conditional"]}
    # CFG-L-RANGE, CFG-L-FAR, CFG-S-RANGE-DEFAULT all CONDITIONAL in MARKDOWN
    assert "CFG-L-RANGE" in cond_cfgs
    assert "CFG-L-FAR" in cond_cfgs
    assert "CFG-S-RANGE-DEFAULT" in cond_cfgs


def test_regulation_card_no_regime(tmp_path: Path) -> None:
    """Missing regime label → card with note explaining why no rules."""
    paths = _build_paths(tmp_path)
    state = build_state(
        now=_now(),
        regime_state_path=tmp_path / "no_such_regime.json",
        **paths,
    )
    card = state["regulation_action_card"]
    assert card["regime_label"] is None
    assert card["note"] is not None
    assert card["on"] == []
