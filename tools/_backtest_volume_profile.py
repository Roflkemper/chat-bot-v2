"""Volume Profile (POC proxy) edge backtest.

Hypothesis: цена тяготеет к Point of Control (POC) — уровню с наибольшим
объёмом за окно (HVN). После долгого отдаления цена возвращается к POC.
Покупка/продажа на отдалении 1-2% от POC → mean revert к POC.

Proxy (без tick data):
  - Для каждого окна (например 4h) считаем POC как close-price бара с
    максимальным volume в окне.
  - Если current_price отклонился от POC ≥ X% → trade в сторону POC.
  - Hold M часов, exit на close.

Sweep:
  - window_hours: [4, 8, 12, 24]
  - distance_threshold_pct: [1.0, 1.5, 2.0, 2.5]
  - hold_hours: [1, 2, 4, 6]
  - direction: both / long_only / short_only

4 folds walk-forward, fees 2×0.075% taker.

Output:
  docs/STRATEGIES/VOLUME_PROFILE_BACKTEST.md
  state/volume_profile_results.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "VOLUME_PROFILE_BACKTEST.md"
CSV_OUT = ROOT / "state" / "volume_profile_results.csv"
PRICE_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"

WINDOW_HOURS = [4, 8, 12, 24]
DISTANCE_PCT = [1.0, 1.5, 2.0, 2.5]
HOLD_HOURS = [1, 2, 4, 6]
DIRECTIONS = ["both", "long_only", "short_only"]
COOLDOWN_BARS = 4

BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075
N_FOLDS = 4


def load_data() -> pd.DataFrame:
    df = pd.read_csv(PRICE_1H)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def simulate(df: pd.DataFrame, *, window_hours: int, distance_pct: float,
             hold_hours: int, direction_filter: str) -> dict:
    if len(df) < window_hours + hold_hours + 10:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0, "avg_pnl": 0.0, "max_dd": 0.0}

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values
    n = len(df)

    trades = []
    last_trade = -10**9
    threshold = distance_pct / 100

    for i in range(window_hours, n - hold_hours):
        if i - last_trade < COOLDOWN_BARS:
            continue
        # POC proxy = close of bar with max volume in [i-window_hours, i)
        win_vol = volume[i - window_hours:i]
        win_close = close[i - window_hours:i]
        if len(win_vol) == 0:
            continue
        poc_idx_local = int(np.argmax(win_vol))
        poc = float(win_close[poc_idx_local])
        if poc <= 0:
            continue

        cur = float(close[i])
        dev_pct = (cur - poc) / poc

        side = None
        if dev_pct > threshold:
            side = "short"   # price above POC → revert down
        elif dev_pct < -threshold:
            side = "long"

        if side is None:
            continue
        if direction_filter == "long_only" and side != "long":
            continue
        if direction_filter == "short_only" and side != "short":
            continue

        last_trade = i
        entry_price = cur
        exit_price = float(close[i + hold_hours])

        if side == "long":
            gross_pct = (exit_price - entry_price) / entry_price * 100
        else:
            gross_pct = (entry_price - exit_price) / entry_price * 100
        fee_pct = 2 * TAKER_FEE_PCT
        pnl_usd = BASE_SIZE_USD * (gross_pct - fee_pct) / 100
        trades.append({"side": side, "pnl_usd": pnl_usd})

    if not trades:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0, "avg_pnl": 0.0, "max_dd": 0.0}

    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    wr = float((pnls > 0).mean() * 100)
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(peak - eq))
    return {
        "n": len(trades), "pnl": float(pnls.sum()),
        "pf": pf, "wr": wr, "avg_pnl": float(pnls.mean()),
        "max_dd": dd,
    }


def walk_forward(df: pd.DataFrame, *, window_hours: int, distance_pct: float,
                 hold_hours: int, direction_filter: str,
                 n_folds: int = N_FOLDS) -> list[dict]:
    n = len(df)
    fold_size = n // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub = df.iloc[start:end].reset_index(drop=True)
        m = simulate(sub, window_hours=window_hours, distance_pct=distance_pct,
                     hold_hours=hold_hours, direction_filter=direction_filter)
        out.append({"fold": k + 1, "n": m["n"], "pnl": m["pnl"], "pf": m["pf"]})
    return out


def main() -> int:
    print("[vol-profile] loading 1h BTC...")
    df = load_data()
    print(f"[vol-profile] {len(df)} 1h bars")

    results = []
    n_combos = (len(WINDOW_HOURS) * len(DISTANCE_PCT) * len(HOLD_HOURS) * len(DIRECTIONS))
    print(f"[vol-profile] {n_combos} combos\n")
    idx = 0
    for wh in WINDOW_HOURS:
        for dp in DISTANCE_PCT:
            for hh in HOLD_HOURS:
                for direction in DIRECTIONS:
                    idx += 1
                    m = simulate(df, window_hours=wh, distance_pct=dp,
                                 hold_hours=hh, direction_filter=direction)
                    wf = walk_forward(df, window_hours=wh, distance_pct=dp,
                                      hold_hours=hh, direction_filter=direction)
                    pos = sum(1 for f in wf if f["pnl"] > 0)
                    results.append({
                        "window_h": wh, "distance_pct": dp, "hold_h": hh,
                        "direction": direction,
                        "n_trades": m["n"], "pnl_usd": m["pnl"],
                        "pf": m["pf"], "wr_pct": m["wr"],
                        "avg_pnl": m["avg_pnl"], "max_dd": m["max_dd"],
                        "fold_pos": pos, "fold_total": len(wf),
                    })
                    if idx % 30 == 0 or idx == n_combos:
                        print(f"  [{idx}/{n_combos}] w={wh}h d={dp}% hold={hh}h "
                              f"{direction:<10} N={m['n']:>4} "
                              f"PnL=${m['pnl']:+,.0f} PF={m['pf']:.2f} pos={pos}/{len(wf)}")

    results.sort(key=lambda r: r["pnl_usd"], reverse=True)
    print("\n[vol-profile] TOP 15:")
    for r in results[:15]:
        print(f"  w={r['window_h']:>3} d={r['distance_pct']:>4} hold={r['hold_h']:>3} "
              f"{r['direction']:<10} N={r['n_trades']:>4} "
              f"PnL=${r['pnl_usd']:>+9,.0f} PF={r['pf']:>5.2f} "
              f"pos={r['fold_pos']}/{r['fold_total']}")

    # Markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Volume Profile (POC proxy) Backtest — BTC 1h 2y\n\n"]
    md.append("**Стратегия:** POC = close цена бара с max volume в окне. "
              "При отклонении ≥X% от POC → trade в сторону POC.\n\n")
    md.append(f"**Sweep:** window={WINDOW_HOURS}h × distance={DISTANCE_PCT}% × "
              f"hold={HOLD_HOURS}h × {DIRECTIONS} = {len(results)} комбо\n")
    md.append(f"**Период:** {len(df)} 1h bars (~2y)\n\n")

    md.append("## Топ-25 по PnL\n\n")
    md.append("| w | d% | hold | dir | N | PnL ($) | PF | WR% | DD | pos |\n")
    md.append("|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|\n")
    for r in results[:25]:
        md.append(f"| {r['window_h']} | {r['distance_pct']} | {r['hold_h']} | "
                  f"{r['direction']} | {r['n_trades']} | {r['pnl_usd']:+,.0f} | "
                  f"{r['pf']:.2f} | {r['wr_pct']:.0f} | {r['max_dd']:,.0f} | "
                  f"{r['fold_pos']}/{r['fold_total']} |\n")

    md.append("\n## Verdict\n\n")
    qualified = [r for r in results
                 if r["pf"] >= 1.3 and r["n_trades"] >= 50 and r["fold_pos"] >= 3]
    if qualified:
        best = max(qualified, key=lambda r: r["pnl_usd"])
        md.append(f"✅ Edge подтверждён. Best: w={best['window_h']}h d={best['distance_pct']}% "
                  f"hold={best['hold_h']}h {best['direction']} → PF {best['pf']}, "
                  f"PnL ${best['pnl_usd']:+,.0f}, {best['fold_pos']}/4 folds.\n")
    else:
        md.append("❌ Edge не подтверждён (PF≥1.3, N≥50, 3+/4 folds — нет ни одной).\n")
        md.append("Это **proxy POC из 1h volume**, реальный tick-level POC может работать лучше. "
                  "Подождать накопления trade ticks 1-2 месяца и переделать backtest на them.\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[vol-profile] wrote {OUT_MD}")
    pd.DataFrame(results).to_csv(CSV_OUT, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
