"""Funding rate extremes edge — backtest.

Hypothesis: когда funding_rate_8h уходит в экстремум (>+X% или <-X%),
лонги/шорты переплачивают противоположной стороне → mean revert в N часов.

Strategy:
  - funding > +threshold → открыть SHORT (longs overcrowded)
  - funding < -threshold → открыть LONG (shorts overcrowded)
  - hold N hours → close at close-price
  - one trade per funding period (8h)
  - fees: 0.075% taker × 2 (in + out)

Sweep:
  - threshold ∈ [0.02, 0.03, 0.05, 0.08, 0.10] (% per 8h)
  - hold_hours ∈ [4, 8, 12, 24, 48]
  - direction filter: both / long_only / short_only

Walk-forward 4 folds.

Outputs:
  docs/STRATEGIES/FUNDING_EXTREMES_BACKTEST.md
  state/funding_extremes_results.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "FUNDING_EXTREMES_BACKTEST.md"
CSV_OUT = ROOT / "state" / "funding_extremes_results.csv"

FUNDING_PARQUETS = {
    "BTCUSDT": ROOT / "data" / "historical" / "binance_funding_BTCUSDT.parquet",
    "ETHUSDT": ROOT / "data" / "historical" / "binance_funding_ETHUSDT.parquet",
    "XRPUSDT": ROOT / "data" / "historical" / "binance_funding_XRPUSDT.parquet",
}
PRICE_CSV_1H = {
    "BTCUSDT": ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv",
    "ETHUSDT": ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv",
    "XRPUSDT": ROOT / "backtests" / "frozen" / "XRPUSDT_1h_2y.csv",
}
PRICE_CSV_1M = {
    "BTCUSDT": ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv",
    "ETHUSDT": ROOT / "backtests" / "frozen" / "ETHUSDT_1m_2y.csv",
    "XRPUSDT": ROOT / "backtests" / "frozen" / "XRPUSDT_1m_2y.csv",
}

# Sweep
THRESHOLD_PCT = [0.02, 0.03, 0.05, 0.08, 0.10]  # % per 8h
HOLD_HOURS = [4, 8, 12, 24, 48]
DIRECTIONS = ["both", "long_only", "short_only"]

# Per-trade
BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075  # %
N_FOLDS = 4


def load_price_1h(symbol: str) -> pd.DataFrame:
    """Returns DataFrame with ts_ms (int) + close (float), 1h cadence."""
    if symbol in PRICE_CSV_1H and PRICE_CSV_1H[symbol].exists():
        df = pd.read_csv(PRICE_CSV_1H[symbol])
        df = df.sort_values("ts").reset_index(drop=True)
        return df[["ts", "close"]].rename(columns={"ts": "ts_ms"})
    # Fallback: resample 1m
    df = pd.read_csv(PRICE_CSV_1M[symbol])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("dt")
    df_1h = df.resample("1h").agg({"close": "last", "ts": "first"}).dropna()
    return df_1h[["ts", "close"]].rename(columns={"ts": "ts_ms"}).reset_index(drop=True)


def simulate(funding_df: pd.DataFrame, price_df: pd.DataFrame, *,
             threshold_pct: float, hold_hours: int, direction_filter: str) -> dict:
    """Return aggregate metrics for one (threshold, hold, direction) combo."""
    threshold = threshold_pct / 100.0  # to fraction
    trades = []

    # Build a price lookup: for each ts_ms, find close at that hour
    # Both funding and price are sorted by ts_ms. Use searchsorted.
    price_ts = price_df["ts_ms"].values
    price_close = price_df["close"].values

    funding_ts = funding_df["ts_ms"].values
    funding_rate = funding_df["funding_rate_8h"].values

    for i, ts_open in enumerate(funding_ts):
        rate = funding_rate[i]
        if abs(rate) < threshold:
            continue
        # Determine side: positive funding → longs pay → fade longs → SHORT
        if rate > 0:
            side = "short"
        else:
            side = "long"
        if direction_filter == "long_only" and side != "long":
            continue
        if direction_filter == "short_only" and side != "short":
            continue

        # Entry price: close at ts_open (or nearest after)
        idx_in = np.searchsorted(price_ts, ts_open, side="left")
        if idx_in >= len(price_ts):
            continue
        entry_price = float(price_close[idx_in])
        if entry_price <= 0:
            continue

        # Exit: hold_hours later
        ts_exit = ts_open + hold_hours * 3600 * 1000
        idx_out = np.searchsorted(price_ts, ts_exit, side="left")
        if idx_out >= len(price_ts):
            continue
        exit_price = float(price_close[idx_out])

        # PnL
        qty = BASE_SIZE_USD / entry_price
        if side == "long":
            gross_pct = (exit_price - entry_price) / entry_price * 100
        else:
            gross_pct = (entry_price - exit_price) / entry_price * 100
        fee_pct = 2 * TAKER_FEE_PCT  # in + out
        pnl_usd = BASE_SIZE_USD * (gross_pct - fee_pct) / 100
        trades.append({
            "ts_open": int(ts_open), "ts_exit": int(ts_exit),
            "side": side, "rate": float(rate),
            "entry": entry_price, "exit": exit_price,
            "gross_pct": gross_pct, "pnl_usd": pnl_usd,
        })

    if not trades:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0,
                "avg_pnl": 0.0, "max_dd": 0.0, "trades": []}

    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    wr = float((pnls > 0).mean() * 100)
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(peak - eq)) if len(eq) else 0.0
    return {
        "n": len(trades), "pnl": float(pnls.sum()),
        "pf": pf, "wr": wr, "avg_pnl": float(pnls.mean()),
        "max_dd": dd, "trades": trades,
    }


def walk_forward(funding_df: pd.DataFrame, price_df: pd.DataFrame, *,
                 threshold_pct: float, hold_hours: int, direction_filter: str,
                 n_folds: int = N_FOLDS) -> list[dict]:
    n = len(funding_df)
    if n < n_folds * 5:
        return []
    fold_size = n // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub_f = funding_df.iloc[start:end].reset_index(drop=True)
        m = simulate(sub_f, price_df, threshold_pct=threshold_pct,
                     hold_hours=hold_hours, direction_filter=direction_filter)
        out.append({
            "fold": k + 1, "n": m["n"], "pnl": m["pnl"], "pf": m["pf"],
            "wr": m["wr"], "max_dd": m["max_dd"],
        })
    return out


def main(symbol: str = "BTCUSDT") -> int:
    print(f"[funding] symbol={symbol}")
    fpath = FUNDING_PARQUETS[symbol]
    if not fpath.exists():
        print(f"[funding] no funding parquet at {fpath}", file=sys.stderr)
        return 1
    fdf = pd.read_parquet(fpath)
    fdf = fdf.sort_values("ts_ms").reset_index(drop=True)
    print(f"[funding] {len(fdf)} funding events  "
          f"{pd.to_datetime(fdf.iloc[0]['ts_ms'], unit='ms')} -> "
          f"{pd.to_datetime(fdf.iloc[-1]['ts_ms'], unit='ms')}")
    print(f"[funding] rate range: min={fdf['funding_rate_8h'].min()*100:.4f}% "
          f"max={fdf['funding_rate_8h'].max()*100:.4f}% "
          f"std={fdf['funding_rate_8h'].std()*100:.4f}%")

    print(f"[funding] loading price...")
    pdf = load_price_1h(symbol)
    print(f"[funding] {len(pdf)} 1h price bars")

    # Trim funding to within price range
    p_min, p_max = int(pdf["ts_ms"].min()), int(pdf["ts_ms"].max())
    fdf = fdf[(fdf["ts_ms"] >= p_min) & (fdf["ts_ms"] <= p_max - 48*3600*1000)].reset_index(drop=True)
    print(f"[funding] {len(fdf)} funding events after price trim")

    results = []
    n_combos = len(THRESHOLD_PCT) * len(HOLD_HOURS) * len(DIRECTIONS)
    idx = 0
    for th in THRESHOLD_PCT:
        for hh in HOLD_HOURS:
            for direction in DIRECTIONS:
                idx += 1
                m = simulate(fdf, pdf, threshold_pct=th, hold_hours=hh,
                             direction_filter=direction)
                wf = walk_forward(fdf, pdf, threshold_pct=th, hold_hours=hh,
                                  direction_filter=direction)
                pos_folds = sum(1 for f in wf if f["pnl"] > 0)
                results.append({
                    "threshold_pct": th, "hold_hours": hh, "direction": direction,
                    "n_trades": m["n"], "pnl_usd": m["pnl"], "pf": m["pf"],
                    "wr_pct": m["wr"], "avg_pnl_usd": m["avg_pnl"],
                    "max_dd_usd": m["max_dd"],
                    "fold_pos": pos_folds, "fold_total": len(wf),
                    "fold_pnls": [f["pnl"] for f in wf],
                })
                if idx % 10 == 0 or idx == n_combos:
                    print(f"  [{idx}/{n_combos}] th={th:.2f}% hold={hh}h "
                          f"{direction:<10} N={m['n']:>3} PnL=${m['pnl']:+,.0f} "
                          f"PF={m['pf']:.2f} WR={m['wr']:.0f}% pos={pos_folds}/{len(wf)}")

    results.sort(key=lambda r: r["pnl_usd"], reverse=True)
    print("\n[funding] TOP 15 by PnL:")
    print(f"  {'th%':>5} {'hold':>4} {'dir':<10} {'N':>4} {'PnL':>10} {'PF':>5} "
          f"{'WR%':>5} {'avg':>7} {'DD':>7} {'pos':>5}")
    for r in results[:15]:
        print(f"  {r['threshold_pct']:>5.2f} {r['hold_hours']:>4} {r['direction']:<10} "
              f"{r['n_trades']:>4} ${r['pnl_usd']:>+9,.0f} {r['pf']:>5.2f} "
              f"{r['wr_pct']:>5.0f} ${r['avg_pnl_usd']:>+6,.1f} "
              f"${r['max_dd_usd']:>6,.0f} {r['fold_pos']}/{r['fold_total']}")

    # Markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = [f"# Funding Extremes Backtest — {symbol}\n\n"]
    md.append(f"**Funding window:** {pd.to_datetime(fdf['ts_ms'].min(), unit='ms')} -> "
              f"{pd.to_datetime(fdf['ts_ms'].max(), unit='ms')} "
              f"({len(fdf)} 8h periods)\n\n")
    md.append("**Стратегия:**\n")
    md.append("- funding > +threshold (% per 8h) → SHORT (longs переплачивают)\n")
    md.append("- funding < -threshold → LONG (shorts переплачивают)\n")
    md.append(f"- hold N часов → close at market\n")
    md.append(f"- fees: 2 × {TAKER_FEE_PCT}% taker (in + out)\n")
    md.append(f"- size: ${BASE_SIZE_USD} per trade\n\n")

    md.append("**Sweep:**\n")
    md.append(f"- threshold: {THRESHOLD_PCT} (% per 8h)\n")
    md.append(f"- hold: {HOLD_HOURS} (hours)\n")
    md.append(f"- direction: {DIRECTIONS}\n")
    md.append(f"- Total combos: {len(results)}\n\n")

    md.append("## Топ-20 по PnL\n\n")
    md.append("| threshold% | hold | direction | N | PnL ($) | PF | WR% | "
              "avg ($) | DD ($) | pos folds |\n")
    md.append("|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results[:20]:
        md.append(f"| {r['threshold_pct']} | {r['hold_hours']} | {r['direction']} | "
                  f"{r['n_trades']} | {r['pnl_usd']:+,.0f} | {r['pf']:.2f} | "
                  f"{r['wr_pct']:.0f} | {r['avg_pnl_usd']:+,.1f} | "
                  f"{r['max_dd_usd']:,.0f} | {r['fold_pos']}/{r['fold_total']} |\n")

    md.append("\n## Худшие 5\n\n")
    md.append("| threshold% | hold | direction | N | PnL ($) | PF |\n|---:|---:|---|---:|---:|---:|\n")
    for r in results[-5:]:
        md.append(f"| {r['threshold_pct']} | {r['hold_hours']} | {r['direction']} | "
                  f"{r['n_trades']} | {r['pnl_usd']:+,.0f} | {r['pf']:.2f} |\n")

    # Best per direction
    md.append("\n## Best combo per direction\n\n")
    for direction in DIRECTIONS:
        rows = [r for r in results if r["direction"] == direction]
        if not rows: continue
        # Filter PF>1, sort by pnl
        valid = [r for r in rows if r["pf"] > 1.0 and r["fold_pos"] >= 2]
        rows_sorted = sorted(valid or rows, key=lambda r: r["pnl_usd"], reverse=True)
        best = rows_sorted[0]
        md.append(f"### {direction}\n")
        md.append(f"- threshold=**{best['threshold_pct']}%**, hold=**{best['hold_hours']}h**\n")
        md.append(f"- N={best['n_trades']}, PnL=**${best['pnl_usd']:+,.0f}**, "
                  f"PF={best['pf']:.2f}, WR={best['wr_pct']:.0f}%\n")
        md.append(f"- Pos folds: {best['fold_pos']}/{best['fold_total']}\n")
        md.append(f"- Per-fold PnL: {[round(p, 0) for p in best['fold_pnls']]}\n\n")

    # Verdict
    md.append("## Verdict\n\n")
    best_overall = results[0]
    if best_overall["pf"] >= 1.5 and best_overall["fold_pos"] >= 3:
        md.append(f"✅ **{symbol} funding edge подтверждён.** Best combo: "
                  f"threshold={best_overall['threshold_pct']}%, "
                  f"hold={best_overall['hold_hours']}h, "
                  f"{best_overall['direction']} — PF {best_overall['pf']:.2f}, "
                  f"{best_overall['fold_pos']}/{best_overall['fold_total']} positive folds. "
                  f"Готово для paper-trade integration.\n\n")
    elif best_overall["pf"] >= 1.0:
        md.append(f"⚠️ Слабый edge: best PF {best_overall['pf']:.2f}, "
                  f"но мало данных или маргинально. Нужен 2y data перед prod.\n\n")
    else:
        md.append(f"❌ Edge не подтверждён: best PF {best_overall['pf']:.2f}. "
                  f"Либо мало данных, либо threshold/hold не оптимальны.\n\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[funding] wrote {OUT_MD}")

    pd.DataFrame([{k: v for k, v in r.items() if k != "fold_pnls"} for r in results]).to_csv(
        CSV_OUT, index=False)
    print(f"[funding] wrote {CSV_OUT}")
    return 0


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    sys.exit(main(sym))
