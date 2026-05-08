"""15m setups backtest — LONG and SHORT, with and without BoS confirmation.

Goal: find tradeable setups on 15m timeframe for the operator's manual
trading workflow. They want fast-reaction signals, both directions.

We test 4 variants:
  1. LONG DIV solo (no BoS confirmation)
  2. LONG DIV + BoS within +N bars
  3. SHORT DIV solo
  4. SHORT DIV + BoS within +N bars

For each: forward returns at 15m, 1h, 4h, 12h horizons.

Walk-forward (4 folds of ~6mo) afterwards on whichever variant passes the
edge bar (PF >= 1.3, WR >= 55%, N >= 50).
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

DATA_15M = Path("backtests/frozen/BTCUSDT_15m_2y.csv")


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


def print_metrics(label: str, scored: pd.DataFrame, horizons: list[int], horizon_labels: list[str]) -> None:
    print(f"\n  {label}  (N={len(scored)})")
    print(f"    {'horizon':>6} | {'WR%':>5} | {'PF':>6} | {'mean%':>7} | verdict")
    for h, hl in zip(horizons, horizon_labels):
        m = compute_metrics(scored[f"ret_{h}h"])
        pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        v = edge_verdict(m)
        print(f"    {hl:>6} | {m['WR_pct']:>5.1f} | {pf_str:>6} | {m['mean_pct']:>+7.3f} | {v}")


def main() -> int:
    print("=" * 90)
    print("15m BACKTEST — LONG and SHORT divergence variants (BTCUSDT 2y)")
    print("=" * 90)
    df = pd.read_csv(DATA_15M).reset_index(drop=True)
    print(f"  bars: {len(df)}")

    inds = build_inds(df)
    sigs = detect_multi_divergences(df, inds)
    bull = [s for s in sigs if s.direction == "bullish" and s.confluence >= 2]
    bear = [s for s in sigs if s.direction == "bearish" and s.confluence >= 2]

    bos_signals = detect_bos_signals(df)
    bull_bos_bars = {s.bar_idx for s in bos_signals if s.direction == "bullish"}
    bear_bos_bars = {s.bar_idx for s in bos_signals if s.direction == "bearish"}

    horizons = [1, 4, 16, 48]   # 15m, 1h, 4h, 12h
    horizon_labels = ["15m", "1h", "4h", "12h"]

    print("\n--- LONG DIV solo (no BoS) ---")
    sub = score_signals(df, bull, horizons)
    print_metrics(f"LONG DIV solo conf>=2", sub, horizons, horizon_labels)

    print("\n--- LONG DIV + BoS ---")
    for win in (10, 20):
        confluent = [s for s in bull if any((s.bar_idx + o) in bull_bos_bars for o in range(0, win + 1))]
        sub = score_signals(df, confluent, horizons)
        print_metrics(f"LONG DIV+BoS win={win}bars ({win*15}min)", sub, horizons, horizon_labels)

    print("\n--- SHORT DIV solo (no BoS) ---")
    sub = score_signals(df, bear, horizons)
    print_metrics(f"SHORT DIV solo conf>=2", sub, horizons, horizon_labels)

    print("\n--- SHORT DIV + BoS ---")
    for win in (10, 20):
        confluent = [s for s in bear if any((s.bar_idx + o) in bear_bos_bars for o in range(0, win + 1))]
        sub = score_signals(df, confluent, horizons)
        print_metrics(f"SHORT DIV+BoS win={win}bars ({win*15}min)", sub, horizons, horizon_labels)

    # ── WALK-FORWARD on 4 folds for both directions ─────────────────────────
    n = len(df)
    fold_size = n // 4

    def run_wf(direction: str, win: int) -> None:
        print()
        print("=" * 90)
        print(f"WALK-FORWARD: 4 folds x ~6mo each ({direction.upper()} DIV+BoS win={win})")
        print("=" * 90)
        for i in range(4):
            start = i * fold_size
            end = (i + 1) * fold_size if i < 3 else n
            sub_df = df.iloc[start:end].reset_index(drop=True)
            sub_inds = build_inds(sub_df)
            sub_sigs = detect_multi_divergences(sub_df, sub_inds)
            wanted_dir = direction
            sub_dir = [s for s in sub_sigs if s.direction == wanted_dir and s.confluence >= 2]
            sub_bos_signals = detect_bos_signals(sub_df)
            sub_bos = {s.bar_idx for s in sub_bos_signals if s.direction == wanted_dir}
            sub_confluent = [s for s in sub_dir if any((s.bar_idx + o) in sub_bos for o in range(0, win + 1))]
            if not sub_confluent:
                print(f"\n  Fold {i+1}: NO SIGNALS")
                continue
            sub_scored = score_signals(sub_df, sub_confluent, horizons)
            ts_start = pd.to_datetime(sub_df["ts"].iloc[0], unit="ms")
            ts_end = pd.to_datetime(sub_df["ts"].iloc[-1], unit="ms")
            m_h1 = compute_metrics(sub_scored["ret_4h"])
            m_h4 = compute_metrics(sub_scored["ret_16h"])
            m_h12 = compute_metrics(sub_scored["ret_48h"])
            pf1 = f"{m_h1['PF']:.2f}" if not np.isinf(m_h1['PF']) else " inf"
            pf4 = f"{m_h4['PF']:.2f}" if not np.isinf(m_h4['PF']) else " inf"
            pf12 = f"{m_h12['PF']:.2f}" if not np.isinf(m_h12['PF']) else " inf"
            print(f"\n  Fold {i+1} {ts_start.strftime('%Y-%m')} -> {ts_end.strftime('%Y-%m')}: N={len(sub_confluent):>3}")
            print(f"    1h:  WR={m_h1['WR_pct']:>5.1f}% PF={pf1}  mean={m_h1['mean_pct']:+.3f}%")
            print(f"    4h:  WR={m_h4['WR_pct']:>5.1f}% PF={pf4}  mean={m_h4['mean_pct']:+.3f}%")
            print(f"    12h: WR={m_h12['WR_pct']:>5.1f}% PF={pf12}  mean={m_h12['mean_pct']:+.3f}%")

    run_wf("bullish", 20)
    run_wf("bearish", 10)   # tighter window for SHORT (best in baseline run)
    run_wf("bearish", 20)

    return 0


if __name__ == "__main__":
    sys.exit(main())
