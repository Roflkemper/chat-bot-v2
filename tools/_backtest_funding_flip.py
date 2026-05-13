"""Funding flip detector — backtest.

Hypothesis: переход funding с positive→negative (или наоборот) указывает на
смену доминирующего позиционирования. Редко но точно.

Strategy:
  At each funding event:
    prev_rate = funding[i-1]
    curr_rate = funding[i]
    if prev_rate > +threshold AND curr_rate < -threshold:
      "positive→negative flip" — толпа была в лонге, теперь в шорте
      → LONG entry (capitulation of longs done, shorts arriving)
    if prev_rate < -threshold AND curr_rate > +threshold:
      "negative→positive flip" — толпа была в шорте, теперь в лонге
      → SHORT entry (capitulation of shorts done, longs arriving)
  Hold N hours, market exit.

Alternative formulation (stronger possibly):
  Consecutive 3-period EMA cross: smooth funding 3-period EMA crosses zero
  from + to - → LONG, vice versa → SHORT.

Sweep:
  - flip_threshold: [0.001, 0.005, 0.01, 0.02]  (% — both legs must exceed)
  - hold_hours: [8, 24, 48, 72]
  - direction: both / long_only / short_only
  - symbol: BTC, ETH, XRP

4 folds walk-forward.

Outputs:
  docs/STRATEGIES/FUNDING_FLIP_BACKTEST.md
  state/funding_flip_results.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "FUNDING_FLIP_BACKTEST.md"
CSV_OUT = ROOT / "state" / "funding_flip_results.csv"

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

# Sweep
FLIP_THRESHOLDS = [0.001, 0.005, 0.01, 0.02]   # % per 8h, both legs must exceed
HOLD_HOURS = [8, 24, 48, 72]
DIRECTIONS = ["both", "long_only", "short_only"]
SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]

BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075
N_FOLDS = 4


def load_price_1h(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(PRICE_CSV_1H[symbol])
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "close"]].rename(columns={"ts": "ts_ms"})


def simulate(funding_df: pd.DataFrame, price_df: pd.DataFrame, *,
             flip_threshold_pct: float, hold_hours: int,
             direction_filter: str) -> dict:
    threshold = flip_threshold_pct / 100.0
    trades = []

    price_ts = price_df["ts_ms"].values
    price_close = price_df["close"].values
    f_ts = funding_df["ts_ms"].values
    f_rate = funding_df["funding_rate_8h"].values

    for i in range(1, len(f_ts)):
        prev = f_rate[i - 1]
        curr = f_rate[i]
        ts_open = f_ts[i]

        side = None
        # positive → negative flip
        if prev > threshold and curr < -threshold:
            side = "long"   # longs capitulated, shorts now paying — bottom signal
        elif prev < -threshold and curr > threshold:
            side = "short"  # shorts capitulated, longs now paying — top signal

        if side is None:
            continue
        if direction_filter == "long_only" and side != "long":
            continue
        if direction_filter == "short_only" and side != "short":
            continue

        idx_in = np.searchsorted(price_ts, ts_open, side="left")
        if idx_in >= len(price_ts):
            continue
        entry_price = float(price_close[idx_in])
        if entry_price <= 0:
            continue

        ts_exit = ts_open + hold_hours * 3600 * 1000
        idx_out = np.searchsorted(price_ts, ts_exit, side="left")
        if idx_out >= len(price_ts):
            continue
        exit_price = float(price_close[idx_out])

        if side == "long":
            gross_pct = (exit_price - entry_price) / entry_price * 100
        else:
            gross_pct = (entry_price - exit_price) / entry_price * 100
        fee_pct = 2 * TAKER_FEE_PCT
        pnl_usd = BASE_SIZE_USD * (gross_pct - fee_pct) / 100
        trades.append({
            "ts_open": int(ts_open), "side": side,
            "prev_rate": float(prev), "curr_rate": float(curr),
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
                 flip_threshold_pct: float, hold_hours: int,
                 direction_filter: str, n_folds: int = N_FOLDS) -> list[dict]:
    n = len(funding_df)
    if n < n_folds * 5:
        return []
    fold_size = n // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub = funding_df.iloc[start:end].reset_index(drop=True)
        m = simulate(sub, price_df, flip_threshold_pct=flip_threshold_pct,
                     hold_hours=hold_hours, direction_filter=direction_filter)
        out.append({"fold": k + 1, "n": m["n"], "pnl": m["pnl"], "pf": m["pf"]})
    return out


def main() -> int:
    all_results = []
    for symbol in SYMBOLS:
        print(f"\n=== {symbol} ===")
        fpath = FUNDING_PARQUETS[symbol]
        fdf = pd.read_parquet(fpath).sort_values("ts_ms").reset_index(drop=True)
        pdf = load_price_1h(symbol)
        p_min, p_max = int(pdf["ts_ms"].min()), int(pdf["ts_ms"].max())
        fdf = fdf[(fdf["ts_ms"] >= p_min)
                  & (fdf["ts_ms"] <= p_max - 72*3600*1000)].reset_index(drop=True)
        print(f"  {len(fdf)} funding events, "
              f"funding range [{fdf['funding_rate_8h'].min()*100:.3f}%, "
              f"{fdf['funding_rate_8h'].max()*100:.3f}%]")

        # Count flips at various thresholds — quick diag
        rates = fdf["funding_rate_8h"].values
        for th in FLIP_THRESHOLDS:
            pos_to_neg = 0
            neg_to_pos = 0
            for i in range(1, len(rates)):
                if rates[i - 1] > th / 100 and rates[i] < -th / 100:
                    pos_to_neg += 1
                elif rates[i - 1] < -th / 100 and rates[i] > th / 100:
                    neg_to_pos += 1
            print(f"  flip threshold {th}%: pos->neg={pos_to_neg}, neg->pos={neg_to_pos}")

        for th in FLIP_THRESHOLDS:
            for hh in HOLD_HOURS:
                for direction in DIRECTIONS:
                    m = simulate(fdf, pdf, flip_threshold_pct=th,
                                 hold_hours=hh, direction_filter=direction)
                    wf = walk_forward(fdf, pdf, flip_threshold_pct=th,
                                      hold_hours=hh, direction_filter=direction)
                    pos_folds = sum(1 for f in wf if f["pnl"] > 0)
                    all_results.append({
                        "symbol": symbol,
                        "flip_threshold_pct": th, "hold_hours": hh,
                        "direction": direction,
                        "n_trades": m["n"], "pnl_usd": m["pnl"],
                        "pf": m["pf"], "wr_pct": m["wr"],
                        "avg_pnl_usd": m["avg_pnl"], "max_dd_usd": m["max_dd"],
                        "fold_pos": pos_folds, "fold_total": len(wf),
                    })

    all_results.sort(key=lambda r: r["pnl_usd"], reverse=True)
    print("\n[funding-flip] TOP 20 by PnL (across all symbols):")
    print(f"  {'sym':<8} {'th%':>5} {'hold':>4} {'dir':<10} {'N':>4} {'PnL':>10} "
          f"{'PF':>5} {'WR%':>5} {'pos':>5}")
    for r in all_results[:20]:
        print(f"  {r['symbol']:<8} {r['flip_threshold_pct']:>5.3f} "
              f"{r['hold_hours']:>4} {r['direction']:<10} {r['n_trades']:>4} "
              f"${r['pnl_usd']:>+9,.0f} {r['pf']:>5.2f} {r['wr_pct']:>5.0f} "
              f"{r['fold_pos']}/{r['fold_total']}")

    # Markdown report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Funding Flip Backtest — 3 symbols, 2y\n\n"]
    md.append("**Стратегия:**\n")
    md.append("- positive→negative flip (longs пр overpaying, then shorts paying): "
              "LONG entry\n")
    md.append("- negative→positive flip: SHORT entry\n")
    md.append("- both rates must |exceed| threshold (strong flip)\n")
    md.append(f"- size: ${BASE_SIZE_USD}, fees: 2 × {TAKER_FEE_PCT}% taker\n\n")

    md.append(f"**Sweep:** thresholds={FLIP_THRESHOLDS}, holds={HOLD_HOURS}, "
              f"directions={DIRECTIONS}, symbols={SYMBOLS}. "
              f"Total combos: {len(all_results)}\n\n")

    md.append("## Top-25 across all symbols by PnL\n\n")
    md.append("| symbol | flip% | hold | dir | N | PnL ($) | PF | WR% | avg | DD | pos |\n")
    md.append("|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in all_results[:25]:
        md.append(f"| {r['symbol']} | {r['flip_threshold_pct']} | {r['hold_hours']} | "
                  f"{r['direction']} | {r['n_trades']} | {r['pnl_usd']:+,.0f} | "
                  f"{r['pf']:.2f} | {r['wr_pct']:.0f} | {r['avg_pnl_usd']:+,.1f} | "
                  f"{r['max_dd_usd']:,.0f} | {r['fold_pos']}/{r['fold_total']} |\n")

    # Best per symbol
    md.append("\n## Best per symbol (filtered: PF>1.5, N>=20, pos>=3)\n\n")
    for sym in SYMBOLS:
        rows = [r for r in all_results
                if r["symbol"] == sym and r["pf"] > 1.5
                and r["n_trades"] >= 20 and r["fold_pos"] >= 3]
        if not rows:
            md.append(f"### {sym}\n_No combo with PF>1.5, N>=20, 3+/4 pos folds._\n\n")
            continue
        best = max(rows, key=lambda r: r["pnl_usd"])
        md.append(f"### {sym}\n")
        md.append(f"- flip_threshold={best['flip_threshold_pct']}%, hold={best['hold_hours']}h, "
                  f"{best['direction']}\n")
        md.append(f"- N={best['n_trades']}, PnL=**${best['pnl_usd']:+,.0f}**, "
                  f"PF={best['pf']:.2f}, WR={best['wr_pct']:.0f}%, "
                  f"{best['fold_pos']}/{best['fold_total']} folds\n\n")

    md.append("\n## Verdict\n\n")
    qualified = [r for r in all_results
                 if r["pf"] >= 1.5 and r["n_trades"] >= 20 and r["fold_pos"] >= 3]
    if qualified:
        md.append(f"✅ Найдено {len(qualified)} комбинаций PF≥1.5, N≥20, 3+/4 фолда.\n")
        for r in qualified[:5]:
            md.append(f"- {r['symbol']} flip={r['flip_threshold_pct']}% hold={r['hold_hours']}h "
                      f"{r['direction']}: PF {r['pf']:.2f}, N={r['n_trades']}, "
                      f"PnL ${r['pnl_usd']:+,.0f}\n")
    else:
        md.append("❌ Ни одна комбинация не прошла фильтр PF≥1.5, N≥20, 3+/4 фолда. "
                  "Funding flip — редкое событие; статистики недостаточно для prod.\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[funding-flip] wrote {OUT_MD}")

    pd.DataFrame(all_results).to_csv(CSV_OUT, index=False)
    print(f"[funding-flip] wrote {CSV_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
