"""Cascade GinArea V4 — расширенный параметрический грид по SHORT-каскаду.

Базируется на V3-победителе (SHORT, TD 0.20/0.35/0.60, grid_step=0.03,
indicator_period=30, indicator_threshold=0.3). Меняем:

  grid_step:           [0.02, 0.03, 0.05, 0.08]      (4)
  indicator_period:    [15, 30, 60]                  (3)
  indicator_thresh:    [0.2, 0.3, 0.5]               (3)
  TD триплеты:         5 готовых наборов             (5)

Итого: 4 × 3 × 3 × 5 = 180 каскадов, каждый = 3 бота через engine_v2.
Кэшируем одиночные прогоны по (grid_step, period, thresh, td) — итого
~180 уникальных одиночных прогона (5 наборов × 3 TD = 15 TD значений ×
4 grid × 3 period × 3 thresh = 540, но при пересечении TD-наборов меньше).

Output:
  state/cascade_ginarea_v4_results.csv
  docs/STRATEGIES/CASCADE_GINAREA_V4_BACKTEST.md
"""
from __future__ import annotations

import csv
import itertools
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CODEX_SRC = Path(os.environ.get("CODEX_SRC",
    r"C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src"))
if str(CODEX_SRC) not in sys.path:
    sys.path.insert(0, str(CODEX_SRC))

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "CASCADE_GINAREA_V4_BACKTEST.md"
CSV_OUT = ROOT / "state" / "cascade_ginarea_v4_results.csv"

GRID_STEPS = [0.02, 0.03, 0.05, 0.08]
INDICATOR_PERIODS = [15, 30, 60]
INDICATOR_THRESHOLDS = [0.2, 0.3, 0.5]

# TD триплеты — операторская идея + 4 вариации
TD_TRIPLETS = [
    (0.20, 0.35, 0.60),   # V3 winner
    (0.25, 0.40, 0.55),   # компактнее
    (0.20, 0.40, 0.80),   # шире
    (0.15, 0.30, 0.50),   # все ниже
    (0.30, 0.50, 0.80),   # все выше
]

# Common params (SHORT only; V3 показал что LONG убыточен)
COMMON = dict(
    side="SHORT", contract="LINEAR",
    order_count=800, order_size=0.003,
    instop=0.03, min_stop=0.01, max_stop=0.04,
    dsblin=False,
    boundaries_lower=10_000.0, boundaries_upper=999_999.0,
)

SIM_START = "2025-05-01T00:00:00+00:00"
SIM_END   = "2026-04-29T23:59:59+00:00"


def load_bars():
    from backtest_lab.engine_v2.bot import OHLCBar
    start_ms = int(datetime.fromisoformat(SIM_START).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(SIM_END).timestamp() * 1000)
    bars = []
    with open(DATA_1M, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts_ms = int(float(row["ts"]))
            if ts_ms < start_ms: continue
            if ts_ms > end_ms: break
            dt = datetime.utcfromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            bars.append(OHLCBar(
                ts=dt, open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                volume=float(row.get("volume") or 0),
            ))
    return bars


def run_one_bot(grid_step: float, period: int, thresh: float, td: float, bars: list) -> dict:
    from backtest_lab.engine_v2.bot import BotConfig, GinareaBot
    from backtest_lab.engine_v2.contracts import LINEAR, Side
    bot_cfg = BotConfig(
        bot_id=f"sim_gs{grid_step}_p{period}_th{thresh}_td{td}",
        alias=f"sim_gs{grid_step}_p{period}_th{thresh}_td{td}",
        side=Side.SHORT, contract=LINEAR,
        order_size=COMMON["order_size"], order_count=COMMON["order_count"],
        grid_step_pct=grid_step, target_profit_pct=td,
        min_stop_pct=COMMON["min_stop"], max_stop_pct=COMMON["max_stop"],
        instop_pct=COMMON["instop"],
        boundaries_lower=COMMON["boundaries_lower"],
        boundaries_upper=COMMON["boundaries_upper"],
        indicator_period=period, indicator_threshold_pct=thresh,
        dsblin=False, leverage=100,
    )
    bot = GinareaBot(bot_cfg)
    equity = []
    last_real = 0.0
    for i, bar in enumerate(bars):
        bot.step(bar, i)
        if bot.realized_pnl != last_real:
            equity.append((i, bot.realized_pnl))
            last_real = bot.realized_pnl
    last_price = bars[-1].close if bars else 0.0
    return {
        "realized_usd": bot.realized_pnl,
        "unrealized_usd": bot.unrealized_pnl(last_price),
        "n_trades": len(bot.closed_orders),
        "volume_usd": bot.in_qty_notional + bot.out_qty_notional,
        "equity": equity,
    }


def aggregate_equity(eq_lists, n_bars):
    series = np.zeros(n_bars, dtype=float)
    for eq in eq_lists:
        local = np.zeros(n_bars, dtype=float)
        last = 0.0
        idx_ptr = 0
        for i in range(n_bars):
            while idx_ptr < len(eq) and eq[idx_ptr][0] <= i:
                last = eq[idx_ptr][1]
                idx_ptr += 1
            local[i] = last
        series += local
    return series


def max_dd(equity):
    if equity.size == 0: return 0.0
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity))


