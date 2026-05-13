"""Cascade GinArea V3 — 3 настоящих GinArea-бота (engine_v2) с разными TD.

Operator clarification:
  - 3 бота SHORT (одна сторона) с одинаковым grid_step = 0.03% но разными TD:
    бот-1 (быстрый): TD 20-25
    бот-2 (средний): TD 30-40
    бот-3 (редкий):  TD 50-60
  - Аналогично 3 бота LONG.
  - Каждый — это полноценный GinareaBot из backtest_lab.engine_v2 с реальной
    механикой: indicator → instop → grid усреднение → out_stop_group trailing.

Тестируем grid TD-комбинаций (фактически 3 × 3 × 3 sets для SHORT + 3 × 3 × 3 для LONG).
Метрики: суммарный PnL, объём, max DD от агрегированного equity curve.

Outputs:
  state/cascade_ginarea_v3_results.csv
  docs/STRATEGIES/CASCADE_GINAREA_V3_BACKTEST.md
"""
from __future__ import annotations

import csv
import itertools
import os
import sys
from dataclasses import dataclass
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
OUT_MD = ROOT / "docs" / "STRATEGIES" / "CASCADE_GINAREA_V3_BACKTEST.md"

# --- TD scenarios per tier (% target profit) ---
# Bot 1 (fast/freq): TD in [0.20, 0.22, 0.25]
# Bot 2 (mid):       TD in [0.30, 0.35, 0.40]
# Bot 3 (slow):      TD in [0.50, 0.55, 0.60]
TD_BOT1 = [0.20, 0.22, 0.25]
TD_BOT2 = [0.30, 0.35, 0.40]
TD_BOT3 = [0.50, 0.55, 0.60]

# Common GinArea params from calibration (real production values).
COMMON_SHORT = dict(
    side="SHORT", contract="LINEAR",
    grid_step=0.03, order_count=800, order_size=0.003,
    instop=0.03, min_stop=0.01, max_stop=0.04,
    dsblin=False,
    boundaries_lower=10_000.0, boundaries_upper=999_999.0,
    indicator_period=30, indicator_threshold_pct=0.3,
)
COMMON_LONG = dict(
    side="LONG", contract="INVERSE",
    grid_step=0.03, order_count=800, order_size=200.0,
    instop=0.018, min_stop=0.01, max_stop=0.30,
    dsblin=False,
    boundaries_lower=10_000.0, boundaries_upper=999_999.0,
    indicator_period=30, indicator_threshold_pct=0.3,
)

# Use last 1 year of OHLCV to keep runs tractable (3 bots × N combos × N bars).
SIM_START = "2025-05-01T00:00:00+00:00"
SIM_END   = "2026-04-29T23:59:59+00:00"


