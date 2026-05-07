"""Backtest /advise verdict against historical OHLCV.

Идея: вместо ожидания 2 недели реальных данных, прогнать advisor v2 по
истории — на каждой точке с шагом 4ч получить regime + verdict, через 4ч/24ч
сверить с фактическим движением.

Output:
  state/advise_backtest_<symbol>_<window>.jsonl
  state/advise_backtest_<symbol>_<window>.summary.json (агрегированные метрики)

Запуск:
  python scripts/backtest_advise_history.py --symbol BTCUSDT --days 180

Что считаем как "успех":
  LONG verdict (BULL CONFLUENCE / MACRO BULL): correct если за +4h цена выросла >=0.3%
  SHORT verdict (BEAR CONFLUENCE / MACRO BEAR): correct если за +4h цена упала >=0.3%
  RANGE / БОКОВИК: correct если |move| < 0.5%
  Остальное: оцениваем по 24h-окну отдельно
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.regime_classifier_v2.classify_v2 import ClassifierInputs, classify_bar


def _ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def _atr_pct(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR as % of close."""
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=1).mean()
    return (atr / df["close"]) * 100


def _adx_proxy(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simplified ADX proxy."""
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = ((up > dn) & (up > 0)) * up
    minus_dm = ((dn > up) & (dn > 0)) * dn
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=1).mean()
    plus_di = 100 * (plus_dm.rolling(period, min_periods=1).sum() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(period, min_periods=1).sum() / atr.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period, min_periods=1).mean().fillna(0)


def _bb_width_pct(df: pd.DataFrame, period: int = 20, std_n: float = 2.0) -> pd.Series:
    mid = df["close"].rolling(period, min_periods=1).mean()
    std = df["close"].rolling(period, min_periods=1).std()
    return (2 * std_n * std / mid) * 100


def _enrich_with_indicators(df: pd.DataFrame, tf_label: str) -> pd.DataFrame:
    """Add EMA50/200, ADX proxy, ATR%, BB width%, slope_12h, dist_ema200%."""
    df = df.copy()
    df["ema50"] = _ema(df["close"], 50)
    df["ema200"] = _ema(df["close"], 200)
    df["atr_pct"] = _atr_pct(df, 14)
    df["adx_proxy"] = _adx_proxy(df, 14)
    df["bb_width_pct"] = _bb_width_pct(df, 20)
    df["bb_width_p20_30d"] = df["bb_width_pct"].rolling(30 * 24 if tf_label == "1h" else 30 * 6, min_periods=10).quantile(0.20)

    # slope = % change of ema50 over last 12h (in bars)
    bars_12h = {"15m": 48, "1h": 12, "4h": 3}.get(tf_label, 12)
    df["ema50_slope_pct"] = (df["ema50"] / df["ema50"].shift(bars_12h) - 1) * 100

    # dist to ema200
    df["dist_to_ema200_pct"] = (df["close"] / df["ema200"] - 1) * 100

    # moves
    bars_per_unit = {
        "15m": {"15m": 1, "1h": 4, "4h": 16, "24h": 96},
        "1h": {"15m": None, "1h": 1, "4h": 4, "24h": 24},
        "4h": {"15m": None, "1h": None, "4h": 1, "24h": 6},
    }[tf_label]
    df["move_15m_pct"] = (df["close"] / df["close"].shift(bars_per_unit["15m"]) - 1) * 100 if bars_per_unit["15m"] else np.nan
    df["move_1h_pct"] = (df["close"] / df["close"].shift(bars_per_unit["1h"]) - 1) * 100 if bars_per_unit["1h"] else np.nan
    df["move_4h_pct"] = (df["close"] / df["close"].shift(bars_per_unit["4h"]) - 1) * 100
    df["move_24h_pct"] = (df["close"] / df["close"].shift(bars_per_unit["24h"]) - 1) * 100
    return df


def _row_to_inputs(row: pd.Series) -> ClassifierInputs:
    def _f(v):
        return None if pd.isna(v) else float(v)
    return ClassifierInputs(
        close=float(row["close"]),
        ema50=_f(row.get("ema50")),
        ema200=_f(row.get("ema200")),
        ema50_slope_pct=_f(row.get("ema50_slope_pct")),
        adx_proxy=_f(row.get("adx_proxy")),
        atr_pct_1h=_f(row.get("atr_pct")),
        bb_width_pct=_f(row.get("bb_width_pct")),
        bb_width_p20_30d=_f(row.get("bb_width_p20_30d")),
        move_15m_pct=_f(row.get("move_15m_pct")),
        move_1h_pct=_f(row.get("move_1h_pct")),
        move_4h_pct=_f(row.get("move_4h_pct")),
        move_24h_pct=_f(row.get("move_24h_pct")),
        dist_to_ema200_pct=_f(row.get("dist_to_ema200_pct")),
    )


def _verdict_from_3tf(state_4h: str, state_1h: str, state_15m: str) -> str:
    """Replicate _summary_verdict logic from advisor_v2 (verdict only, no reasons)."""
    is_macro_up = state_4h in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP")
    is_macro_down = state_4h in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN")
    is_micro_up = state_15m in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP")
    is_micro_down = state_15m in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN")

    if not is_macro_up and not is_macro_down:
        return "RANGE"
    if is_macro_up and is_micro_up:
        return "BULL_CONFLUENCE"
    if is_macro_down and is_micro_down:
        return "BEAR_CONFLUENCE"
    if is_macro_up and is_micro_down:
        return "MACRO_BULL_MICRO_PULLBACK"
    if is_macro_down and is_micro_up:
        return "MACRO_BEAR_MICRO_RALLY"
    return "MIXED"


def _verdict_correct(verdict: str, price_then: float, price_4h: float, price_24h: float) -> tuple[bool | None, bool | None]:
    """Return (correct_4h, correct_24h)."""
    move_4h = (price_4h / price_then - 1) * 100
    move_24h = (price_24h / price_then - 1) * 100

    def _eval(v: str, move: float) -> bool | None:
        if v in ("BULL_CONFLUENCE", "MACRO_BULL_MICRO_PULLBACK"):
            return move >= 0.3
        if v in ("BEAR_CONFLUENCE", "MACRO_BEAR_MICRO_RALLY"):
            return move <= -0.3
        if v == "RANGE":
            return abs(move) < 0.5
        return None  # MIXED — нельзя оценить однозначно

    return _eval(verdict, move_4h), _eval(verdict, move_24h)


def run_backtest(symbol: str, days: int, step_hours: int = 4, output_dir: Path = Path("state")) -> dict:
    csv_path = ROOT / "backtests" / "frozen" / f"{symbol}_1h_2y.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No data: {csv_path}")

    df_1h = pd.read_csv(csv_path)
    df_1h["ts"] = pd.to_datetime(df_1h["ts"], unit="ms", utc=True)
    df_1h = df_1h.set_index("ts").sort_index()

    # Take last N days
    cutoff = df_1h.index.max() - timedelta(days=days)
    df_1h = df_1h[df_1h.index >= cutoff].copy()

    # Build resampled 15m and 4h frames from 1h (15m we approximate via 1h → 15m forward-fill won't help;
    # instead use 1h for both 1h and 15m proxy — accepting bias). For 4h: resample.
    # Better approach: use 1h directly for "15m" (small TF proxy) and resample to 4h.
    df_4h = df_1h.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

    # For "15m" we'd need finer data. Use 1h as 15m-proxy (will reduce micro/macro divergence detection).
    df_15m_proxy = df_1h.copy()  # proxy; in production we'd use 1m resampled

    df_1h_e = _enrich_with_indicators(df_1h, "1h")
    df_4h_e = _enrich_with_indicators(df_4h, "4h")
    df_15m_e = _enrich_with_indicators(df_15m_proxy, "1h")  # treated as 15m-proxy with 1h granularity

    # Iterate with step
    results = []
    step_bars_1h = step_hours
    skip_warmup = 200  # need 200 bars for ema200
    indices = df_1h_e.index[skip_warmup::step_bars_1h]

    for ts in indices:
        try:
            row_1h = df_1h_e.loc[ts]
        except KeyError:
            continue
        # 4h: nearest bar <= ts
        row_4h = df_4h_e[df_4h_e.index <= ts].iloc[-1] if (df_4h_e.index <= ts).any() else None
        row_15m = row_1h  # using 1h as 15m proxy

        if row_4h is None or pd.isna(row_4h["ema200"]) or pd.isna(row_1h["ema200"]):
            continue

        state_4h = classify_bar(_row_to_inputs(row_4h))
        state_1h = classify_bar(_row_to_inputs(row_1h))
        state_15m = classify_bar(_row_to_inputs(row_15m))
        verdict = _verdict_from_3tf(state_4h, state_1h, state_15m)

        # Outcome: read price at +4h and +24h
        ts_4h = ts + timedelta(hours=4)
        ts_24h = ts + timedelta(hours=24)
        future_1h = df_1h.loc[df_1h.index <= ts_24h]
        try:
            price_4h = df_1h.loc[df_1h.index <= ts_4h].iloc[-1]["close"] if (df_1h.index <= ts_4h).any() else None
            price_24h = df_1h.loc[df_1h.index <= ts_24h].iloc[-1]["close"] if (df_1h.index <= ts_24h).any() else None
        except IndexError:
            continue

        if price_4h is None or price_24h is None:
            continue

        price_then = float(row_1h["close"])
        correct_4h, correct_24h = _verdict_correct(verdict, price_then, float(price_4h), float(price_24h))
        move_4h = (price_4h / price_then - 1) * 100
        move_24h = (price_24h / price_then - 1) * 100

        results.append({
            "ts": ts.isoformat(),
            "price": round(price_then, 2),
            "state_4h": state_4h,
            "state_1h": state_1h,
            "state_15m_proxy": state_15m,
            "verdict": verdict,
            "price_4h": round(float(price_4h), 2),
            "price_24h": round(float(price_24h), 2),
            "move_4h_pct": round(move_4h, 2),
            "move_24h_pct": round(move_24h, 2),
            "correct_4h": correct_4h,
            "correct_24h": correct_24h,
        })

    # Aggregate metrics
    by_verdict_4h: dict[str, list[bool]] = defaultdict(list)
    by_verdict_24h: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        if r["correct_4h"] is not None:
            by_verdict_4h[r["verdict"]].append(r["correct_4h"])
        if r["correct_24h"] is not None:
            by_verdict_24h[r["verdict"]].append(r["correct_24h"])

    summary = {
        "symbol": symbol,
        "days": days,
        "step_hours": step_hours,
        "total_calls": len(results),
        "verdict_distribution": dict(Counter(r["verdict"] for r in results)),
        "accuracy_4h": {
            v: {
                "n": len(lst),
                "correct": sum(lst),
                "accuracy_pct": round(sum(lst) / len(lst) * 100, 1) if lst else None,
            }
            for v, lst in by_verdict_4h.items()
        },
        "accuracy_24h": {
            v: {
                "n": len(lst),
                "correct": sum(lst),
                "accuracy_pct": round(sum(lst) / len(lst) * 100, 1) if lst else None,
            }
            for v, lst in by_verdict_24h.items()
        },
    }

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_path = output_dir / f"advise_backtest_{symbol}_{days}d.jsonl"
    with detail_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_path = output_dir / f"advise_backtest_{symbol}_{days}d.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--step-hours", type=int, default=4)
    args = p.parse_args()

    summary = run_backtest(args.symbol, args.days, args.step_hours)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
