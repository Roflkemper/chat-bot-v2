"""Walk-forward validation across all P-15-style edge detectors.

For each detector:
  - Split BTC 1h 2y into 4 folds x 6mo
  - Run signal detection per fold
  - Score signals (forward-return at horizon)
  - Report PnL, PF, Sharpe per fold
  - Verdict: STABLE if 3+/4 folds positive PF>1.5, OVERFIT otherwise

Detectors covered (from setup_detector registry):
  - LONG DIV (multi-divergence base)
  - LONG DIV+BoS w=10 (best of multi-horizon backtest)
  - SHORT DIV (none)
  - SHORT DIV+BoS w=10
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
    score_signals, compute_metrics,
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


def run_fold(df: pd.DataFrame, label: str, horizons: list[int]) -> dict:
    """Score one detector on one fold; return metrics for hold=12h horizon."""
    inds = build_inds(df)
    sigs = detect_multi_divergences(df, inds)
    bull = [s for s in sigs if s.direction == "bullish" and s.confluence >= 2]
    bear = [s for s in sigs if s.direction == "bearish" and s.confluence >= 2]
    bos_signals = detect_bos_signals(df)
    bull_bos_bars = {s.bar_idx for s in bos_signals if s.direction == "bullish"}
    bear_bos_bars = {s.bar_idx for s in bos_signals if s.direction == "bearish"}

    if "long_div" in label:
        sub_setups = bull
    elif "short_div" in label:
        sub_setups = bear
    elif "long_bos" in label:
        sub_setups = [s for s in bull if any((s.bar_idx + o) in bull_bos_bars for o in range(11))]
    elif "short_bos" in label:
        sub_setups = [s for s in bear if any((s.bar_idx + o) in bear_bos_bars for o in range(11))]
    else:
        sub_setups = []

    if not sub_setups:
        return {"label": label, "N": 0, "WR": 0.0, "PF": 0.0, "mean": 0.0}
    scored = score_signals(df, sub_setups, horizons)
    h = 12  # use 12h horizon for verdict
    m = compute_metrics(scored[f"ret_{h}h"])
    return {
        "label": label, "N": len(sub_setups),
        "WR": m["WR_pct"], "PF": m["PF"] if not np.isinf(m["PF"]) else 999.0,
        "mean": m["mean_pct"],
    }


def walk_forward(df: pd.DataFrame, label: str, n_folds: int = 4) -> list[dict]:
    horizons = [1, 4, 12, 24, 48]
    fold_size = len(df) // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else len(df)
        fold_df = df.iloc[start:end].reset_index(drop=True)
        m = run_fold(fold_df, label, horizons)
        m["fold"] = k + 1
        out.append(m)
    return out


def main() -> int:
    print("=" * 100)
    print("WALK-FORWARD VALIDATION FOR ALL DETECTORS (BTC 1h, 2y, 4 folds x 6mo)")
    print("=" * 100)

    df = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)

    detectors = [
        "long_div",         # base bullish divergence
        "long_bos",         # bullish DIV + BoS (best of horizons sim)
        "short_div",        # base bearish divergence
        "short_bos",        # bearish DIV + BoS
    ]

    print(f"{'detector':<20} | {'fold':<5} | {'N':>4} | {'WR%':>5} | {'PF':>6} | {'mean%':>7}")
    print("-" * 70)

    summary = {}
    for det in detectors:
        folds = walk_forward(df, det)
        for f in folds:
            pf_str = f"{f['PF']:.2f}" if f['PF'] < 999 else " inf"
            print(f"{det:<20} | {f['fold']:<5} | {f['N']:>4} | "
                  f"{f['WR']:>5.1f} | {pf_str:>6} | {f['mean']:>+7.3f}")
        positive_folds = sum(1 for f in folds if f["PF"] > 1.5 and f["N"] > 5)
        summary[det] = {"folds": folds, "positive": positive_folds}
        print(f"{'':<20} |  >>> positive folds (PF>1.5, N>5): {positive_folds}/4")
        print()

    print("=" * 100)
    print("VERDICT")
    print("=" * 100)
    for det, s in summary.items():
        verdict = "STABLE" if s["positive"] >= 3 else \
                  "MARGINAL" if s["positive"] >= 2 else "OVERFIT"
        print(f"  {det:<20} -> {verdict} ({s['positive']}/4 folds with PF>1.5)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
