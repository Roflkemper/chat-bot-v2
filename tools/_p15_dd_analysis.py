"""P-15 drawdown analysis (TZ #4, 2026-05-10).

Adaptive re-tune gives +117% PnL but we never measured DD properly.
Compute equity curve + max DD per window for both fixed and adaptive,
identify worst windows for sizing decisions.

Output: docs/STRATEGIES/P15_DD_ANALYSIS.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_p15_honest_v2 import simulate_p15_harvest  # noqa: E402

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "P15_DD_ANALYSIS.md"

# Same as rolling_retune
TRAIN_DAYS = 60
TEST_DAYS = 30
R_GRID = [0.2, 0.3, 0.4, 0.5]
K_GRID = [0.5, 1.0, 1.5, 2.0]
DD_GRID = [2.0, 3.0, 4.0]
BASELINE_R, BASELINE_K, BASELINE_DD = 0.3, 1.0, 3.0


def _build_15m(df_1m):
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts_utc").resample("15min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()


def _eval(df, R, K, dd):
    short = simulate_p15_harvest(df, R_pct=R, K_pct=K, dd_cap_pct=dd, direction="short")
    long_ = simulate_p15_harvest(df, R_pct=R, K_pct=K, dd_cap_pct=dd, direction="long")
    return {
        "pnl": short.realized_pnl_usd + long_.realized_pnl_usd,
        "max_dd": min(short.max_drawdown_usd, long_.max_drawdown_usd),
        "min_n": min(short.n_trades, long_.n_trades),
    }


def _grid_search(df_train):
    best = None
    best_pnl = -float("inf")
    for R in R_GRID:
        for K in K_GRID:
            for dd in DD_GRID:
                e = _eval(df_train, R, K, dd)
                if e["min_n"] < 5: continue
                if e["pnl"] > best_pnl:
                    best_pnl = e["pnl"]
                    best = (R, K, dd)
    return best or (BASELINE_R, BASELINE_K, BASELINE_DD)


def main() -> int:
    print("[p15-dd] loading 2y 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m["ts_utc"] = pd.to_datetime(df_1m["ts"], unit="ms", utc=True)
    df_15m = _build_15m(df_1m)
    print(f"[p15-dd] {len(df_15m):,} 15m bars")

    bars_per_day = 96
    train_bars = TRAIN_DAYS * bars_per_day
    test_bars = TEST_DAYS * bars_per_day

    rebalance_points = []
    start = train_bars
    while start + test_bars <= len(df_15m):
        rebalance_points.append(start)
        start += test_bars

    rows = []
    fixed_equity = 0.0
    adaptive_equity = 0.0
    fixed_peak = 0.0
    adaptive_peak = 0.0
    fixed_dd_running = 0.0  # running max DD
    adaptive_dd_running = 0.0

    for idx, rb in enumerate(rebalance_points):
        train = df_15m.iloc[rb - train_bars:rb].reset_index(drop=True)
        test = df_15m.iloc[rb:rb + test_bars].reset_index(drop=True)
        if len(train) < 100 or len(test) < 100: continue

        R, K, dd = _grid_search(train)
        adaptive = _eval(test, R, K, dd)
        fixed = _eval(test, BASELINE_R, BASELINE_K, BASELINE_DD)

        fixed_equity += fixed["pnl"]
        adaptive_equity += adaptive["pnl"]
        fixed_peak = max(fixed_peak, fixed_equity)
        adaptive_peak = max(adaptive_peak, adaptive_equity)
        fixed_running = fixed_peak - fixed_equity
        adaptive_running = adaptive_peak - adaptive_equity
        fixed_dd_running = max(fixed_dd_running, fixed_running)
        adaptive_dd_running = max(adaptive_dd_running, adaptive_running)

        rows.append({
            "window": idx + 1,
            "test_start": str(test["ts_utc"].iloc[0])[:10],
            "fixed_pnl$": round(fixed["pnl"], 0),
            "fixed_max_dd_in_win$": round(fixed["max_dd"], 0),
            "fixed_equity$": round(fixed_equity, 0),
            "fixed_dd_so_far$": round(fixed_running, 0),
            "adaptive_pnl$": round(adaptive["pnl"], 0),
            "adaptive_max_dd_in_win$": round(adaptive["max_dd"], 0),
            "adaptive_equity$": round(adaptive_equity, 0),
            "adaptive_dd_so_far$": round(adaptive_running, 0),
            "adaptive_R": R, "adaptive_K": K, "adaptive_dd": dd,
        })

    df_out = pd.DataFrame(rows)

    # Summary stats
    fixed_total = fixed_equity
    adaptive_total = adaptive_equity
    fixed_max_dd = -df_out["fixed_max_dd_in_win$"].min()  # max DD across windows
    adaptive_max_dd = -df_out["adaptive_max_dd_in_win$"].min()
    fixed_max_dd_overall = fixed_dd_running
    adaptive_max_dd_overall = adaptive_dd_running

    # MAR ratio (CAGR / max DD) — risk-adjusted return
    fixed_mar = (fixed_total / fixed_max_dd_overall) if fixed_max_dd_overall > 0 else 0
    adaptive_mar = (adaptive_total / adaptive_max_dd_overall) if adaptive_max_dd_overall > 0 else 0

    # Worst window
    worst_fixed = df_out.loc[df_out["fixed_pnl$"].idxmin()]
    worst_adaptive = df_out.loc[df_out["adaptive_pnl$"].idxmin()]

    md = []
    md.append("# P-15 drawdown analysis")
    md.append("")
    md.append(f"**Period:** ~2y BTC | **Train:** {TRAIN_DAYS}d | **Test:** {TEST_DAYS}d rolling")
    md.append("")
    md.append("## Summary")
    md.append("")
    md.append(f"| Metric | FIXED | ADAPTIVE |")
    md.append(f"|---|---:|---:|")
    md.append(f"| Total PnL | ${fixed_total:.0f} | ${adaptive_total:.0f} |")
    md.append(f"| Max DD (single window) | ${fixed_max_dd:.0f} | ${adaptive_max_dd:.0f} |")
    md.append(f"| Max DD (running, peak-to-trough) | ${fixed_max_dd_overall:.0f} | "
              f"${adaptive_max_dd_overall:.0f} |")
    md.append(f"| MAR ratio (PnL / max DD) | {fixed_mar:.2f} | {adaptive_mar:.2f} |")
    md.append(f"| Worst window | win {int(worst_fixed['window'])} ({worst_fixed['test_start']}) "
              f"${worst_fixed['fixed_pnl$']:.0f} | win {int(worst_adaptive['window'])} "
              f"({worst_adaptive['test_start']}) ${worst_adaptive['adaptive_pnl$']:.0f} |")
    md.append("")
    md.append("## Per-window detail")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Sizing recommendation")
    md.append("")

    # If max DD overall is X, a sane sizing is to keep risk capital at 3x DD
    safe_capital_fixed = fixed_max_dd_overall * 3
    safe_capital_adaptive = adaptive_max_dd_overall * 3
    md.append(f"For risk-of-ruin <1%, allocate at least **3× max DD** as risk capital:")
    md.append(f"- FIXED needs ${safe_capital_fixed:.0f} (max DD ${fixed_max_dd_overall:.0f})")
    md.append(f"- ADAPTIVE needs ${safe_capital_adaptive:.0f} (max DD ${adaptive_max_dd_overall:.0f})")
    md.append("")
    md.append("With base_size=$1000, that's the minimum free margin operator should "
              "have available to run P-15 without margin call risk.")
    md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[p15-dd] wrote {OUT_MD}")
    print(f"\nFixed: total ${fixed_total:.0f}, max DD ${fixed_max_dd_overall:.0f}, MAR {fixed_mar:.2f}")
    print(f"Adapt: total ${adaptive_total:.0f}, max DD ${adaptive_max_dd_overall:.0f}, MAR {adaptive_mar:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
