"""Multi-horizon backtest — TZ-MULTI-HORIZON-BACKTEST from PENDING_TZ.

Hypothesis: maybe direction-edge exists at horizons we haven't tested.
Default sweep so far: 1h, 4h, 12h. Adding 24h and 48h may reveal slower
mean-reversion edges that don't appear short-term.

Tests both LONG and SHORT divergence (with/without BoS) on 1h BTC 2y across
five horizons: 1h, 4h, 12h, 24h, 48h.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_signals import (  # noqa: E402
    rsi, mfi, obv, cmf, macd_hist, stoch,
    detect_multi_divergences, detect_bos_signals,
    score_signals, compute_metrics, edge_verdict,
    PIVOT_LOOKBACK, RSI_PERIOD,
)


def build_inds(df: pd.DataFrame) -> dict[str, pd.Series]:
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    mfv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl * df["volume"]
    return {
        "RSI":      rsi(df["close"], RSI_PERIOD),
        "MFI":      mfi(df["high"], df["low"], df["close"], df["volume"], 14),
        "OBV":      obv(df["close"], df["volume"]),
        "CMF":      cmf(df["high"], df["low"], df["close"], df["volume"], 20),
        "MACDh":    macd_hist(df["close"], 12, 26, 9),
        "Stoch":    stoch(df["high"], df["low"], df["close"], 14, 3),
        "DeltaCum": mfv.cumsum(),
    }


def report(label: str, scored: pd.DataFrame, horizons: list[int]) -> None:
    print(f"\n  {label}  (N={len(scored)})")
    print(f"    {'h':>4} | {'WR%':>5} | {'PF':>6} | {'mean%':>7} | {'median%':>8} | verdict")
    for h in horizons:
        m = compute_metrics(scored[f"ret_{h}h"])
        pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        v = edge_verdict(m)
        print(f"    {h:>4} | {m['WR_pct']:>5.1f} | {pf_str:>6} | {m['mean_pct']:>+7.3f} | {m['median_pct']:>+8.3f} | {v}")


def main() -> int:
    print("=" * 90)
    print("MULTI-HORIZON BACKTEST (BTCUSDT 1h, 2y, horizons 1/4/12/24/48 h)")
    print("=" * 90)
    df = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    print(f"  bars: {len(df)}")

    inds = build_inds(df)
    sigs = detect_multi_divergences(df, inds)
    bull = [s for s in sigs if s.direction == "bullish" and s.confluence >= 2]
    bear = [s for s in sigs if s.direction == "bearish" and s.confluence >= 2]
    bos_signals = detect_bos_signals(df)
    bull_bos_bars = {s.bar_idx for s in bos_signals if s.direction == "bullish"}
    bear_bos_bars = {s.bar_idx for s in bos_signals if s.direction == "bearish"}

    horizons = [1, 4, 12, 24, 48]

    print("\n=== LONG DIV solo ===")
    sub = score_signals(df, bull, horizons)
    report("LONG DIV", sub, horizons)

    print("\n=== LONG DIV+BoS within +10 bars ===")
    confluent_bull_10 = [s for s in bull if any((s.bar_idx + o) in bull_bos_bars for o in range(0, 11))]
    sub = score_signals(df, confluent_bull_10, horizons)
    report("LONG DIV+BoS w=10", sub, horizons)

    print("\n=== SHORT DIV solo ===")
    sub = score_signals(df, bear, horizons)
    report("SHORT DIV", sub, horizons)

    print("\n=== SHORT DIV+BoS within +10 bars ===")
    confluent_bear_10 = [s for s in bear if any((s.bar_idx + o) in bear_bos_bars for o in range(0, 11))]
    sub = score_signals(df, confluent_bear_10, horizons)
    report("SHORT DIV+BoS w=10", sub, horizons)

    return 0


if __name__ == "__main__":
    sys.exit(main())
