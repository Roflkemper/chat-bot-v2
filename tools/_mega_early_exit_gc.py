"""Mega-pair early exit via GC overbought signal (TZ #4, 2026-05-10).

Hypothesis: mega-pair (LONG) trades that haven't hit TP within X hours
should exit early when GC upside_score >= 4 (= top exhaustion signal),
instead of waiting for TP/SL/timeout.

Compare:
  A) BASELINE: standard mega-pair exit (TP1, SL, timeout 240min)
  B) GC_EXIT:  same as A, but if GC up>=4 detected after entry, exit at
              that bar's close.

Track per-trade:
  - Trigger entry timestamp
  - Standard exit (baseline)
  - GC-flagged early exit (if any)
  - Compare PnL difference

Output: docs/STRATEGIES/MEGA_EARLY_EXIT_GC.md
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
    MAKER_REBATE, TAKER_FEE, SLIPPAGE,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "MEGA_EARLY_EXIT_GC.md"

LOOKBACK_DAYS = 730
WINDOW_MIN = 60
DEDUP_HOURS = 4
SL_PCT = 0.8
TP1_RR = 2.5
TP2_RR = 5.0
HOLD_MIN = 240
GC_EARLY_EXIT_SCORE = 4

CONSTITUENTS = ("detect_long_dump_reversal", "detect_long_pdl_bounce")


def _build_triggers(emits, df_1m):
    dump = emits.get("detect_long_dump_reversal", [])
    pdl = emits.get("detect_long_pdl_bounce", [])
    if not dump or not pdl: return []
    window_ms = WINDOW_MIN * 60 * 1000
    dedup_ms = DEDUP_HOURS * 3600 * 1000
    triggers = []
    last = None
    for p in pdl:
        if last is not None and (p["ts"] - last) < dedup_ms: continue
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
            "sl": entry * (1 - SL_PCT / 100),
            "tp1": entry * (1 + SL_PCT * TP1_RR / 100),
            "tp2": entry * (1 + SL_PCT * TP2_RR / 100),
            "window_min": HOLD_MIN,
        })
        last = trigger_ts
    return triggers


def _build_gc_history(df_1h, eth_full, deriv):
    from services.grid_coordinator.loop import evaluate_exhaustion
    deriv_idx = deriv.set_index("ts_utc").sort_index()

    def _deriv_at(ts):
        if ts < deriv_idx.index[0] or ts > deriv_idx.index[-1]:
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
        try: row = deriv_idx.loc[deriv_idx.index.asof(ts)]
        except (KeyError, ValueError):
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
        def f(v, d=0.0):
            try: x = float(v); return d if pd.isna(x) else x
            except: return d
        return {"oi_change_1h_pct": f(row.get("oi_change_1h_pct")),
                "funding_rate_8h": f(row.get("funding_rate_8h")),
                "global_ls_ratio": f(row.get("global_ls_ratio"), 1.0)}

    out = []
    for i in range(50, len(df_1h)):
        sub = df_1h.iloc[i - 50:i + 1].reset_index(drop=True)
        ts = sub.iloc[-1]["ts_utc"]
        eth_w = eth_full[eth_full["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        ev = evaluate_exhaustion(sub, sub_eth, {"BTCUSDT": _deriv_at(ts)}, xrp=None)
        out.append({"ts": ts, "ts_ms": int(ts.timestamp() * 1000),
                    "up": ev["upside_score"], "down": ev["downside_score"]})
    return pd.DataFrame(out)


def _simulate_with_gc_exit(trigger, df_1m, gc_df):
    """Like _simulate_trade but also exits early if GC up>=4 after entry."""
    bar_idx = trigger["bar_idx"]
    entry = trigger["entry"]
    sl = trigger["sl"]
    tp1 = trigger["tp1"]
    qty_btc = 1000.0 / entry  # base $1k

    # Phase 1: limit fill — assume immediate (entry == close)
    # Walk forward up to HOLD_MIN minutes
    end_idx = min(bar_idx + HOLD_MIN, len(df_1m) - 1)
    fee_in = MAKER_REBATE
    fee_out = TAKER_FEE + SLIPPAGE

    # Find earliest GC up>=4 after entry_ts
    entry_ts_ms = int(df_1m["ts"].iloc[bar_idx])
    gc_match = gc_df[(gc_df["ts_ms"] >= entry_ts_ms) &
                     (gc_df["ts_ms"] <= entry_ts_ms + HOLD_MIN * 60 * 1000) &
                     (gc_df["up"] >= GC_EARLY_EXIT_SCORE)]
    gc_exit_ts_ms = int(gc_match.iloc[0]["ts_ms"]) if len(gc_match) else None

    # Walk bars looking for TP/SL or GC exit
    exit_price = None
    exit_reason = None
    for j in range(bar_idx + 1, end_idx + 1):
        ts_j = int(df_1m["ts"].iloc[j])
        h = float(df_1m["high"].iloc[j])
        l = float(df_1m["low"].iloc[j])
        # SL hit (LONG)
        if l <= sl:
            exit_price = sl
            exit_reason = "SL"
            break
        # TP hit (LONG)
        if h >= tp1:
            exit_price = tp1
            exit_reason = "TP1"
            break
        # GC early exit
        if gc_exit_ts_ms is not None and ts_j >= gc_exit_ts_ms:
            exit_price = float(df_1m["close"].iloc[j])
            exit_reason = "GC_EXIT"
            break
    if exit_price is None:
        exit_price = float(df_1m["close"].iloc[end_idx])
        exit_reason = "TIMEOUT"

    # PnL
    fee_in_usd = entry * qty_btc * fee_in
    fee_out_usd = exit_price * qty_btc * fee_out
    gross = (exit_price - entry) * qty_btc  # LONG
    pnl_usd = gross - fee_in_usd - fee_out_usd
    pnl_pct = pnl_usd / 1000.0 * 100  # back to %
    return {
        "exit_reason": exit_reason,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
    }


def main() -> int:
    print(f"[mega-exit] loading {LOOKBACK_DAYS}d 1m...")
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

    print("[mega-exit] building GC history...")
    gc_df = _build_gc_history(df_1h, eth, deriv)
    print(f"  {len(gc_df)} GC ticks, up>={GC_EARLY_EXIT_SCORE}: "
          f"{(gc_df['up'] >= GC_EARLY_EXIT_SCORE).sum()}")

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    detectors = {fn.__name__: fn for fn in DETECTOR_REGISTRY if fn.__name__ in CONSTITUENTS}
    print("[mega-exit] emitting constituents...")
    emits = {}
    for name, fn in detectors.items():
        e = _emit_setups(fn, df_1m, df_15m, df_1h, freq_bars=60)
        emits[name] = e
        print(f"  {name}: {len(e)}")

    triggers = _build_triggers(emits, df_1m)
    print(f"[mega-exit] {len(triggers)} mega triggers")

    # Run both simulations
    baseline_results = []
    gc_exit_results = []
    for t in triggers:
        # Baseline (existing simulator)
        r_base = _simulate_trade(t, df_1m)
        baseline_results.append({"ts": t["ts"], "exit": r_base.outcome,
                                  "pnl_pct": r_base.pnl_pct})
        # GC exit version
        r_gc = _simulate_with_gc_exit(t, df_1m, gc_df)
        gc_exit_results.append({"ts": t["ts"], "exit": r_gc["exit_reason"],
                                "pnl_pct": r_gc["pnl_pct"]})

    base_df = pd.DataFrame(baseline_results)
    gc_df_res = pd.DataFrame(gc_exit_results)

    def _summary(df):
        n = len(df)
        wins = df[df["pnl_pct"] > 0]["pnl_pct"].sum()
        losses = -df[df["pnl_pct"] < 0]["pnl_pct"].sum()
        pf = (wins / losses) if losses > 0 else (999.0 if wins > 0 else 0.0)
        return {
            "n": n, "wr": round((df["pnl_pct"] > 0).sum() / n * 100, 1),
            "pf": round(pf, 3),
            "pnl_pct": round(df["pnl_pct"].sum(), 2),
            "avg_pnl_pct": round(df["pnl_pct"].mean(), 4),
        }

    s_base = _summary(base_df)
    s_gc = _summary(gc_df_res)
    base_exit = base_df["exit"].value_counts().to_dict()
    gc_exit_dist = gc_df_res["exit"].value_counts().to_dict()
    gc_exit_count = gc_exit_dist.get("GC_EXIT", 0)

    md = []
    md.append("# Mega-pair early exit via GC")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d | **GC early-exit threshold:** up>={GC_EARLY_EXIT_SCORE}")
    md.append(f"**Trade params:** SL=-{SL_PCT}%, TP1=+{SL_PCT*TP1_RR}%, hold={HOLD_MIN}min")
    md.append("")
    md.append("## Results")
    md.append("")
    rows = pd.DataFrame([
        {"mode": "BASELINE", **s_base},
        {"mode": "GC_EARLY_EXIT", **s_gc},
    ])
    md.append(rows.to_markdown(index=False))
    md.append("")
    md.append(f"**Baseline exit distribution:** {base_exit}")
    md.append(f"**GC mode exit distribution:** {gc_exit_dist}")
    md.append(f"**Trades flagged for GC early exit:** {gc_exit_count}")
    md.append("")
    md.append("## Verdict")
    md.append("")
    delta = s_gc["pnl_pct"] - s_base["pnl_pct"]
    if delta > 5:
        md.append(f"✅ **GC early exit ADDS {delta:+.2f}pp PnL.** Wire into mega_setup.py.")
    elif delta > 0:
        md.append(f"🟡 **Marginal improvement {delta:+.2f}pp.** Maybe wire but small.")
    elif delta > -5:
        md.append(f"⚪ **Roughly equal ({delta:+.2f}pp).** GC exit doesn't add or hurt much.")
    else:
        md.append(f"❌ **GC exit HURTS by {abs(delta):.2f}pp.** Don't wire — TP gives better exit.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[mega-exit] wrote {OUT_MD}")
    print(f"[mega-exit] base PnL {s_base['pnl_pct']}% / gc-exit PnL {s_gc['pnl_pct']}% / "
          f"delta {delta:+.2f}pp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
