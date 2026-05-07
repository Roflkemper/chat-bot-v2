"""Multi-timeframe regime view — classify 4h + 1h + 15m independently.

Reads `data/forecast_features/full_features_1y.parquet` for history +
optionally `market_live/market_1m.csv` for fresh bars.

Output: MultiTimeframeView dataclass with per-TF classification + reasoning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from services.regime_classifier_v2.classify_v2 import (
    ClassifierInputs,
    classify_bar,
    project_3state,
)

logger = logging.getLogger(__name__)

PARQUET_1Y = Path("data/forecast_features/full_features_1y.parquet")
LIVE_1M = Path("market_live/market_1m.csv")


@dataclass
class TimeframeRead:
    timeframe: str
    state_v2: str
    state_3state: str
    last_bar_close: float
    last_bar_ts: str
    indicators: dict


@dataclass
class MultiTimeframeView:
    generated_at: str
    bar_4h: Optional[TimeframeRead]
    bar_1h: Optional[TimeframeRead]
    bar_15m: Optional[TimeframeRead]
    macro_micro_diverge: bool   # True if 4h ≠ 15m at 3-state level


def _load_combined_close() -> pd.Series:
    """Combine 1y parquet history + live 1m for fresh data.

    Returns a 1m-resolution close series (use .resample to get other TFs).
    """
    parts = []
    if PARQUET_1Y.exists():
        df = pd.read_parquet(PARQUET_1Y)[["close"]]
        # parquet is 5m → resample to 1m via forward-fill (gives same close in nested 1m bars)
        # Actually safer: keep as 5m and combine with live 1m later
        df_5m = df.copy()
        df_5m.index = df_5m.index
        parts.append(("5m", df_5m["close"]))
    if LIVE_1M.exists():
        try:
            live = pd.read_csv(LIVE_1M, parse_dates=["ts_utc"]).set_index("ts_utc").sort_index()
            parts.append(("1m", live["close"]))
        except Exception as exc:
            logger.warning("multi_timeframe.live_load_failed: %s", exc)

    if not parts:
        return pd.Series(dtype=float)

    # Strategy: use 5m parquet for history; for any bars after the parquet end,
    # use live 1m resampled to 5m (so we have one consistent 5m series).
    if len(parts) == 1:
        return parts[0][1]

    series_5m = parts[0][1]
    series_1m = parts[1][1]
    # Resample live to 5m last
    live_5m = series_1m.resample("5min").last().dropna()
    # Concat without overlap
    cutoff = series_5m.index[-1]
    fresh = live_5m[live_5m.index > cutoff]
    return pd.concat([series_5m, fresh]).sort_index()


def _compute_tf_indicators(close_5m: pd.Series, tf: str) -> Optional[dict]:
    """Resample to TF and compute indicators for the LAST bar.

    Returns dict ready to feed into ClassifierInputs, or None if insufficient data.
    """
    if tf == "15m":
        rule, ema_lookback = "15min", 200
    elif tf == "1h":
        rule, ema_lookback = "1h", 200
    elif tf == "4h":
        rule, ema_lookback = "4h", 200
    else:
        return None

    series = close_5m.resample(rule).last().dropna()
    if len(series) < 30:
        return None

    ema50 = series.ewm(span=50, adjust=False).mean()
    ema200 = series.ewm(span=min(ema_lookback, len(series)), adjust=False).mean()
    slope = (ema50 - ema50.shift(12)) / ema50.shift(12) * 100
    ret = series.pct_change()
    atr = ret.rolling(14, min_periods=14).std() * 100 * np.sqrt(14)
    bb_mid = series.rolling(20, min_periods=20).mean()
    bb_std = series.rolling(20, min_periods=20).std()
    bb_width = (bb_std * 4) / bb_mid * 100
    bb_width_p20 = bb_width.rolling(720, min_periods=100).quantile(0.20)
    move_24h = (series / series.shift(int(24 * 60 / _tf_minutes(tf))) - 1) * 100
    # Use a single-bar "move_15m"/"move_1h"/"move_4h" appropriate for this TF
    bars_per_15m = max(1, int(15 / _tf_minutes(tf)))
    bars_per_1h = max(1, int(60 / _tf_minutes(tf)))
    bars_per_4h = max(1, int(240 / _tf_minutes(tf)))
    move_15m = (series / series.shift(bars_per_15m) - 1) * 100
    move_1h = (series / series.shift(bars_per_1h) - 1) * 100
    move_4h = (series / series.shift(bars_per_4h) - 1) * 100
    # ADX proxy: |slope| / atr * 25
    adx_proxy = (slope.abs() / atr).clip(0, 4) * 25

    last_ts = series.index[-1]
    return {
        "ts": last_ts,
        "close": float(series.iloc[-1]),
        "ema50": float(ema50.iloc[-1]) if not pd.isna(ema50.iloc[-1]) else None,
        "ema200": float(ema200.iloc[-1]) if not pd.isna(ema200.iloc[-1]) else None,
        "ema50_slope_pct": float(slope.iloc[-1]) if not pd.isna(slope.iloc[-1]) else None,
        "atr_pct": float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None,
        "bb_width_pct": float(bb_width.iloc[-1]) if not pd.isna(bb_width.iloc[-1]) else None,
        "bb_width_p20_30d": float(bb_width_p20.iloc[-1]) if not pd.isna(bb_width_p20.iloc[-1]) else None,
        "move_15m_pct": float(move_15m.iloc[-1]) if not pd.isna(move_15m.iloc[-1]) else None,
        "move_1h_pct": float(move_1h.iloc[-1]) if not pd.isna(move_1h.iloc[-1]) else None,
        "move_4h_pct": float(move_4h.iloc[-1]) if not pd.isna(move_4h.iloc[-1]) else None,
        "move_24h_pct": float(move_24h.iloc[-1]) if not pd.isna(move_24h.iloc[-1]) else None,
        "adx_proxy": float(adx_proxy.iloc[-1]) if not pd.isna(adx_proxy.iloc[-1]) else None,
    }


def _tf_minutes(tf: str) -> int:
    return {"15m": 15, "1h": 60, "4h": 240}.get(tf, 60)


def _classify_tf(close_5m: pd.Series, tf: str) -> Optional[TimeframeRead]:
    ind = _compute_tf_indicators(close_5m, tf)
    if ind is None:
        return None
    dist_ema200 = (
        (ind["close"] - ind["ema200"]) / ind["ema200"] * 100
        if ind["ema200"] else None
    )
    inp = ClassifierInputs(
        close=ind["close"],
        ema50=ind["ema50"],
        ema200=ind["ema200"],
        ema50_slope_pct=ind["ema50_slope_pct"],
        adx_proxy=ind["adx_proxy"],
        atr_pct_1h=ind["atr_pct"],
        bb_width_pct=ind["bb_width_pct"],
        bb_width_p20_30d=ind["bb_width_p20_30d"],
        move_15m_pct=ind["move_15m_pct"],
        move_1h_pct=ind["move_1h_pct"],
        move_4h_pct=ind["move_4h_pct"],
        move_24h_pct=ind["move_24h_pct"],
        dist_to_ema200_pct=dist_ema200,
    )
    state = classify_bar(inp)
    return TimeframeRead(
        timeframe=tf,
        state_v2=state,
        state_3state=project_3state(state),
        last_bar_close=ind["close"],
        last_bar_ts=str(ind["ts"]),
        indicators={
            "ema50": ind["ema50"], "ema200": ind["ema200"],
            "ema50_slope_pct": ind["ema50_slope_pct"],
            "dist_to_ema200_pct": dist_ema200,
            "atr_pct": ind["atr_pct"], "adx_proxy": ind["adx_proxy"],
            "move_24h_pct": ind["move_24h_pct"],
        },
    )


def build_multi_timeframe_view(
    *,
    parquet_1y: Path = PARQUET_1Y,
    live_1m: Path = LIVE_1M,
    now: Optional[datetime] = None,
) -> MultiTimeframeView:
    """Build a multi-TF view from current data sources."""
    now = now or datetime.now(timezone.utc)
    # Override module paths if injected
    global PARQUET_1Y, LIVE_1M
    saved = (PARQUET_1Y, LIVE_1M)
    PARQUET_1Y, LIVE_1M = parquet_1y, live_1m
    try:
        close_5m = _load_combined_close()
    finally:
        PARQUET_1Y, LIVE_1M = saved

    if close_5m.empty:
        return MultiTimeframeView(
            generated_at=now.isoformat(),
            bar_4h=None, bar_1h=None, bar_15m=None,
            macro_micro_diverge=False,
        )

    bar_4h = _classify_tf(close_5m, "4h")
    bar_1h = _classify_tf(close_5m, "1h")
    bar_15m = _classify_tf(close_5m, "15m")

    diverge = False
    if bar_4h and bar_15m:
        diverge = bar_4h.state_3state != bar_15m.state_3state

    return MultiTimeframeView(
        generated_at=now.isoformat(),
        bar_4h=bar_4h, bar_1h=bar_1h, bar_15m=bar_15m,
        macro_micro_diverge=diverge,
    )


# Persistence (TZ-REGIME-V2-PERSIST 2026-05-07)
# Classifier v1 (core/orchestrator/regime_classifier.py) пишет state/regime_state.json
# (3-state RANGE/MARKUP/MARKDOWN с hysteresis). Classifier v2 (10-state per-TF) до
# 2026-05-07 пересчитывался на каждый /advise call без persist'а — нельзя было
# увидеть когда state_v2 переключился (DRIFT_UP → CASCADE_UP среди ночи etc.) и
# не было hysteresis на v2.
#
# Persist в state/regime_v2_state.json:
#   {
#     "version": 1,
#     "last_updated": "2026-05-07T14:00:00Z",
#     "BTCUSDT": {
#       "4h": {"state": "DRIFT_UP", "since": "...", "indicators": {...}, "last_close": ...},
#       "1h": {...},
#       "15m": {...},
#       "macro_micro_diverge": false,
#       "history": [{"ts": "...", "tf": "4h", "from": "RANGE", "to": "DRIFT_UP"}, ...]  # last 50
#     }
#   }
#
# History позволяет видеть переходы за последние ~12-24 часа без анализа всего
# parquet. Используется future Decision Layer hysteresis на v2.

REGIME_V2_STATE_PATH = Path("state/regime_v2_state.json")
HISTORY_MAX = 50


def persist_view(view: MultiTimeframeView, *, symbol: str = "BTCUSDT", path: Path = REGIME_V2_STATE_PATH) -> None:
    """Append-update regime_v2_state.json with current view + transition history.

    Idempotent: если state не изменился — обновляется только last_updated/indicators.
    Если изменился — добавляется запись в history (last 50 transitions).
    """
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        prev = {}

    if not isinstance(prev, dict):
        prev = {}

    sym_prev = prev.get(symbol, {}) if isinstance(prev.get(symbol), dict) else {}
    history = sym_prev.get("history", []) if isinstance(sym_prev.get("history"), list) else []

    new_sym = {
        "macro_micro_diverge": view.macro_micro_diverge,
    }
    transitions = []

    for tf_name, bar in (("4h", view.bar_4h), ("1h", view.bar_1h), ("15m", view.bar_15m)):
        if bar is None:
            new_sym[tf_name] = None
            continue
        old_tf = sym_prev.get(tf_name) if isinstance(sym_prev.get(tf_name), dict) else None
        old_state = old_tf.get("state") if old_tf else None
        new_state = bar.state_v2

        # If state changed → keep "since" as now; else preserve original since.
        if old_tf and old_state == new_state:
            since = old_tf.get("since", view.generated_at)
        else:
            since = view.generated_at
            if old_state is not None:
                transitions.append({
                    "ts": view.generated_at,
                    "tf": tf_name,
                    "from": old_state,
                    "to": new_state,
                })

        new_sym[tf_name] = {
            "state": new_state,
            "state_3state": bar.state_3state,
            "since": since,
            "last_close": bar.last_bar_close,
            "last_bar_ts": bar.last_bar_ts,
            "indicators": bar.indicators,
        }

    # Append transitions, trim to HISTORY_MAX
    history.extend(transitions)
    if len(history) > HISTORY_MAX:
        history = history[-HISTORY_MAX:]
    new_sym["history"] = history

    out = dict(prev) if isinstance(prev, dict) else {}
    out.setdefault("version", 1)
    out["last_updated"] = view.generated_at
    out[symbol] = new_sym

    try:
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("regime_v2.persist_failed path=%s", path)


def build_and_persist_view(*, symbol: str = "BTCUSDT", **kwargs) -> MultiTimeframeView:
    """Convenience: build view and persist in one call."""
    view = build_multi_timeframe_view(**kwargs)
    try:
        persist_view(view, symbol=symbol)
    except Exception:
        logger.exception("regime_v2.persist_failed_in_build_and_persist")
    return view
