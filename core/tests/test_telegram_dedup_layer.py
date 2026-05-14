"""Tests for services/telegram/dedup_layer.py — state-change + cooldown + cluster."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from services.telegram.dedup_layer import DedupLayer, DedupConfig, DedupDecision


@pytest.fixture
def tmp_state(tmp_path):
    return tmp_path / "dedup_state.json"


# ── State-change check ────────────────────────────────────────────────────────

def test_first_emit_always_passes(tmp_state):
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    d = layer.evaluate("rsi", "BTC", value=27, now_ts=100)
    assert d.should_emit is True
    assert "первый" in d.reason_ru


def test_state_unchanged_suppressed(tmp_state):
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.record_emit("rsi", "BTC", value=27, now_ts=100)
    # 10 minutes later, RSI still 28 → delta=1 < threshold 5
    d = layer.evaluate("rsi", "BTC", value=28, now_ts=700)
    assert d.should_emit is False
    assert "не изменилось" in d.reason_ru


def test_state_changed_passes(tmp_state):
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.record_emit("rsi", "BTC", value=27, now_ts=100)
    d = layer.evaluate("rsi", "BTC", value=35, now_ts=400)  # delta=8 ≥ 5
    assert d.should_emit is True


# ── Cooldown active/expired ───────────────────────────────────────────────────

def test_cooldown_active_suppressed(tmp_state):
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.record_emit("rsi", "BTC", value=27, now_ts=100)
    # 60s later, big change but cooldown active
    d = layer.evaluate("rsi", "BTC", value=50, now_ts=160)
    assert d.should_emit is False
    assert "cooldown" in d.reason_ru


def test_cooldown_expired_with_state_change_passes(tmp_state):
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.record_emit("rsi", "BTC", value=27, now_ts=100)
    # 200s later (> cooldown), big change
    d = layer.evaluate("rsi", "BTC", value=50, now_ts=300)
    assert d.should_emit is True


def test_cooldown_expired_but_state_unchanged_still_suppressed(tmp_state):
    """The whole point of Finding 1: cooldown ≠ dedup."""
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.record_emit("rsi", "BTC", value=27, now_ts=100)
    # 200s later, RSI still hovering at 28 (delta 1 < threshold)
    d = layer.evaluate("rsi", "BTC", value=28, now_ts=300)
    assert d.should_emit is False
    assert "не изменилось" in d.reason_ru


# ── Cluster collapse ──────────────────────────────────────────────────────────

def test_cluster_first_emit_passes(tmp_state):
    cfg = DedupConfig(cluster_enabled=True, cluster_window_sec=60, cluster_price_delta_pct=0.5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    d = layer.evaluate_cluster("level_break", "BTC", price=78523, now_ts=100)
    assert d.should_emit is True
    assert d.cluster_levels == [78523]


def test_cluster_second_close_price_buffered(tmp_state):
    cfg = DedupConfig(cluster_enabled=True, cluster_window_sec=60, cluster_price_delta_pct=0.5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.evaluate_cluster("level_break", "BTC", price=78523, now_ts=100)
    # 30s later, close price 78494 (Δ=29, ≈0.04%) → cluster
    d = layer.evaluate_cluster("level_break", "BTC", price=78494, now_ts=130)
    assert d.should_emit is False
    assert "накапливаем" in d.reason_ru


def test_cluster_flush_returns_all_levels(tmp_state):
    cfg = DedupConfig(cluster_enabled=True, cluster_window_sec=60, cluster_price_delta_pct=0.5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.evaluate_cluster("level_break", "BTC", price=78523, now_ts=100)
    layer.evaluate_cluster("level_break", "BTC", price=78494, now_ts=120)
    layer.evaluate_cluster("level_break", "BTC", price=78510, now_ts=140)
    d = layer.flush_cluster("level_break", "BTC", now_ts=200)
    assert d.should_emit is True
    assert d.cluster_levels is not None
    assert len(d.cluster_levels) == 3
    assert sorted(d.cluster_levels) == [78494, 78510, 78523]


def test_cluster_far_price_starts_new_cluster(tmp_state):
    cfg = DedupConfig(cluster_enabled=True, cluster_window_sec=60, cluster_price_delta_pct=0.5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.evaluate_cluster("level_break", "BTC", price=78523, now_ts=100)
    # 1.5% away — beyond cluster_price_delta_pct → new cluster
    d = layer.evaluate_cluster("level_break", "BTC", price=80000, now_ts=130)
    assert d.should_emit is True
    assert d.cluster_levels == [80000]


def test_cluster_disabled_falls_through_to_evaluate(tmp_state):
    """cluster_enabled=False → evaluate_cluster() defers to plain evaluate()."""
    cfg = DedupConfig(cluster_enabled=False, value_delta_min=10, cooldown_sec=60)
    layer = DedupLayer(cfg, state_path=tmp_state)
    d1 = layer.evaluate_cluster("level_break", "BTC", price=78523, now_ts=100)
    layer.record_emit("level_break", "BTC", value=78523, now_ts=100)
    # Tiny delta → suppressed by state-change check
    d2 = layer.evaluate_cluster("level_break", "BTC", price=78525, now_ts=200)
    assert d1.should_emit is True
    assert d2.should_emit is False


# ── Persistence ───────────────────────────────────────────────────────────────

def test_state_persists_to_disk(tmp_state):
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer1 = DedupLayer(cfg, state_path=tmp_state)
    layer1.record_emit("rsi", "BTC", value=27, now_ts=100)
    # New instance reads from disk
    layer2 = DedupLayer(cfg, state_path=tmp_state)
    d = layer2.evaluate("rsi", "BTC", value=28, now_ts=700)  # tiny delta
    assert d.should_emit is False
    assert "не изменилось" in d.reason_ru


def test_state_independent_keys(tmp_state):
    """BTCUSDT_15m and BTCUSDT_1h are independent keys."""
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.record_emit("rsi", "BTC_15m", value=27, now_ts=100)
    # Different key → still first emit
    d = layer.evaluate("rsi", "BTC_1h", value=27, now_ts=110)
    assert d.should_emit is True


# ── Edge case: cluster crossing cooldown boundary ────────────────────────────

def test_old_pending_cluster_entries_dropped(tmp_state):
    """Entries older than cluster_window_sec are pruned."""
    cfg = DedupConfig(cluster_enabled=True, cluster_window_sec=60, cluster_price_delta_pct=0.5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.evaluate_cluster("level_break", "BTC", price=78523, now_ts=100)
    # 200s later (>60s window), close price → previous cluster entry should be dropped
    d = layer.evaluate_cluster("level_break", "BTC", price=78510, now_ts=300)
    # New cluster started (single level, emit immediately)
    assert d.should_emit is True
    assert d.cluster_levels == [78510]


def test_reasoning_string_in_russian(tmp_state):
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    layer = DedupLayer(cfg, state_path=tmp_state)
    layer.record_emit("rsi", "BTC", value=27, now_ts=100)
    d = layer.evaluate("rsi", "BTC", value=28, now_ts=700)
    # Cyrillic content present
    assert any(c in d.reason_ru for c in "абвгдежзийклмнопрстуфхцчшщъыьэюя")


# ── Dry-run integration ──────────────────────────────────────────────────────

def test_dry_run_handles_missing_log(tmp_path, capsys):
    import scripts.dedup_layer_dry_run as dr
    rc = dr.main(["--log", str(tmp_path / "missing.jsonl")])
    assert rc == 0


def test_dry_run_processes_sample_log(tmp_path, capsys):
    import scripts.dedup_layer_dry_run as dr
    log = tmp_path / "alert_log.jsonl"
    log.write_text(
        '{"emitter": "auto_edge_alerts.rsi", "key": "BTCUSDT_15m", "value": 27, "ts": 100}\n'
        '{"emitter": "auto_edge_alerts.rsi", "key": "BTCUSDT_15m", "value": 28, "ts": 500}\n'
        '{"emitter": "auto_edge_alerts.rsi", "key": "BTCUSDT_15m", "value": 35, "ts": 1000}\n',
        encoding="utf-8",
    )
    rc = dr.main(["--log", str(log)])
    assert rc == 0