def load_bars():
    """Load OHLC bars as engine_v2 OHLCBar list (single linear scan over 1y window)."""
    from backtest_lab.engine_v2.bot import OHLCBar
    start_ms = int(datetime.fromisoformat(SIM_START).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(SIM_END).timestamp() * 1000)
    bars = []
    with open(DATA_1M, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_ms = int(float(row["ts"]))
            if ts_ms < start_ms:
                continue
            if ts_ms > end_ms:
                break
            dt = datetime.utcfromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            bars.append(OHLCBar(
                ts=dt,
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                volume=float(row.get("volume") or 0),
            ))
    return bars


def run_one_bot(cfg: dict, td: float, bars: list) -> dict:
    """Run one GinareaBot end-to-end. Returns dict with realized, n_trades, vol, equity."""
    from backtest_lab.engine_v2.bot import BotConfig, GinareaBot
    from backtest_lab.engine_v2.contracts import LINEAR, INVERSE, Side
    side = Side.SHORT if cfg["side"] == "SHORT" else Side.LONG
    contract = LINEAR if cfg["contract"] == "LINEAR" else INVERSE
    bot_cfg = BotConfig(
        bot_id=f"sim_{cfg['side']}_td{td}",
        alias=f"sim_{cfg['side']}_td{td}",
        side=side, contract=contract,
        order_size=cfg["order_size"], order_count=cfg["order_count"],
        grid_step_pct=cfg["grid_step"], target_profit_pct=td,
        min_stop_pct=cfg["min_stop"], max_stop_pct=cfg["max_stop"],
        instop_pct=cfg["instop"],
        boundaries_lower=cfg["boundaries_lower"],
        boundaries_upper=cfg["boundaries_upper"],
        indicator_period=cfg["indicator_period"],
        indicator_threshold_pct=cfg["indicator_threshold_pct"],
        dsblin=cfg["dsblin"], leverage=100,
    )
    bot = GinareaBot(bot_cfg)
    # Track realized PnL trajectory at each closed_order event
    equity = []
    last_real = 0.0
    for i, bar in enumerate(bars):
        bot.step(bar, i)
        if bot.realized_pnl != last_real:
            equity.append((i, bot.realized_pnl))
            last_real = bot.realized_pnl
    last_price = bars[-1].close if bars else 0.0
    unreal = bot.unrealized_pnl(last_price)
    # Convert INVERSE realized BTC → USD at last price for unified PnL comparison
    if cfg["contract"] == "INVERSE":
        realized_usd = bot.realized_pnl * last_price
        unreal_usd = unreal * last_price
        vol_usd = bot.in_qty_notional + bot.out_qty_notional  # already USD notional
    else:
        realized_usd = bot.realized_pnl
        unreal_usd = unreal
        vol_usd = bot.in_qty_notional + bot.out_qty_notional
    return {
        "realized_usd": realized_usd,
        "unrealized_usd": unreal_usd,
        "n_trades": len(bot.closed_orders),
        "volume_usd": vol_usd,
        "equity": equity,
        "last_price": last_price,
    }


def aggregate_equity(eq_lists: list[list[tuple[int, float]]], n_bars: int) -> np.ndarray:
    """Align multiple per-bot equity step-event series onto one curve."""
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


def max_dd(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity))


