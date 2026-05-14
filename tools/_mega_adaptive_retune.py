"""Mega-pair adaptive re-tune walk-forward.

P-15 adaptive re-tune gave +117% over fixed. Try same approach for mega-pair:
re-tune SL/TP_RR/window every 30 days based on best params on previous 60d.

Approach (analogous to _p15_rolling_retune.py):
  1. Walk in 60d-train / 30d-test windows over 815d data.
  2. At each rebalance: grid search best (SL_pct, TP1_RR, window_min) on
     past 60d using mega-pair triggers.
  3. Apply those to next 30d test, accumulate PnL.
  4. Compare:
     A) FIXED baseline (SL=0.8%, TP1=2.5RR, window=240min)
     B) ADAPTIVE re-tuned every 30d
  5. Verdict: does mega-pair benefit from adaptive params?

Output: docs/STRATEGIES/MEGA_ADAPTIVE_RETUNE.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, _simulate_trade, DATA_1M,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "MEGA_ADAPTIVE_RETUNE.md"

LOOKBACK_DAYS = 815
TRAIN_DAYS = 60
TEST_DAYS = 30
WINDOW_MIN_GRID = [30, 60, 90]   # confluence window between constituents
DEDUP_HOURS = 4

# Mega-pair trade parameter grids
SL_GRID = [0.5, 0.6, 0.8, 1.0]
TP1_RR_GRID = [1.5, 2.0, 2.5, 3.0]

BASELINE_SL = 0.8
BASELINE_TP1_RR = 2.5
BASELINE_WINDOW_MIN = 60

CONSTITUENTS = ("detect_long_dump_reversal", "detect_long_pdl_bounce")


def _build_triggers(emits, df_1m, sl_pct, tp1_rr, window_min):
    """Find mega triggers with given window, return trade dicts with given SL/TP."""
    dump = emits.get("detect_long_dump_reversal", [])
    pdl = emits.get("detect_long_pdl_bounce", [])
    if not dump or not pdl:
        return []
    window_ms = window_min * 60 * 1000
    dedup_ms = DEDUP_HOURS * 3600 * 1000
    triggers = []
    last = None
    tp2_rr = tp1_rr * 2
    for p in pdl:
        if last is not None and (p["ts"] - last) < dedup_ms:
            continue
        nearby = [d for d in dump if abs(d["ts"] - p["ts"]) <= window_ms]
        if not nearby: continue
        dump_match = max(nearby, key=lambda d: d["ts"])
        trigger_ts = max(p["ts"], dump_match["ts"])
        idx = int(np.searchsorted(df_1m["ts"].values, trigger_ts, side="right")) - 1
        if idx < 0 or idx >= len(df_1m): continue
        entry = float(df_1m["close"].iloc[idx])
        if entry <= 0: continue
        triggers.append({
            "bar_idx": idx, "ts": trigger_ts, "side": "long",
            "setup_type": "mega_long", "entry": entry,
            "sl": entry * (1 - sl_pct / 100),
            "tp1": entry * (1 + sl_pct * tp1_rr / 100),
            "tp2": entry * (1 + sl_pct * tp2_rr / 100),
            "window_min": 240,
        })
        last = trigger_ts
    return triggers


def _eval(emits, df_1m, sl, tp1_rr, window_min):
    trigs = _build_triggers(emits, df_1m, sl, tp1_rr, window_min)
    if not trigs:
        return {"n": 0, "pnl_pct": 0.0, "pf": 0.0}
    trades_pnl = []
    for t in trigs:
        r = _simulate_trade(t, df_1m)
        trades_pnl.append(r.pnl_pct)
    if not trades_pnl:
        return {"n": 0, "pnl_pct": 0.0, "pf": 0.0}
    arr = np.array(trades_pnl)
    wins = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    pf = (wins / losses) if losses > 0 else (999.0 if wins > 0 else 0.0)
    return {
        "n": len(trades_pnl),
        "pnl_pct": float(arr.sum()),
        "pf": float(pf),
    }


def _grid_search_window(emits_train, df_1m_train):
    """Find best (sl, tp1_rr, window_min) on training emits."""
    best = (BASELINE_SL, BASELINE_TP1_RR, BASELINE_WINDOW_MIN)
    best_pnl = -float("inf")
    for sl in SL_GRID:
        for rr in TP1_RR_GRID:
            for w in WINDOW_MIN_GRID:
                e = _eval(emits_train, df_1m_train, sl, rr, w)
                if e["n"] < 3: continue
                if e["pnl_pct"] > best_pnl:
                    best_pnl = e["pnl_pct"]
                    best = (sl, rr, w)
    return best


def _slice_emits_by_bar_range(emits, start_bar, end_bar):
    """Filter dict-of-list emits to within [start_bar, end_bar) range."""
    out = {}
    for name, lst in emits.items():
        out[name] = [e for e in lst if start_bar <= e["bar_idx"] < end_bar]
    return out


def main() -> int:
    print(f"[mega-retune] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    df_15m, df_1h = _build_aggregations(df_1m)

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    detectors = {fn.__name__: fn for fn in DETECTOR_REGISTRY if fn.__name__ in CONSTITUENTS}

    print("[mega-retune] emitting constituents (full period)...")
    emits = {}
    for name, fn in detectors.items():
        e = _emit_setups(fn, df_1m, df_15m, df_1h, freq_bars=60)
        emits[name] = e
        print(f"  {name}: {len(e)} emits")

    bars_per_day = 1440  # 1m
    train_bars = TRAIN_DAYS * bars_per_day
    test_bars = TEST_DAYS * bars_per_day

    rebalance_points = []
    start = train_bars
    while start + test_bars <= len(df_1m):
        rebalance_points.append(start)
        start += test_bars
    print(f"[mega-retune] {len(rebalance_points)} rebalance windows")

    rows = []
    fixed_total = 0.0
    adaptive_total = 0.0
    for idx, rb in enumerate(rebalance_points):
        train_emits = _slice_emits_by_bar_range(emits, rb - train_bars, rb)
        test_emits = _slice_emits_by_bar_range(emits, rb, rb + test_bars)

        # Grid search on train
        sl, rr, w = _grid_search_window(train_emits, df_1m)
        adaptive_test = _eval(test_emits, df_1m, sl, rr, w)
        fixed_test = _eval(test_emits, df_1m, BASELINE_SL, BASELINE_TP1_RR, BASELINE_WINDOW_MIN)

        fixed_total += fixed_test["pnl_pct"]
        adaptive_total += adaptive_test["pnl_pct"]

        rows.append({
            "win": idx + 1,
            "test_start": str(pd.to_datetime(int(df_1m["ts"].iloc[rb]), unit="ms", utc=True))[:10],
            "tuned_sl": sl, "tuned_rr": rr, "tuned_window_min": w,
            "adaptive_n": adaptive_test["n"],
            "adaptive_pnl%": round(adaptive_test["pnl_pct"], 2),
            "fixed_n": fixed_test["n"],
            "fixed_pnl%": round(fixed_test["pnl_pct"], 2),
            "delta": round(adaptive_test["pnl_pct"] - fixed_test["pnl_pct"], 2),
        })
        print(f"  win {idx+1}: tuned sl={sl} rr={rr} w={w} | "
              f"adapt {adaptive_test['pnl_pct']:.2f}% / fixed {fixed_test['pnl_pct']:.2f}%")

    df_out = pd.DataFrame(rows)
    delta_pct = ((adaptive_total / fixed_total - 1) * 100) if fixed_total else 0

    md = []
    md.append("# Mega-pair adaptive re-tune walk-forward")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d | **Train:** {TRAIN_DAYS}d | **Test:** {TEST_DAYS}d rolling")
    md.append(f"**Fixed baseline:** SL={BASELINE_SL}%, TP1_RR={BASELINE_TP1_RR}, "
              f"window={BASELINE_WINDOW_MIN}min")
    md.append(f"**Grid:** SL∈{SL_GRID}, RR∈{TP1_RR_GRID}, window∈{WINDOW_MIN_GRID}")
    md.append("")
    md.append("## Per-window")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Summary")
    md.append("")
    md.append(f"- **Fixed total PnL:** {fixed_total:.2f}%")
    md.append(f"- **Adaptive total PnL:** {adaptive_total:.2f}%")
    md.append(f"- **Delta:** {adaptive_total-fixed_total:+.2f}pp ({delta_pct:+.1f}%)")
    md.append("")
    md.append("## Verdict")
    md.append("")
    if delta_pct >= 30:
        md.append(f"✅ **Adaptive re-tune adds {delta_pct:+.1f}%.** Wire weekly auto-tuner "
                  f"for mega-pair params (analogous to P-15 D3).")
    elif delta_pct >= 5:
        md.append(f"🟡 **Marginal +{delta_pct:.1f}%.** Re-tune helps slightly.")
    elif delta_pct >= -5:
        md.append(f"⚪ **Roughly equal.** Mega-pair fixed params robust enough.")
    else:
        md.append(f"❌ **Adaptive WORSE by {abs(delta_pct):.1f}%.** Grid search overfits "
                  f"60d train. Keep fixed params.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[mega-retune] wrote {OUT_MD}")
    print(f"[mega-retune] fixed ${fixed_total:.2f}% | adaptive ${adaptive_total:.2f}% "
          f"| delta {delta_pct:+.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
