"""Edge studies на derivatives данных (binance topls/globalls/oi/taker).

Запуск: python scripts/derivatives_edge_studies.py [--days N]

Что считает:
1. Smart-money divergence (top_trader_long_pct vs global_long_pct)
2. OI delta 1h forward returns
3. Taker buy/sell imbalance
4. Combo BULL/BEAR (divergence × taker)

Текущие данные: ~23 дня (апр-май 2026), гранулярность ~1h, 546 строк.
ВЫБОРКА КОРОТКАЯ — результаты suggestive, не conclusive.
Нужна валидация ≥3 мес перед live size > $1K.

Best findings (commit на момент написания):
- taker_buy_pct > 58% → +4h 68% pct_up, +0.27%; 24h 70% pct_up, +0.63%
- taker_buy_pct < 42% → 4h 62% pct_down, -0.15%
- top-bearish divergence (top_trader_long − global_long < -5pp) → 24h 71% pct_up, +0.87%
  (КОНТРАРИАН: top-traders ≠ smart money)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/historical"
PRICE = ROOT / "backtests/frozen/BTCUSDT_1m_2y.csv"


def load_parq(name: str) -> pd.DataFrame:
    df = pd.read_parquet(DATA / f"binance_{name}_BTCUSDT.parquet")
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    return df.set_index("ts").sort_index()


def fwd_fn(price: pd.DataFrame):
    """Build a function that computes forward return at given hour."""
    def fwd(t: pd.Timestamp, hours: int):
        t_then = t + pd.Timedelta(hours=hours)
        if t_then > price.index[-1] or t < price.index[0]:
            return None
        i0 = price.index.get_indexer([t], method="nearest")[0]
        i1 = price.index.get_indexer([t_then], method="nearest")[0]
        if i0 < 0 or i1 < 0:
            return None
        return (price.close.iloc[i1] / price.close.iloc[i0] - 1) * 100
    return fwd


def print_quantile_table(df: pd.DataFrame, col: str, qcol: str, fwd_cols: list[str]):
    aggs = {"n": (fwd_cols[0], "size"), f"{col}_mean": (col, "mean")}
    for c in fwd_cols:
        aggs[f"{c}_mean"] = (c, "mean")
        aggs[f"{c}_up_pct"] = (c, lambda x: (x > 0).mean() * 100)
    g = df.groupby(qcol, observed=True).agg(**aggs).round(3)
    print(g.to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    args = ap.parse_args()

    top = load_parq("topls")
    glob = load_parq("globalls")
    oi = load_parq("oi")
    taker = load_parq("taker")
    price = pd.read_csv(PRICE, usecols=["ts", "close"])
    price["ts"] = pd.to_datetime(price["ts"], unit="ms", utc=True)
    price = price.set_index("ts").sort_index()
    fwd = fwd_fn(price)

    print(f"Window: {top.index.min()} → {top.index.max()}  rows={len(top)}")
    if args.days:
        cutoff = top.index.max() - pd.Timedelta(days=args.days)
        for name, df in [("top", top), ("glob", glob), ("oi", oi), ("taker", taker)]:
            df.drop(df.index[df.index < cutoff], inplace=True)
        print(f"  After tail {args.days}d: top={len(top)} rows")

    # ── 1. Smart-money divergence ───────────────────────────────────────
    print("\n=== 1. SMART-MONEY DIVERGENCE (top_trader_long − global_long, pp) ===")
    merged = top.join(glob, how="inner", lsuffix="_top", rsuffix="_glob")
    merged = merged.assign(divg=merged["top_trader_long_pct"].values - merged["global_long_pct"].values)
    print(f"Divg: mean={merged.divg.mean():+.2f}pp, std={merged.divg.std():.2f}, range=[{merged.divg.min():+.2f}, {merged.divg.max():+.2f}]")
    for h in (4, 12, 24):
        merged[f"r{h}"] = [fwd(t, h) for t in merged.index]
    m = merged.dropna(subset=["r4", "r12", "r24"]).copy()
    m["q"] = pd.qcut(m["divg"], 5, duplicates="drop", labels=["top_bearish", "q2", "q3", "q4", "top_bullish"])
    print_quantile_table(m, "divg", "q", ["r4", "r24"])
    ex_l = m[m.divg > m.divg.quantile(0.90)]
    ex_s = m[m.divg < m.divg.quantile(0.10)]
    print(f"\nTop 10% top-LONG divg (n={len(ex_l)}): 4h {ex_l.r4.mean():+.2f}% / 24h {ex_l.r24.mean():+.2f}% / win24h {(ex_l.r24>0).mean()*100:.0f}%")
    print(f"Top 10% top-SHORT divg (n={len(ex_s)}): 4h {ex_s.r4.mean():+.2f}% / 24h {ex_s.r24.mean():+.2f}% / win24h {(ex_s.r24>0).mean()*100:.0f}%   ← contrarian edge")

    # ── 2. OI delta ─────────────────────────────────────────────────────
    print("\n\n=== 2. OI DELTA 1h forward returns ===")
    oi_c = oi.assign(oi_d=oi["oi_native"].pct_change() * 100).copy()
    oi_c["r4"] = [fwd(t, 4) for t in oi_c.index]
    oi_c["r24"] = [fwd(t, 24) for t in oi_c.index]
    oi_c = oi_c.dropna(subset=["oi_d", "r4", "r24"])
    print(f"OI 1h Δ: mean={oi_c.oi_d.mean():+.3f}%, std={oi_c.oi_d.std():.3f}")
    oi_c["q"] = pd.qcut(oi_c["oi_d"], 5, duplicates="drop", labels=["drop", "q2", "q3", "q4", "spike"])
    print_quantile_table(oi_c, "oi_d", "q", ["r4", "r24"])

    # ── 3. Taker imbalance ──────────────────────────────────────────────
    print("\n\n=== 3. TAKER BUY/SELL imbalance ===")
    tk = taker.copy()
    tk["r4"] = [fwd(t, 4) for t in tk.index]
    tk["r24"] = [fwd(t, 24) for t in tk.index]
    tk = tk.dropna(subset=["taker_buy_pct", "r4", "r24"])
    print(f"taker_buy_pct: mean={tk.taker_buy_pct.mean():.2f}, std={tk.taker_buy_pct.std():.2f}")
    tk["q"] = pd.qcut(tk["taker_buy_pct"], 5, duplicates="drop", labels=["heavy_sell", "q2", "q3", "q4", "heavy_buy"])
    print_quantile_table(tk, "taker_buy_pct", "q", ["r4", "r24"])

    # ── 4. Combo ────────────────────────────────────────────────────────
    print("\n\n=== 4. COMBO: divergence × taker imbalance ===")
    mt = merged.join(taker[["taker_buy_pct"]], how="inner").dropna(subset=["r4", "r24", "taker_buy_pct"])
    bull = mt[(mt.divg > mt.divg.quantile(0.75)) & (mt.taker_buy_pct > mt.taker_buy_pct.quantile(0.75))]
    bear = mt[(mt.divg < mt.divg.quantile(0.25)) & (mt.taker_buy_pct < mt.taker_buy_pct.quantile(0.25))]
    print(f"BULL combo (top_long div top25 + taker buy top25): n={len(bull)}, 4h {bull.r4.mean():+.2f}% ({(bull.r4>0).mean()*100:.0f}% up), 24h {bull.r24.mean():+.2f}% ({(bull.r24>0).mean()*100:.0f}% up)")
    print(f"BEAR combo (top_short div bottom25 + taker sell top25): n={len(bear)}, 4h {bear.r4.mean():+.2f}% ({(bear.r4>0).mean()*100:.0f}% up), 24h {bear.r24.mean():+.2f}% ({(bear.r24>0).mean()*100:.0f}% up)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
