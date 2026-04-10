from core.pipeline import build_full_snapshot


def test_build_full_snapshot_uses_active_side_for_ginarea(monkeypatch):
    candles = [
        {"open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0}
        for _ in range(200)
    ]

    monkeypatch.setattr("core.pipeline.get_price", lambda symbol: 106.0)
    monkeypatch.setattr("core.pipeline.get_klines", lambda symbol, interval, limit: candles)
    monkeypatch.setattr("core.pipeline.aggregate_to_4h", lambda rows: rows[-50:])
    monkeypatch.setattr("core.pipeline.aggregate_to_1d", lambda rows: rows[-20:])
    monkeypatch.setattr("core.pipeline.detect_trigger", lambda candles_1h, active_block, range_low, range_high: (False, None, None))
    monkeypatch.setattr("core.pipeline.short_term_forecast", lambda candles_1h: {"direction": "SHORT", "confidence": 61})
    monkeypatch.setattr("core.pipeline.session_forecast", lambda candles_4h: {"direction": "SHORT", "confidence": 58})
    monkeypatch.setattr("core.pipeline.medium_forecast", lambda candles_1d: {"direction": "SHORT", "confidence": 55})
    monkeypatch.setattr("core.pipeline.build_consensus", lambda short_fc, session_fc, medium_fc: ("SHORT", 58, {"SHORT": 3}, 3))
    monkeypatch.setattr("core.pipeline.compute_block_pressure", lambda active_block, consensus_direction, consensus_alignment_count, session_fc, medium_fc: ("WITH", "LOW", False, ""))
    monkeypatch.setattr("core.pipeline.load_market_state", lambda: {})
    monkeypatch.setattr("core.pipeline.update_flip_prep", lambda prev_market_state, base_snapshot: {"flip_prep_status": "IDLE"})
    monkeypatch.setattr("core.pipeline.compute_scenario_weights", lambda snapshot: (65, 35, ["base"], ["alt"]))
    monkeypatch.setattr("core.pipeline.save_market_state", lambda prep_state: None)

    snapshot = build_full_snapshot(symbol="BTCUSDT")

    assert snapshot["execution_side"] == "SHORT"
    assert snapshot["ginarea"]["long_grid"] == "REDUCE"
    assert snapshot["ginarea"]["short_grid"] == "WORK"
