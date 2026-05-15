"""Range Hunter signal detection — pure, тестируемая логика.

Соответствует scripts/range_hunter_backtest.py (мак-колега), но переписана
под live use:
- работает на DataFrame с 1m OHLCV (можно скармливать market_live/market_1m.csv)
- compute_signal(window, params) → bool (тот же контракт)
- build_signal_card(...) — собирает payload для TG/journal
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class RangeHunterParams:
    """Фильтры ренжа + параметры сделки."""
    # Фильтр-индикаторы
    lookback_h: int = 4            # окно для range/ATR/trend
    range_max_pct: float = 0.70    # max-min за lookback < этого %
    atr_pct_max: float = 0.10      # средний 1m TR в % < этого
    trend_max_pct_per_h: float = 0.10  # |slope| < этого %/час
    cooldown_h: int = 2            # после сигнала пауза N часов

    # Параметры размещения (вшиваются в карточку)
    width_pct: float = 0.10        # ±0.10% от mid
    hold_h: int = 6                # окно жизни сделки
    stop_loss_pct: float = 0.20    # SL при single-leg
    size_usd: float = 10_000.0     # размер каждой ноги
    contract: str = "XBTUSDT"      # linear


@dataclass
class RangeHunterSignal:
    """Подготовленный сигнал для TG-карточки и журнала."""
    ts: str                        # ISO ts when computed
    mid: float                     # current BTC price
    buy_level: float               # mid * (1 - width_pct/100)
    sell_level: float              # mid * (1 + width_pct/100)
    stop_loss_pct: float           # 0.20%
    hold_h: int                    # 6h
    size_usd: float                # 10000
    contract: str                  # XBTUSDT

    # Фильтр-показатели в момент сигнала (для журнала)
    range_4h_pct: float
    atr_pct: float
    trend_pct_per_h: float

    # Размеры в native (для удобства копи-паста)
    size_btc: float                # size_usd / mid

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_PARAMS = RangeHunterParams()


def _trend_pct_per_h(window: pd.DataFrame) -> float:
    """Linear-regression slope, нормализован к %/час.

    Возвращает signed slope (положительный = вверх).
    """
    if len(window) < 2:
        return 0.0
    closes = window["close"].values.astype(float)
    x = np.arange(len(closes), dtype=float)
    slope = np.polyfit(x, closes, 1)[0]  # USD per minute
    mid = float(closes[-1])
    return float(slope * 60.0 / mid * 100.0)  # convert to %/hr


def _range_pct(window: pd.DataFrame) -> float:
    """(high.max - low.min) / mid * 100"""
    hi = float(window["high"].max())
    lo = float(window["low"].min())
    mid = float(window["close"].iloc[-1])
    if mid <= 0:
        return float("inf")
    return (hi - lo) / mid * 100.0


def _atr_pct(window: pd.DataFrame) -> float:
    """Mean (high - low) / mid * 100. Дешёвая прокси ATR на 1m."""
    mid = float(window["close"].iloc[-1])
    if mid <= 0:
        return float("inf")
    tr = (window["high"] - window["low"]).values.astype(float)
    return float(np.mean(tr) / mid * 100.0)


def compute_signal(window: pd.DataFrame, params: RangeHunterParams = DEFAULT_PARAMS
                   ) -> Optional[RangeHunterSignal]:
    """Проверяет фильтры на хвосте окна. Возвращает Signal или None.

    window: DataFrame с колонками [high, low, close], индекс monotonically.
    Минимальная длина — lookback_h * 60 баров (4h × 60 = 240).
    """
    needed = params.lookback_h * 60
    if len(window) < needed:
        return None
    tail = window.iloc[-needed:]

    range_pct = _range_pct(tail)
    if range_pct > params.range_max_pct:
        return None

    atr_pct = _atr_pct(tail)
    if atr_pct > params.atr_pct_max:
        return None

    trend = _trend_pct_per_h(tail)
    if abs(trend) > params.trend_max_pct_per_h:
        return None

    mid = float(tail["close"].iloc[-1])
    if mid <= 0:
        return None
    buy_level = mid * (1.0 - params.width_pct / 100.0)
    sell_level = mid * (1.0 + params.width_pct / 100.0)
    size_btc = params.size_usd / mid

    # Используем индекс последнего бара, если есть timestamp; иначе now
    last_ts = tail.index[-1]
    if isinstance(last_ts, (pd.Timestamp, datetime)):
        ts_iso = pd.Timestamp(last_ts).tz_localize("UTC").isoformat() \
            if pd.Timestamp(last_ts).tz is None else pd.Timestamp(last_ts).isoformat()
    else:
        ts_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return RangeHunterSignal(
        ts=ts_iso,
        mid=round(mid, 2),
        buy_level=round(buy_level, 2),
        sell_level=round(sell_level, 2),
        stop_loss_pct=params.stop_loss_pct,
        hold_h=params.hold_h,
        size_usd=params.size_usd,
        contract=params.contract,
        range_4h_pct=round(range_pct, 4),
        atr_pct=round(atr_pct, 4),
        trend_pct_per_h=round(trend, 4),
        size_btc=round(size_btc, 6),
    )


def format_tg_card(sig: RangeHunterSignal, *, expected_pair_win: float = 0.685,
                   avg_win: float = 24.0, avg_loss: float = -25.5,
                   expiry_ts: Optional[datetime] = None) -> str:
    """Строит готовый текст TG-сообщения для копи-паста в BitMEX.

    expected_pair_win/avg_win/avg_loss — из walk-forward (68.5% WR).
    """
    if expiry_ts is None:
        expiry_ts = datetime.now(timezone.utc) + pd.Timedelta(hours=sig.hold_h)
    expiry_str = expiry_ts.strftime("%H:%M UTC")

    sl_usd = sig.size_usd * sig.stop_loss_pct / 100.0
    ev = expected_pair_win * avg_win + (1 - expected_pair_win) * avg_loss

    lines = [
        f"🎯 RANGE HUNTER signal",
        f"BTC mid: ${sig.mid:,.0f}",
        "Условия выполнены:",
        f"  range_4h: {sig.range_4h_pct:.2f}% (порог ≤{0.70:.2f}%)",
        f"  ATR_1m:   {sig.atr_pct:.2f}% (порог ≤{0.10:.2f}%)",
        f"  trend:    {sig.trend_pct_per_h:+.2f}%/ч (порог ≤{0.10:.2f}%)",
        "",
        f"📋 Ставь 2 лимитки (post-only) на {sig.contract}:",
        f"  BUY:  ${sig.buy_level:,.2f}   (-{0.10:.2f}%)",
        f"  SELL: ${sig.sell_level:,.2f}   (+{0.10:.2f}%)",
        f"  Размер: ${sig.size_usd:,.0f} (≈{sig.size_btc:.3f} BTC) каждая",
        "",
        f"⏱️ Окно жизни: до {expiry_str} (+{sig.hold_h}h)",
        f"🛑 Stop: при единичном fill — закрыть при ходе {sig.stop_loss_pct:.2f}% против (≈${sl_usd:.0f})",
        "",
        f"Ожидание:",
        f"  {expected_pair_win*100:.0f}% оба fill = +${avg_win:.1f}",
        f"  {(1-expected_pair_win)*100:.0f}% single → SL = ${avg_loss:.1f}",
        f"EV: ${ev:+.2f} на сигнал",
    ]
    return "\n".join(lines)