def main() -> int:
    print(f"[v4] loading bars {SIM_START} -> {SIM_END}...")
    bars = load_bars()
    n = len(bars)
    print(f"[v4] {n:,} bars")
    if n == 0:
        return 1

    # Unique single-bot keys to run
    all_tds = sorted({td for trip in TD_TRIPLETS for td in trip})
    print(f"[v4] unique TDs: {all_tds}")
    n_singles = len(GRID_STEPS) * len(INDICATOR_PERIODS) * len(INDICATOR_THRESHOLDS) * len(all_tds)
    print(f"[v4] {n_singles} unique single-bot sims to run")

    cache = {}
    done = 0
    for gs in GRID_STEPS:
        for per in INDICATOR_PERIODS:
            for th in INDICATOR_THRESHOLDS:
                for td in all_tds:
                    key = (gs, per, th, td)
                    r = run_one_bot(gs, per, th, td, bars)
                    cache[key] = r
                    done += 1
                    if done % 20 == 0 or done == n_singles:
                        print(f"  [{done}/{n_singles}] gs={gs} per={per} th={th} td={td}  "
                              f"real=${r['realized_usd']:+,.0f}  trades={r['n_trades']}")

    # Build cascades
    print(f"\n[v4] building cascades...")
    results = []
    for gs in GRID_STEPS:
        for per in INDICATOR_PERIODS:
            for th in INDICATOR_THRESHOLDS:
                for trip in TD_TRIPLETS:
                    td1, td2, td3 = trip
                    r1 = cache[(gs, per, th, td1)]
                    r2 = cache[(gs, per, th, td2)]
                    r3 = cache[(gs, per, th, td3)]
                    realized = r1["realized_usd"] + r2["realized_usd"] + r3["realized_usd"]
                    unreal = r1["unrealized_usd"] + r2["unrealized_usd"] + r3["unrealized_usd"]
                    vol = r1["volume_usd"] + r2["volume_usd"] + r3["volume_usd"]
                    n_tr = r1["n_trades"] + r2["n_trades"] + r3["n_trades"]
                    agg = aggregate_equity([r1["equity"], r2["equity"], r3["equity"]], n)
                    dd = max_dd(agg)
                    results.append({
                        "grid_step": gs, "ind_period": per, "ind_thresh": th,
                        "td1": td1, "td2": td2, "td3": td3,
                        "realized": realized, "unrealized": unreal,
                        "total_pnl": realized + unreal, "volume_usd": vol,
                        "n_trades": n_tr, "max_dd": dd,
                        "roi_on_dd": (realized / dd) if dd > 0 else float("inf"),
                    })

    print(f"[v4] {len(results)} cascade combos evaluated")
    results.sort(key=lambda r: r["realized"], reverse=True)
    best = results[0]
    print(f"\n[v4] BEST cascade:")
    print(f"     grid_step={best['grid_step']}  period={best['ind_period']}  "
          f"thresh={best['ind_thresh']}  TD=({best['td1']}, {best['td2']}, {best['td3']})")
    print(f"     realized=${best['realized']:+,.0f}  unreal=${best['unrealized']:+,.0f}  "
          f"DD=${best['max_dd']:,.0f}  ROI/DD={best['roi_on_dd']:.2f}")

    # Top by ROI/DD (capital efficiency)
    finite = [r for r in results if r["max_dd"] > 0]
    finite.sort(key=lambda r: r["roi_on_dd"], reverse=True)
    best_eff = finite[0] if finite else None

    # Report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Cascade GinArea V4 — расширенный параметрический грид\n\n"]
    md.append(f"**Период:** {SIM_START[:10]} → {SIM_END[:10]} ({n:,} 1m bars)\n\n")
    md.append("**Грид:**\n")
    md.append(f"- grid_step: {GRID_STEPS}\n")
    md.append(f"- indicator_period: {INDICATOR_PERIODS}\n")
    md.append(f"- indicator_threshold: {INDICATOR_THRESHOLDS}\n")
    md.append(f"- TD триплеты: {TD_TRIPLETS}\n")
    md.append(f"- Итого: {len(results)} каскадов\n\n")

    md.append("## Топ-20 по realized PnL\n\n")
    md.append("| gs | period | thresh | TD1 | TD2 | TD3 | realized ($) | unreal ($) | "
              "total ($) | vol ($M) | trades | DD ($) | ROI/DD |\n")
    md.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results[:20]:
        md.append(f"| {r['grid_step']} | {r['ind_period']} | {r['ind_thresh']} | "
                  f"{r['td1']} | {r['td2']} | {r['td3']} | "
                  f"{r['realized']:+,.0f} | {r['unrealized']:+,.0f} | "
                  f"{r['total_pnl']:+,.0f} | {r['volume_usd']/1e6:.1f} | "
                  f"{r['n_trades']} | {r['max_dd']:,.0f} | {r['roi_on_dd']:.2f} |\n")

    md.append("\n## Топ-10 по ROI/DD (эффективность капитала)\n\n")
    md.append("| gs | period | thresh | TD triplet | realized ($) | DD ($) | ROI/DD |\n")
    md.append("|---:|---:|---:|---|---:|---:|---:|\n")
    for r in finite[:10]:
        md.append(f"| {r['grid_step']} | {r['ind_period']} | {r['ind_thresh']} | "
                  f"({r['td1']}, {r['td2']}, {r['td3']}) | "
                  f"{r['realized']:+,.0f} | {r['max_dd']:,.0f} | {r['roi_on_dd']:.2f} |\n")

    md.append("\n## Сравнение параметров (среднее realized по гриду)\n\n")
    # average realized by each param
    md.append("### По grid_step\n\n| grid_step | avg realized ($) | avg DD ($) | n |\n|---:|---:|---:|---:|\n")
    for gs in GRID_STEPS:
        rows = [r for r in results if r["grid_step"] == gs]
        avg_r = sum(r["realized"] for r in rows) / len(rows)
        avg_d = sum(r["max_dd"] for r in rows) / len(rows)
        md.append(f"| {gs} | {avg_r:+,.0f} | {avg_d:,.0f} | {len(rows)} |\n")
    md.append("\n### По indicator_period\n\n| period | avg realized ($) | avg DD ($) | n |\n|---:|---:|---:|---:|\n")
    for per in INDICATOR_PERIODS:
        rows = [r for r in results if r["ind_period"] == per]
        avg_r = sum(r["realized"] for r in rows) / len(rows)
        avg_d = sum(r["max_dd"] for r in rows) / len(rows)
        md.append(f"| {per} | {avg_r:+,.0f} | {avg_d:,.0f} | {len(rows)} |\n")
    md.append("\n### По indicator_threshold\n\n| thresh | avg realized ($) | avg DD ($) | n |\n|---:|---:|---:|---:|\n")
    for th in INDICATOR_THRESHOLDS:
        rows = [r for r in results if r["ind_thresh"] == th]
        avg_r = sum(r["realized"] for r in rows) / len(rows)
        avg_d = sum(r["max_dd"] for r in rows) / len(rows)
        md.append(f"| {th} | {avg_r:+,.0f} | {avg_d:,.0f} | {len(rows)} |\n")
    md.append("\n### По TD триплету\n\n| TD triplet | avg realized ($) | avg DD ($) | n |\n|---|---:|---:|---:|\n")
    for trip in TD_TRIPLETS:
        rows = [r for r in results if (r["td1"], r["td2"], r["td3"]) == trip]
        avg_r = sum(r["realized"] for r in rows) / len(rows)
        avg_d = sum(r["max_dd"] for r in rows) / len(rows)
        md.append(f"| {trip} | {avg_r:+,.0f} | {avg_d:,.0f} | {len(rows)} |\n")

    md.append("\n## Худшие 5\n\n")
    md.append("| gs | period | thresh | TD triplet | realized ($) | DD ($) |\n|---:|---:|---:|---|---:|---:|\n")
    for r in results[-5:]:
        md.append(f"| {r['grid_step']} | {r['ind_period']} | {r['ind_thresh']} | "
                  f"({r['td1']}, {r['td2']}, {r['td3']}) | "
                  f"{r['realized']:+,.0f} | {r['max_dd']:,.0f} |\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"[v4] wrote {OUT_MD}")

    pd.DataFrame(results).to_csv(CSV_OUT, index=False)
    print(f"[v4] wrote {CSV_OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
