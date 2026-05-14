"""H10 honest backtest — does the 79.3% WR survive walk-forward + honest fees?

Original H10 backtest (TZ-056, 2026-04-29) reported 79.3% WR / $324 PnL on
150 setups. But: relaxed C1=1.2%/C2=1.0% (vs strict 1.5%/2.5%), ~0%
liquidations weight (collectors <3 days). Now we have:
  - Restrictive params (C1=1.5%, C2=2.5%) per current detector
  - Real liquidations.csv data (724 entries / 72h tested)
  - Honest fee model (0.165% RT)
  - 4-fold walk-forward

Approach:
  Use detect_h10_liquidity_probe adapter (already wired in setup_detector
  registry) to emit setups on 365d 1m honest engine, simulate trades with
  H10 native TP/SL params (TP=0.5%, SL=0.8%, max_hold=120min).

Output: docs/STRATEGIES/H10_HONEST_BACKTEST.md
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
    _build_aggregations, _emit_setups, _simulate_trade, _StubCtx, DATA_1M,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "H10_HONEST_BACKTEST.md"

LOOKBACK_DAYS = 365
N_FOLDS = 4


def _summary(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "total_pnl_pct": 0.0}
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


def _walk_forward(emits, df_1m, n_folds=N_FOLDS):
    fold_size = len(df_1m) // n_folds
    out = []
    for k in range(n_folds):
        start_bar = k * fold_size
        end_bar = (k + 1) * fold_size if k < n_folds - 1 else len(df_1m)
        fold_emits = [e for e in emits if start_bar <= e["bar_idx"] < end_bar]
        trades = []
        for e in fold_emits:
            r = _simulate_trade(e, df_1m)
            trades.append({"ts": e["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        out.append({"fold": k + 1, **_summary(trades)})
    return out


def main() -> int:
    print(f"[h10-bt] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    df_15m, df_1h = _build_aggregations(df_1m)
    print(f"[h10-bt] {len(df_1m):,} 1m / {len(df_1h):,} 1h")

    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    h10 = next((fn for fn in DETECTOR_REGISTRY if fn.__name__ == "detect_h10_liquidity_probe"), None)
    if h10 is None:
        print("[h10-bt] H10 detector not in registry"); return 1

    print("[h10-bt] emitting H10 setups (this is slow, building liq map per call)...")
    # H10 builds liq_map every call which is expensive — sample every 60 1m bars (1h).
    emits = _emit_setups(h10, df_1m, df_15m, df_1h, freq_bars=60)
    print(f"[h10-bt] {len(emits)} H10 setups emitted")

    if not emits:
        print("[h10-bt] no emits — H10 may need restrictive C1/C2 params");
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(f"# H10 honest backtest\n\n0 setups emitted on {LOOKBACK_DAYS}d. "
                          f"Restrictive C1/C2 + relaxed liq weight thresholds may be too tight.\n",
                          encoding="utf-8")
        return 0

    trades = []
    for e in emits:
        r = _simulate_trade(e, df_1m)
        trades.append({"ts": e["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
    full_summary = _summary(trades)
    wf = _walk_forward(emits, df_1m)
    pos_folds = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 3)

    md = []
    md.append("# H10 honest backtest")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d BTCUSDT 1m honest engine")
    md.append(f"**Detector:** detect_h10_liquidity_probe (registered in DETECTOR_REGISTRY)")
    md.append(f"**Trade params:** SL/TP from h10_adapter.py (TP=+0.5%, SL=-0.8%, hold=120min)")
    md.append(f"**Fees:** maker -0.0125% IN + taker 0.075% + slip 0.02% OUT = 0.165% RT")
    md.append("")
    md.append("## Original TZ-056 claim")
    md.append("")
    md.append("- 79.3% WR / $324 PnL / 150 setups (relaxed C1=1.2%/C2=1.0%, 0% liq weight)")
    md.append("")
    md.append("## Current honest backtest")
    md.append("")
    md.append(pd.DataFrame([full_summary]).to_markdown(index=False))
    md.append("")
    md.append("## Walk-forward (4 folds)")
    md.append("")
    md.append(pd.DataFrame(wf).to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    pf = full_summary["pf"]; n = full_summary["n"]
    if n == 0:
        md.append(f"❌ No setups in {LOOKBACK_DAYS}d. Restrictive params too tight.")
    elif n < 20:
        md.append(f"⚠ Only {n} setups in {LOOKBACK_DAYS}d. Sample too small for confidence.")
    elif pf >= 1.5 and pos_folds >= 3:
        md.append(f"✅ STABLE: PF={pf}, {pos_folds}/{N_FOLDS} folds positive. Original 79% claim "
                  f"holds with restrictive C1/C2 + real liq.")
    elif pf >= 1.2:
        md.append(f"🟡 MARGINAL: PF={pf}, {pos_folds}/{N_FOLDS} folds. Original 79% number was "
                  f"inflated by relaxed C1/C2.")
    else:
        md.append(f"❌ POOR: PF={pf}, {pos_folds}/{N_FOLDS}. Either H10 doesn't survive 365d "
                  f"OR our liq map differs significantly from TZ-056 implementation.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[h10-bt] wrote {OUT_MD}")
    print(f"[h10-bt] full: {full_summary}")
    print(f"[h10-bt] WF: {wf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
