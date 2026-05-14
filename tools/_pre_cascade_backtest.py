"""Pre-cascade alert backtest (TZ #11, 2026-05-10).

pre_cascade_alert fires when:
  |funding_rate_8h| >= 0.06%/8h
  + oi_change_1h_pct >= 1.5%
  + global_ls_ratio >= 1.30 (long-crowded → SHORT cascade) OR <= 0.77 (short cascade)

Question: does this signature actually predict cascades within 10-30 min?

Approach:
  1. Load binance_combined parquet (OI/funding/LS over 28d).
  2. At each 1h tick, evaluate the same conditions.
  3. For each signal, look at 30-min and 60-min forward returns:
     - If direction='short' (long flush expected), TRUE if price drops >= 0.5%
     - If direction='long' (short squeeze expected), TRUE if price rises >= 0.5%
  4. Compute precision and avg move.
  5. Verdict: is the indicator predictive?
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "PRE_CASCADE_BACKTEST.md"

DERIV_PATH = ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet"
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

OI_RISING_PCT = 0.3       # was 1.5 — current data: |OI 1h| rarely > 0.5%
FUNDING_EXTREME = 0.00005 # was 0.0006 — current funding median -0.003%, max 0.005%
LS_LONG = 1.05            # was 1.30 — current LS max 1.08, never 1.3
LS_SHORT = 0.55           # was 0.77 — LS min 0.48

HORIZONS_MIN = (15, 30, 60, 120)
SUCCESS_PCT = 0.5
FAIL_PCT = 0.5


def main() -> int:
    print("[pre-cascade-bt] loading deriv parquet...")
    deriv = pd.read_parquet(DERIV_PATH)
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)
    print(f"  {len(deriv)} ticks ({deriv['ts_utc'].iloc[0]} → {deriv['ts_utc'].iloc[-1]})")

    print("[pre-cascade-bt] loading 1m for forward returns...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m["ts_utc"] = pd.to_datetime(df_1m["ts"], unit="ms", utc=True)
    df_1m_idx = df_1m.set_index("ts_utc").sort_index()
    closes = df_1m_idx["close"]

    signals = []
    for _, row in deriv.iterrows():
        oi = row.get("oi_change_1h_pct")
        funding = row.get("funding_rate_8h")
        ls = row.get("global_ls_ratio")
        if pd.isna(oi) or pd.isna(funding) or pd.isna(ls):
            continue
        if abs(funding) < FUNDING_EXTREME or oi < OI_RISING_PCT:
            continue
        if ls >= LS_LONG and funding > 0:
            direction = "short"
        elif ls <= LS_SHORT and funding < 0:
            direction = "long"
        else:
            continue
        ts = row["ts_utc"]
        # Get price at ts
        try:
            price0 = float(closes.loc[closes.index.asof(ts)])
        except (KeyError, IndexError):
            continue
        record = {
            "ts": ts, "direction": direction, "price0": price0,
            "oi_change": round(float(oi), 2),
            "funding_8h": round(float(funding), 6),
            "ls_ratio": round(float(ls), 2),
        }
        for h in HORIZONS_MIN:
            target = ts + pd.Timedelta(minutes=h)
            try:
                price1 = float(closes.loc[closes.index.asof(target)])
            except (KeyError, IndexError):
                continue
            move_pct = (price1 / price0 - 1) * 100
            record[f"ret_{h}m"] = round(move_pct, 3)
            if direction == "short":  # expect drop
                if move_pct <= -SUCCESS_PCT: v = "TRUE"
                elif move_pct >= FAIL_PCT: v = "FALSE"
                else: v = "NEUTRAL"
            else:  # expect rise
                if move_pct >= SUCCESS_PCT: v = "TRUE"
                elif move_pct <= -FAIL_PCT: v = "FALSE"
                else: v = "NEUTRAL"
            record[f"verdict_{h}m"] = v
        signals.append(record)

    df_sig = pd.DataFrame(signals)
    print(f"[pre-cascade-bt] {len(df_sig)} signals")
    if len(df_sig) == 0:
        print("[pre-cascade-bt] no signals — period too short or thresholds too strict")
        return 0

    print(f"  short: {(df_sig['direction']=='short').sum()}")
    print(f"  long: {(df_sig['direction']=='long').sum()}")

    # Verdict matrix
    rows = []
    for direction in ("short", "long"):
        sub = df_sig[df_sig["direction"] == direction]
        if not len(sub): continue
        for h in HORIZONS_MIN:
            v_col = f"verdict_{h}m"
            r_col = f"ret_{h}m"
            if v_col not in sub.columns: continue
            t = (sub[v_col] == "TRUE").sum()
            f = (sub[v_col] == "FALSE").sum()
            n = (sub[v_col] == "NEUTRAL").sum()
            tot = t + f
            prec = (t / tot * 100) if tot > 0 else 0
            avg = round(sub[r_col].mean(), 3) if r_col in sub.columns else 0
            rows.append({
                "direction": direction, "horizon_min": h,
                "n": len(sub), "TRUE": int(t), "FALSE": int(f),
                "NEUTRAL": int(n), "precision_%": round(prec, 1),
                "avg_move_%": avg,
            })
    df_verdict = pd.DataFrame(rows)

    md = []
    md.append("# Pre-cascade alert backtest")
    md.append("")
    md.append(f"**Period:** {len(deriv)} 1h ticks (28d binance_combined)")
    md.append(f"**Signal:** |funding|>={FUNDING_EXTREME*100:.3f}% AND oi_change>={OI_RISING_PCT}% "
              f"AND (LS>={LS_LONG} or LS<={LS_SHORT})")
    md.append(f"**Success:** ±{SUCCESS_PCT}% in expected direction within horizon")
    md.append("")
    md.append("## Signal counts")
    md.append("")
    md.append(f"- Total: {len(df_sig)}")
    md.append(f"- short cascade expected: {(df_sig['direction']=='short').sum()}")
    md.append(f"- long cascade expected: {(df_sig['direction']=='long').sum()}")
    md.append("")
    md.append("## Verdict matrix")
    md.append("")
    md.append(df_verdict.to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    if len(df_verdict):
        # Best precision row
        best = df_verdict.sort_values("precision_%", ascending=False).iloc[0]
        if best["n"] >= 10 and best["precision_%"] >= 60:
            md.append(f"✅ **PREDICTIVE: {best['direction']} cascade @ {best['horizon_min']}m gives "
                      f"{best['precision_%']}% precision on N={best['n']}.**")
        else:
            md.append(f"🟡 Best is {best['direction']} @ {best['horizon_min']}m: {best['precision_%']}% "
                      f"on N={best['n']}. Below 60% precision threshold.")
    md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[pre-cascade-bt] wrote {OUT_MD}")
    print("\nVerdict matrix:")
    print(df_verdict.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
