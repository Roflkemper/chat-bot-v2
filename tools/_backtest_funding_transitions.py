"""Funding sign-change as a signal — backtest 2026-05-08.

Hypothesis: when funding flips sign (neg->pos = shorts capitulating, pos->neg
= longs capitulating), price moves in the direction implied by the new
sign of funding (or opposite — we test both).

Funding history: _recovery/restored/scripts/frozen/BTCUSDT/_combined_fundingRate.parquet
Coverage: 2025-03-01 -> 2026-03-31 (13mo, 1188 funding events at 8h interval).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_signals import compute_metrics  # noqa: E402


FUND_PATH = Path("_recovery/restored/scripts/frozen/BTCUSDT/_combined_fundingRate.parquet")
OHLCV_PATH = Path("backtests/frozen/BTCUSDT_1h_2y.csv")


def main() -> int:
    fund = pd.read_parquet(FUND_PATH).sort_values("calc_time").reset_index(drop=True)
    fund["calc_time"] = pd.to_datetime(fund["calc_time"], utc=True)
    fund["sign"] = np.sign(fund["last_funding_rate"])

    df = pd.read_csv(OHLCV_PATH).reset_index(drop=True)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    closes = df["close"].values

    # Find sign-change events (only true flips, ignore zero-crossings via 0).
    flips = []
    prev_sign = None
    for i, row in fund.iterrows():
        s = row["sign"]
        if s == 0:
            continue
        if prev_sign is not None and s != prev_sign:
            flips.append({
                "ts": row["calc_time"],
                "from_sign": prev_sign,
                "to_sign": s,
                "rate": row["last_funding_rate"],
            })
        prev_sign = s

    print(f"Funding flips found: {len(flips)}")
    print(f"Funding coverage: {fund['calc_time'].iloc[0]} -> {fund['calc_time'].iloc[-1]}")
    print(f"OHLCV coverage:   {df['dt'].iloc[0]} -> {df['dt'].iloc[-1]}")

    # For each flip, find the bar at the flip time and compute forward returns.
    horizons_h = [1, 4, 8, 24]
    results = {f"to_pos_h{h}": [] for h in horizons_h}
    results.update({f"to_neg_h{h}": [] for h in horizons_h})

    df_indexed = df.set_index("dt")["close"]

    for flip in flips:
        ts = flip["ts"]
        # Find nearest bar >= ts
        future_idx = df_indexed.index.searchsorted(ts, side="left")
        if future_idx >= len(df_indexed):
            continue
        entry = float(df_indexed.iloc[future_idx])
        for h in horizons_h:
            target_idx = future_idx + h
            if target_idx >= len(df_indexed):
                continue
            future_price = float(df_indexed.iloc[target_idx])
            # Direction-aware: neg->pos means shorts gave up -> expect price up
            #                   pos->neg means longs gave up   -> expect price down
            if flip["to_sign"] > 0:
                ret = (future_price - entry) / entry * 100.0
                results[f"to_pos_h{h}"].append(ret)
            else:
                # If flip to negative, "win" means price drops
                ret = (entry - future_price) / entry * 100.0
                results[f"to_neg_h{h}"].append(ret)

    print()
    print("=" * 90)
    print("FUNDING SIGN-CHANGE -> forward returns (direction-aware)")
    print("Hypothesis: neg->pos shorts capitulate (price up); pos->neg longs capitulate (down)")
    print("=" * 90)
    print(f"  {'pattern':<24} | {'horizon':>8} | {'N':>4} | {'WR%':>5} | {'PF':>6} | {'mean%':>7} | {'median%':>8}")
    print("  " + "-" * 80)
    for pattern in ("to_pos", "to_neg"):
        for h in horizons_h:
            key = f"{pattern}_h{h}"
            rets = pd.Series(results[key]).dropna()
            m = compute_metrics(rets)
            pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
            label = "neg->pos (longs+)" if pattern == "to_pos" else "pos->neg (shorts+)"
            print(f"  {label:<24} | h{h}  ({h}h) | {m['N']:>4} | {m['WR_pct']:>5.1f} | {pf_str:>5} | {m['mean_pct']:>+7.3f} | {m['median_pct']:>+8.3f}")

    # Counter-hypothesis: maybe flips actually mark continuation, not reversal.
    # Re-run with reversed direction expectation.
    print()
    print("=" * 90)
    print("COUNTER: maybe flip means CONTINUATION (price keeps going same way)")
    print("=" * 90)
    counter_results = {f"counter_h{h}": [] for h in horizons_h}
    for flip in flips:
        ts = flip["ts"]
        future_idx = df_indexed.index.searchsorted(ts, side="left")
        if future_idx >= len(df_indexed):
            continue
        entry = float(df_indexed.iloc[future_idx])
        for h in horizons_h:
            target_idx = future_idx + h
            if target_idx >= len(df_indexed):
                continue
            future_price = float(df_indexed.iloc[target_idx])
            # Counter-direction: neg->pos means actually price down (continuation of recent dump)
            if flip["to_sign"] > 0:
                ret = (entry - future_price) / entry * 100.0
            else:
                ret = (future_price - entry) / entry * 100.0
            counter_results[f"counter_h{h}"].append(ret)

    print(f"  {'horizon':>8} | {'N':>4} | {'WR%':>5} | {'PF':>6} | {'mean%':>7}")
    for h in horizons_h:
        rets = pd.Series(counter_results[f"counter_h{h}"]).dropna()
        m = compute_metrics(rets)
        pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        print(f"  h{h}  ({h:>2}h)| {m['N']:>4} | {m['WR_pct']:>5.1f} | {pf_str:>5} | {m['mean_pct']:>+7.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
