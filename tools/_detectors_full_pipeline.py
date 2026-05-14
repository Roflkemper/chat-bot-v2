"""All 14 detectors with full pipeline (filter + confirmation + GC) on 2y.

A1 honest backtest showed 0/14 STABLE detectors (all OVERFIT). But that
test was BEFORE we built:
  - Per-detector calibration (RSI/OI/funding hard gates)
  - Confirmation gate (10min wait + drift)
  - GC-confirmation gating (block misaligned, boost aligned)

Apply full pipeline to each detector on 2y honest engine, see which ones
flip from OVERFIT to STABLE / MARGINAL.

Pipeline (per detector):
  1. Emit setups on 2y data (uses calibrated detectors with hard gates).
  2. Apply confirmation gate (10min lag, +0.1% drift in side direction).
  3. Apply GC-confirmation:
     - HARD_BLOCK list → drop if misaligned
     - Aligned → keep (boost is just confidence flag, doesn't filter)
     - Misaligned non-blocked → keep (penalty doesn't filter)
  4. Simulate remaining trades. PF, WR, walk-forward 4 folds.

Output: docs/STRATEGIES/DETECTORS_FULL_PIPELINE.md
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

OUT_MD = ROOT / "docs" / "STRATEGIES" / "DETECTORS_FULL_PIPELINE.md"

LOOKBACK_DAYS = 730
N_FOLDS = 4
CONFIRM_LAG_MIN = 10
CONFIRM_DRIFT_PCT = 0.1
GC_SCORE_MIN = 3
GC_HARD_BLOCK = {"long_multi_divergence", "long_double_bottom", "short_double_top",
                 "long_rsi_momentum_ga"}

EXCLUDE = {"detect_long_mega_dump_bounce", "detect_h10_liquidity_probe",
           "detect_p15_long", "detect_p15_short",
           "detect_grid_raise_boundary", "detect_grid_pause_entries",
           "detect_grid_booster_activate", "detect_grid_adaptive_tighten",
           "detect_defensive_margin_low", "detect_long_liq_magnet",
           "detect_short_liq_magnet"}


def _confirmation_gate(emits, df_1m):
    """Filter emits: keep only if price drifted >=0.1% in side direction
    within 10 min after emission.
    """
    closes = df_1m["close"].values
    out = []
    for e in emits:
        i = int(e["bar_idx"])
        target = i + CONFIRM_LAG_MIN
        if target >= len(closes): continue
        c = float(closes[target])
        e_price = float(e.get("entry") or e.get("entry_price") or df_1m["close"].iloc[i])
        if e["side"] == "long":
            if c >= e_price * (1 + CONFIRM_DRIFT_PCT / 100):
                out.append(e)
        else:
            if c <= e_price * (1 - CONFIRM_DRIFT_PCT / 100):
                out.append(e)
    return out


def _build_gc_history(df_1h, eth_full, deriv):
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
            try: x = float(v); return d if pd.isna(x) else x
            except: return d
        return {"oi_change_1h_pct": f(row.get("oi_change_1h_pct")),
                "funding_rate_8h": f(row.get("funding_rate_8h")),
                "global_ls_ratio": f(row.get("global_ls_ratio"), 1.0)}

    rows = []
    for i in range(50, len(df_1h)):
        sub = df_1h.iloc[i - 50:i + 1].reset_index(drop=True)
        ts = sub.iloc[-1]["ts_utc"]
        eth_w = eth_full[eth_full["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        ev = evaluate_exhaustion(sub, sub_eth, {"BTCUSDT": _deriv_at(ts)}, xrp=None)
        rows.append({"ts": ts, "up": ev["upside_score"], "down": ev["downside_score"]})
    return pd.DataFrame(rows).set_index("ts").sort_index()


def _gc_filter(emits, gc_idx, setup_type: str):
    """Apply GC filter: HARD_BLOCK list → drop if misaligned."""
    if setup_type not in GC_HARD_BLOCK:
        return emits  # only block specific noisy detectors
    out = []
    for e in emits:
        ts = pd.to_datetime(int(e["ts"]), unit="ms", utc=True)
        try:
            gc_row = gc_idx.loc[gc_idx.index.asof(ts)]
            up, down = int(gc_row["up"]), int(gc_row["down"])
        except (KeyError, ValueError, IndexError):
            out.append(e); continue
        side = e["side"]
        # Misaligned: long+up_high, short+down_high → drop
        if side == "long" and up >= GC_SCORE_MIN:
            continue
        if side == "short" and down >= GC_SCORE_MIN:
            continue
        out.append(e)
    return out


def _summary(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "pnl_pct": 0.0}
    df = pd.DataFrame(trades)
    n = len(df)
    wins = df[df["pnl_pct"] > 0]["pnl_pct"].sum()
    losses = -df[df["pnl_pct"] < 0]["pnl_pct"].sum()
    pf = (wins / losses) if losses > 0 else (999.0 if wins > 0 else 0.0)
    return {
        "n": n,
        "wr": round((df["pnl_pct"] > 0).sum() / n * 100, 1),
        "pf": round(pf, 3),
        "pnl_pct": round(df["pnl_pct"].sum(), 2),
    }


def _walk_forward(emits, df_1m, n_folds=N_FOLDS):
    fold_size = len(df_1m) // n_folds
    out = []
    for k in range(n_folds):
        start_bar = k * fold_size
        end_bar = (k + 1) * fold_size if k < n_folds - 1 else len(df_1m)
        ftr = [e for e in emits if start_bar <= e["bar_idx"] < end_bar]
        trades = []
        for e in ftr:
            r = _simulate_trade(e, df_1m)
            trades.append({"ts": e["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        s = _summary(trades)
        out.append({"fold": k + 1, **s})
    return out


def main() -> int:
    print(f"[full-pipeline] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    df_15m, df_1h = _build_aggregations(df_1m)
    df_1h["ts_utc"] = pd.to_datetime(df_1h["ts"], unit="ms", utc=True)

    eth = pd.read_csv(ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv")
    if "ts_utc" not in eth.columns:
        eth["ts_utc"] = pd.to_datetime(eth["ts"], unit="ms", utc=True)
    else:
        eth["ts_utc"] = pd.to_datetime(eth["ts_utc"], utc=True)

    deriv = pd.read_parquet(ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet")
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)

    print("[full-pipeline] building GC history...")
    gc_idx = _build_gc_history(df_1h, eth, deriv)
    print(f"  {len(gc_idx)} GC ticks")

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    detectors = [fn for fn in DETECTOR_REGISTRY
                 if fn.__name__ not in EXCLUDE
                 and not fn.__name__.startswith("detect_p15")
                 and not fn.__name__.startswith("detect_grid")]
    print(f"[full-pipeline] {len(detectors)} detectors\n")

    rows = []
    for det in detectors:
        name = det.__name__
        print(f"=== {name} ===")
        emits = _emit_setups(det, df_1m, df_15m, df_1h, freq_bars=60)
        n_baseline = len(emits)
        if not emits:
            print(f"  baseline: 0 emits"); continue

        # Stage 1: confirmation gate
        emits_after_conf = _confirmation_gate(emits, df_1m)
        # Stage 2: GC filter (drops misaligned for HARD_BLOCK list)
        setup_type = name.replace("detect_", "")
        emits_after_gc = _gc_filter(emits_after_conf, gc_idx, setup_type)

        # Simulate baseline (no pipeline) for comparison
        trades_baseline = []
        for e in emits:
            r = _simulate_trade(e, df_1m)
            trades_baseline.append({"ts": e["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        s_baseline = _summary(trades_baseline)

        # Simulate with pipeline
        trades_pipeline = []
        for e in emits_after_gc:
            r = _simulate_trade(e, df_1m)
            trades_pipeline.append({"ts": e["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        s_pipeline = _summary(trades_pipeline)
        wf = _walk_forward(emits_after_gc, df_1m)
        pos_folds = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 5)

        if s_pipeline["n"] >= 30 and s_pipeline["pf"] >= 1.5 and pos_folds >= 3:
            verdict = "STABLE"
        elif s_pipeline["n"] >= 20 and s_pipeline["pf"] >= 1.2 and pos_folds >= 2:
            verdict = "MARGINAL"
        else:
            verdict = "OVERFIT"

        rows.append({
            "detector": name,
            "baseline_n": s_baseline["n"],
            "baseline_pf": s_baseline["pf"],
            "baseline_pnl%": s_baseline["pnl_pct"],
            "after_conf": len(emits_after_conf),
            "after_gc": len(emits_after_gc),
            "pipeline_n": s_pipeline["n"],
            "pipeline_pf": s_pipeline["pf"],
            "pipeline_pnl%": s_pipeline["pnl_pct"],
            "wf_pos_folds": f"{pos_folds}/{N_FOLDS}",
            "verdict": verdict,
        })
        print(f"  baseline: N={s_baseline['n']} PF={s_baseline['pf']} PnL={s_baseline['pnl_pct']}%")
        print(f"  pipeline: N={s_pipeline['n']} PF={s_pipeline['pf']} PnL={s_pipeline['pnl_pct']}% "
              f"WF {pos_folds}/{N_FOLDS} → {verdict}")

    df_out = pd.DataFrame(rows).sort_values("pipeline_pnl%", ascending=False)

    md = []
    md.append(f"# Full pipeline: 14 detectors (filter+conf+GC) on {LOOKBACK_DAYS}d")
    md.append("")
    md.append(f"**Pipeline:** raw emit → confirmation gate (+0.1% drift in 10min) → "
              f"GC filter (HARD_BLOCK list drops misaligned)")
    md.append(f"**HARD_BLOCK:** {sorted(GC_HARD_BLOCK)}")
    md.append("")
    md.append("## Results sorted by pipeline_pnl%")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Verdict summary")
    md.append("")
    stable = df_out[df_out["verdict"] == "STABLE"]
    marginal = df_out[df_out["verdict"] == "MARGINAL"]
    overfit = df_out[df_out["verdict"] == "OVERFIT"]
    md.append(f"- STABLE: {len(stable)} ({list(stable['detector'])})")
    md.append(f"- MARGINAL: {len(marginal)} ({list(marginal['detector'])})")
    md.append(f"- OVERFIT: {len(overfit)} ({list(overfit['detector'])})")
    md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[full-pipeline] wrote {OUT_MD}")
    print(f"[full-pipeline] STABLE: {len(stable)}, MARGINAL: {len(marginal)}, OVERFIT: {len(overfit)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
