"""SHORT 1h divergence on bear-only segments — TZ-2 of large batch.

Earlier full-2y backtest (commit 02330b5) showed 1h SHORT divergence had
PF<1 across the board. Hypothesis: that's because 2y was bull-biased —
SHORTs got run over by uptrends. If we restrict to bear-regime segments
only, SHORT divergence might have edge.

We use compute_regime (50/200 EMA on 1h) to tag each bar's regime, then:
  1. Detect SHORT DIV signals (with and without BoS) globally
  2. Filter to those that fired during regime=trend_down or impulse_down
  3. Compute forward returns at 1h, 4h, 12h
  4. Walk-forward across 4 folds (full 2y, since regime distribution shifts)

Comparison: full-2y baseline vs bear-segments-only.
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
    compute_regime,
    PIVOT_LOOKBACK, RSI_PERIOD,
)

DATA_1H = Path("backtests/frozen/BTCUSDT_1h_2y.csv")


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
    print(f"    {'h':>4} | {'WR%':>5} | {'PF':>6} | {'mean%':>7} | verdict")
    for h in horizons:
        m = compute_metrics(scored[f"ret_{h}h"])
        pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        v = edge_verdict(m)
        print(f"    {h:>4} | {m['WR_pct']:>5.1f} | {pf_str:>6} | {m['mean_pct']:>+7.3f} | {v}")


def main() -> int:
    print("=" * 90)
    print("SHORT 1h on bear-only segments (BTCUSDT 2y)")
    print("=" * 90)

    df = pd.read_csv(DATA_1H).reset_index(drop=True)
    print(f"  bars: {len(df)}")

    regime = compute_regime(df, 50, 200)
    bear_mask = regime.isin(["trend_down", "impulse_down"])
    range_mask = regime == "range"
    bull_mask = regime.isin(["trend_up", "impulse_up"])
    print(f"  bear bars: {bear_mask.sum()} ({bear_mask.sum() / len(df) * 100:.1f}%)")
    print(f"  range bars: {range_mask.sum()} ({range_mask.sum() / len(df) * 100:.1f}%)")
    print(f"  bull bars: {bull_mask.sum()} ({bull_mask.sum() / len(df) * 100:.1f}%)")

    inds = build_inds(df)
    sigs = detect_multi_divergences(df, inds)
    bear_sigs = [s for s in sigs if s.direction == "bearish" and s.confluence >= 2]

    bos_signals = detect_bos_signals(df)
    bear_bos_bars = {s.bar_idx for s in bos_signals if s.direction == "bearish"}

    horizons = [1, 4, 12]

    # ── Baseline: all bear DIV signals (full 2y, all regimes) ──
    print("\n=== BASELINE: SHORT DIV solo (all regimes) ===")
    sub = score_signals(df, bear_sigs, horizons)
    report("SHORT DIV all regimes", sub, horizons)

    # ── Filter by regime at signal bar ──
    print("\n=== SHORT DIV solo, filtered by regime at signal bar ===")
    for label, mask in [("bear regime", bear_mask), ("range regime", range_mask), ("bull regime", bull_mask)]:
        filtered = [s for s in bear_sigs if mask.iloc[s.bar_idx]]
        if not filtered:
            print(f"\n  {label}: no signals")
            continue
        sub = score_signals(df, filtered, horizons)
        report(f"SHORT DIV in {label}", sub, horizons)

    # ── DIV+BoS variant (the strong recipe from prior work) ──
    print("\n=== SHORT DIV+BoS within +10 bars, filtered by regime ===")
    confluent = [s for s in bear_sigs if any((s.bar_idx + o) in bear_bos_bars for o in range(0, 11))]
    print(f"\n  total DIV+BoS confluent (all regimes): N={len(confluent)}")

    for label, mask in [("bear regime", bear_mask), ("range regime", range_mask), ("bull regime", bull_mask)]:
        filtered = [s for s in confluent if mask.iloc[s.bar_idx]]
        if not filtered:
            print(f"\n  {label}: no signals")
            continue
        sub = score_signals(df, filtered, horizons)
        report(f"SHORT DIV+BoS in {label}", sub, horizons)

    # ── Walk-forward (4 folds), restricted to bear regime ──
    print("\n=== WALK-FORWARD: SHORT DIV+BoS in bear regime only (4 folds) ===")
    n = len(df)
    fold_size = n // 4
    for i in range(4):
        start = i * fold_size
        end = (i + 1) * fold_size if i < 3 else n
        sub_df = df.iloc[start:end].reset_index(drop=True)
        sub_regime = compute_regime(sub_df, 50, 200)
        sub_bear = sub_regime.isin(["trend_down", "impulse_down"])
        sub_inds = build_inds(sub_df)
        sub_sigs = detect_multi_divergences(sub_df, sub_inds)
        sub_bear_sigs = [s for s in sub_sigs if s.direction == "bearish" and s.confluence >= 2]
        sub_bos = {s.bar_idx for s in detect_bos_signals(sub_df) if s.direction == "bearish"}
        sub_confluent = [s for s in sub_bear_sigs if any((s.bar_idx + o) in sub_bos for o in range(0, 11))]
        sub_in_bear = [s for s in sub_confluent if sub_bear.iloc[s.bar_idx]]
        ts_start = pd.to_datetime(sub_df["ts"].iloc[0], unit="ms")
        ts_end = pd.to_datetime(sub_df["ts"].iloc[-1], unit="ms")
        if not sub_in_bear:
            print(f"\n  Fold {i+1} {ts_start.strftime('%Y-%m')} -> {ts_end.strftime('%Y-%m')}: NO bear signals")
            continue
        sub_scored = score_signals(sub_df, sub_in_bear, horizons)
        m_h1 = compute_metrics(sub_scored["ret_1h"])
        m_h4 = compute_metrics(sub_scored["ret_4h"])
        m_h12 = compute_metrics(sub_scored["ret_12h"])
        pf1 = f"{m_h1['PF']:.2f}" if not np.isinf(m_h1['PF']) else " inf"
        pf4 = f"{m_h4['PF']:.2f}" if not np.isinf(m_h4['PF']) else " inf"
        pf12 = f"{m_h12['PF']:.2f}" if not np.isinf(m_h12['PF']) else " inf"
        print(f"\n  Fold {i+1} {ts_start.strftime('%Y-%m')} -> {ts_end.strftime('%Y-%m')}: N={len(sub_in_bear)}")
        print(f"    1h:  WR={m_h1['WR_pct']:>5.1f}% PF={pf1}  mean={m_h1['mean_pct']:+.3f}%")
        print(f"    4h:  WR={m_h4['WR_pct']:>5.1f}% PF={pf4}  mean={m_h4['mean_pct']:+.3f}%")
        print(f"    12h: WR={m_h12['WR_pct']:>5.1f}% PF={pf12}  mean={m_h12['mean_pct']:+.3f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
