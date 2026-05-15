"""OI + price action quadrant edge study.

Анализирует совместное поведение OI delta и price delta за 1h окно →
forward returns 4h/24h. Находит 4 квадранта с разной направленностью.

Результаты (23 дня апр-май 2026, n=544 hourly observations):

  OI↑ price↑ (longs accumulate on up):  4h 70.8% pct_up, +0.24% mean
  OI↑ price↓ (shorts add on down):       4h 40.4% pct_up = 59.6% pct_down, -0.15%
  OI↓ price↑ (short squeeze close):      4h 66.0% pct_up, +0.25%
  OI↓ price↓ (long squeeze on down):     4h 37.9% pct_up = 62.1% pct_down, -0.13%

Сильные сетапы (>0.3% threshold каждой стороны):
  OI↑>0.3 + price↑>0.3 → LONG 4h: 77.8% pct_up, +0.45% (n=18) ← best signal
  OI↓<-0.3 + price↑>0.3 → LONG 4h: 75.0% pct_up, +0.50% (n=16) short squeeze
  OI↑>0.3 + price↓<-0.3 → SHORT 4h: 70.6% pct_down, -0.34% (n=17)
  OI↓<-0.3 + price↓<-0.3 → SHORT 4h: 76.5% pct_down, -0.31% (n=17) long squeeze

⚠ Выборка короткая (23 дня). Перед live wire-up — рекалибровать на >60 дней.

Usage: python scripts/oi_price_quadrant_study.py [--days N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OI_PARQUET = ROOT / "data/historical/binance_oi_BTCUSDT.parquet"
PRICE_CSV = ROOT / "backtests/frozen/BTCUSDT_1m_2y.csv"

THRESHOLD_PCT = 0.3  # 1h move/OI delta threshold для "strong" sets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    args = ap.parse_args()

    oi = pd.read_parquet(OI_PARQUET)
    oi["ts"] = pd.to_datetime(oi["ts_ms"], unit="ms", utc=True)
    oi = oi.set_index("ts").sort_index()
    oi["oi_d_1h"] = oi["oi_native"].pct_change() * 100

    price = pd.read_csv(PRICE_CSV, usecols=["ts", "close"])
    price["ts"] = pd.to_datetime(price["ts"], unit="ms", utc=True)
    price = price.set_index("ts").sort_index()
    price_1h = price.resample("1h").last().reindex(oi.index, method="ffill")
    df = oi.join(price_1h, how="inner").dropna()
    df["price_d_1h"] = df["close"].pct_change() * 100

    if args.days:
        cutoff = df.index.max() - pd.Timedelta(days=args.days)
        df = df[df.index >= cutoff]

    def fwd(t, h):
        t_then = t + pd.Timedelta(hours=h)
        if t_then > price.index[-1] or t < price.index[0]:
            return None
        i0 = price.index.get_indexer([t], method="nearest")[0]
        i1 = price.index.get_indexer([t_then], method="nearest")[0]
        if i0 < 0 or i1 < 0:
            return None
        return (price.close.iloc[i1] / price.close.iloc[i0] - 1) * 100

    df["r4"] = [fwd(t, 4) for t in df.index]
    df["r24"] = [fwd(t, 24) for t in df.index]
    df = df.dropna(subset=["oi_d_1h", "price_d_1h", "r4", "r24"])
    print(f"Joined: {len(df)} hourly rows, {df.index.min()} → {df.index.max()}")

    df["oi_sign"] = np.sign(df["oi_d_1h"])
    df["price_sign"] = np.sign(df["price_d_1h"])

    print(f"\n=== QUADRANTS (1h OI sign / price sign) → forward returns ===")
    print(f"{'oi':>3} {'price':>5} {'n':>5} {'r4_mean':>10} {'r4_up%':>8} {'r24_mean':>10} {'r24_up%':>9}")
    for (oi_s, pr_s), grp in df.groupby(["oi_sign", "price_sign"]):
        if len(grp) < 10:
            continue
        oi_l = "↑" if oi_s > 0 else "↓"
        pr_l = "↑" if pr_s > 0 else "↓"
        print(f"  {oi_l:>3} {pr_l:>5} {len(grp):>5} "
              f"{grp.r4.mean():>+9.3f} {(grp.r4>0).mean()*100:>6.1f}% "
              f"{grp.r24.mean():>+9.3f} {(grp.r24>0).mean()*100:>7.1f}%")

    print(f"\n=== STRONG setups (|move| > {THRESHOLD_PCT}%) ===")
    plays = [
        ("OI↑ + price↑ → LONG (accumulation continuation)",
         df[(df.oi_d_1h > THRESHOLD_PCT) & (df.price_d_1h > THRESHOLD_PCT)], "LONG"),
        ("OI↓ + price↑ → LONG (short squeeze closeout)",
         df[(df.oi_d_1h < -THRESHOLD_PCT) & (df.price_d_1h > THRESHOLD_PCT)], "LONG"),
        ("OI↑ + price↓ → SHORT (distribution / shorts piling)",
         df[(df.oi_d_1h > THRESHOLD_PCT) & (df.price_d_1h < -THRESHOLD_PCT)], "SHORT"),
        ("OI↓ + price↓ → SHORT (long squeeze on down)",
         df[(df.oi_d_1h < -THRESHOLD_PCT) & (df.price_d_1h < -THRESHOLD_PCT)], "SHORT"),
    ]
    for label, grp, direction in plays:
        if len(grp) < 5:
            print(f"\n{label}: n={len(grp)} (too few)")
            continue
        if direction == "LONG":
            pct_correct_4h = (grp.r4 > 0).mean() * 100
            mean_4h = grp.r4.mean()
            mean_24h = grp.r24.mean()
            pct_correct_24h = (grp.r24 > 0).mean() * 100
        else:
            pct_correct_4h = (grp.r4 < 0).mean() * 100
            mean_4h = -grp.r4.mean()
            mean_24h = -grp.r24.mean()
            pct_correct_24h = (grp.r24 < 0).mean() * 100
        print(f"\n{label}: n={len(grp)}")
        print(f"  4h:  pct_correct {pct_correct_4h:.1f}%, mean (in dir) {mean_4h:+.3f}%")
        print(f"  24h: pct_correct {pct_correct_24h:.1f}%, mean (in dir) {mean_24h:+.3f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
