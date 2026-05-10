"""Mega-setup triple backtest — does confluence of co-firing detectors give
real edge, or is it noise inheritance?

Per C2 (docs/STRATEGIES/C2_STRATEGY_CORRELATION.md): the triple
  grid_booster + long_dump_reversal + long_pdl_bounce
co-fired 20 times in 9 days (±30min window).

Existing mega_setup.py uses ONLY 2 constituents (dump+pdl) at
MEGA_WINDOW_MIN=60min, MEGA_SL_PCT=0.8%, TP1=2.5RR, TP2=5RR.

Question: does this confluence beat each constituent alone on honest
fees + walk-forward?

Approach (consistent with our other tools):
  1. Run all 14 detectors on 365d 1m frozen data, collect emission times.
  2. For each "trigger event" (= last constituent emission), check if both
     dump_reversal AND pdl_bounce fired within ±60min on the same bar.
  3. Simulate the resulting LONG trade with mega_setup TP/SL: SL=-0.8%,
     TP1=+2.0% (2.5×0.8), TP2=+4.0%. Honest fees 0.165% RT.
  4. Compare to each constituent alone (re-using SETUP_FILTER_RESEARCH baselines).
  5. 4-fold walk-forward.

Output: docs/STRATEGIES/MEGA_SETUP_BACKTEST.md
"""
from __future__ import annotations

import io
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# NOTE: don't reopen stdout — _backtest_detectors_honest does it on import.
from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, _simulate_trade, _StubCtx,
    DATA_1M, MAKER_REBATE, TAKER_FEE, SLIPPAGE,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "MEGA_SETUP_BACKTEST.md"
OUT_CSV = ROOT / "state" / "mega_setup_backtest.csv"

LOOKBACK_DAYS = 365
WINDOW_MIN = 60        # both constituents must fire within this window
DEDUP_HOURS = 4        # don't fire mega twice in 4h
SL_PCT = 0.8
TP1_RR = 2.5
TP2_RR = 5.0
N_FOLDS = 4

# 2026-05-10: TP/SL parameter sweep (when SWEEP=1 env var set)
SWEEP_SL = [0.5, 0.6, 0.8, 1.0]
SWEEP_TP1_RR = [1.0, 1.25, 1.5, 2.0, 2.5]

# Constituent set
CONSTITUENTS = ("detect_long_dump_reversal", "detect_long_pdl_bounce")


def _emit_all(detectors_dict, df_1m, df_15m, df_1h):
    """Run each detector once over full df, return {detector_name: [emits]}."""
    out = {}
    for name, fn in detectors_dict.items():
        emits = _emit_setups(fn, df_1m, df_15m, df_1h, freq_bars=60)
        out[name] = emits
        print(f"  {name}: {len(emits)} emits")
    return out


def _find_mega_triggers(emits_by_det: dict[str, list], df_1m: pd.DataFrame,
                       window_min: int = WINDOW_MIN,
                       dedup_hours: float = DEDUP_HOURS) -> list[dict]:
    """For each pdl_bounce emission, check if dump_reversal also fired
    within ±window_min. If yes, emit mega trigger at the LATER constituent's
    bar_idx.
    """
    dump_emits = emits_by_det.get("detect_long_dump_reversal", [])
    pdl_emits = emits_by_det.get("detect_long_pdl_bounce", [])
    if not dump_emits or not pdl_emits:
        return []

    dump_ts = sorted([e["ts"] for e in dump_emits])
    pdl_ts = sorted([e["ts"] for e in pdl_emits])

    triggers = []
    last_mega_ts_ms = None
    window_ms = window_min * 60 * 1000
    dedup_ms = dedup_hours * 3600 * 1000

    # For each pdl_bounce, check if any dump was within ±window
    for pdl in pdl_emits:
        pdl_t = pdl["ts"]
        # Dedup
        if last_mega_ts_ms is not None and (pdl_t - last_mega_ts_ms) < dedup_ms:
            continue
        # Find dump within window
        nearby = [d for d in dump_emits
                  if abs(d["ts"] - pdl_t) <= window_ms]
        if not nearby:
            continue
        # Use the LATER of (pdl, dump) as trigger time so both have already happened
        dump_match = max(nearby, key=lambda d: d["ts"])
        trigger_ts = max(pdl_t, dump_match["ts"])
        # Find bar_idx in df_1m corresponding to trigger_ts
        idx = int(np.searchsorted(df_1m["ts"].values, trigger_ts, side="right")) - 1
        if idx < 0 or idx >= len(df_1m):
            continue
        entry_price = float(df_1m["close"].iloc[idx])
        if entry_price <= 0:
            continue
        triggers.append({
            "bar_idx": idx,
            "ts": trigger_ts,
            "side": "long",
            "setup_type": "mega_triple",
            "entry": entry_price,
            "sl": entry_price * (1 - SL_PCT / 100),
            "tp1": entry_price * (1 + SL_PCT * TP1_RR / 100),
            "tp2": entry_price * (1 + SL_PCT * TP2_RR / 100),
            "window_min": 240,  # 4h max hold
        })
        last_mega_ts_ms = trigger_ts
    return triggers


