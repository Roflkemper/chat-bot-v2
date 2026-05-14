"""15m intraday-flush detector backtest (TZ #14, 2026-05-10).

The new grid_coordinator_intraday_loop runs evaluate_exhaustion on 15m TF
and fires when downside_score >= 4. We need to validate it on history
before trusting it in prod.

Approach:
  1. Build 15m bars from frozen 1m for last 365d.
  2. At each 15m close, run evaluate_exhaustion(btc_15m, eth_15m, deriv).
  3. Record all downside signals (score 3, 4, 5, 6).
  4. For each signal at threshold T, look at forward returns 60/120/240 min.
  5. Compute precision (TRUE if price went up >= 0.3%, FALSE if down >= 0.3%).
  6. Specifically check coverage of operator's intraday-flush extrema:
     - 21 Apr 19:46 low (single-bar flush, missed by 1h)
     - 29 Apr 18:10 low
     - 28 Apr 14:41 low

Output: docs/STRATEGIES/GRID_INTRADAY_BACKTEST.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "GRID_INTRADAY_BACKTEST.md"
OUT_CSV = ROOT / "state" / "grid_intraday_signals.csv"

LOOKBACK_DAYS = 365
HORIZONS_MIN = (60, 120, 240)
SUCCESS_PCT = 0.3
FAIL_PCT = 0.3

# Operator extrema we want intraday to catch
KNOWN_EXTREMA = [
    ("2026-04-21 19:46", "low", "intraday flush (missed by 1h)"),
    ("2026-04-29 18:10", "low", "fat low"),
    ("2026-04-28 14:41", "low", "fat low"),
    ("2026-04-20 00:00", "low", "fat"),
    ("2026-04-12 22:30", "low", "fat"),
]


def _build_tf_from_1m(df_1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts_utc").resample(rule).agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()


def main() -> int:
    print(f"[intraday-bt] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv")
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    print(f"[intraday-bt] {len(df_1m):,} 1m bars")

    df_15m = _build_tf_from_1m(df_1m, "15min")
    print(f"[intraday-bt] {len(df_15m):,} 15m bars")

    # ETH 15m (rebuild from 1m if available, else use 1h fallback)
    eth_path = ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv"
    eth_full = pd.read_csv(eth_path)
    if "ts_utc" not in eth_full.columns:
        eth_full["ts_utc"] = pd.to_datetime(eth_full["ts"], unit="ms", utc=True)
    else:
        eth_full["ts_utc"] = pd.to_datetime(eth_full["ts_utc"], utc=True)
    print(f"[intraday-bt] eth 1h bars: {len(eth_full):,} (using 1h as proxy for 15m ETH)")

    deriv = pd.read_parquet(ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet")
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)
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
            except (TypeError, ValueError):
                return d
        return {
            "oi_change_1h_pct": f(row.get("oi_change_1h_pct")),
            "funding_rate_8h": f(row.get("funding_rate_8h")),
            "global_ls_ratio": f(row.get("global_ls_ratio"), 1.0),
        }

    from services.grid_coordinator.loop import evaluate_exhaustion

    print("[intraday-bt] scanning 15m bars for downside signals...")
    signals = []
    df_1m_idx = df_1m.set_index("ts_utc" if "ts_utc" in df_1m.columns
                                 else pd.DatetimeIndex(pd.to_datetime(df_1m["ts"], unit="ms", utc=True)))
    if "ts_utc" not in df_1m.columns:
        df_1m_idx = df_1m.copy()
        df_1m_idx["ts_utc"] = pd.to_datetime(df_1m_idx["ts"], unit="ms", utc=True)
        df_1m_idx = df_1m_idx.set_index("ts_utc").sort_index()
    closes_1m = df_1m_idx["close"]

    for i in range(50, len(df_15m)):
        sub_btc = df_15m.iloc[i - 50:i + 1].reset_index(drop=True)
        ts = sub_btc.iloc[-1]["ts_utc"]
        eth_w = eth_full[eth_full["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        # XRP not available for 15m frozen — pass None
        ev = evaluate_exhaustion(sub_btc, sub_eth, {"BTCUSDT": _deriv_at(ts)}, xrp=None)
        d_score = ev["downside_score"]
        if d_score < 3:
            continue
        price0 = float(sub_btc.iloc[-1]["close"])
        record = {
            "ts": ts, "score": d_score, "price": price0,
            "rsi": ev["details"].get("rsi_btc_now"),
            "mfi": ev["details"].get("mfi_btc_now"),
        }
        # Forward returns
        for h in HORIZONS_MIN:
            target = ts + pd.Timedelta(minutes=h)
            try:
                price1 = float(closes_1m.loc[closes_1m.index.asof(target)])
            except (KeyError, IndexError):
                price1 = np.nan
            if not np.isnan(price1):
                move_pct = (price1 / price0 - 1) * 100
                record[f"ret_{h}m"] = round(move_pct, 3)
                if move_pct >= SUCCESS_PCT: record[f"verdict_{h}m"] = "TRUE"
                elif move_pct <= -FAIL_PCT: record[f"verdict_{h}m"] = "FALSE"
                else: record[f"verdict_{h}m"] = "NEUTRAL"
        signals.append(record)

    df_sigs = pd.DataFrame(signals)
    df_sigs.to_csv(OUT_CSV, index=False)
    print(f"[intraday-bt] {len(df_sigs)} downside signals (score>=3)")
    print(f"  score=3: {(df_sigs['score']==3).sum()}  "
          f"score=4: {(df_sigs['score']==4).sum()}  "
          f"score=5: {(df_sigs['score']==5).sum()}  "
          f"score=6: {(df_sigs['score']==6).sum()}")

    # Verdict matrix per score threshold and horizon
    print("[intraday-bt] computing verdict matrix...")
    rows = []
    for thresh in (3, 4, 5):
        sub = df_sigs[df_sigs["score"] >= thresh]
        for h in HORIZONS_MIN:
            v_col = f"verdict_{h}m"
            if v_col not in sub.columns: continue
            t = (sub[v_col] == "TRUE").sum()
            f = (sub[v_col] == "FALSE").sum()
            n_neutral = (sub[v_col] == "NEUTRAL").sum()
            n_total = t + f
            prec = (t / n_total * 100) if n_total > 0 else 0
            move_col = f"ret_{h}m"
            avg = round(sub[move_col].mean(), 3) if move_col in sub.columns and len(sub) else 0
            rows.append({
                "score>=": thresh, "horizon_min": h,
                "n_signals": len(sub),
                "TRUE": int(t), "FALSE": int(f), "NEUTRAL": int(n_neutral),
                "precision_%": round(prec, 1),
                "avg_move_%": avg,
            })
    df_verdicts = pd.DataFrame(rows)

    # Coverage of operator extrema
    print("[intraday-bt] checking coverage of operator extrema...")
    coverage_rows = []
    for ts_str, kind, descr in KNOWN_EXTREMA:
        target = pd.Timestamp(ts_str, tz="UTC")
        # Look for downside signal in ±2h window around the extremum
        win = df_sigs[(df_sigs["ts"] >= target - pd.Timedelta(hours=2)) &
                     (df_sigs["ts"] <= target + pd.Timedelta(hours=2))]
        if len(win):
            best_score = int(win["score"].max())
            n_sigs = len(win)
            caught_by_4 = (win["score"] >= 4).any()
            coverage_rows.append({
                "extremum": ts_str, "type": kind, "descr": descr,
                "caught": True, "best_score": best_score, "n_signals": n_sigs,
                "score_4_caught": caught_by_4,
            })
        else:
            coverage_rows.append({
                "extremum": ts_str, "type": kind, "descr": descr,
                "caught": False, "best_score": 0, "n_signals": 0,
                "score_4_caught": False,
            })
    df_cov = pd.DataFrame(coverage_rows)

    # Write report
    md = []
    md.append("# 15m intraday grid_coordinator backtest")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d BTCUSDT 15m")
    md.append(f"**Horizons:** 60/120/240 min forward returns")
    md.append(f"**Success/Fail:** ±{SUCCESS_PCT}% in expected direction")
    md.append("")
    md.append(f"**Total signals score>=3:** {len(df_sigs)} "
              f"(~{len(df_sigs)/LOOKBACK_DAYS:.1f}/day)")
    md.append("")
    md.append("## Verdict matrix (downside-only)")
    md.append("")
    md.append(df_verdicts.to_markdown(index=False))
    md.append("")
    md.append("## Coverage of operator extrema")
    md.append("")
    md.append(df_cov.to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    # Best precision at score>=4 240m
    row_4_240 = df_verdicts[(df_verdicts["score>="] == 4) & (df_verdicts["horizon_min"] == 240)]
    if len(row_4_240):
        prec_4_240 = row_4_240.iloc[0]["precision_%"]
        n_4 = row_4_240.iloc[0]["n_signals"]
        if prec_4_240 >= 60 and n_4 >= 20:
            md.append(f"✅ **STABLE: score>=4 at 240m gives {prec_4_240}% precision on N={n_4}.** "
                      f"15m intraday detector is profitable. Production-ready.")
        elif prec_4_240 >= 50:
            md.append(f"🟡 **MARGINAL: {prec_4_240}% on N={n_4}.** Some skill, watch live.")
        else:
            md.append(f"❌ **POOR: {prec_4_240}% precision.** 15m intraday too noisy. "
                      f"Disable in prod or raise threshold to 5.")
    md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[intraday-bt] wrote {OUT_MD}")
    print("\nVerdict matrix:")
    print(df_verdicts.to_string(index=False))
    print("\nExtrema coverage:")
    print(df_cov.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
