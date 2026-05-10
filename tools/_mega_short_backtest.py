"""SHORT mega-setup confluence backtest.

Mirror of _mega_setup_backtest.py but for SHORT direction. Tests pairs and
triples of SHORT detectors:
  - short_rally_fade (PF 1.53 calibrated, RSI_15m>=75 hard gate, our fix)
  - short_pdh_rejection
  - short_overbought_fade
  - short_div_bos_15m
  - short_mfi_multi_ga

For each combination: emit constituents on 365d 1m honest engine, find
confluence triggers (all constituents within ±60min), simulate trade with
SL=+0.8%/TP1=-2.0%/TP2=-4.0%, walk-forward 4 folds.

Output: docs/STRATEGIES/MEGA_SHORT_BACKTEST.md
"""
from __future__ import annotations

import io
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, _simulate_trade,
    DATA_1M,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "MEGA_SHORT_BACKTEST.md"
OUT_CSV = ROOT / "state" / "mega_short_backtest.csv"

LOOKBACK_DAYS = 365
WINDOW_MIN = 60
DEDUP_HOURS = 4
SL_PCT = 0.8
TP1_RR = 2.5
TP2_RR = 5.0
N_FOLDS = 4
MIN_TRIGGERS = 15  # need this many to evaluate

SHORT_DETECTORS = [
    "detect_short_rally_fade",
    "detect_short_pdh_rejection",
    "detect_short_overbought_fade",
    "detect_short_div_bos_15m",
    "detect_short_mfi_multi_ga",
]


def _emit_all(detectors_dict, df_1m, df_15m, df_1h):
    out = {}
    for name, fn in detectors_dict.items():
        emits = _emit_setups(fn, df_1m, df_15m, df_1h, freq_bars=60)
        out[name] = emits
        print(f"  {name}: {len(emits)} emits")
    return out


def _build_short_triggers(emits_for_constituents: dict[str, list], df_1m: pd.DataFrame,
                          window_min: int = WINDOW_MIN,
                          dedup_hours: float = DEDUP_HOURS) -> list[dict]:
    """Find confluence triggers — moments when ALL constituents fired within
    ±window_min of each other. Trigger time = latest constituent emission.

    For SHORT: entry = current price, SL above entry, TP below.
    """
    if not emits_for_constituents or any(not v for v in emits_for_constituents.values()):
        return []
    # Convert to sorted lists of (ts, name)
    all_emits = []
    for name, emits in emits_for_constituents.items():
        for e in emits:
            all_emits.append({"ts": e["ts"], "name": name})
    all_emits.sort(key=lambda x: x["ts"])

    constituents = set(emits_for_constituents.keys())
    window_ms = window_min * 60 * 1000
    dedup_ms = dedup_hours * 3600 * 1000

    triggers = []
    last_mega = None
    # Sliding window: for each emit, look at all emits within ±window_min back,
    # check if all constituents are present
    for i, anchor in enumerate(all_emits):
        anchor_ts = anchor["ts"]
        if last_mega is not None and (anchor_ts - last_mega) < dedup_ms:
            continue
        # Collect emits in [anchor_ts - window_ms, anchor_ts]
        window_emits = [
            all_emits[j] for j in range(max(0, i - 200), i + 1)
            if (anchor_ts - all_emits[j]["ts"]) <= window_ms
        ]
        names_in_window = {e["name"] for e in window_emits}
        if not constituents.issubset(names_in_window):
            continue
        # Anchor is latest; use as trigger time
        idx = int(np.searchsorted(df_1m["ts"].values, anchor_ts, side="right")) - 1
        if idx < 0 or idx >= len(df_1m):
            continue
        entry = float(df_1m["close"].iloc[idx])
        if entry <= 0:
            continue
        # SHORT trade
        triggers.append({
            "bar_idx": idx, "ts": anchor_ts, "side": "short",
            "setup_type": "mega_short", "entry": entry,
            "sl": entry * (1 + SL_PCT / 100),         # SL above for SHORT
            "tp1": entry * (1 - SL_PCT * TP1_RR / 100),  # TP below for SHORT
            "tp2": entry * (1 - SL_PCT * TP2_RR / 100),
            "window_min": 240,
        })
        last_mega = anchor_ts
    return triggers


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
    }


def _walk_forward(triggers, df_1m, n_folds=N_FOLDS):
    fold_size = len(df_1m) // n_folds
    out = []
    for k in range(n_folds):
        start_bar = k * fold_size
        end_bar = (k + 1) * fold_size if k < n_folds - 1 else len(df_1m)
        fold_trigs = [t for t in triggers if start_bar <= t["bar_idx"] < end_bar]
        fold_trades = []
        for t in fold_trigs:
            res = _simulate_trade(t, df_1m)
            fold_trades.append({
                "ts": t["ts"],
                "outcome": res.outcome,
                "pnl_pct": res.pnl_pct,
            })
        out.append({"fold": k + 1, **_summary(fold_trades)})
    return out