def _simulate_all(triggers: list[dict], df_1m: pd.DataFrame) -> list[dict]:
    out = []
    for t in triggers:
        res = _simulate_trade(t, df_1m)
        out.append({
            "ts": t["ts"],
            "entry": t["entry"],
            "outcome": res.outcome,
            "pnl_pct": res.pnl_pct,
            "bars_held": res.bars_held,
        })
    return out


def _summary(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "total_pnl_pct": 0.0, "avg_pnl_pct": 0.0}
    df = pd.DataFrame(trades)
    n = len(df)
    wins = df[df["pnl_pct"] > 0]["pnl_pct"].sum()
    losses = -df[df["pnl_pct"] < 0]["pnl_pct"].sum()
    pf = (wins / losses) if losses > 0 else (999.0 if wins > 0 else 0.0)
    return {
        "n": n,
        "wr": round((df["pnl_pct"] > 0).sum() / n * 100, 1),
        "pf": round(pf, 3),
        "total_pnl_pct": round(df["pnl_pct"].sum(), 2),
        "avg_pnl_pct": round(df["pnl_pct"].mean(), 4),
        "n_tp": int(df["outcome"].isin(["TP1", "TP2"]).sum()),
        "n_sl": int((df["outcome"] == "SL").sum()),
        "n_expire": int((df["outcome"] == "EXPIRE").sum()),
    }


def _walk_forward(triggers: list[dict], df_1m: pd.DataFrame, n_folds: int = N_FOLDS) -> list[dict]:
    fold_size = len(df_1m) // n_folds
    out = []
    for k in range(n_folds):
        start_bar = k * fold_size
        end_bar = (k + 1) * fold_size if k < n_folds - 1 else len(df_1m)
        fold_triggers = [t for t in triggers if start_bar <= t["bar_idx"] < end_bar]
        # Adjust bar_idx relative to fold start? No — we use the full df_1m
        # for simulation with absolute idx. That's fine.
        fold_trades = _simulate_all(fold_triggers, df_1m)
        s = _summary(fold_trades)
        out.append({"fold": k + 1, **s})
    return out


def _build_triggers_with_params(emits, df_1m, sl_pct, tp1_rr, tp2_rr) -> list:
    """Same as _find_mega_triggers but with custom SL/TP params."""
    dump_emits = emits.get("detect_long_dump_reversal", [])
    pdl_emits = emits.get("detect_long_pdl_bounce", [])
    if not dump_emits or not pdl_emits:
        return []
    window_ms = WINDOW_MIN * 60 * 1000
    dedup_ms = DEDUP_HOURS * 3600 * 1000
    triggers = []
    last = None
    for pdl in pdl_emits:
        if last is not None and (pdl["ts"] - last) < dedup_ms:
            continue
        nearby = [d for d in dump_emits if abs(d["ts"] - pdl["ts"]) <= window_ms]
        if not nearby: continue
        dump_match = max(nearby, key=lambda d: d["ts"])
        trigger_ts = max(pdl["ts"], dump_match["ts"])
        idx = int(np.searchsorted(df_1m["ts"].values, trigger_ts, side="right")) - 1
        if idx < 0 or idx >= len(df_1m): continue
        entry = float(df_1m["close"].iloc[idx])
        if entry <= 0: continue
        triggers.append({
            "bar_idx": idx, "ts": trigger_ts, "side": "long",
            "setup_type": "mega_triple", "entry": entry,
            "sl": entry * (1 - sl_pct / 100),
            "tp1": entry * (1 + sl_pct * tp1_rr / 100),
            "tp2": entry * (1 + sl_pct * tp2_rr / 100),
            "window_min": 240,
        })
        last = trigger_ts
    return triggers


def _run_sweep(emits, df_1m) -> pd.DataFrame:
    """SL/TP parameter sweep."""
    rows = []
    for sl in SWEEP_SL:
        for tp1_rr in SWEEP_TP1_RR:
            tp2_rr = tp1_rr * 2
            trigs = _build_triggers_with_params(emits, df_1m, sl, tp1_rr, tp2_rr)
            if not trigs: continue
            trades = _simulate_all(trigs, df_1m)
            s = _summary(trades)
            rows.append({
                "SL_pct": sl, "TP1_RR": tp1_rr, "TP1_pct": round(sl * tp1_rr, 2),
                **s,
            })
    return pd.DataFrame(rows).sort_values("total_pnl_pct", ascending=False)