def main() -> int:
    print(f"[v3] loading bars {SIM_START} -> {SIM_END}...")
    bars = load_bars()
    n = len(bars)
    print(f"[v3] {n:,} bars")

    if n == 0:
        print("[v3] no bars in window")
        return 1

    # Cache single-bot runs by (side, TD) so we don't repeat work.
    cache: dict[tuple[str, float], dict] = {}

    def runc(side_cfg: dict, td: float) -> dict:
        key = (side_cfg["side"], td)
        if key not in cache:
            r = run_one_bot(side_cfg, td, bars)
            cache[key] = r
            print(f"  [{side_cfg['side']} TD={td:.2f}] realized=${r['realized_usd']:+,.0f}  "
                  f"unreal=${r['unrealized_usd']:+,.0f}  trades={r['n_trades']}  "
                  f"vol=${r['volume_usd']/1e6:.1f}M")
        return cache[key]

    # Warm cache: run each unique TD once per side (9 SHORT + 9 LONG = 18 runs)
    print("\n[v3] running individual bots (18 sims)...")
    for td in TD_BOT1 + TD_BOT2 + TD_BOT3:
        runc(COMMON_SHORT, td)
    for td in TD_BOT1 + TD_BOT2 + TD_BOT3:
        runc(COMMON_LONG, td)

    # Now enumerate cascade combos (3 bots per side).
    combos = list(itertools.product(TD_BOT1, TD_BOT2, TD_BOT3))
    print(f"\n[v3] {len(combos)} cascade combos × 2 sides = {len(combos)*2} cascades")

    results = []
    for side_name, side_cfg in [("SHORT", COMMON_SHORT), ("LONG", COMMON_LONG)]:
        for td1, td2, td3 in combos:
            r1 = cache[(side_name, td1)]
            r2 = cache[(side_name, td2)]
            r3 = cache[(side_name, td3)]
            realized = r1["realized_usd"] + r2["realized_usd"] + r3["realized_usd"]
            unreal = r1["unrealized_usd"] + r2["unrealized_usd"] + r3["unrealized_usd"]
            vol = r1["volume_usd"] + r2["volume_usd"] + r3["volume_usd"]
            n_trades = r1["n_trades"] + r2["n_trades"] + r3["n_trades"]
            agg = aggregate_equity(
                [r1["equity"], r2["equity"], r3["equity"]], n,
            )
            dd = max_dd(agg)
            results.append({
                "side": side_name, "td1": td1, "td2": td2, "td3": td3,
                "realized": realized, "unrealized": unreal,
                "total_pnl": realized + unreal, "volume_usd": vol,
                "n_trades": n_trades, "max_dd": dd,
                "roi_on_dd": (realized / dd) if dd > 0 else float("inf"),
            })

    # Sort by realized PnL
    results.sort(key=lambda r: r["realized"], reverse=True)
    best = results[0]
    print(f"\n[v3] Best cascade: {best['side']} TD=({best['td1']}, {best['td2']}, {best['td3']})")
    print(f"     realized ${best['realized']:+,.0f}  unreal ${best['unrealized']:+,.0f}  "
          f"DD ${best['max_dd']:,.0f}  ROI/DD {best['roi_on_dd']:.2f}")

    # Write report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Cascade GinArea V3 — 3 настоящих бота с разными TD\n"]
    md.append(f"**Период:** {SIM_START[:10]} → {SIM_END[:10]} ({n:,} 1m bars)\n")
    md.append("**Движок:** backtest_lab.engine_v2 (полноценный GinArea-симулятор)\n")
    md.append(f"**Параметры общие:** grid_step=0.03%, order_count=800, "
              f"indicator_period=30, indicator_threshold=0.3%\n")
    md.append("**TD-каскад:**\n")
    md.append(f"- Бот-1 (быстрый): TD ∈ {TD_BOT1}\n")
    md.append(f"- Бот-2 (средний): TD ∈ {TD_BOT2}\n")
    md.append(f"- Бот-3 (редкий):  TD ∈ {TD_BOT3}\n")

    md.append("\n## Топ-15 каскадов по realized PnL\n")
    md.append("| side | TD1 | TD2 | TD3 | realized ($) | unreal ($) | total ($) | "
              "vol ($M) | trades | DD ($) | ROI/DD |\n")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results[:15]:
        md.append(f"| {r['side']} | {r['td1']} | {r['td2']} | {r['td3']} | "
                  f"{r['realized']:+,.0f} | {r['unrealized']:+,.0f} | "
                  f"{r['total_pnl']:+,.0f} | {r['volume_usd']/1e6:.1f} | "
                  f"{r['n_trades']} | {r['max_dd']:,.0f} | {r['roi_on_dd']:.2f} |\n")

    md.append("\n## Худшие 5\n")
    md.append("| side | TD1 | TD2 | TD3 | realized ($) | unreal ($) | DD ($) |\n")
    md.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for r in results[-5:]:
        md.append(f"| {r['side']} | {r['td1']} | {r['td2']} | {r['td3']} | "
                  f"{r['realized']:+,.0f} | {r['unrealized']:+,.0f} | {r['max_dd']:,.0f} |\n")

    # Per-bot standalone
    md.append("\n## Одиночные боты (для сравнения)\n")
    md.append("| side | TD | realized ($) | unreal ($) | trades | vol ($M) |\n")
    md.append("|---|---:|---:|---:|---:|---:|\n")
    for (side, td), r in sorted(cache.items()):
        md.append(f"| {side} | {td} | {r['realized_usd']:+,.0f} | "
                  f"{r['unrealized_usd']:+,.0f} | {r['n_trades']} | "
                  f"{r['volume_usd']/1e6:.1f} |\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"[v3] wrote {OUT_MD}")

    # CSV
    csv_path = ROOT / "state" / "cascade_ginarea_v3_results.csv"
    pd.DataFrame(results).to_csv(csv_path, index=False)
    print(f"[v3] wrote {csv_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
