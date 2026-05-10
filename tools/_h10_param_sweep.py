"""H10 parameter sweep — find values that produce reasonable signal density
without sacrificing edge.

Original backtest (TZ-053a, 150 setups, 79.3% WR) used relaxed C1=1.2%, C2=1.0%.
Current detector (TZ-056) restored strict C1=1.5%, C2=2.5%. On 365d → 0 setups.

This sweep tries 4 combinations:
  A. STRICT current (C1=1.5%, C2=2.5%, weight>=0.5)
  B. RELAXED original (C1=1.2%, C2=1.0%, weight>=0.5)  -- claim was 79.3% WR
  C. MEDIUM  (C1=1.2%, C2=2.0%, weight>=0.4)
  D. LOOSE  (C1=1.0%, C2=3.0%, weight>=0.3)

For each: emit setups on 365d, simulate trades, count WR/PF/PnL.
Higher freq_bars=15 (every 15 min check) to match live granularity.
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
    _build_aggregations, _simulate_trade, _StubCtx, DATA_1M,
)
from services.h10_detector import detect_setup as h10_detect
from services.liquidity_map import build_liquidity_map

OUT_MD = ROOT / "docs" / "STRATEGIES" / "H10_PARAM_SWEEP.md"

LOOKBACK_DAYS = 365
FREQ_BARS = 60   # check H10 every 60 1m bars = 1h (was 60 in default)

# H10 trade params from h10_adapter.py
H10_TP_PCT = 0.5
H10_STOP_PCT = 0.8
H10_HOLD_MIN = 120

CONFIGS = [
    {"name": "A_STRICT (current)", "min_impulse": 0.015, "consol_range_max": 0.025, "weight": 0.50},
    {"name": "B_RELAXED (TZ-053a)", "min_impulse": 0.012, "consol_range_max": 0.010, "weight": 0.50},
    {"name": "C_MEDIUM", "min_impulse": 0.012, "consol_range_max": 0.020, "weight": 0.40},
    {"name": "D_LOOSE", "min_impulse": 0.010, "consol_range_max": 0.030, "weight": 0.30},
]


def _emit_h10(df_1m, df_1h, cfg) -> list[dict]:
    """Walk df_1m at FREQ_BARS interval, call h10_detect, collect setups."""
    emits = []
    n = len(df_1m)
    ts_1m = df_1m["ts"].values
    ts_1h = df_1h["ts"].values
    min_1h = 60  # need at least 60h history for impulse+consol scan
    for i in range(0, n, FREQ_BARS):
        if i < 60 * 24:
            continue
        h_idx = int(np.searchsorted(ts_1h, ts_1m[i], side="right")) - 1
        if h_idx < min_1h:
            continue
        sub_1h = df_1h.iloc[max(0, h_idx - 100):h_idx + 1].reset_index(drop=True)
        if not isinstance(sub_1h.index, pd.DatetimeIndex):
            sub_1h_ts = pd.to_datetime(sub_1h["ts"], unit="ms", utc=True)
            sub_1h_idx = sub_1h.copy()
            sub_1h_idx.index = sub_1h_ts
        else:
            sub_1h_idx = sub_1h
        ts = pd.to_datetime(int(ts_1m[i]), unit="ms", utc=True)
        try:
            liq_map = build_liquidity_map(ts, ohlcv_1h=sub_1h_idx)
        except Exception:
            continue
        if not liq_map:
            continue
        try:
            h10_setup = h10_detect(
                ts, sub_1h_idx, liq_map,
                weight_threshold=cfg["weight"],
                min_impulse_pct=cfg["min_impulse"],
                consol_range_max=cfg["consol_range_max"],
            )
        except Exception:
            continue
        if h10_setup is None:
            continue
        # Build trade emission for our simulator
        current_price = float(df_1m["close"].iloc[i])
        if h10_setup.target_side == "long_probe":
            side = "long"
            entry = current_price
            tp1 = entry * (1 + H10_TP_PCT / 100)
            tp2 = entry * (1 + H10_TP_PCT * 2 / 100)
            sl = entry * (1 - H10_STOP_PCT / 100)
        else:
            side = "short"
            entry = current_price
            tp1 = entry * (1 - H10_TP_PCT / 100)
            tp2 = entry * (1 - H10_TP_PCT * 2 / 100)
            sl = entry * (1 + H10_STOP_PCT / 100)
        emits.append({
            "bar_idx": i, "ts": int(ts_1m[i]),
            "setup_type": "h10", "side": side,
            "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
            "window_min": H10_HOLD_MIN,
        })
    return emits


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


def main() -> int:
    print(f"[h10-sweep] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    df_15m, df_1h = _build_aggregations(df_1m)
    print(f"[h10-sweep] {len(df_1m):,} 1m / {len(df_1h):,} 1h")

    rows = []
    for cfg in CONFIGS:
        print(f"\n[h10-sweep] === {cfg['name']} ===")
        print(f"  C1>={cfg['min_impulse']*100:.1f}% C2<={cfg['consol_range_max']*100:.1f}% "
              f"weight>={cfg['weight']}")
        emits = _emit_h10(df_1m, df_1h, cfg)
        print(f"  emits: {len(emits)}")
        if not emits:
            rows.append({"config": cfg["name"], "n": 0, "wr": 0, "pf": 0, "pnl_pct": 0,
                         "long_n": 0, "short_n": 0})
            continue
        trades = []
        for e in emits:
            r = _simulate_trade(e, df_1m)
            trades.append({"ts": e["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct,
                           "side": e["side"]})
        s = _summary(trades)
        long_n = sum(1 for t in trades if t["side"] == "long")
        short_n = sum(1 for t in trades if t["side"] == "short")
        rows.append({"config": cfg["name"], **s, "long_n": long_n, "short_n": short_n})
        print(f"  N={s['n']} WR={s['wr']}% PF={s['pf']} PnL={s['pnl_pct']}% "
              f"(long {long_n} / short {short_n})")

    df_out = pd.DataFrame(rows)

    md = []
    md.append("# H10 parameter sweep")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d BTCUSDT 1m honest engine")
    md.append(f"**TP/SL/hold:** +{H10_TP_PCT}% / -{H10_STOP_PCT}% / {H10_HOLD_MIN}min")
    md.append(f"**Detection frequency:** every {FREQ_BARS} 1m bars (1h)")
    md.append("")
    md.append("## Sweep results")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    # Find best by PF (with N >= 30)
    eligible = df_out[df_out["n"] >= 30].copy()
    if len(eligible):
        best = eligible.sort_values("pf", ascending=False).iloc[0]
        if best["pf"] >= 1.5:
            md.append(f"✅ **Best: {best['config']}** PF={best['pf']}, "
                      f"PnL={best['pnl_pct']}%, N={best['n']}, WR={best['wr']}%. "
                      f"Recommend updating h10_detector defaults.")
        elif best["pf"] >= 1.2:
            md.append(f"🟡 **Marginal: {best['config']}** PF={best['pf']}.")
        else:
            md.append(f"❌ Even best config gives PF={best['pf']}. H10 doesn't work as live "
                      f"strategy at these params.")
    else:
        md.append(f"❌ No config with N>=30 — all configs too restrictive for {LOOKBACK_DAYS}d.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[h10-sweep] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
