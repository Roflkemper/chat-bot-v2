"""P-15 rolling re-tune walk-forward (TZ #1, 2026-05-10).

Question: P-15 fixed params (R=0.3, K=1.0, dd=3.0) gave +$24k/2y honest.
What if every 30 days we re-tune R/K/dd on last 30d (like our weekly auto-tuner
does live)? Does adaptive re-tune add +30-50% PnL or eat the edge?

Approach:
  1. Fix train_window=60d, test_window=30d.
  2. Sliding window over 2y of 1m data:
     - At each rebalance point: grid search best (R, K, dd_cap) on last 60d
     - Apply those params to next 30d test
     - Sum PnL across all test windows
  3. Compare:
     A) FIXED baseline (R=0.3, K=1.0, dd=3.0) over full period
     B) ADAPTIVE re-tuned every 30d
  4. Output verdict.

Note: this is a SLOW backtest — 2y / 30d = 24 rebalance points × grid search
~50 combos = ~1200 simulations. ~10-30 min compute.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# NOTE: don't reopen stdout — _backtest_p15_honest_v2 does it on import.
from _backtest_p15_honest_v2 import simulate_p15_harvest  # noqa: E402

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "P15_ROLLING_RETUNE.md"

# Grid (smaller than auto-tuner to keep compute reasonable)
R_GRID = [0.2, 0.3, 0.4, 0.5]
K_GRID = [0.5, 1.0, 1.5, 2.0]
DD_GRID = [2.0, 3.0, 4.0]

TRAIN_DAYS = 60
TEST_DAYS = 30
BASELINE_R, BASELINE_K, BASELINE_DD = 0.3, 1.0, 3.0


def _build_15m_from_1m(df_1m: pd.DataFrame) -> pd.DataFrame:
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts_utc").resample("15min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()


def _eval(df_15m, R, K, dd):
    """Return combined (short+long) realized PnL."""
    short = simulate_p15_harvest(df_15m, R_pct=R, K_pct=K, dd_cap_pct=dd, direction="short")
    long_ = simulate_p15_harvest(df_15m, R_pct=R, K_pct=K, dd_cap_pct=dd, direction="long")
    return {
        "pnl": short.realized_pnl_usd + long_.realized_pnl_usd,
        "short_n": short.n_trades,
        "long_n": long_.n_trades,
        "min_n": min(short.n_trades, long_.n_trades),
    }


def _grid_search(df_train) -> tuple:
    """Find best (R, K, dd) on train window."""
    best = None
    best_pnl = -float("inf")
    for R in R_GRID:
        for K in K_GRID:
            for dd in DD_GRID:
                e = _eval(df_train, R, K, dd)
                if e["min_n"] < 5:
                    continue
                if e["pnl"] > best_pnl:
                    best_pnl = e["pnl"]
                    best = (R, K, dd)
    return best or (BASELINE_R, BASELINE_K, BASELINE_DD)


def main() -> int:
    print(f"[retune] loading 2y 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m["ts_utc"] = pd.to_datetime(df_1m["ts"], unit="ms", utc=True)
    print(f"[retune] {len(df_1m):,} bars  ({df_1m['ts_utc'].iloc[0]} → {df_1m['ts_utc'].iloc[-1]})")

    df_15m = _build_15m_from_1m(df_1m)
    print(f"[retune] {len(df_15m):,} 15m bars")

    total_days = (df_15m["ts_utc"].iloc[-1] - df_15m["ts_utc"].iloc[0]).days
    print(f"[retune] total span: {total_days} days")

    # We need at least train+test
    bars_per_day = 96  # 24h × 4 (15m)
    train_bars = TRAIN_DAYS * bars_per_day
    test_bars = TEST_DAYS * bars_per_day

    if len(df_15m) < train_bars + test_bars:
        print(f"[retune] not enough data for one rebalance"); return 1

    # Walk through rebalance points
    rebalance_points = []
    start = train_bars
    while start + test_bars <= len(df_15m):
        rebalance_points.append(start)
        start += test_bars
    print(f"[retune] {len(rebalance_points)} rebalance points")

    adaptive_pnl_total = 0.0
    fixed_pnl_total = 0.0
    rows = []

    for idx, rb in enumerate(rebalance_points):
        train = df_15m.iloc[rb - train_bars:rb].reset_index(drop=True)
        test = df_15m.iloc[rb:rb + test_bars].reset_index(drop=True)
        if len(train) < 100 or len(test) < 100:
            continue
        R, K, dd = _grid_search(train)
        # Apply best params to test
        adaptive_eval = _eval(test, R, K, dd)
        fixed_eval = _eval(test, BASELINE_R, BASELINE_K, BASELINE_DD)
        adaptive_pnl_total += adaptive_eval["pnl"]
        fixed_pnl_total += fixed_eval["pnl"]
        rows.append({
            "window": idx + 1,
            "test_start": str(test["ts_utc"].iloc[0])[:10],
            "test_end": str(test["ts_utc"].iloc[-1])[:10],
            "tuned_R": R, "tuned_K": K, "tuned_dd": dd,
            "adaptive_pnl$": round(adaptive_eval["pnl"], 0),
            "fixed_pnl$": round(fixed_eval["pnl"], 0),
            "delta$": round(adaptive_eval["pnl"] - fixed_eval["pnl"], 0),
            "adaptive_min_n": adaptive_eval["min_n"],
        })
        print(f"  win {idx+1}: tuned R={R} K={K} dd={dd} | adaptive=${adaptive_eval['pnl']:.0f} "
              f"fixed=${fixed_eval['pnl']:.0f} Δ=${adaptive_eval['pnl']-fixed_eval['pnl']:.0f}")

    df_out = pd.DataFrame(rows)
    print(f"\n[retune] FIXED total: ${fixed_pnl_total:.0f}")
    print(f"[retune] ADAPTIVE total: ${adaptive_pnl_total:.0f}")
    print(f"[retune] DELTA: ${adaptive_pnl_total - fixed_pnl_total:.0f} "
          f"({(adaptive_pnl_total/fixed_pnl_total - 1)*100:+.1f}%)" if fixed_pnl_total else "")

    md = []
    md.append(f"# P-15 rolling re-tune walk-forward")
    md.append("")
    md.append(f"**Period:** ~2y BTC 15m honest engine")
    md.append(f"**Train window:** {TRAIN_DAYS}d  |  **Test window:** {TEST_DAYS}d (rolling)")
    md.append(f"**Fixed baseline:** R={BASELINE_R}, K={BASELINE_K}, dd={BASELINE_DD}")
    md.append(f"**Grid:** R∈{R_GRID}, K∈{K_GRID}, dd∈{DD_GRID}")
    md.append("")
    md.append(f"## Per-window results")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Summary")
    md.append("")
    md.append(f"- **Fixed baseline total:** ${fixed_pnl_total:.0f}")
    md.append(f"- **Adaptive re-tune total:** ${adaptive_pnl_total:.0f}")
    delta_pct = ((adaptive_pnl_total / fixed_pnl_total - 1) * 100) if fixed_pnl_total else 0
    md.append(f"- **Delta:** ${adaptive_pnl_total - fixed_pnl_total:+.0f} ({delta_pct:+.1f}%)")
    md.append("")
    md.append("## Verdict")
    md.append("")
    if delta_pct >= 30:
        md.append(f"✅ **Adaptive re-tune adds {delta_pct:+.1f}%.** Auto-tuner (D3) approach validated. "
                  f"Operator should consider lower threshold for accepting tuner suggestions.")
    elif delta_pct >= 5:
        md.append(f"🟡 **Marginal improvement {delta_pct:+.1f}%.** Re-tune helps but compute overhead may "
                  f"not justify.")
    elif delta_pct >= -5:
        md.append(f"⚪ **Roughly equal ({delta_pct:+.1f}%).** Fixed params are robust enough; re-tune "
                  f"offers no edge but no harm. Auto-tuner can stay as a sanity check.")
    else:
        md.append(f"❌ **Adaptive WORSE by {abs(delta_pct):.1f}%.** Grid-search overfits 60d train and "
                  f"underperforms fixed params on out-of-sample. Auto-tuner should NOT auto-apply suggestions.")
    md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[retune] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
