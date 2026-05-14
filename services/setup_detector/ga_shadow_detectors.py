"""GA-найденные кандидаты-детекторы в shadow-mode.

Найдено 2026-05-14 GA-поиском (Stage E1) — см. docs/GA_CANDIDATES_2026-05-14.md.
Shadow-mode: пишут срабатывания в state/ga_shadow_emissions.jsonl, в TG не отправляют.
Цель: 2 недели forward-валидации перед wire'ом в основной setup_detector.

Три кандидата:
1. BTC LONG  — Пробой вверх на пике MACD-импульса (PF 2.53 STABLE)
2. ETH SHORT — Пробой вниз на дне MACD-импульса (PF 1.59 MARGINAL)
3. XRP SHORT — Шорт от лёгкой перекупленности на тренде (PF 1.64 STABLE)

Все используют 1h timeframe, hold 24h, walk-forward на 2 годах.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

SHADOW_LOG = Path("state/ga_shadow_emissions.jsonl")


@dataclass
class ShadowEmission:
    """Одно срабатывание shadow-детектора."""
    ts: str
    detector_id: str
    detector_name_ru: str
    pair: str
    side: str             # 'long' or 'short'
    entry_price: float
    sl_pct: float
    tp_rr: float
    hold_horizon_h: int
    triggered_by: dict    # {indicator: value, gate: bool, ...}
    note: str = ""


def _ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    ef = close.ewm(span=fast, adjust=False).mean()
    es = close.ewm(span=slow, adjust=False).mean()
    macd_line = ef - es
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line


def _volume_z(volume: pd.Series, lookback: int = 100) -> float:
    """Z-score последнего volume vs последние `lookback` баров."""
    if len(volume) < lookback + 1:
        return 0.0
    window = volume.iloc[-lookback - 1 : -1]
    mu = float(window.mean())
    sigma = float(window.std())
    if sigma == 0:
        return 0.0
    return (float(volume.iloc[-1]) - mu) / sigma


def evaluate_btc_macd_long(df1h: pd.DataFrame) -> Optional[ShadowEmission]:
    """BTC LONG: «Пробой вверх на пике MACD-импульса».

    Условия (из GA, BTC champion PF 2.53 STABLE):
      1. EMA(93) > EMA(251) — долгий uptrend подтверждён
      2. MACD-hist > 75 — сильный bullish momentum уже идёт
      3. Volume z-score > 2.76 — аномально высокий объём (~1 раз в 100 баров)

    ВНИМАНИЕ: порог MACD-hist > 75 — абсолютный, валиден ТОЛЬКО для BTC
    в диапазоне $40k-$200k. При сильной смене масштаба цены порог нужно
    пересчитать через GA. TODO TZ-072: нормализовать MACD-hist в % от цены
    или через z-score, чтобы детектор был устойчив к ценовому масштабу.
    """
    if len(df1h) < 260:
        return None
    close = df1h["close"]
    volume = df1h["volume"]
    ema_fast = _ema(close, 93).iloc[-1]
    ema_slow = _ema(close, 251).iloc[-1]
    macd = _macd_hist(close).iloc[-1]
    vol_z = _volume_z(volume, lookback=100)

    cond_trend = bool(ema_fast > ema_slow)
    cond_macd = bool(macd > 75)
    cond_vol = bool(vol_z > 2.76)
    if not (cond_trend and cond_macd and cond_vol):
        return None

    entry = float(close.iloc[-1])
    return ShadowEmission(
        ts=datetime.now(timezone.utc).isoformat(),
        detector_id="long_macd_momentum_breakout",
        detector_name_ru="Пробой вверх на пике MACD-импульса (LONG)",
        pair="BTCUSDT",
        side="long",
        entry_price=entry,
        sl_pct=0.83,
        tp_rr=2.24,
        hold_horizon_h=24,
        triggered_by={
            "ema_fast_93": float(ema_fast),
            "ema_slow_251": float(ema_slow),
            "macd_hist": float(macd),
            "volume_z_score": float(vol_z),
            "ema_gate_passed": cond_trend,
            "macd_above_75": cond_macd,
            "vol_above_2.76": cond_vol,
        },
        note="GA champion BTC, 2y backtest PF 2.53 (3/4 walk-forward folds)",
    )


def evaluate_eth_macd_short(df1h: pd.DataFrame) -> Optional[ShadowEmission]:
    """ETH SHORT: «Пробой вниз на дне MACD-импульса».

    MARGINAL (только 2/4 fold positive в backtest). Включаем в shadow для накопления
    данных, в production не выводить пока не подтвердится 3+/4 на forward.

    Условия:
      1. EMA(50) < EMA(200) — bearish trend по umolianию ETH-defaults
      2. MACD-hist < 20.1 (отрицательный, сильный bearish momentum)
      3. Volume z-score > 2.0 — аномальный объём
    """
    if len(df1h) < 210:
        return None
    close = df1h["close"]
    volume = df1h["volume"]
    ema_fast = _ema(close, 50).iloc[-1]
    ema_slow = _ema(close, 200).iloc[-1]
    macd = _macd_hist(close).iloc[-1]
    vol_z = _volume_z(volume, lookback=100)

    cond_trend = bool(ema_fast < ema_slow)
    cond_macd = bool(macd < 20.1 and macd < 0)
    cond_vol = bool(vol_z > 2.0)
    if not (cond_trend and cond_macd and cond_vol):
        return None

    entry = float(close.iloc[-1])
    return ShadowEmission(
        ts=datetime.now(timezone.utc).isoformat(),
        detector_id="short_macd_oversold_breakdown",
        detector_name_ru="Пробой вниз на дне MACD-импульса (SHORT, ETH)",
        pair="ETHUSDT",
        side="short",
        entry_price=entry,
        sl_pct=0.77,
        tp_rr=4.0,
        hold_horizon_h=24,
        triggered_by={
            "ema_fast_50": float(ema_fast),
            "ema_slow_200": float(ema_slow),
            "macd_hist": float(macd),
            "volume_z_score": float(vol_z),
            "ema_gate_bear": cond_trend,
            "macd_below_20": cond_macd,
            "vol_above_2.0": cond_vol,
        },
        note="GA candidate ETH, MARGINAL (2/4 folds), wait forward for confirmation",
    )


def evaluate_xrp_rsi_short(df1h: pd.DataFrame) -> Optional[ShadowEmission]:
    """XRP SHORT: «Шорт от лёгкой перекупленности на тренде».

    Условия (из GA, XRP champion PF 1.64 STABLE):
      1. EMA(50) > EMA(200) — на самом деле long-trend по EMA, но шортим откат
      2. RSI(14) > 53.2 — мягкая перекупленность (не классический >70)
      3. Без volume-фильтра (XRP реагирует на сам RSI без подтверждения объёма)
    """
    if len(df1h) < 210:
        return None
    close = df1h["close"]
    ema_fast = _ema(close, 50).iloc[-1]
    ema_slow = _ema(close, 200).iloc[-1]
    rsi_val = _rsi(close).iloc[-1]

    cond_trend = bool(ema_fast > ema_slow)
    cond_rsi = bool(rsi_val > 53.2)
    if not (cond_trend and cond_rsi):
        return None

    entry = float(close.iloc[-1])
    return ShadowEmission(
        ts=datetime.now(timezone.utc).isoformat(),
        detector_id="short_rsi_overbought_xrp",
        detector_name_ru="Шорт от лёгкой перекупленности на тренде (SHORT, XRP)",
        pair="XRPUSDT",
        side="short",
        entry_price=entry,
        sl_pct=0.77,
        tp_rr=3.53,
        hold_horizon_h=24,
        triggered_by={
            "ema_fast_50": float(ema_fast),
            "ema_slow_200": float(ema_slow),
            "rsi_14": float(rsi_val),
            "ema_gate_passed": cond_trend,
            "rsi_above_53.2": cond_rsi,
        },
        note="GA champion XRP, 2y backtest PF 1.64 (3/4 walk-forward folds)",
    )


def write_emission(em: ShadowEmission) -> None:
    """Atomic-ish append в shadow log."""
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": em.ts,
        "detector_id": em.detector_id,
        "detector_name_ru": em.detector_name_ru,
        "pair": em.pair,
        "side": em.side,
        "entry_price": em.entry_price,
        "sl_pct": em.sl_pct,
        "tp_rr": em.tp_rr,
        "hold_horizon_h": em.hold_horizon_h,
        "triggered_by": em.triggered_by,
        "note": em.note,
    }
    with SHADOW_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    logger.info("ga_shadow.fired %s pair=%s entry=%.4f", em.detector_id, em.pair, em.entry_price)


# Mapping pair → applicable evaluators
EVALUATORS_BY_PAIR = {
    "BTCUSDT": [evaluate_btc_macd_long],
    "ETHUSDT": [evaluate_eth_macd_short],
    "XRPUSDT": [evaluate_xrp_rsi_short],
}


def evaluate_all(pair: str, df1h: pd.DataFrame) -> list[ShadowEmission]:
    """Запустить все детекторы для данной пары на её 1h данных."""
    evaluators = EVALUATORS_BY_PAIR.get(pair, [])
    out = []
    for fn in evaluators:
        try:
            em = fn(df1h)
            if em is not None:
                out.append(em)
        except Exception:
            logger.exception("ga_shadow.evaluator_failed pair=%s fn=%s", pair, fn.__name__)
    return out
