"""Test "inverted verdict" hypothesis on full history.

Hypothesis: текущий /advise verdict проигрывает (BULL/BEAR_CONFLUENCE accuracy 31-32%).
Если инвертировать — получим 68-69% mean-reversion edge?

Symmetric eval:
  Original BULL_CONFLUENCE → "expect price up" → correct if move >+0.3%
  Inverted BULL_CONFLUENCE → "expect price down" → correct if move <-0.3%

Output: state/advise_inverted_test.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_advise_history import (
    classify_bar, _enrich_with_indicators, _row_to_inputs, _verdict_from_3tf,
)


def _eval_inverted(verdict: str, move_pct: float) -> bool | None:
    """Inverted version: trend confluence -> expect mean reversion."""
    if verdict in ("BULL_CONFLUENCE", "MACRO_BULL_MICRO_PULLBACK"):
        return move_pct < -0.3
    if verdict in ("BEAR_CONFLUENCE", "MACRO_BEAR_MICRO_RALLY"):
        return move_pct > 0.3
    if verdict == "RANGE":
        return abs(move_pct) < 0.5  # same as original
    return None


def _bucket_regime(state_4h: str) -> str:
    if state_4h in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP"):
        return "BULL"
    if state_4h in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN"):
        return "BEAR"
    return "RANGE"


def main(days: int = 785, step_hours: int = 1):
    btc = pd.read_csv(ROOT / "backtests/frozen/BTCUSDT_1h_2y.csv")
    btc["ts"] = pd.to_datetime(btc["ts"], unit="ms", utc=True)
    btc = btc.set_index("ts").sort_index()
    cutoff = btc.index.max() - timedelta(days=days)
    btc = btc[btc.index >= cutoff].copy()
    print(f"Loaded {len(btc)} 1h bars from {btc.index.min()} to {btc.index.max()}")

    df_1h_e = _enrich_with_indicators(btc, "1h")
    df_4h = btc.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    df_4h_e = _enrich_with_indicators(df_4h, "4h")

    skip_warmup = 200
    indices = btc.index[skip_warmup::step_hours]
    print(f"Iterating {len(indices)} timestamps")

    results = defaultdict(lambda: {"original_4h": [], "inverted_4h": [], "original_24h": [], "inverted_24h": []})

    for ts in indices:
        try:
            row_1h = df_1h_e.loc[ts]
        except KeyError:
            continue
        m = df_4h_e.index <= ts
        if not m.any():
            continue
        row_4h = df_4h_e[m].iloc[-1]
        if pd.isna(row_4h["ema200"]) or pd.isna(row_1h["ema200"]):
            continue

        state_4h = classify_bar(_row_to_inputs(row_4h))
        state_1h = classify_bar(_row_to_inputs(row_1h))
        verdict = _verdict_from_3tf(state_4h, state_1h, state_1h)
        regime = _bucket_regime(state_4h)

        # Outcomes
        ts_4h = ts + timedelta(hours=4)
        ts_24h = ts + timedelta(hours=24)
        try:
            p_now = float(btc.loc[ts]["close"])
            p_4h = float(btc.loc[btc.index <= ts_4h].iloc[-1]["close"])
            p_24h = float(btc.loc[btc.index <= ts_24h].iloc[-1]["close"])
        except (IndexError, KeyError):
            continue
        if p_now == 0:
            continue
        move_4h = (p_4h / p_now - 1) * 100
        move_24h = (p_24h / p_now - 1) * 100

        # Original eval
        from scripts.backtest_advise_history import _verdict_correct
        orig_4h, orig_24h = _verdict_correct(verdict, p_now, p_4h, p_24h)
        # Inverted eval
        inv_4h = _eval_inverted(verdict, move_4h)
        inv_24h = _eval_inverted(verdict, move_24h)

        key = f"{verdict}__{regime}"
        if orig_4h is not None:
            results[key]["original_4h"].append(orig_4h)
        if inv_4h is not None:
            results[key]["inverted_4h"].append(inv_4h)
        if orig_24h is not None:
            results[key]["original_24h"].append(orig_24h)
        if inv_24h is not None:
            results[key]["inverted_24h"].append(inv_24h)

    # Compile summary
    summary = {}
    for key, lists in results.items():
        n = len(lists["original_4h"])
        if n < 30:  # minimum sample
            continue
        summary[key] = {
            "n": n,
            "original_4h_acc_pct": round(np.mean(lists["original_4h"]) * 100, 1) if lists["original_4h"] else None,
            "inverted_4h_acc_pct": round(np.mean(lists["inverted_4h"]) * 100, 1) if lists["inverted_4h"] else None,
            "original_24h_acc_pct": round(np.mean(lists["original_24h"]) * 100, 1) if lists["original_24h"] else None,
            "inverted_24h_acc_pct": round(np.mean(lists["inverted_24h"]) * 100, 1) if lists["inverted_24h"] else None,
        }

    out_path = ROOT / "state" / f"advise_inverted_test_{days}d.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}\n")
    print("=== INVERTED VERDICT TEST ===")
    print(f"{'verdict__regime':<40} {'n':>5} {'orig 4h':>9} {'inv 4h':>9} {'orig 24h':>10} {'inv 24h':>9}")
    for key, s in sorted(summary.items()):
        print(f"{key:<40} {s['n']:>5} {s['original_4h_acc_pct']:>8}% {s['inverted_4h_acc_pct']:>8}% {s['original_24h_acc_pct']:>9}% {s['inverted_24h_acc_pct']:>8}%")


if __name__ == "__main__":
    main()