def main() -> int:
    print("[mega-short] loading 365d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    print(f"[mega-short] {len(df_1m):,} 1m bars")
    df_15m, df_1h = _build_aggregations(df_1m)

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    detectors = {fn.__name__: fn for fn in DETECTOR_REGISTRY
                 if fn.__name__ in SHORT_DETECTORS}
    print(f"[mega-short] {len(detectors)} SHORT detectors loaded")

    print("[mega-short] emitting all SHORT detectors...")
    emits = _emit_all(detectors, df_1m, df_15m, df_1h)

    # Skip detectors with 0 emits
    active = {k: v for k, v in emits.items() if v}
    print(f"[mega-short] active detectors: {list(active.keys())}")

    # Per-detector baselines
    print("[mega-short] computing baselines...")
    baselines = {}
    for name, det_emits in active.items():
        trades = []
        for e in det_emits:
            res = _simulate_trade(e, df_1m)
            trades.append({"ts": e["ts"], "outcome": res.outcome, "pnl_pct": res.pnl_pct})
        baselines[name] = _summary(trades)

    # All pair combinations
    print("[mega-short] testing pair combinations...")
    pair_results = []
    for combo in combinations(active.keys(), 2):
        sub_emits = {k: active[k] for k in combo}
        trigs = _build_short_triggers(sub_emits, df_1m)
        if len(trigs) < MIN_TRIGGERS:
            print(f"  {' + '.join(combo)}: {len(trigs)} triggers (skip — <{MIN_TRIGGERS})")
            continue
        trades = [{
            "ts": t["ts"],
            "outcome": _simulate_trade(t, df_1m).outcome,
            "pnl_pct": _simulate_trade(t, df_1m).pnl_pct,
        } for t in trigs]
        s = _summary(trades)
        wf = _walk_forward(trigs, df_1m)
        pos_folds = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 5)
        pair_results.append({
            "combo": " + ".join(combo),
            "n_constituents": 2,
            **s,
            "wf_pos_folds": f"{pos_folds}/{N_FOLDS}",
        })
        print(f"  {' + '.join(combo)}: N={s['n']}, PF={s['pf']}, "
              f"PnL={s['total_pnl_pct']}%, WF {pos_folds}/{N_FOLDS}")

    # All triple combinations
    print("\n[mega-short] testing triple combinations...")
    triple_results = []
    if len(active) >= 3:
        for combo in combinations(active.keys(), 3):
            sub_emits = {k: active[k] for k in combo}
            trigs = _build_short_triggers(sub_emits, df_1m)
            if len(trigs) < MIN_TRIGGERS:
                print(f"  {' + '.join(combo)}: {len(trigs)} triggers (skip)")
                continue
            trades = [{
                "ts": t["ts"],
                "outcome": _simulate_trade(t, df_1m).outcome,
                "pnl_pct": _simulate_trade(t, df_1m).pnl_pct,
            } for t in trigs]
            s = _summary(trades)
            wf = _walk_forward(trigs, df_1m)
            pos_folds = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 5)
            triple_results.append({
                "combo": " + ".join(combo),
                "n_constituents": 3,
                **s,
                "wf_pos_folds": f"{pos_folds}/{N_FOLDS}",
            })
            print(f"  {' + '.join(combo)}: N={s['n']}, PF={s['pf']}, "
                  f"PnL={s['total_pnl_pct']}%, WF {pos_folds}/{N_FOLDS}")

    all_results = pair_results + triple_results
    pd.DataFrame(all_results).to_csv(OUT_CSV, index=False)

    # Sort by total_pnl_pct
    all_results_df = pd.DataFrame(all_results).sort_values("total_pnl_pct", ascending=False)

    md = []
    md.append("# SHORT mega-setup confluence backtest")
    md.append("")
    md.append(f"**Date:** 2026-05-10 | **Lookback:** {LOOKBACK_DAYS}d 1m honest")
    md.append(f"**Window:** ±{WINDOW_MIN}min | **Dedup:** {DEDUP_HOURS}h")
    md.append(f"**Trade params:** SL=+{SL_PCT}%, TP1=-{SL_PCT*TP1_RR}%, TP2=-{SL_PCT*TP2_RR}%, hold=240min")
    md.append(f"**Min triggers for evaluation:** {MIN_TRIGGERS}")
    md.append("")
    md.append("## Constituent baselines (each SHORT detector alone)")
    md.append("")
    rows = [{"detector": k, **v} for k, v in baselines.items()]
    md.append(pd.DataFrame(rows).to_markdown(index=False))
    md.append("")
    md.append("## Confluence results (sorted by PnL)")
    md.append("")
    if len(all_results_df):
        md.append(all_results_df.to_markdown(index=False))
    else:
        md.append("_no combinations met MIN_TRIGGERS threshold_")
    md.append("")

    # Verdict
    if len(all_results_df):
        best = all_results_df.iloc[0]
        if best["pf"] >= 1.5 and "wf_pos_folds" in best:
            pf_n, pf_d = map(int, best["wf_pos_folds"].split("/"))
            verdict = (f"✅ **STABLE: {best['combo']}** PF={best['pf']}, "
                      f"PnL={best['total_pnl_pct']}%, WF {best['wf_pos_folds']}.")
        elif best["pf"] >= 1.2:
            verdict = (f"🟡 **MARGINAL: {best['combo']}** PF={best['pf']}, "
                      f"PnL={best['total_pnl_pct']}%. Worth paper trial.")
        else:
            verdict = (f"❌ **No SHORT confluence yields edge.** Best is {best['combo']} "
                      f"PF={best['pf']} — not above 1.2 threshold.")
        md.append("## Verdict")
        md.append("")
        md.append(verdict)
        md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[mega-short] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
