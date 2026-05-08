"""Tests for the DedupLayer wire-up in core.auto_edge_alerts.

P3 of TZ-AUTO-EDGE-ALERTS-DEDUP-WIRE-UP.

We test the dedup helpers (_apply_dedup, _record_dedup_emit, _get_dedup_layer)
directly. The full build_auto_edge_alert flow is not tested end-to-end here
because of an unrelated pre-existing bug at line 317 (`RETURN_SENTINEL` typo
that raises NameError before any text is returned). Fixing that is out of
this TZ's scope; this test suite is structured to exercise the dedup contract
without requiring the broken text builder to run.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

import core.auto_edge_alerts as ae


@pytest.fixture(autouse=True)
def _fresh_dedup_layer(tmp_path, monkeypatch):
    """Replace the module-level dedup singleton for the duration of each test.

    Each test gets a fresh DedupLayer instance bound to a tmp state file. This
    prevents cross-test pollution from production dedup state and from earlier
    tests in the same session.

    We monkey-patch `_get_dedup_layer` itself so that any internal call inside
    auto_edge_alerts gets the test-scoped layer, regardless of how the singleton
    was initialized previously.
    """
    from services.telegram.dedup_layer import DedupLayer
    from services.telegram.dedup_configs import AUTO_EDGE_ALERTS_DEDUP_CONFIG

    test_layer = {"layer": DedupLayer(AUTO_EDGE_ALERTS_DEDUP_CONFIG, state_path=tmp_path / "dedup_state.json")}

    def _test_get_layer():
        if not ae.DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS:
            return None
        return test_layer["layer"]

    monkeypatch.setattr(ae, "_get_dedup_layer", _test_get_layer)
    ae._reset_dedup_layer_for_tests()
    yield
    ae._reset_dedup_layer_for_tests()


# ── Lazy init + env toggle ─────────────────────────────────────────────────

def test_layer_disabled_returns_none() -> None:
    """When env toggle is off, _get_dedup_layer returns None."""
    with patch.object(ae, "DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS", False):
        ae._reset_dedup_layer_for_tests()
        layer = ae._get_dedup_layer()
        assert layer is None


def test_layer_enabled_initializes_singleton() -> None:
    layer = ae._get_dedup_layer()
    assert layer is not None
    # cfg must come from AUTO_EDGE_ALERTS_DEDUP_CONFIG
    assert layer.cfg.cooldown_sec == 1800
    assert layer.cfg.value_delta_min == 5.0
    assert layer.cfg.cluster_enabled is True


def test_layer_singleton_cached() -> None:
    layer_a = ae._get_dedup_layer()
    layer_b = ae._get_dedup_layer()
    assert layer_a is layer_b


# ── _apply_dedup behavior ──────────────────────────────────────────────────

def test_apply_dedup_first_emit_passes() -> None:
    """First-ever emit for a slot is always allowed (no last_emit_value)."""
    should, reason, cluster = ae._apply_dedup(
        slot_key="123:1h", kind="SETUP_ON", value=70.0, price=80000.0, now_ts=1000.0,
    )
    assert should is True
    assert "первый сигнал" in reason or "пропускаем" in reason or "кластер" in reason


def test_apply_dedup_blocks_inside_cooldown() -> None:
    """After a recorded emit, the next attempt within cooldown is blocked."""
    ae._record_dedup_emit("123:1h", value=70.0, now_ts=1000.0)
    # 60s later — well inside 1800s cooldown
    should, reason, _ = ae._apply_dedup(
        slot_key="123:1h", kind="SETUP_ON", value=72.0, price=80000.0, now_ts=1060.0,
    )
    assert should is False
    assert "cooldown" in reason


def test_apply_dedup_blocks_when_value_unchanged_after_cooldown() -> None:
    """Past cooldown but value-delta < threshold → suppressed."""
    ae._record_dedup_emit("123:1h", value=70.0, now_ts=1000.0)
    # 1801s later (past cooldown) but value moved by only 2 pp (< 5 threshold)
    should, reason, _ = ae._apply_dedup(
        slot_key="123:1h", kind="SETUP_ON", value=72.0, price=80000.0, now_ts=2801.0,
    )
    assert should is False
    assert "не изменилось материально" in reason


def test_apply_dedup_passes_when_value_moved_after_cooldown_and_price_far() -> None:
    """Past cooldown AND value-delta ≥ threshold AND price differs enough → allowed."""
    ae._record_dedup_emit("123:1h", value=70.0, now_ts=1000.0)
    # Past cooldown + delta=10 pp + price 1% away (outside 0.5% cluster band)
    should, reason, _ = ae._apply_dedup(
        slot_key="123:1h", kind="SETUP_ON", value=80.0, price=80800.0, now_ts=2900.0,
    )
    assert should is True


def test_apply_dedup_setup_off_skips_cluster_logic() -> None:
    """SETUP_OFF events skip cluster collapse — every disappearance is reported."""
    ae._record_dedup_emit("123:1h", value=70.0, now_ts=1000.0)
    should, _, cluster = ae._apply_dedup(
        slot_key="123:1h", kind="SETUP_OFF", value=80.0, price=80000.0, now_ts=2900.0,
    )
    assert should is True
    # cluster_levels should be None for SETUP_OFF — cluster path skipped
    assert cluster is None


def test_apply_dedup_setup_on_first_event_starts_cluster() -> None:
    """First SETUP_ON event for a slot starts a 1-level cluster and emits."""
    should, _, levels = ae._apply_dedup(
        slot_key="999:1h", kind="SETUP_ON", value=70.0, price=80000.0, now_ts=1000.0,
    )
    assert should is True
    assert levels == [80000.0]


def test_apply_dedup_disabled_layer_passes_through() -> None:
    """When the layer is disabled, _apply_dedup is a no-op pass-through."""
    with patch.object(ae, "DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS", False):
        ae._reset_dedup_layer_for_tests()
        should, reason, cluster = ae._apply_dedup(
            slot_key="abc:1h", kind="SETUP_ON", value=50.0, price=80000.0, now_ts=1000.0,
        )
        assert should is True
        assert "disabled" in reason
        assert cluster is None


def test_apply_dedup_no_price_skips_cluster_for_setup_on() -> None:
    """SETUP_ON without a usable price still emits via state-change gate."""
    should, _, cluster = ae._apply_dedup(
        slot_key="abc:1h", kind="SETUP_ON", value=50.0, price=None, now_ts=1000.0,
    )
    assert should is True
    # cluster path skipped because price is None
    assert cluster is None


# ── _record_dedup_emit ─────────────────────────────────────────────────────

def test_record_dedup_emit_persists_value() -> None:
    """After record_emit, the layer's state reflects the recorded value."""
    layer = ae._get_dedup_layer()
    ae._record_dedup_emit("777:1h", value=50.0, now_ts=1000.0)
    sk = layer._state_key(ae._AUTO_EDGE_EMITTER_NAME, "777:1h")
    st = layer._state.get(sk)
    assert st is not None
    assert st.last_emit_value == 50.0
    assert st.last_emit_ts == 1000.0


