"""Walk-forward для top-кандидатов из range_hunter_multi_tf.

Проверяем что 5m_12h_24h_0.30 (наш чемпион по PnL, $80K за 2y) не overfit
на конкретное окно — прогоняем 4 хронологических фолда без рефита параметров.

Также прогоняем 15m_24h_48h_0.60 (high-avg вариант) для сравнения.

Usage: python scripts/range_hunter_multi_tf_walkforward.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Импорт логики из multi_tf
sys.path.insert(0, str(Path(__file__).resolve().parent))
from range_hunter_multi_tf import P, backtest, resample, PRICE


CANDIDATES = [
    ("1m_4h_6h_0.10  (baseline)",  "1min",  P(240, 0.70, 0.10, 0.10, 360, 120, 0.20)),
    ("5m_12h_24h_0.30 (champ)",    "5min",  P(144, 2.50, 0.25, 0.30, 288, 24,  0.60)),
    ("15m_24h_48h_0.60",           "15min", P(96,  4.00, 0.40, 0.60, 192, 8,   1.20)),
]


def summarize_trades(trades: list[tuple[str, float]]) -> dict:
    if not trades:
        return {"n": 0}
    wins = sum(1 for o, pnl in trades if pnl > 0)
    total = sum(pnl for _, pnl in trades)
    pnls = [pnl for _, pnl in trades]
    cum = np.cumsum(pnls)
    dd = float(np.min(cum - np.maximum.accumulate(cum)))
    return {
        "n": len(trades),
        "wins": wins,
        "wr": wins / len(trades) * 100,
        "total": total,
        "avg": total / len(trades),
        "dd": dd,
    }


def main():
    print(f"Loading 1m baseline...")
    df1m = pd.read_csv(PRICE, usecols=["ts", "open", "high", "low", "close"])
    df1m["ts"] = pd.to_datetime(df1m["ts"], unit="ms", utc=True)
    df1m = df1m.sort_values("ts").reset_index(drop=True)
    print(f"  {len(df1m):,} bars  {df1m.ts.iloc[0]} → {df1m.ts.iloc[-1]}")

    # Build resampled dataframes once
    by_rule = {
        "1min": df1m,
        "5min": resample(df1m, "5min"),
        "15min": resample(df1m, "15min"),
    }

    for label, rule, p in CANDIDATES:
        df = by_rule[rule]
        print(f"\n{'='*78}")
        print(f"  {label}")
        print(f"  bars={len(df):,}  lookback_bars={p.lookback_bars}  hold={p.hold_bars}  width={p.width_pct}%  SL={p.stop_loss_pct}%")
        print(f"{'='*78}")
        n_folds = 4
        fold_results = []
        for k in range(n_folds):
            a = len(df) * k // n_folds
            b = len(df) * (k + 1) // n_folds
            sub = df.iloc[a:b].reset_index(drop=True)
            window = f"{sub.ts.iloc[0].strftime('%Y-%m-%d')} → {sub.ts.iloc[-1].strftime('%Y-%m-%d')}"
            tr = backtest(sub, p)
            s = summarize_trades(tr)
            if s["n"] == 0:
                print(f"  fold_{k+1}  {window}    (no signals)")
                continue
            fold_results.append(s)
            print(f"  fold_{k+1}  {window}   n={s['n']:>5}  WR={s['wr']:>5.1f}%  total=${s['total']:>+9,.0f}  avg=${s['avg']:>+6.2f}  DD=${s['dd']:>+7.0f}")
        if fold_results:
            wrs = [r["wr"] for r in fold_results]
            totals = [r["total"] for r in fold_results]
            print(f"  ─── consistency ───")
            print(f"  WR диапазон: {min(wrs):.1f}% – {max(wrs):.1f}%  std={np.std(wrs):.2f}")
            print(f"  PnL диапазон: ${min(totals):+,.0f}..${max(totals):+,.0f}  все 4 положительные: {all(t > 0 for t in totals)}")
            print(f"  Sum total: ${sum(totals):+,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