def main() -> int:
    print("[mega-bt] loading 365d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    print(f"[mega-bt] {len(df_1m):,} 1m bars")
    df_15m, df_1h = _build_aggregations(df_1m)

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    detectors = {fn.__name__: fn for fn in DETECTOR_REGISTRY
                 if fn.__name__ in CONSTITUENTS}

    print("[mega-bt] emitting constituents...")
    emits = _emit_all(detectors, df_1m, df_15m, df_1h)

    print(f"[mega-bt] finding mega triggers (window={WINDOW_MIN}min, dedup={DEDUP_HOURS}h)...")
    triggers = _find_mega_triggers(emits, df_1m)
    print(f"[mega-bt] {len(triggers)} mega triggers found")

    if not triggers:
        print("[mega-bt] no triggers; nothing to backtest")
        return 0

    trades = _simulate_all(triggers, df_1m)
    full_summary = _summary(trades)
    wf = _walk_forward(triggers, df_1m)

    # Constituent baselines for comparison — re-run honest sim per detector
    print("[mega-bt] computing constituent baselines (alone)...")
    baseline_summaries = {}
    for det_name, det_emits in emits.items():
        # Use TP/SL from each setup directly
        det_trades = []
        for emit in det_emits:
            res = _simulate_trade(emit, df_1m)
            det_trades.append({
                "ts": emit["ts"], "outcome": res.outcome,
                "pnl_pct": res.pnl_pct, "bars_held": res.bars_held,
            })
        baseline_summaries[det_name] = _summary(det_trades)

    pd.DataFrame(trades).to_csv(OUT_CSV, index=False)

    md = []
    md.append("# Mega-setup triple backtest")
    md.append("")
    md.append(f"**Date:** 2026-05-10")
    md.append(f"**Lookback:** {LOOKBACK_DAYS}d BTCUSDT 1m honest engine")
    md.append(f"**Window:** ±{WINDOW_MIN}min between constituents")
    md.append(f"**Dedup:** {DEDUP_HOURS}h between consecutive megas")
    md.append(f"**Trade params:** SL=-{SL_PCT}%, TP1=+{SL_PCT*TP1_RR}% ({TP1_RR}RR), "
              f"TP2=+{SL_PCT*TP2_RR}% ({TP2_RR}RR), max_hold=240min")
    md.append(f"**Fees:** maker -0.0125% IN + taker 0.075% + slip 0.02% OUT = 0.165% RT")
    md.append("")
    md.append("## Constituent baselines (each detector alone)")
    md.append("")
    rows_b = []
    for det, s in baseline_summaries.items():
        rows_b.append({"detector": det, **s})
    md.append(pd.DataFrame(rows_b).to_markdown(index=False))
    md.append("")
    md.append("## Mega-triple result")
    md.append("")
    md.append(f"- Triggers found: **{len(triggers)}**")
    md.append("")
    md.append(pd.DataFrame([full_summary]).to_markdown(index=False))
    md.append("")
    md.append("## Walk-forward (4 folds)")
    md.append("")
    md.append(pd.DataFrame(wf).to_markdown(index=False))
    md.append("")

    # SL/TP sweep
    print("[mega-bt] running SL/TP sweep...")
    sweep = _run_sweep(emits, df_1m)
    md.append("## SL/TP parameter sweep")
    md.append("")
    md.append(f"Tested {len(SWEEP_SL)}×{len(SWEEP_TP1_RR)} = {len(SWEEP_SL)*len(SWEEP_TP1_RR)} combos. "
              f"Top 10 by total_pnl_pct:")
    md.append("")
    md.append(sweep.head(10).to_markdown(index=False))
    md.append("")
    best = sweep.iloc[0]
    md.append(f"**Best:** SL={best['SL_pct']}%, TP1_RR={best['TP1_RR']} (TP1=+{best['TP1_pct']}%) "
              f"→ PF={best['pf']}, PnL={best['total_pnl_pct']}%, N={best['n']}, WR={best['wr']}%")
    md.append("")

    # Verdict
    pf = full_summary["pf"]
    n = full_summary["n"]
    pos_folds = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 5)
    md.append("## Verdict")
    md.append("")
    if n < 20:
        md.append(f"⚠ **Too few triggers ({n}) for statistical confidence.** Need 365d+ or relaxed window.")
    elif pf >= 1.5 and pos_folds >= 3:
        md.append(f"✅ **STABLE: PF={pf}, {pos_folds}/{N_FOLDS} folds positive.** Triple confluence "
                  f"DOES give edge. Promote to live wire test (mega_setup.py is already wired).")
    elif pf >= 1.2 and pos_folds >= 2:
        md.append(f"🟡 **MARGINAL: PF={pf}, {pos_folds}/{N_FOLDS} folds positive.** Edge weak but "
                  f"directional. Worth paper-trade observation, not live promotion yet.")
    else:
        md.append(f"❌ **OVERFIT: PF={pf}, {pos_folds}/{N_FOLDS} folds positive.** Confluence inherits "
                  f"OVERFIT noise of constituents. The +5.7pp WR boost from C2 doesn't survive "
                  f"honest fees + 4-fold WF. Disable wire in mega_setup.py.")
    md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[mega-bt] wrote {OUT_MD}")
    print(f"[mega-bt] mega: {full_summary}")
    print(f"[mega-bt] WF folds: {[(f['fold'], f['pf'], f['n']) for f in wf]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
