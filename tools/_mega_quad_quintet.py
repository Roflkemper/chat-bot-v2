"""LONG mega quad/quintet exploration.

Existing LONG mega (commit d922b56): dump_reversal + pdl_bounce → PF 1.54, +15.5%/365d.

Question: does adding 3rd/4th LONG detector as additional confluence boost edge,
or does sample size collapse below useful?

Test combos:
  Pair (baseline):  dump + pdl
  Triple A:         dump + pdl + oversold_reclaim  (close-relative LONG)
  Triple B:         dump + pdl + double_bottom (pattern)
  Triple C:         dump + pdl + multi_divergence (divergence)
  Triple D:         dump + pdl + div_bos_confirmed
  Triple E:         dump + pdl + div_bos_15m
  Triple F:         dump + pdl + multi_asset_confluence
  Quad:             best triple + 4th detector

Output: docs/STRATEGIES/MEGA_QUAD_EXPLORATION.md
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, _simulate_trade, DATA_1M,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "MEGA_QUAD_EXPLORATION.md"
OUT_CSV = ROOT / "state" / "mega_quad_exploration.csv"

LOOKBACK_DAYS = 365
WINDOW_MIN = 60
DEDUP_HOURS = 4
SL_PCT = 0.8
TP1_RR = 2.5
TP2_RR = 5.0
N_FOLDS = 4
MIN_TRIGGERS = 10  # lower threshold — quads will be rare

LONG_DETECTORS = [
    "detect_long_dump_reversal",      # always
    "detect_long_pdl_bounce",         # always
    "detect_long_oversold_reclaim",
    "detect_double_bottom_setup",
    "detect_long_multi_divergence",
    "detect_long_div_bos_confirmed",
    "detect_long_div_bos_15m",
    "detect_long_multi_asset_confluence",
    "detect_long_multi_asset_confluence_v2",
    "detect_long_mega_dump_bounce",  # itself the pair-mega — exclude
]
EXCLUDE = {"detect_long_mega_dump_bounce"}

# Mandatory base pair (the proven mega-triple constituents)
BASE = ("detect_long_dump_reversal", "detect_long_pdl_bounce")


def _build_triggers(emits_for: dict[str, list], df_1m, window_min=WINDOW_MIN, dedup_hours=DEDUP_HOURS):
    if any(not v for v in emits_for.values()):
        return []
    all_emits = []
    for name, emits in emits_for.items():
        for e in emits:
            all_emits.append({"ts": e["ts"], "name": name})
    all_emits.sort(key=lambda x: x["ts"])
    constituents = set(emits_for.keys())
    window_ms = window_min * 60 * 1000
    dedup_ms = dedup_hours * 3600 * 1000
    triggers = []
    last_mega = None
    for i, anchor in enumerate(all_emits):
        anchor_ts = anchor["ts"]
        if last_mega is not None and (anchor_ts - last_mega) < dedup_ms:
            continue
        window_emits = [
            all_emits[j] for j in range(max(0, i - 500), i + 1)
            if (anchor_ts - all_emits[j]["ts"]) <= window_ms
        ]
        names_in_window = {e["name"] for e in window_emits}
        if not constituents.issubset(names_in_window):
            continue
        idx = int(np.searchsorted(df_1m["ts"].values, anchor_ts, side="right")) - 1
        if idx < 0 or idx >= len(df_1m): continue
        entry = float(df_1m["close"].iloc[idx])
        if entry <= 0: continue
        triggers.append({
            "bar_idx": idx, "ts": anchor_ts, "side": "long",
            "setup_type": "mega_long_n", "entry": entry,
            "sl": entry * (1 - SL_PCT / 100),
            "tp1": entry * (1 + SL_PCT * TP1_RR / 100),
            "tp2": entry * (1 + SL_PCT * TP2_RR / 100),
            "window_min": 240,
        })
        last_mega = anchor_ts
    return triggers


def _summary(trades):
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
    }


def _walk_forward(triggers, df_1m, n_folds=N_FOLDS):
    fold_size = len(df_1m) // n_folds
    out = []
    for k in range(n_folds):
        start_bar = k * fold_size
        end_bar = (k + 1) * fold_size if k < n_folds - 1 else len(df_1m)
        ftr = [t for t in triggers if start_bar <= t["bar_idx"] < end_bar]
        trades = []
        for t in ftr:
            r = _simulate_trade(t, df_1m)
            trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        out.append({"fold": k + 1, **_summary(trades)})
    return out


def main() -> int:
    print("[mega-quad] loading data...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    df_15m, df_1h = _build_aggregations(df_1m)

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    pool = [n for n in LONG_DETECTORS if n not in EXCLUDE]
    detectors = {fn.__name__: fn for fn in DETECTOR_REGISTRY if fn.__name__ in pool}
    print(f"[mega-quad] {len(detectors)} candidate LONG detectors")

    print("[mega-quad] emitting all...")
    emits = {}
    for name, fn in detectors.items():
        e = _emit_setups(fn, df_1m, df_15m, df_1h, freq_bars=60)
        emits[name] = e
        print(f"  {name}: {len(e)}")

    active = {k: v for k, v in emits.items() if v}
    print(f"\n[mega-quad] active: {list(active.keys())}")

    if not all(b in active for b in BASE):
        print(f"ERR: base pair {BASE} not all active"); return 1

    # Pair baseline (BASE only)
    print("\n[mega-quad] BASE pair (dump + pdl)...")
    base_trigs = _build_triggers({k: active[k] for k in BASE}, df_1m)
    base_trades = []
    for t in base_trigs:
        r = _simulate_trade(t, df_1m)
        base_trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
    base_summary = _summary(base_trades)
    base_wf = _walk_forward(base_trigs, df_1m)
    base_pos = sum(1 for f in base_wf if f["pf"] >= 1.3 and f["n"] >= 5)
    print(f"  BASE: N={base_summary['n']}, PF={base_summary['pf']}, "
          f"PnL={base_summary['total_pnl_pct']}%, WF {base_pos}/{N_FOLDS}")

    # Add 3rd detector — try each
    print("\n[mega-quad] testing TRIPLE (BASE + 1)...")
    triple_results = []
    for extra in active:
        if extra in BASE: continue
        combo = list(BASE) + [extra]
        sub_emits = {k: active[k] for k in combo}
        trigs = _build_triggers(sub_emits, df_1m)
        if len(trigs) < MIN_TRIGGERS:
            print(f"  +{extra}: {len(trigs)} (skip)")
            continue
        trades = []
        for t in trigs:
            r = _simulate_trade(t, df_1m)
            trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        s = _summary(trades)
        wf = _walk_forward(trigs, df_1m)
        pos = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 5)
        triple_results.append({
            "combo": "+ " + extra,
            "n_constituents": 3,
            **s,
            "wf_pos_folds": f"{pos}/{N_FOLDS}",
        })
        print(f"  +{extra}: N={s['n']}, PF={s['pf']}, PnL={s['total_pnl_pct']}%, WF {pos}/{N_FOLDS}")

    # Add 4th — try each combo of 2 extras
    print("\n[mega-quad] testing QUAD (BASE + 2)...")
    quad_results = []
    extras = [n for n in active if n not in BASE]
    for combo in combinations(extras, 2):
        sub_combo = list(BASE) + list(combo)
        sub_emits = {k: active[k] for k in sub_combo}
        trigs = _build_triggers(sub_emits, df_1m)
        if len(trigs) < MIN_TRIGGERS:
            print(f"  +{combo}: {len(trigs)} (skip)")
            continue
        trades = []
        for t in trigs:
            r = _simulate_trade(t, df_1m)
            trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        s = _summary(trades)
        wf = _walk_forward(trigs, df_1m)
        pos = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 3)
        quad_results.append({
            "combo": "+ " + " + ".join(combo),
            "n_constituents": 4,
            **s,
            "wf_pos_folds": f"{pos}/{N_FOLDS}",
        })
        print(f"  +{combo}: N={s['n']}, PF={s['pf']}, PnL={s['total_pnl_pct']}%, WF {pos}/{N_FOLDS}")

    base_row = {"combo": "BASE pair (dump+pdl)", "n_constituents": 2, **base_summary,
                "wf_pos_folds": f"{base_pos}/{N_FOLDS}"}
    all_results = [base_row] + triple_results + quad_results
    df_out = pd.DataFrame(all_results).sort_values("total_pnl_pct", ascending=False)
    df_out.to_csv(OUT_CSV, index=False)

    md = []
    md.append(f"# LONG mega quad/quintet exploration")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d 1m honest engine | **Window:** ±{WINDOW_MIN}min | "
              f"**Dedup:** {DEDUP_HOURS}h")
    md.append(f"**Trade:** SL=-{SL_PCT}% TP1=+{SL_PCT*TP1_RR}% TP2=+{SL_PCT*TP2_RR}% hold=240min")
    md.append(f"**Min triggers for evaluation:** {MIN_TRIGGERS}")
    md.append(f"**Base pair (proven mega-triple):** {' + '.join(BASE)}")
    md.append("")
    md.append("## Results (sorted by total_pnl_pct desc)")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    best = df_out.iloc[0]
    base_pnl = base_row["total_pnl_pct"]
    if best["combo"] != "BASE pair (dump+pdl)" and best["total_pnl_pct"] > base_pnl * 1.2:
        md.append(f"✅ **Quad/quintet improves on base:** {best['combo']} gives "
                  f"PnL={best['total_pnl_pct']}% vs base {base_pnl}% (+{best['total_pnl_pct']-base_pnl:.1f}pp).")
    else:
        md.append(f"🟡 **Adding 3rd/4th detector does NOT improve base.** Base pair "
                  f"(N={base_row['n']}, PF={base_row['pf']}, PnL={base_pnl}%) remains best. "
                  f"Triple/quad combos give fewer triggers and similar/worse PF — "
                  f"confluence already extracted by the pair.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[mega-quad] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
