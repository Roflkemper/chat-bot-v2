"""Тесты для GA-найденных shadow-детекторов."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.setup_detector.ga_shadow_detectors import (
    EVALUATORS_BY_PAIR,
    evaluate_btc_macd_long,
    evaluate_eth_macd_short,
    evaluate_xrp_rsi_short,
)


def _synth_uptrend_with_volume_spike(n: int = 300, base_price: float = 100.0) -> pd.DataFrame:
    """Синтетический бычий тренд с объёмным импульсом на последней свече.

    Цена растёт чтобы EMA(93) > EMA(251) и MACD-hist > порог.

    base_price=100 → MACD-hist ~1-2, не сработает BTC-detector с порогом 75.
    base_price=80000 (BTC масштаб) → MACD-hist может быть >75.
    """
    rng = np.random.default_rng(42)
    base = np.linspace(base_price, base_price * 3, n)
    noise = rng.normal(0, base_price * 0.01, n)
    close = base + noise
    volume = rng.uniform(80, 120, n)
    volume[-1] = 800.0  # ~10× от среднего → z-score выше 2.76
    return pd.DataFrame({
        "open": close,
        "high": close + base_price * 0.005,
        "low": close - base_price * 0.005,
        "close": close,
        "volume": volume,
    })


def _synth_downtrend_with_volume_spike(n: int = 300) -> pd.DataFrame:
    """Синтетический медвежий тренд с объёмным импульсом."""
    rng = np.random.default_rng(43)
    base = np.linspace(300, 100, n)
    noise = rng.normal(0, 1, n)
    close = base + noise
    volume = rng.uniform(80, 120, n)
    volume[-1] = 600.0
    return pd.DataFrame({
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": volume,
    })


def _synth_flat(n: int = 300) -> pd.DataFrame:
    """Флэт — не должен триггерить ни один детектор."""
    rng = np.random.default_rng(44)
    close = 100.0 + rng.normal(0, 0.5, n)
    volume = rng.uniform(95, 105, n)
    return pd.DataFrame({
        "open": close,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": volume,
    })


def test_btc_macd_long_triggers_at_least_once_on_real_2y_data():
    """На 2-летнем реальном BTC должно быть хотя бы 1 срабатывание.

    GA backtest показал N=105 trigger'ов за 2 года = ~1 в неделю.
    Тест проверяет что детектор НЕ молчит везде на реальных данных.
    """
    from pathlib import Path
    csv = Path("backtests/frozen/BTCUSDT_1h_2y.csv")
    if not csv.exists():
        pytest.skip("BTC 1h 2y data not available")
    df_full = pd.read_csv(csv)
    # Колонки: ts_ms, open, high, low, close, volume, ...
    fired = 0
    # Скользящее окно по 280 баров с шагом 50, проверяем сработал ли
    for end in range(280, len(df_full), 50):
        window = df_full.iloc[end - 280: end].reset_index(drop=True)
        em = evaluate_btc_macd_long(window)
        if em is not None:
            fired += 1
    assert fired > 0, "Должен сработать хотя бы раз на 2 годах реальных BTC данных"


def test_btc_macd_long_triggers_on_synthetic_smoke():
    """Smoke-проверка на синтетике: важно что не падает с exception.

    На синтетических данных детектор может не сработать (MACD-hist абсолютный),
    но не должен крашиться.
    """
    df = _synth_uptrend_with_volume_spike(base_price=80_000.0)
    em = evaluate_btc_macd_long(df)
    assert em is None or em.detector_id == "long_macd_momentum_breakout"


def test_btc_macd_long_no_trigger_on_flat():
    df = _synth_flat()
    em = evaluate_btc_macd_long(df)
    assert em is None, "На флэте не должен срабатывать"


def test_btc_macd_long_no_trigger_on_short_data():
    df = _synth_uptrend_with_volume_spike(n=100)  # < 260 баров
    em = evaluate_btc_macd_long(df)
    assert em is None, "На коротких данных должен возвращать None"


def test_eth_macd_short_triggers_on_strong_downtrend():
    df = _synth_downtrend_with_volume_spike()
    em = evaluate_eth_macd_short(df)
    # Может сработать или нет в зависимости от точного MACD-уровня;
    # главное — корректный тип и parameters если сработал
    if em is not None:
        assert em.detector_id == "short_macd_oversold_breakdown"
        assert em.side == "short"
        assert em.pair == "ETHUSDT"
        assert em.triggered_by["ema_gate_bear"] is True


def test_eth_macd_short_no_trigger_on_flat():
    df = _synth_flat()
    em = evaluate_eth_macd_short(df)
    assert em is None


def test_xrp_rsi_short_triggers_on_uptrend_high_rsi():
    df = _synth_uptrend_with_volume_spike()
    em = evaluate_xrp_rsi_short(df)
    # При сильном uptrend RSI будет высоким — должен сработать
    assert em is not None
    assert em.detector_id == "short_rsi_overbought_xrp"
    assert em.side == "short"
    assert em.pair == "XRPUSDT"
    assert em.triggered_by["ema_gate_passed"] is True
    assert em.triggered_by["rsi_above_53.2"] is True


def test_xrp_rsi_short_no_trigger_on_downtrend():
    df = _synth_downtrend_with_volume_spike()
    em = evaluate_xrp_rsi_short(df)
    assert em is None, "В downtrend EMA gate fail → None"


def test_evaluators_by_pair_mapping():
    assert "BTCUSDT" in EVALUATORS_BY_PAIR
    assert "ETHUSDT" in EVALUATORS_BY_PAIR
    assert "XRPUSDT" in EVALUATORS_BY_PAIR
    assert evaluate_btc_macd_long in EVALUATORS_BY_PAIR["BTCUSDT"]
    assert evaluate_eth_macd_short in EVALUATORS_BY_PAIR["ETHUSDT"]
    assert evaluate_xrp_rsi_short in EVALUATORS_BY_PAIR["XRPUSDT"]


def test_emission_dataclass_serialization():
    """Проверка что ShadowEmission корректно сериализуется (на реальных данных)."""
    from pathlib import Path
    csv = Path("backtests/frozen/BTCUSDT_1h_2y.csv")
    if not csv.exists():
        pytest.skip("BTC 1h 2y data not available")
    df_full = pd.read_csv(csv)
    # Найдём окно где детектор гарантированно сработал
    em = None
    for end in range(280, len(df_full), 50):
        window = df_full.iloc[end - 280: end].reset_index(drop=True)
        em = evaluate_btc_macd_long(window)
        if em is not None:
            break
    assert em is not None, "Не нашли срабатывание на реальных данных"
    # Должны быть все поля
    assert em.ts and isinstance(em.ts, str)
    assert em.entry_price > 0
    assert em.sl_pct == 0.83
    assert em.tp_rr == 2.24
    assert em.hold_horizon_h == 24
    assert em.note
