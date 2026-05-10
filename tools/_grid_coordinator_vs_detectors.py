"""Grid coordinator vs setup detectors — co-firing analysis around reversals.

Question: when grid_coordinator emits a high-confidence exhaustion signal
(score>=4), which OTHER detectors fire within ±N minutes? Are they
correlated, complementary, or random?

Pipeline:
  1. Generate grid_coordinator signals from history (1h, 90d).
  2. Generate ALL detector signals from same period.
  3. For each grid_coordinator event:
       - Find all detector setups within ±60 min of same direction
       - Tally co-firings
  4. Compute conditional rates:
       P(detector fires | grid_coordinator fires) — concentration metric
       P(grid_coordinator | detector) — confirmation metric
  5. Identify pairs with strong co-firing (Phi correlation > 0.3) — these
     are NATURAL confirmation candidates: enter on detector ONLY if
     grid_coordinator also fired in window.

Output: docs/STRATEGIES/GRID_COORDINATOR_VS_DETECTORS.md
"""
from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, _StubCtx, DATA_1M,
)

# NOTE: _backtest_detectors_honest reopens stdout on import, double-wrap breaks.

OUT_MD = ROOT / "docs" / "STRATEGIES" / "GRID_COORDINATOR_VS_DETECTORS.md"
OUT_CSV = ROOT / "state" / "grid_coordinator_vs_detectors.csv"

LOOKBACK_DAYS = 90
WINDOW_MIN = 60  # ±60 min co-firing window
GC_SCORE_MIN = 3  # consider grid_coordinator events with score>=3
DETECTION_FREQ_BARS = 60  # detectors evaluated hourly (1m bars)


