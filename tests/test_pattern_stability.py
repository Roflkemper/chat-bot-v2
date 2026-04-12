from core.pattern_stability import PatternSnapshot, stabilize_pattern_signal
from core.execution_zone_sync import build_execution_zone_state


def test_opposite_pattern_needs_persistence():
    prev = PatternSnapshot(direction="SHORT", strength=64, confidence=0.64, meaningful=True)
    cur = PatternSnapshot(direction="LONG", strength=64, confidence=0.64, meaningful=True)
    out = stabilize_pattern_signal(cur, prev, persistence_bars_seen=0, min_persistence_bars=2)
    assert out.direction == "SHORT"
    assert out.stability_state == "WAIT_PERSISTENCE"


def test_zone_sync_sets_search_trigger_inside_short_block():
    snap = build_execution_zone_state(
        price=72211.0,
        range_low=68198.22,
        range_mid=70527.61,
        range_high=72857.0,
        stable_pattern_direction="SHORT",
        consensus_direction="SHORT",
        consensus_agreement="LOW",
        zone_enter_buffer=80.0,
        hedge_buffer=300.0,
    )
    assert snap.state == "SEARCH_TRIGGER"
    assert snap.action_side == "SHORT"
    assert snap.metrics.in_active_block is True
