"""SHORT mega v2 — confluence of short detector + grid_coordinator UPSIDE signal.

C2 found that SHORT detectors are rare individually and almost never co-fire.
Instead, use grid_coordinator (already running with calibrated thresholds) as
the primary "exhaustion confirmed" signal, and pair it with one of the SHORT
detectors as additional confirm.

GC vs detectors analysis (90d):
  short_rally_fade:    81% aligned with GC, 0% misaligned
  short_overbought_fade: 80% aligned, 0% misaligned
  short_pdh_rejection:  40% aligned, 0% misaligned

Hypothesis: trade SHORT only when:
  (a) GC upside_score >= 3 (exhaustion confirmed)
  (b) ANY short detector emitted within ±60min

This is exactly the GC-confirmation we already have in setup_detector loop,
but as a STANDALONE backtested strategy with own SL/TP.
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
    _build_aggregations, _emit_setups, _simulate_trade, DATA_1M,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "MEGA_SHORT_V2_GC.md"
OUT_CSV = ROOT / "state" / "mega_short_v2_gc.csv"

LOOKBACK_DAYS = 365
WINDOW_MIN = 60
DEDUP_HOURS = 4
SL_PCT = 0.8
TP1_RR = 2.5
TP2_RR = 5.0
N_FOLDS = 4
GC_SCORE_MIN = 3

SHORT_DETECTORS = [
    "detect_short_rally_fade",
    "detect_short_pdh_rejection",
    "detect_short_overbought_fade",
]


def _generate_gc_upside_signals(df_1h, eth_1h, deriv) -> pd.DataFrame:
    """Replicate retro_validation logic for GC upside signals."""
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
            try: x = float(v); return d if pd.isna(x) else x
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
        if ev["upside_score"] >= GC_SCORE_MIN:
            signals.append({
                "ts": ts,
                "ts_ms": int(ts.timestamp() * 1000),
                "upside_score": ev["upside_score"],
                "price": float(sub.iloc[-1]["close"]),
            })
    return pd.DataFrame(signals)


def _build_triggers(short_emits: list, gc_signals: pd.DataFrame, df_1m: pd.DataFrame
                    ) -> list[dict]:
    """For each SHORT detector emit, find a GC upside_score>=3 within ±window_min."""
    if not short_emits or len(gc_signals) == 0:
        return []
    gc_ts_ms = gc_signals["ts_ms"].values
    window_ms = WINDOW_MIN * 60 * 1000
    dedup_ms = DEDUP_HOURS * 3600 * 1000
    triggers = []
    last = None
    for e in short_emits:
        anchor = e["ts"]
        if last is not None and (anchor - last) < dedup_ms:
            continue
        # Find GC signal within ±window
        delta = np.abs(gc_ts_ms - anchor)
        if not (delta <= window_ms).any():
            continue
        # Use detector emit time as trigger
        idx = int(np.searchsorted(df_1m["ts"].values, anchor, side="right")) - 1
        if idx < 0 or idx >= len(df_1m):
            continue
        entry = float(df_1m["close"].iloc[idx])
        if entry <= 0:
            continue
        triggers.append({
            "bar_idx": idx, "ts": anchor, "side": "short",
            "setup_type": "mega_short_v2", "entry": entry,
            "sl": entry * (1 + SL_PCT / 100),
            "tp1": entry * (1 - SL_PCT * TP1_RR / 100),
            "tp2": entry * (1 - SL_PCT * TP2_RR / 100),
            "window_min": 240,
        })
        last = anchor
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
    print("[mega-short-v2] loading data...")
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

    print("[mega-short-v2] generating GC upside signals (1h)...")
    gc = _generate_gc_upside_signals(df_1h, eth, deriv)
    print(f"  {len(gc)} GC upside signals (score>={GC_SCORE_MIN})")

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    detectors = {fn.__name__: fn for fn in DETECTOR_REGISTRY
                 if fn.__name__ in SHORT_DETECTORS}

    print("[mega-short-v2] emitting SHORT detectors...")
    emits = {}
    for name, fn in detectors.items():
        e = _emit_setups(fn, df_1m, df_15m, df_1h, freq_bars=60)
        emits[name] = e
        print(f"  {name}: {len(e)}")

    # Per-detector + GC confluence
    print("\n[mega-short-v2] testing detector + GC confluence...")
    results = []
    for name, det_emits in emits.items():
        if not det_emits: continue
        trigs = _build_triggers(det_emits, gc, df_1m)
        if len(trigs) < 5:
            print(f"  {name} + GC_upside: {len(trigs)} (too few)")
            continue
        trades = []
        for t in trigs:
            r = _simulate_trade(t, df_1m)
            trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        s = _summary(trades)
        wf = _walk_forward(trigs, df_1m)
        pos_folds = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 3)
        results.append({
            "combo": f"{name} + GC_upside>=3",
            **s,
            "wf_pos_folds": f"{pos_folds}/{N_FOLDS}",
        })
        print(f"  {name} + GC_upside: N={s['n']}, PF={s['pf']}, "
              f"PnL={s['total_pnl_pct']}%, WF {pos_folds}/{N_FOLDS}")

    # ALSO: GC upside alone (no detector requirement) — as baseline
    print("\n[mega-short-v2] GC upside alone (baseline)...")
    if len(gc):
        gc_emits = [{"ts": int(row["ts_ms"]), "bar_idx": int(np.searchsorted(df_1m["ts"].values, row["ts_ms"], side="right")) - 1}
                    for _, row in gc.iterrows()]
        gc_trigs = []
        last = None
        for e in gc_emits:
            if last is not None and (e["ts"] - last) < DEDUP_HOURS * 3600 * 1000:
                continue
            if e["bar_idx"] < 0 or e["bar_idx"] >= len(df_1m):
                continue
            entry = float(df_1m["close"].iloc[e["bar_idx"]])
            if entry <= 0: continue
            gc_trigs.append({
                "bar_idx": e["bar_idx"], "ts": e["ts"], "side": "short",
                "setup_type": "gc_upside_alone", "entry": entry,
                "sl": entry * (1 + SL_PCT / 100),
                "tp1": entry * (1 - SL_PCT * TP1_RR / 100),
                "tp2": entry * (1 - SL_PCT * TP2_RR / 100),
                "window_min": 240,
            })
            last = e["ts"]
        gc_trades = []
        for t in gc_trigs:
            r = _simulate_trade(t, df_1m)
            gc_trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        gs = _summary(gc_trades)
        wf = _walk_forward(gc_trigs, df_1m)
        pos_folds = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 3)
        results.append({
            "combo": "GC_upside>=3 ALONE (baseline)",
            **gs,
            "wf_pos_folds": f"{pos_folds}/{N_FOLDS}",
        })
        print(f"  GC_upside alone: N={gs['n']}, PF={gs['pf']}, "
              f"PnL={gs['total_pnl_pct']}%, WF {pos_folds}/{N_FOLDS}")

    pd.DataFrame(results).to_csv(OUT_CSV, index=False)
    df_out = pd.DataFrame(results).sort_values("total_pnl_pct", ascending=False)

    md = []
    md.append(f"# SHORT mega v2 — detector + grid_coordinator confluence")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d | **GC threshold:** score>={GC_SCORE_MIN} | "
              f"**Window:** ±{WINDOW_MIN}min | **Dedup:** {DEDUP_HOURS}h")
    md.append(f"**Trade params:** SL=+{SL_PCT}%, TP1=-{SL_PCT*TP1_RR}%, "
              f"TP2=-{SL_PCT*TP2_RR}%, hold={240}min")
    md.append("")
    md.append("## Results (sorted by total_pnl_pct)")
    md.append("")
    if len(df_out):
        md.append(df_out.to_markdown(index=False))
    md.append("")
    if len(df_out):
        best = df_out.iloc[0]
        if best["pf"] >= 1.5:
            md.append(f"## ✅ STABLE: **{best['combo']}** PF={best['pf']}, "
                      f"PnL={best['total_pnl_pct']}%, WF {best['wf_pos_folds']}")
        elif best["pf"] >= 1.2:
            md.append(f"## 🟡 MARGINAL: best is {best['combo']} PF={best['pf']}")
        else:
            md.append(f"## ❌ No SHORT edge from GC confluence")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[mega-short-v2] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
