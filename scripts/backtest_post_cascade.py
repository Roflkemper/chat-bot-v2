"""Post-liquidation cascade direction backtest.

Hypothesis (selection-based, not all-bars): после крупного liquidation event
(>X BTC за Y минут) рынок имеет direction-bias на 4-12-24h.

Method:
1. Read data/historical/bybit_liquidations_2024.parquet
2. Find cascade windows: 5-min rolling sum of long-side OR short-side liquidations
3. Threshold: cascade = >= 1.0 BTC (medium) and >= 5.0 BTC (large)
4. For each cascade event:
   - Get BTC price at cascade end (BTCUSDT_1h_2y.csv)
   - Measure price move at +1h, +4h, +12h, +24h
5. Aggregate:
   - long_cascade (Sell side = liquidated longs) → does price rebound (squeeze recovery)?
     Or continue down (fundamental selling)?
   - short_cascade (Buy side = liquidated shorts) → does price continue up?

Output:
  state/post_cascade_test.json
  docs/ANALYSIS/POST_LIQUIDATION_CASCADE_2026-05-07.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    print("Loading liquidations...")
    df_liq = pd.read_parquet(ROOT / "data/historical/bybit_liquidations_2024.parquet")
    df_liq["ts"] = pd.to_datetime(df_liq["ts_ms"], unit="ms", utc=True)
    df_liq = df_liq.sort_values("ts")
    print(f"Liquidations: {len(df_liq):,} rows, {df_liq['ts'].min()} to {df_liq['ts'].max()}")

    # Side normalization: Bybit "Buy"/"Sell".
    # "Sell" = liquidated long position (long got rekt, sell-side pressure)
    # "Buy" = liquidated short position (short squeeze buy-side pressure)
    df_liq["side_norm"] = df_liq["side"].str.lower()
    df_liq["is_long_liq"] = df_liq["side_norm"] == "sell"   # long was liquidated
    df_liq["is_short_liq"] = df_liq["side_norm"] == "buy"   # short was liquidated

    # Resample to 5-min sums
    df_liq.set_index("ts", inplace=True)
    long_5m = df_liq[df_liq["is_long_liq"]]["qty"].resample("5min").sum()
    short_5m = df_liq[df_liq["is_short_liq"]]["qty"].resample("5min").sum()

    print("\n=== 5-min liquidation distribution ===")
    print(f"Long-side max 5min sum: {long_5m.max():.2f} BTC")
    print(f"Short-side max 5min sum: {short_5m.max():.2f} BTC")
    print(f"Long-side >= 1 BTC bins: {(long_5m >= 1).sum()}")
    print(f"Long-side >= 5 BTC bins: {(long_5m >= 5).sum()}")
    print(f"Short-side >= 1 BTC bins: {(short_5m >= 1).sum()}")
    print(f"Short-side >= 5 BTC bins: {(short_5m >= 5).sum()}")

    # Load BTC 1h price for outcomes
    print("\nLoading BTC 1h price...")
    btc = pd.read_csv(ROOT / "backtests/frozen/BTCUSDT_1h_2y.csv")
    btc["ts"] = pd.to_datetime(btc["ts"], unit="ms", utc=True)
    btc = btc.set_index("ts").sort_index()
    print(f"BTC 1h: {len(btc):,} rows, {btc.index.min()} to {btc.index.max()}")

    # Filter btc to overlap with liquidations period
    liq_start = df_liq.index.min()
    liq_end = df_liq.index.max()
    btc_overlap = btc[(btc.index >= liq_start) & (btc.index <= liq_end + timedelta(days=2))]
    print(f"BTC overlap: {len(btc_overlap)} hours")

    def _eval_cascades(side_5m: pd.Series, threshold: float, label: str) -> dict:
        """For each 5min bin where threshold reached, measure forward price move."""
        cascades = side_5m[side_5m >= threshold]
        results = []
        for ts_5m, total_qty in cascades.items():
            # ts_5m = end of 5-min bin
            # Find current BTC price at that time
            try:
                price_now_idx = btc.index.searchsorted(ts_5m)
                if price_now_idx >= len(btc):
                    continue
                price_now = float(btc.iloc[price_now_idx]["close"])
            except Exception:
                continue

            outcome = {"ts": ts_5m.isoformat(), "qty_btc": float(total_qty), "price_at_cascade": price_now}

            for hours in (1, 4, 12, 24):
                future_ts = ts_5m + timedelta(hours=hours)
                future_rows = btc[btc.index <= future_ts]
                if len(future_rows) == 0:
                    continue
                price_future = float(future_rows.iloc[-1]["close"])
                move_pct = (price_future / price_now - 1) * 100
                outcome[f"move_{hours}h_pct"] = round(move_pct, 3)
            results.append(outcome)

        if not results:
            return {"n": 0}

        out: dict = {"n": len(results), "label": label, "threshold_btc": threshold}
        for hours in (1, 4, 12, 24):
            moves = [r.get(f"move_{hours}h_pct") for r in results if f"move_{hours}h_pct" in r]
            if not moves:
                continue
            arr = np.array(moves)
            out[f"{hours}h"] = {
                "n": len(moves),
                "mean": round(float(arr.mean()), 3),
                "median": round(float(np.median(arr)), 3),
                "pct_up": round(float((arr > 0).mean() * 100), 1),
                "pct_strong_up": round(float((arr > 0.3).mean() * 100), 1),
                "pct_strong_down": round(float((arr < -0.3).mean() * 100), 1),
                "p25": round(float(np.percentile(arr, 25)), 3),
                "p75": round(float(np.percentile(arr, 75)), 3),
            }
        return out

    print("\n=== POST-CASCADE BACKTEST ===\n")
    summary = {
        "data_window": {"start": str(liq_start), "end": str(liq_end)},
        "total_liquidations": len(df_liq),
        "scenarios": {},
    }

    # Scenarios:
    #   Long cascade (LONG positions liquidated, sell pressure):
    #     hypothesis A: bounce/recovery (squeeze low → +ve move)
    #     hypothesis B: continuation down (fundamental selling)
    #   Short cascade (SHORT positions liquidated, buy pressure):
    #     hypothesis A: continuation up (short squeeze rally)
    #     hypothesis B: pullback (overshoot exhaustion)

    for thresh in (0.5, 1.0, 2.0, 5.0):
        for side_5m, label in ((long_5m, "long_liq"), (short_5m, "short_liq")):
            r = _eval_cascades(side_5m, thresh, f"{label}_{thresh}btc")
            summary["scenarios"][f"{label}_{thresh}btc"] = r

    # Print
    for key, info in summary["scenarios"].items():
        n = info.get("n", 0)
        if n < 5:
            continue
        print(f"--- {key} (n={n}) ---")
        for hours in (1, 4, 12, 24):
            stats = info.get(f"{hours}h", {})
            if stats:
                print(
                    f"  +{hours}h: mean {stats['mean']:+.2f}% | "
                    f"pct_up {stats['pct_up']}% | "
                    f"strong_up {stats['pct_strong_up']}% | "
                    f"strong_down {stats['pct_strong_down']}% | "
                    f"P25/P75 {stats['p25']:+.2f}/{stats['p75']:+.2f}"
                )
        print()

    out_path = ROOT / "state" / "post_cascade_test.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