def test_record_dedup_emit_disabled_layer_no_op() -> None:
    """When the layer is disabled, record_emit is a silent no-op."""
    with patch.object(ae, "DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS", False):
        ae._reset_dedup_layer_for_tests()
        # Should not raise
        ae._record_dedup_emit("xyz:1h", value=99.0, now_ts=1000.0)


def test_record_then_apply_simulates_burst_suppression() -> None:
    """Record an emit, then a burst of nearby attempts within cooldown → all suppressed."""
    ae._record_dedup_emit("burst:1h", value=70.0, now_ts=1000.0)
    suppressed = 0
    attempted = 0
    for offset in range(60, 1800, 120):  # one attempt every 2 min for 30 min
        attempted += 1
        should, _, _ = ae._apply_dedup(
            slot_key="burst:1h",
            kind="SETUP_ON",
            value=72.0 + offset / 100,  # tiny drift in value
            price=80000.0,
            now_ts=1000.0 + offset,
        )
        if not should:
            suppressed += 1
    # All attempts should have been suppressed by the cooldown
    assert suppressed == attempted
    assert attempted >= 14


def test_build_alert_text_returns_rendered_string() -> None:
    """Regression: text builder returns a string instead of raising on sentinel typo."""
    current = {
        "timeframe": "1h",
        "price": 80000.0,
        "action_title": "RUN LONG",
        "runtime_line": "active",
        "scenario_text": "range reclaim",
        "forecast_text": "market neutral",
        "scenario_confidence": 61,
    }
    text = ae._build_alert_text({}, current, "SETUP_ON")
    assert isinstance(text, str)
    assert "1h" in text
    assert "80000" in text or "80 000" in text
