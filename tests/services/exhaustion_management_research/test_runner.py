from __future__ import annotations

import pandas as pd

from services.exhaustion_management_research.runner import (
    _scenario_config,
    detect_exhaustion_signals,
    should_open_dca_on_pullback,
    simulate_episode,
    Episode,
)


def _hourly(rows: list[tuple[str, float, float, float, float, float, float]]) -> pd.DataFrame:
    index = pd.to_datetime([r[0] for r in rows], utc=True)
    return pd.DataFrame(
        {
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
            "roc_1h_pct": [r[6] for r in rows],
        },
        index=index,
    )


def _minute_path() -> pd.DataFrame:
    idx = pd.date_range("2026-05-01T03:00:00Z", periods=180, freq="1min", tz="UTC")
    close = []
    price = 100.0
    for i in range(len(idx)):
        if i < 60:
            price += 0.05
        elif i < 90:
            price -= 0.2
        elif i < 120:
            price += 0.15
        else:
            price -= 0.18
        close.append(price)
    df = pd.DataFrame({"close": close}, index=idx)
    df["open"] = df["close"].shift(1).fillna(df["close"])
    df["high"] = df[["open", "close"]].max(axis=1) + 0.05
    df["low"] = df[["open", "close"]].min(axis=1) - 0.05
    df["volume"] = 100.0
    return df[["open", "high", "low", "close", "volume"]]


def test_exhaustion_signal_detection() -> None:
    df = _hourly(
        [
            ("2026-05-01T00:00:00Z", 100, 101, 99.5, 100.8, 120, 0.8),
            ("2026-05-01T01:00:00Z", 100.8, 101.8, 100.4, 101.5, 130, 0.7),
            ("2026-05-01T02:00:00Z", 101.5, 101.7, 100.9, 101.0, 90, -0.5),
            ("2026-05-01T03:00:00Z", 101.0, 101.6, 100.2, 100.5, 80, -0.5),
            ("2026-05-01T04:00:00Z", 100.5, 101.55, 99.8, 99.9, 70, -0.6),
            ("2026-05-01T05:00:00Z", 99.9, 100.2, 98.0, 98.2, 60, -1.8),
        ]
    )
    signals = detect_exhaustion_signals(df, "long")
    assert signals["failed_breakouts"] is True
    assert signals["volume_drop"] is True
    assert signals["counter_candle"] is True


def test_dca_on_pullback_trigger() -> None:
    ts = pd.Timestamp("2026-05-01T01:30:00Z")
    assert should_open_dca_on_pullback("long", current_close=99.5, running_extreme=100.0, trend_confirmed=True, last_dca_ts=None, ts=ts)
    assert not should_open_dca_on_pullback("long", current_close=99.95, running_extreme=100.0, trend_confirmed=True, last_dca_ts=None, ts=ts)


def test_adaptive_sizing_in_stage_1() -> None:
    cfg = _scenario_config("adaptive")
    assert cfg.stage1_size_mult == 1.5
    assert cfg.stage1_target_mult == 1.5
    assert cfg.dca_mult == 2.0


def test_exit_on_exhaustion() -> None:
    df_1m = _minute_path()
    df_1h = _hourly(
        [
            ("2026-05-01T00:00:00Z", 100, 101, 99.5, 100.8, 120, 0.8),
            ("2026-05-01T01:00:00Z", 100.8, 102.0, 100.6, 101.8, 140, 1.0),
            ("2026-05-01T02:00:00Z", 101.8, 103.0, 101.5, 102.9, 150, 1.1),
            ("2026-05-01T03:00:00Z", 102.9, 103.1, 102.2, 102.5, 90, -0.4),
            ("2026-05-01T04:00:00Z", 102.5, 103.05, 101.8, 101.9, 80, -0.6),
            ("2026-05-01T05:00:00Z", 101.9, 103.0, 100.0, 100.2, 70, -1.7),
            ("2026-05-01T06:00:00Z", 100.2, 100.5, 98.9, 99.0, 65, -1.2),
        ]
    )
    ep = Episode(
        ts_start=pd.Timestamp("2026-05-01T00:00:00Z"),
        ts_confirm=pd.Timestamp("2026-05-01T03:00:00Z"),
        ts_exhaustion=pd.Timestamp("2026-05-01T05:00:00Z"),
        ts_end=pd.Timestamp("2026-05-01T09:00:00Z"),
        trend_side="long",
        trend_duration_bucket="2-4h",
        magnitude_bucket="1.5-3%",
        session_label="ny_am",
        volatility_regime="normal_vol",
        move_pct=2.0,
        exhaustion_signals=("failed_breakouts", "counter_candle"),
    )
    result = simulate_episode(df_1m, df_1h, ep, "adaptive")
    assert result["exit_on_exhaustion"] is True
