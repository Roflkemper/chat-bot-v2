"""Cross-asset relative strength / lead-lag backtest.

Hypothesis: альты (XRP, ETH) часто двигаются раньше BTC. Если за последние N
часов XRP вырос/упал заметно сильнее BTC (или ETH сильнее BTC) → BTC скоро
"догонит" в том же направлении. Trade BTC в направлении лидера.

Strategy:
  At each 1h bar:
    btc_return_Nh = (BTC.close[i] - BTC.close[i-N]) / BTC.close[i-N]
    alt_return_Nh = same for alt (ETH or XRP)
    spread = alt_return_Nh - btc_return_Nh
    if spread > +threshold (alt outperformed BTC by X%):
      → LONG BTC entry — BTC will catch up
    if spread < -threshold (alt underperformed):
      → SHORT BTC entry
  Hold M hours, market exit.
  Cooldown 4h between trades.

Sweep:
  - lookback_h: [4, 8, 12, 24]
  - threshold_pct: [0.5, 1.0, 1.5, 2.0]
  - hold_hours: [2, 4, 6, 12]
  - lead_asset: [ETHUSDT, XRPUSDT]
  - direction: both / long_only / short_only

4 folds walk-forward.

Output:
  docs/STRATEGIES/CROSS_ASSET_LEAD_BACKTEST.md
  state/cross_asset_lead_results.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "CROSS_ASSET_LEAD_BACKTEST.md"
CSV_OUT = ROOT / "state" / "cross_asset_lead_results.csv"

PRICE_CSV_1H = {
    "BTCUSDT": ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv",
    "ETHUSDT": ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv",
    "XRPUSDT": ROOT / "backtests" / "frozen" / "XRPUSDT_1h_2y.csv",
}

LOOKBACK_HOURS = [4, 8, 12, 24]
THRESHOLD_PCT = [0.5, 1.0, 1.5, 2.0]
HOLD_HOURS = [2, 4, 6, 12]
LEAD_ASSETS = ["ETHUSDT", "XRPUSDT"]
DIRECTIONS = ["both", "long_only", "short_only"]
COOLDOWN_HOURS = 4

BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075
N_FOLDS = 4


def load_price_1h(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(PRICE_CSV_1H[symbol])
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "close"]].rename(columns={"ts": "ts_ms"})


def align_on_ts(btc: pd.DataFrame, alt: pd.DataFrame) -> pd.DataFrame:
    """Inner-join by ts_ms. Returns df with columns: ts_ms, btc_close, alt_close."""
    merged = btc.merge(alt, on="ts_ms", suffixes=("_btc", "_alt"))
    merged = merged.rename(columns={"close_btc": "btc_close", "close_alt": "alt_close"})
    merged = merged.sort_values("ts_ms").reset_index(drop=True)
    return merged


def simulate(merged: pd.DataFrame, *, lookback_h: int, threshold_pct: float,
             hold_hours: int, direction_filter: str) -> dict:
    if len(merged) < lookback_h + hold_hours + 10:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0,
                "avg_pnl": 0.0, "max_dd": 0.0}

    btc = merged["btc_close"].values
    alt = merged["alt_close"].values
    n = len(merged)
    threshold = threshold_pct / 100.0
    cooldown_bars = COOLDOWN_HOURS  # bars are 1h

    trades = []
    last_trade = -10**9

    for i in range(lookback_h, n - hold_hours):
        if i - last_trade < cooldown_bars:
            continue
        btc_ret = (btc[i] - btc[i - lookback_h]) / btc[i - lookback_h]
        alt_ret = (alt[i] - alt[i - lookback_h]) / alt[i - lookback_h]
        spread = alt_ret - btc_ret

        side = None
        if spread > threshold:
            side = "long"   # alt led up; BTC should catch up
        elif spread < -threshold:
            side = "short"  # alt led down

        if side is None:
            continue
        if direction_filter == "long_only" and side != "long":
            continue
        if direction_filter == "short_only" and side != "short":
            continue

        last_trade = i
        entry_price = float(btc[i])
        exit_price = float(btc[i + hold_hours])
        if entry_price <= 0:
            continue

        if side == "long":
            gross_pct = (exit_price - entry_price) / entry_price * 100
        else:
            gross_pct = (entry_price - exit_price) / entry_price * 100
        fee_pct = 2 * TAKER_FEE_PCT
        pnl_usd = BASE_SIZE_USD * (gross_pct - fee_pct) / 100
        trades.append({
            "i": i, "side": side, "spread": float(spread),
            "entry": entry_price, "exit": exit_price,
            "pnl_usd": pnl_usd,
        })

    if not trades:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0,
                "avg_pnl": 0.0, "max_dd": 0.0}

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
        "max_dd": dd,
    }


def walk_forward(merged: pd.DataFrame, *, lookback_h: int, threshold_pct: float,
                 hold_hours: int, direction_filter: str,
                 n_folds: int = N_FOLDS) -> list[dict]:
    n = len(merged)
    fold_size = n // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub = merged.iloc[start:end].reset_index(drop=True)
        m = simulate(sub, lookback_h=lookback_h, threshold_pct=threshold_pct,
                     hold_hours=hold_hours, direction_filter=direction_filter)
        out.append({"fold": k + 1, "n": m["n"], "pnl": m["pnl"], "pf": m["pf"]})
    return out


def main() -> int:
    print("[cross-lead] loading BTC 1h...")
    btc = load_price_1h("BTCUSDT")
    print(f"[cross-lead] BTC: {len(btc)} 1h bars")

    all_results = []
    for lead_asset in LEAD_ASSETS:
        print(f"\n=== Lead asset: {lead_asset} ===")
        alt = load_price_1h(lead_asset)
        merged = align_on_ts(btc, alt)
        print(f"  merged: {len(merged)} 1h bars after inner-join")

        n_combos_per_lead = (len(LOOKBACK_HOURS) * len(THRESHOLD_PCT)
                              * len(HOLD_HOURS) * len(DIRECTIONS))
        idx = 0
        for lb in LOOKBACK_HOURS:
            for th in THRESHOLD_PCT:
                for hh in HOLD_HOURS:
                    for direction in DIRECTIONS:
                        idx += 1
                        m = simulate(merged, lookback_h=lb,
                                     threshold_pct=th, hold_hours=hh,
                                     direction_filter=direction)
                        wf = walk_forward(merged, lookback_h=lb,
                                          threshold_pct=th, hold_hours=hh,
                                          direction_filter=direction)
                        pos_folds = sum(1 for f in wf if f["pnl"] > 0)
                        all_results.append({
                            "lead_asset": lead_asset,
                            "lookback_h": lb, "threshold_pct": th,
                            "hold_hours": hh, "direction": direction,
                            "n_trades": m["n"], "pnl_usd": m["pnl"],
                            "pf": m["pf"], "wr_pct": m["wr"],
                            "avg_pnl_usd": m["avg_pnl"], "max_dd_usd": m["max_dd"],
                            "fold_pos": pos_folds, "fold_total": len(wf),
                        })
                        if idx % 30 == 0 or idx == n_combos_per_lead:
                            print(f"  [{idx}/{n_combos_per_lead}] lb={lb}h th={th}% "
                                  f"hold={hh}h {direction:<10} N={m['n']:>4} "
                                  f"PnL=${m['pnl']:+,.0f} PF={m['pf']:.2f} "
                                  f"pos={pos_folds}/{len(wf)}")

    all_results.sort(key=lambda r: r["pnl_usd"], reverse=True)
    print("\n[cross-lead] TOP 20 by PnL:")
    print(f"  {'lead':<8} {'lb':>3} {'th':>4} {'hold':>4} {'dir':<10} {'N':>4} "
          f"{'PnL':>10} {'PF':>5} {'pos':>4}")
    for r in all_results[:20]:
        print(f"  {r['lead_asset']:<8} {r['lookback_h']:>3} {r['threshold_pct']:>4.1f} "
              f"{r['hold_hours']:>4} {r['direction']:<10} {r['n_trades']:>4} "
              f"${r['pnl_usd']:>+9,.0f} {r['pf']:>5.2f} {r['fold_pos']}/{r['fold_total']}")

    # Markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Cross-Asset Lead-Lag Backtest — BTC follows ETH/XRP\n\n"]
    md.append(f"**Период:** ~2y BTCUSDT 1h, target=BTCUSDT, leads={LEAD_ASSETS}\n\n")
    md.append("**Стратегия:**\n")
    md.append("- В каждом 1h баре считаем return BTC и return альта (ETH или XRP) "
              "за `lookback_h` часов\n")
    md.append("- spread = alt_return - btc_return\n")
    md.append("- если spread > +threshold → LONG BTC (BTC догонит)\n")
    md.append("- если spread < -threshold → SHORT BTC\n")
    md.append(f"- hold N часов; cooldown {COOLDOWN_HOURS}h между trade-ми\n")
    md.append(f"- fees 2×{TAKER_FEE_PCT}% taker, size ${BASE_SIZE_USD}\n\n")

    md.append(f"**Sweep:** lookback={LOOKBACK_HOURS}, threshold={THRESHOLD_PCT}, "
              f"hold={HOLD_HOURS}, direction={DIRECTIONS}, lead={LEAD_ASSETS}. "
              f"Total combos: {len(all_results)}\n\n")

    md.append("## Топ-25 по PnL\n\n")
    md.append("| lead | lb | th% | hold | dir | N | PnL ($) | PF | WR% | avg | DD | pos |\n")
    md.append("|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in all_results[:25]:
        md.append(f"| {r['lead_asset']} | {r['lookback_h']} | {r['threshold_pct']} | "
                  f"{r['hold_hours']} | {r['direction']} | {r['n_trades']} | "
                  f"{r['pnl_usd']:+,.0f} | {r['pf']:.2f} | {r['wr_pct']:.0f} | "
                  f"{r['avg_pnl_usd']:+,.1f} | {r['max_dd_usd']:,.0f} | "
                  f"{r['fold_pos']}/{r['fold_total']} |\n")

    md.append("\n## Best per lead (filtered: PF>=1.3, N>=50, pos>=3)\n\n")
    for lead in LEAD_ASSETS:
        rows = [r for r in all_results
                if r["lead_asset"] == lead and r["pf"] >= 1.3
                and r["n_trades"] >= 50 and r["fold_pos"] >= 3]
        if not rows:
            md.append(f"### {lead}\n_No combo qualified._\n\n")
            continue
        best = max(rows, key=lambda r: r["pnl_usd"])
        md.append(f"### {lead}\n")
        md.append(f"- lookback={best['lookback_h']}h, threshold={best['threshold_pct']}%, "
                  f"hold={best['hold_hours']}h, {best['direction']}\n")
        md.append(f"- N={best['n_trades']}, PnL=**${best['pnl_usd']:+,.0f}**, "
                  f"PF={best['pf']:.2f}, WR={best['wr_pct']:.0f}%, "
                  f"{best['fold_pos']}/{best['fold_total']} folds\n\n")

    md.append("\n## Verdict\n\n")
    qualified = [r for r in all_results
                 if r["pf"] >= 1.3 and r["n_trades"] >= 50 and r["fold_pos"] >= 3]
    if qualified:
        md.append(f"✅ {len(qualified)} combos passed PF≥1.3, N≥50, 3+/4 folds.\n")
    else:
        md.append("❌ No combos passed filter PF≥1.3, N≥50, 3+/4 folds.\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[cross-lead] wrote {OUT_MD}")

    pd.DataFrame(all_results).to_csv(CSV_OUT, index=False)
    print(f"[cross-lead] wrote {CSV_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
