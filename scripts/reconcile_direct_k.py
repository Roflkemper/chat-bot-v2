"""Run reconcile_v3 in direct_k mode now that 1s OHLCV covers the full GA window.

Computes K factor per (config, horizon) by simulating each ground-truth GA bot
on 1s OHLCV across the GA period and comparing realized PnL to GA actuals.

Usage:
    python scripts/reconcile_direct_k.py
    python scripts/reconcile_direct_k.py --json data/calibration/reconcile_direct_k_<ts>.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.calibration.reconcile_v3 import (
    DEFAULT_GT_PATH, DEFAULT_OHLCV_1S, DEFAULT_OHLCV_1M,
    csv_span_iso, check_direct_k_feasible, load_ga_points, k_factor,
)
from services.calibration.sim import load_ohlcv_bars, run_sim


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None,
                    help="Output JSON path (default: data/calibration/reconcile_direct_k_<ts>.json)")
    args = ap.parse_args()

    t0 = time.time()

    gt = json.loads(DEFAULT_GT_PATH.read_text(encoding="utf-8"))
    ga_period = (gt["period"]["start"] + "T00:00:00+00:00",
                 gt["period"]["end"] + "T23:59:59+00:00")

    span_1s = csv_span_iso(DEFAULT_OHLCV_1S)
    print(f"GA period:   {ga_period[0]} -> {ga_period[1]}")
    print(f"1s span:     {span_1s[0]} -> {span_1s[1]}")

    ok, reason = check_direct_k_feasible(ga_period, span_1s, min_coverage_pct=95.0)
    print(f"Feasibility: {'OK' if ok else 'BLOCKED'} ({reason})")
    if not ok:
        print("ABORTED: 1s OHLCV does not cover GA period sufficiently.")
        return 1

    ga_points = load_ga_points()
    print(f"GA points:   {len(ga_points)} configs "
          f"({sum(1 for p in ga_points if p.side == 'SHORT')} SHORT, "
          f"{sum(1 for p in ga_points if p.side == 'LONG')} LONG)")

    print(f"Loading 1s bars from {DEFAULT_OHLCV_1S} ...")
    t_load = time.time()
    bars_1s = load_ohlcv_bars(DEFAULT_OHLCV_1S, ga_period[0], ga_period[1])
    print(f"  loaded {len(bars_1s):,} bars in {time.time()-t_load:.1f}s")

    if not bars_1s:
        print("ABORTED: empty bar set after window filter.")
        return 1

    results: list[dict] = []
    print("\nRunning sims:")
    for i, p in enumerate(ga_points, 1):
        t_sim = time.time()
        sim = run_sim(
            bars_1s, p.side, p.order_size, p.grid_step_pct,
            p.target_pct, p.max_orders, mode="raw",
        )
        K = k_factor(p.ga_realized, sim.realized_pnl)
        elapsed_sim = time.time() - t_sim
        results.append({
            "bot_id": p.bot_id,
            "side": p.side,
            "target_pct": p.target_pct,
            "ga_realized": p.ga_realized,
            "sim_realized": sim.realized_pnl,
            "K": K,
            "sim_secs": round(elapsed_sim, 2),
        })
        print(f"  [{i}/{len(ga_points)}] {p.bot_id} {p.side} t={p.target_pct:.3f} "
              f"GA={p.ga_realized:,.2f} sim={sim.realized_pnl:,.2f} K={K:.4f} ({elapsed_sim:.1f}s)")

    # Aggregates by side
    aggregates: dict[str, dict] = {}
    for side in ("SHORT", "LONG"):
        ks = [r["K"] for r in results if r["side"] == side and not math.isnan(r["K"])]
        if not ks:
            aggregates[side] = {"n": 0, "K_mean": None, "K_cv_pct": None, "notes": "no usable K"}
            continue
        mean = statistics.fmean(ks)
        std = statistics.pstdev(ks) if len(ks) > 1 else 0.0
        cv = (std / abs(mean) * 100) if mean != 0 else None
        aggregates[side] = {
            "n": len(ks),
            "K_mean": round(mean, 4),
            "K_median": round(statistics.median(ks), 4),
            "K_std": round(std, 4),
            "K_cv_pct": round(cv, 2) if cv is not None else None,
            "K_min": round(min(ks), 4),
            "K_max": round(max(ks), 4),
        }

    print("\n=== AGGREGATES BY SIDE ===")
    for side, agg in aggregates.items():
        if agg.get("n", 0) == 0:
            print(f"  {side}: no usable K factor")
            continue
        print(f"  {side}: n={agg['n']}  K_mean={agg['K_mean']}  median={agg['K_median']}  "
              f"CV={agg['K_cv_pct']}%  range=[{agg['K_min']}, {agg['K_max']}]")

    # Persist JSON
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.json) if args.json else Path("data/calibration") / f"reconcile_direct_k_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "ga_period": ga_period,
        "ohlcv_1s_span": span_1s,
        "n_bars": len(bars_1s),
        "n_configs": len(ga_points),
        "results": results,
        "aggregates": aggregates,
        "elapsed_secs": round(time.time() - t0, 1),
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nReport: {out}")
    print(f"Wall-clock: {time.time() - t0:.1f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