def _generate_grid_signals(df_1h: pd.DataFrame, eth_1h: pd.DataFrame,
                           deriv: pd.DataFrame) -> pd.DataFrame:
    """Replicate retro_validation logic: scan 1h bars, emit gc signals."""
    from services.grid_coordinator.loop import evaluate_exhaustion

    deriv_idx = deriv.set_index("ts_utc").sort_index() if "ts_utc" in deriv.columns else deriv

    def _deriv_at(ts):
        if ts < deriv_idx.index[0] or ts > deriv_idx.index[-1]:
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
        try:
            row = deriv_idx.loc[deriv_idx.index.asof(ts)]
        except (KeyError, ValueError):
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
        def f(v, d=0.0):
            try:
                x = float(v); return d if pd.isna(x) else x
            except (TypeError, ValueError): return d
        return {
            "oi_change_1h_pct": f(row.get("oi_change_1h_pct")),
            "funding_rate_8h": f(row.get("funding_rate_8h")),
            "global_ls_ratio": f(row.get("global_ls_ratio"), 1.0),
        }

    signals = []
    for i in range(50, len(df_1h)):
        sub = df_1h.iloc[i - 50:i + 1].reset_index(drop=True)
        ts = sub.iloc[-1]["ts_utc"]
        eth_w = eth_1h[eth_1h["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        ev = evaluate_exhaustion(sub, sub_eth, {"BTCUSDT": _deriv_at(ts)})
        for direction in ("upside", "downside"):
            score = ev[f"{direction}_score"]
            if score >= GC_SCORE_MIN:
                signals.append({
                    "ts": ts, "direction": direction, "score": score,
                    "price": float(sub.iloc[-1]["close"]),
                })
    return pd.DataFrame(signals)


def _generate_detector_signals(df_1m, df_15m, df_1h) -> pd.DataFrame:
    """Run all detectors over the period."""
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    out = []
    for det in DETECTOR_REGISTRY:
        name = det.__name__
        # Skip P-15 lifecycle (separate handling)
        if "p15" in name: continue
        emits = _emit_setups(det, df_1m, df_15m, df_1h, freq_bars=DETECTION_FREQ_BARS)
        for e in emits:
            ts_dt = pd.to_datetime(int(e["ts"]), unit="ms", utc=True)
            out.append({
                "ts": ts_dt,
                "detector": name,
                "side": e["side"],
                "price": e["entry"],
            })
        print(f"  {name}: {len(emits)} emits")
    return pd.DataFrame(out)


def _compute_cofiring(gc_signals: pd.DataFrame, det_signals: pd.DataFrame) -> pd.DataFrame:
    """For each detector: count co-firings with grid_coordinator within window."""
    cofiring = defaultdict(lambda: {"total_det": 0, "total_gc": 0, "co_aligned": 0,
                                    "co_misaligned": 0})

    # Total counts per detector
    for det in det_signals["detector"].unique():
        cofiring[det]["total_det"] = int((det_signals["detector"] == det).sum())

    total_gc = len(gc_signals)
    for det in cofiring:
        cofiring[det]["total_gc"] = total_gc

    # For each detector signal, find nearby gc signals (any direction)
    for _, det_row in det_signals.iterrows():
        det = det_row["detector"]
        ts = det_row["ts"]
        side = det_row["side"]
        # gc events within ±window_min
        nearby = gc_signals[
            (gc_signals["ts"] >= ts - pd.Timedelta(minutes=WINDOW_MIN)) &
            (gc_signals["ts"] <= ts + pd.Timedelta(minutes=WINDOW_MIN))
        ]
        if not len(nearby): continue
        # Aligned: LONG detector ↔ downside gc signal (oversold = long opportunity)
        #          SHORT detector ↔ upside gc signal (overbought = short opportunity)
        expected_dir = "downside" if side == "long" else "upside"
        if (nearby["direction"] == expected_dir).any():
            cofiring[det]["co_aligned"] += 1
        elif (nearby["direction"] != expected_dir).any():
            cofiring[det]["co_misaligned"] += 1

    rows = []
    for det, counts in cofiring.items():
        n_det = counts["total_det"]
        if n_det == 0: continue
        co_a = counts["co_aligned"]
        co_m = counts["co_misaligned"]
        rows.append({
            "detector": det,
            "n_detector_emits": n_det,
            "n_gc_total": counts["total_gc"],
            "co_aligned": co_a,
            "co_misaligned": co_m,
            "p_co_aligned_%": round(co_a / n_det * 100, 1) if n_det else 0,
            "p_co_misaligned_%": round(co_m / n_det * 100, 1) if n_det else 0,
            "uplift_factor": round((co_a / n_det) / (counts["total_gc"] / max(1, n_det) / 1.0), 2) if n_det else 0,
        })
    return pd.DataFrame(rows).sort_values("co_aligned", ascending=False)


def main() -> int:
    print("[gc_vs_det] loading data...")
    df_1m = pd.read_csv(DATA_1M).reset_index(drop=True)
    days = LOOKBACK_DAYS
    df_1m = df_1m.iloc[-(days * 1440):].reset_index(drop=True)
    print(f"[gc_vs_det] {len(df_1m):,} 1m bars")
    df_15m, df_1h = _build_aggregations(df_1m)
    df_1h["ts_utc"] = pd.to_datetime(df_1h["ts"], unit="ms", utc=True)
    print(f"[gc_vs_det] {len(df_15m):,} 15m, {len(df_1h):,} 1h")

    # ETH
    eth = pd.read_csv(ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv")
    if "ts_utc" not in eth.columns:
        eth["ts_utc"] = pd.to_datetime(eth["ts"], unit="ms", utc=True)
    else:
        eth["ts_utc"] = pd.to_datetime(eth["ts_utc"], utc=True)

    # Deriv
    deriv = pd.read_parquet(ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet")
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)

    print("[gc_vs_det] generating grid_coordinator signals...")
    gc = _generate_grid_signals(df_1h, eth, deriv)
    print(f"[gc_vs_det] {len(gc)} gc signals (score>={GC_SCORE_MIN})")
    print(gc["direction"].value_counts().to_dict() if len(gc) else {})

    print("[gc_vs_det] generating detector signals...")
    dets = _generate_detector_signals(df_1m, df_15m, df_1h)
    print(f"[gc_vs_det] {len(dets)} total detector emits")

    print("[gc_vs_det] computing co-firings...")
    cof = _compute_cofiring(gc, dets)
    cof.to_csv(OUT_CSV, index=False)

    md = []
    md.append("# Grid coordinator vs detectors — co-firing analysis")
    md.append("")
    md.append(f"**Period:** last {LOOKBACK_DAYS} days BTC")
    md.append(f"**Window:** ±{WINDOW_MIN} min")
    md.append(f"**Grid_coordinator threshold:** score >= {GC_SCORE_MIN}")
    md.append(f"**GC signals total:** {len(gc)}")
    md.append("")
    md.append("**Aligned co-firing logic:**")
    md.append("- LONG detector emit + grid_coordinator DOWNSIDE signal (oversold) = aligned")
    md.append("- SHORT detector emit + grid_coordinator UPSIDE signal (overbought) = aligned")
    md.append("- Mismatched direction = misaligned (signals contradict)")
    md.append("")
    md.append("## Detector co-firing rates with grid_coordinator")
    md.append("")
    if len(cof) > 0:
        md.append(cof.to_markdown(index=False))
    else:
        md.append("_no co-firings_")
    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("- **High p_co_aligned (≥30%)** = detector usually agrees with grid_coordinator. "
              "These are naturally confirmed by GC — entry condition: detector fires AND GC "
              "shows aligned direction within ±60min.")
    md.append("- **High p_co_misaligned (≥30%)** = detector contradicts GC — these emissions "
              "are likely false signals (other side of market is exhausted, not entry side).")
    md.append("- **Low both** = detector and GC measure different things — independent signals "
              "(combining adds genuine information).")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[gc_vs_det] wrote {OUT_MD}")
    print(f"[gc_vs_det] csv: {OUT_CSV}")

    if len(cof):
        top = cof.head(10)
        print("\nTop detectors by co_aligned count:")
        print(top.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
