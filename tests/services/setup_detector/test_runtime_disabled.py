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
