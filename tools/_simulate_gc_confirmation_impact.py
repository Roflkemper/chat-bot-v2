"""Simulate impact of GC-confirmation gating on detector emit history.

Walk 90d, generate detector signals + grid_coordinator signals, compute
what would have happened if GC-confirmation rules applied:
  - aligned → boost +15% (no actual filter, but trade with higher prio)
  - misaligned + hard-block list → suppressed
  - misaligned otherwise → -30% confidence (kept but lower prio)
  - neutral → pass-through

Output: per-detector counts (boost / penalty / block / neutral).
"""
from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, DATA_1M,
)

# NOTE: don't reopen stdout — _backtest_detectors_honest does it on import.

OUT_MD = ROOT / "docs" / "STRATEGIES" / "GC_CONFIRMATION_SIMULATION.md"
OUT_CSV = ROOT / "state" / "gc_confirmation_simulation.csv"

LOOKBACK_DAYS = 90
WINDOW_MIN = 60
GC_SCORE_MIN = 3
GC_HARD_BLOCK = {"long_multi_divergence", "long_double_bottom", "short_double_top"}


def _generate_grid_signals(df_1h, eth, deriv):
    from services.grid_coordinator.loop import evaluate_exhaustion
    deriv_idx = deriv.set_index("ts_utc").sort_index()

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
        eth_w = eth[eth["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        ev = evaluate_exhaustion(sub, sub_eth, {"BTCUSDT": _deriv_at(ts)})
        signals.append({
            "ts": ts,
            "upside_score": ev["upside_score"],
            "downside_score": ev["downside_score"],
        })
    return pd.DataFrame(signals)


def _classify(setup_side: str, gc_row: dict | None) -> str:
    if gc_row is None: return "no_gc_data"
    up = int(gc_row.get("upside_score", 0))
    down = int(gc_row.get("downside_score", 0))
    if setup_side == "long":
        if down >= GC_SCORE_MIN: return "aligned"
        if up >= GC_SCORE_MIN: return "misaligned"
    else:
        if up >= GC_SCORE_MIN: return "aligned"
        if down >= GC_SCORE_MIN: return "misaligned"
    return "neutral"


def main() -> int:
    print(f"[gc-sim] loading data ({LOOKBACK_DAYS}d)...")
    df_1m = pd.read_csv(DATA_1M).reset_index(drop=True)
    df_1m = df_1m.iloc[-(LOOKBACK_DAYS * 1440):].reset_index(drop=True)
    df_15m, df_1h = _build_aggregations(df_1m)
    df_1h["ts_utc"] = pd.to_datetime(df_1h["ts"], unit="ms", utc=True)

    eth = pd.read_csv(ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv")
    if "ts_utc" not in eth.columns:
        eth["ts_utc"] = pd.to_datetime(eth["ts"], unit="ms", utc=True)
    else:
        eth["ts_utc"] = pd.to_datetime(eth["ts_utc"], utc=True)

    deriv = pd.read_parquet(ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet")
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)

    print("[gc-sim] generating grid_coordinator history...")
    gc = _generate_grid_signals(df_1h, eth, deriv)
    print(f"  {len(gc)} 1h GC ticks")

    print("[gc-sim] generating detector emits...")
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    classify_counts = defaultdict(lambda: {"aligned": 0, "misaligned": 0, "neutral": 0, "no_gc_data": 0, "total": 0})

    for det in DETECTOR_REGISTRY:
        name = det.__name__
        if "p15" in name or "grid_" in name or "_liq_magnet" in name:
            continue
        emits = _emit_setups(det, df_1m, df_15m, df_1h, freq_bars=60)
        side = "long" if "long" in name else "short"
        # Use the actual setup_type.value for hard-block matching (not function name).
        if emits:
            classify_counts[name]["_st_value"] = emits[0].get("setup_type", name.replace("detect_", ""))
        for e in emits:
            ts_dt = pd.to_datetime(int(e["ts"]), unit="ms", utc=True)
            # Find GC tick closest to emit (1h granularity)
            gc_match = gc[
                (gc["ts"] >= ts_dt - pd.Timedelta(minutes=WINDOW_MIN)) &
                (gc["ts"] <= ts_dt + pd.Timedelta(minutes=WINDOW_MIN))
            ]
            gc_row = None
            if len(gc_match):
                # Pick the most recent within window
                gc_row = gc_match.iloc[-1].to_dict()
            cls = _classify(side, gc_row)
            classify_counts[name][cls] += 1
            classify_counts[name]["total"] += 1

    rows = []
    for name, counts in classify_counts.items():
        total = counts["total"]
        if total == 0: continue
        a = counts["aligned"]
        m = counts["misaligned"]
        n = counts["neutral"]
        nd = counts["no_gc_data"]
        # What gating does:
        # - aligned: boost (kept, +conf) → ENTERS
        # - neutral: pass-through → ENTERS
        # - misaligned + hard-block: BLOCKED
        # - misaligned otherwise: penalty (kept, -conf) → ENTERS
        # Match hard-block by setup_type.value, not function name
        st_value = classify_counts[name].get("_st_value", name.replace("detect_", ""))
        if st_value in GC_HARD_BLOCK:
            blocked = m
            kept = total - m
        else:
            blocked = 0
            kept = total
        rows.append({
            "detector": name,
            "setup_type": st_value,
            "total": total,
            "aligned_%": round(a / total * 100, 1),
            "misaligned_%": round(m / total * 100, 1),
            "neutral_%": round(n / total * 100, 1),
            "no_gc_%": round(nd / total * 100, 1),
            "hard_block_list": st_value in GC_HARD_BLOCK,
            "would_block": blocked,
            "would_keep": kept,
            "keep_rate_%": round(kept / total * 100, 1),
        })
    df_out = pd.DataFrame(rows).sort_values("total", ascending=False)
    df_out.to_csv(OUT_CSV, index=False)

    md = []
    md.append("# GC-confirmation simulation impact (90d)")
    md.append("")
    md.append(f"**Lookback:** {LOOKBACK_DAYS}d, GC threshold score>={GC_SCORE_MIN}, ±{WINDOW_MIN}min window")
    md.append(f"**Hard-block list:** {sorted(GC_HARD_BLOCK)}")
    md.append("")
    md.append("Categories per emit:")
    md.append("- **aligned**: GC confirms direction → +15% confidence boost")
    md.append("- **misaligned**: GC contradicts → if in hard-block list = BLOCKED, else -30% conf")
    md.append("- **neutral**: GC has no strong signal → pass-through")
    md.append("- **no_gc_data**: emit outside GC time range (rare)")
    md.append("")
    md.append("## Per-detector impact")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")

    # Aggregate
    total_emits = df_out["total"].sum()
    total_blocked = df_out["would_block"].sum()
    total_aligned = sum(int(r["aligned_%"] * r["total"] / 100) for _, r in df_out.iterrows())
    md.append("## Aggregate impact")
    md.append("")
    md.append(f"- **Total emits across all detectors:** {total_emits}")
    md.append(f"- **Hard-blocked by GC (multi_divergence + double_top/bottom misaligned):** {total_blocked}")
    md.append(f"- **Aligned (boosted):** ~{total_aligned}")
    md.append(f"- **Suppression rate:** {total_blocked/total_emits*100:.1f}% of all signals filtered out")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[gc-sim] wrote {OUT_MD}")
    print(f"[gc-sim] total emits {total_emits}, hard-blocked {total_blocked} ({total_blocked/total_emits*100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
