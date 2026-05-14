from features.regime_aware_pattern_engine import find_regime_aware_matches
from storage.pattern_history_store import PatternRecord


def test_regime_aware_match_filters_by_tf_regime_and_range_position():
    history = [
        PatternRecord(
            ts="2025-01-01T00:00:00Z",
            tf="1h",
            market_regime="CHOP",
            range_position="UPPER",
            direction="SHORT",
            future_move_pct=-0.8,
            horizon_bars=6,
            normalized_closes=[0.0, 0.2, 0.1, -0.1],
            similarity_features={"atr_pct": 1.2, "range_pos": 0.72},
        ),
        PatternRecord(
            ts="2025-01-02T00:00:00Z",
            tf="4h",
            market_regime="TREND_UP",
            range_position="MID",
            direction="LONG",
            future_move_pct=1.1,
            horizon_bars=4,
            normalized_closes=[0.0, 0.3, 0.5, 0.9],
            similarity_features={"atr_pct": 2.0, "range_pos": 0.50},
        ),
    ]

    result = find_regime_aware_matches(
        current_closes=[0.0, 0.18, 0.09, -0.08],
        current_regime="CHOP",
        current_range_position="UPPER",
        current_features={"atr_pct": 1.1, "range_pos": 0.70},
        history=history,
        tf="1h",
        top_k=3,
    )

    assert result.sample_count == 1
    assert result.direction == "SHORT"
