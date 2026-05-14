"""Tests for runtime detector kill switch."""
from __future__ import annotations

from services.setup_detector import runtime_disabled


def setup_function(_):
    runtime_disabled.reset_cache_for_tests()


def test_empty_env_disables_nothing(monkeypatch):
    monkeypatch.delenv("DISABLED_DETECTORS", raising=False)
    assert not runtime_disabled.is_detector_disabled("detect_long_pdl_bounce")


def test_exact_match(monkeypatch):
    monkeypatch.setenv("DISABLED_DETECTORS", "detect_long_pdl_bounce")
    assert runtime_disabled.is_detector_disabled("detect_long_pdl_bounce")
    assert not runtime_disabled.is_detector_disabled("detect_short_rally_fade")


def test_substring_match(monkeypatch):
    """Loose match: token 'multi_divergence' disables detect_long_multi_divergence."""
    monkeypatch.setenv("DISABLED_DETECTORS", "multi_divergence")
    assert runtime_disabled.is_detector_disabled("detect_long_multi_divergence")
    assert not runtime_disabled.is_detector_disabled("detect_short_rally_fade")


def test_multiple_comma_separated(monkeypatch):
    monkeypatch.setenv("DISABLED_DETECTORS", "h10,multi_divergence,foo")
    assert runtime_disabled.is_detector_disabled("detect_h10_liquidity_probe")
    assert runtime_disabled.is_detector_disabled("detect_long_multi_divergence")
    assert not runtime_disabled.is_detector_disabled("detect_long_pdl_bounce")


def test_whitespace_tolerance(monkeypatch):
    monkeypatch.setenv("DISABLED_DETECTORS", "  h10 , multi_divergence  ,  ")
    assert runtime_disabled.is_detector_disabled("detect_h10_liquidity_probe")


def test_empty_name_returns_false(monkeypatch):
    monkeypatch.setenv("DISABLED_DETECTORS", "h10")
    assert not runtime_disabled.is_detector_disabled("")


def test_cache_returns_consistent_within_ttl(monkeypatch):
    """Within TTL the cache is reused — env mutation isn't picked up immediately."""
    monkeypatch.setenv("DISABLED_DETECTORS", "h10")
    assert runtime_disabled.is_detector_disabled("detect_h10_liquidity_probe")
    # Mutate env — should NOT take effect until TTL expires (we don't wait,
    # so this verifies the cache holds).
    monkeypatch.setenv("DISABLED_DETECTORS", "")
    # Cache still says h10 is disabled.
    assert runtime_disabled.is_detector_disabled("detect_h10_liquidity_probe")


def test_reset_for_tests_forces_refetch(monkeypatch):
    monkeypatch.setenv("DISABLED_DETECTORS", "h10")
    assert runtime_disabled.is_detector_disabled("detect_h10_liquidity_probe")
    monkeypatch.setenv("DISABLED_DETECTORS", "")
    runtime_disabled.reset_cache_for_tests()
    assert not runtime_disabled.is_detector_disabled("detect_h10_liquidity_probe")


# ── State-file source tests (2026-05-11 — TG /disable command) ────────────────

def test_state_file_disables_detector(tmp_path, monkeypatch):
    """Tokens written to state/disabled_detectors.json take effect."""
    monkeypatch.setattr(runtime_disabled, "_STATE_PATH", tmp_path / "d.json")
    monkeypatch.delenv("DISABLED_DETECTORS", raising=False)
    runtime_disabled.reset_cache_for_tests()
    runtime_disabled.add_runtime_disabled("h10")
    assert runtime_disabled.is_detector_disabled("detect_h10_liquidity_probe")
    assert not runtime_disabled.is_detector_disabled("detect_long_pdl_bounce")


def test_state_file_persists(tmp_path, monkeypatch):
    """After add then remove, file is empty / deleted."""
    monkeypatch.setattr(runtime_disabled, "_STATE_PATH", tmp_path / "d.json")
    monkeypatch.delenv("DISABLED_DETECTORS", raising=False)
    runtime_disabled.add_runtime_disabled("foo")
    runtime_disabled.add_runtime_disabled("bar")
    assert (tmp_path / "d.json").exists()
    runtime_disabled.remove_runtime_disabled("foo")
    runtime_disabled.remove_runtime_disabled("bar")
    # File should be removed when set is empty
    assert not (tmp_path / "d.json").exists()


def test_state_and_env_union(tmp_path, monkeypatch):
    """Either source disables — they're OR'd."""
    monkeypatch.setattr(runtime_disabled, "_STATE_PATH", tmp_path / "d.json")
    monkeypatch.setenv("DISABLED_DETECTORS", "env_only")
    runtime_disabled.add_runtime_disabled("state_only")
    runtime_disabled.reset_cache_for_tests()
    assert runtime_disabled.is_detector_disabled("foo_env_only_bar")
    assert runtime_disabled.is_detector_disabled("foo_state_only_bar")
    assert not runtime_disabled.is_detector_disabled("clean_detector")


def test_list_disabled_returns_both_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_disabled, "_STATE_PATH", tmp_path / "d.json")
    monkeypatch.setenv("DISABLED_DETECTORS", "env_a,env_b")
    runtime_disabled.add_runtime_disabled("state_x")
    d = runtime_disabled.list_disabled()
    assert "env_a" in d["env"] and "env_b" in d["env"]
    assert "state_x" in d["state_file"]


def test_add_returns_false_when_already_present(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_disabled, "_STATE_PATH", tmp_path / "d.json")
    assert runtime_disabled.add_runtime_disabled("foo") is True
    assert runtime_disabled.add_runtime_disabled("foo") is False


def test_remove_returns_false_when_not_present(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_disabled, "_STATE_PATH", tmp_path / "d.json")
    assert runtime_disabled.remove_runtime_disabled("absent") is False
