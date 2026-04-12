from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from core.data_loader import load_year_klines

CACHE_DIR = Path("state")
YEARS = (2024, 2025, 2026)
TIMEFRAME_YEARS = {
    '1h': (2024, 2025, 2026),
    '4h': (2024, 2025, 2026),
    '1d': (2024, 2025, 2026),
}
WINDOWS = {
    "1h": {"lookback": 24, "horizon": 8, "move_threshold": 0.006},
    "4h": {"lookback": 18, "horizon": 6, "move_threshold": 0.010},
    "1d": {"lookback": 12, "horizon": 5, "move_threshold": 0.018},
}


def _settings(timeframe: str) -> Dict[str, float]:
    return WINDOWS.get(str(timeframe or "1h").lower(), {}).copy()


def _cache_path(symbol: str, timeframe: str, year: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"pattern_memory_{symbol.upper()}_{timeframe}_{year}.csv"


def _ensure_history(symbol: str, timeframe: str, year: int) -> pd.DataFrame:
    path = _cache_path(symbol, timeframe, year)
    if path.exists():
        try:
            df = pd.read_csv(path)
            if not df.empty and {"open_time", "open", "high", "low", "close", "volume"}.issubset(df.columns):
                df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                return df.dropna().reset_index(drop=True)
        except Exception:
            pass

    df = load_year_klines(symbol=symbol, timeframe=timeframe, year=year)
    if not df.empty:
        try:
            df.to_csv(path, index=False)
        except Exception:
            pass
    return df


def _normalize_window(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    if len(close) < 3:
        return np.zeros(18, dtype=float)

    ret = np.diff(close) / np.maximum(close[:-1], 1e-9)
    ret = np.clip(ret, -0.08, 0.08)
    vol = volume / np.maximum(np.nanmedian(volume), 1e-9)
    vol = np.clip(vol, 0.0, 4.0)
    price_path = close / max(close[0], 1e-9) - 1.0
    price_path = np.clip(price_path, -0.12, 0.12)

    buckets = 6
    idx = np.linspace(0, len(price_path) - 1, buckets).round().astype(int)
    sampled_path = price_path[idx]

    ret_idx = np.linspace(0, len(ret) - 1, buckets).round().astype(int)
    sampled_ret = ret[ret_idx]

    vol_idx = np.linspace(0, len(vol) - 1, buckets).round().astype(int)
    sampled_vol = (vol[vol_idx] - 1.0) / 3.0

    vec = np.concatenate([sampled_path, sampled_ret, sampled_vol])
    norm = np.linalg.norm(vec)
    if norm > 1e-9:
        vec = vec / norm
    return vec.astype(float)


def _future_label(future_return: float, move_threshold: float) -> str:
    if future_return >= move_threshold:
        return "UP"
    if future_return <= -move_threshold:
        return "DOWN"
    return "FLAT"


def analyze_history_pattern(df: pd.DataFrame, symbol: str = "BTCUSDT", timeframe: str = "1h") -> Dict[str, Any]:
    tf = str(timeframe or '1h').lower()
    settings = _settings(tf)
    if not settings:
        return {
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "summary": "pattern-memory отключён для быстрого таймфрейма",
            "matched_count": 0,
            "top_matches": [],
            "source_year": None,
            "source_years": [],
            "pattern_scope": "disabled_fast_tf",
            "regime": "FAST_TF_DISABLED",
            "move_style": "fast_tf_disabled",
        }
    years = tuple(TIMEFRAME_YEARS.get(tf, YEARS))

    lookback = int(settings["lookback"])
    horizon = int(settings["horizon"])
    move_threshold = float(settings["move_threshold"])

    if df is None or df.empty or len(df) < lookback + horizon + 5:
        return {
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "summary": "исторический паттерн ещё не готов: мало локальных данных",
            "matched_count": 0,
            "top_matches": [],
            "source_year": None,
            "source_years": list(years),
            "pattern_scope": "recent_multi_cycle",
            "regime": "INSUFFICIENT_LOCAL_DATA",
            "move_style": "unknown",
        }

    current = df.tail(lookback).reset_index(drop=True)
    current_vec = _normalize_window(current["close"].to_numpy(), current["volume"].to_numpy())

    matches: List[Dict[str, Any]] = []
    loaded_years: List[int] = []
    for year in years:
        history = _ensure_history(symbol=symbol, timeframe=timeframe, year=year)
        if history.empty or len(history) < lookback + horizon + 20:
            continue
        loaded_years.append(year)
        closes = history["close"].to_numpy(dtype=float)
        volumes = history["volume"].to_numpy(dtype=float)
        times = pd.to_datetime(history["open_time"], utc=True, errors="coerce")

        for end in range(lookback, len(history) - horizon):
            start = end - lookback
            vec = _normalize_window(closes[start:end], volumes[start:end])
            distance = float(np.linalg.norm(current_vec - vec))
            base = float(closes[end - 1])
            future_price = float(closes[end + horizon - 1])
            future_ret = (future_price - base) / max(base, 1e-9)
            matches.append({
                "distance": distance,
                "future_return": future_ret,
                "label": _future_label(future_ret, move_threshold),
                "date": str(times.iloc[end - 1].date()) if hasattr(times, 'iloc') else str(times[end - 1]),
                "source_year": year,
            })

    if not matches:
        years_text = ", ".join(map(str, years))
        return {
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "summary": f"не удалось собрать историю BTC за {years_text} для pattern-memory",
            "matched_count": 0,
            "top_matches": [],
            "source_year": None,
            "source_years": loaded_years,
            "pattern_scope": "recent_multi_cycle",
            "regime": "HISTORY_UNAVAILABLE",
            "move_style": "unknown",
        }

    matches.sort(key=lambda x: x["distance"])
    top = matches[:18]
    weights = np.array([1.0 / max(m["distance"], 0.05) for m in top], dtype=float)
    up = float(weights[[m["label"] == "UP" for m in top]].sum())
    down = float(weights[[m["label"] == "DOWN" for m in top]].sum())
    flat = float(weights[[m["label"] == "FLAT" for m in top]].sum())
    total = max(up + down + flat, 1e-9)
    bias = (up - down) / total

    if bias >= 0.08:
        direction = "UP"
        confidence = min(0.54 + abs(bias) * 0.34, 0.84)
    elif bias <= -0.08:
        direction = "DOWN"
        confidence = min(0.54 + abs(bias) * 0.34, 0.84)
    else:
        direction = "NEUTRAL"
        confidence = min(0.42 + abs(bias) * 0.20, 0.60)

    avg_future = float(np.average([m["future_return"] for m in top], weights=weights))
    dates = ", ".join(f"{m['date']} ({m['source_year']})" for m in top[:3])
    years_text = ", ".join(map(str, loaded_years or years))

    abs_move = abs(avg_future)
    if flat / total >= 0.52:
        regime = "RANGE_MEAN_REVERSION"
        move_style = "mean_reversion"
    elif abs_move >= move_threshold * 1.8:
        regime = "TREND_CONTINUATION" if direction in {"UP", "DOWN"} else "EXPANSION"
        move_style = "trend_continuation"
    elif abs_move >= move_threshold * 0.9:
        regime = "DIRECTIONAL_BIAS" if direction in {"UP", "DOWN"} else "BALANCED_EXPANSION"
        move_style = "directional_bias"
    else:
        regime = "COMPRESSION" if direction == "NEUTRAL" else "FADE_AFTER_IMPULSE"
        move_style = "compression" if direction == "NEUTRAL" else "fade_after_impulse"

    if direction == "UP":
        summary = (
            f"pattern-memory: похожие участки BTC из {years_text} чаще продолжались вверх; "
            f"средний ход после паттерна {avg_future * 100:.2f}% за {horizon} баров; "
            f"ближайшие совпадения: {dates}"
        )
    elif direction == "DOWN":
        summary = (
            f"pattern-memory: похожие участки BTC из {years_text} чаще уходили вниз; "
            f"средний ход после паттерна {avg_future * 100:.2f}% за {horizon} баров; "
            f"ближайшие совпадения: {dates}"
        )
    else:
        summary = (
            f"pattern-memory: похожие участки BTC из {years_text} не дали чистого перевеса; "
            f"средний ход {avg_future * 100:.2f}% за {horizon} баров; "
            f"ближайшие совпадения: {dates}"
        )

    return {
        "direction": direction,
        "confidence": round(float(confidence), 3),
        "summary": summary,
        "matched_count": len(top),
        "avg_future_return": round(avg_future, 5),
        "top_matches": top[:5],
        "source_year": loaded_years[0] if len(loaded_years) == 1 else None,
        "source_years": loaded_years,
        "pattern_scope": "recent_multi_cycle",
        "lookback_bars": lookback,
        "horizon_bars": horizon,
        "regime": regime,
        "move_style": move_style,
    }
