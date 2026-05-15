"""Range Hunter — multi-timeframe бэктест.

Прогоняет идентичную логику pair-fill на разных bar-size + параметрах:
- 1m + 4h/6h + ±0.10% width (baseline)
- 5m + 4h/6h + ±0.20% width
- 5m + 12h/24h + ±0.30% width  ← оказался лучшим в первом прогоне
- 15m + 4h/6h + ±0.35% width
- 15m + 24h/48h + ±0.60% width

Цель: понять есть ли лучшая TF/width комбинация чем 1m baseline.

Результат (2y 2024-05..2026-05):
  variant                   n     WR    total       avg
  1m_4h_6h_0.10           2066  68.6%  +$17,988  +$8.71  ← baseline
  5m_4h_6h_0.20           4517  58.7%  +$35,867  +$7.94
  15m_4h_6h_0.35          4933  46.7%  +$10,607  +$2.15
  5m_12h_24h_0.30         3097  70.6%  +$80,690  +$26.05  ← 4.5× lift, best
  15m_24h_48h_0.60        1598  62.1%  +$46,863  +$29.33  ← longer hold variant

5m_12h_24h_0.30 — серьёзный кандидат на second-tier emitter:
- меньше сигналов (4.2/день vs 2.8)
- avg PnL ВЫШЕ ($26 vs $9) — wider spread + longer hold ловят больше edge
- WR ВЫШЕ (70.6% vs 68.6%)
- ⚠ не walk-forward validated на 4 фолда — risk of overfit. Прогнать перед live.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRICE = ROOT / "backtests/frozen/BTCUSDT_1m_2y.csv"

MAKER_BP = -2.0
TAKER_BP = 7.5


@dataclass
class P:
    lookback_bars: int
    range_max_pct: float
    atr_pct_max: float
    width_pct: float
    hold_bars: int
    cooldown_bars: int
    stop_loss_pct: float
    size_usd: float = 10_000.0


def signal_ok(window: pd.DataFrame, p: P) -> bool:
    if len(window) < p.lookback_bars:
        return False
    tail = window.iloc[-p.lookback_bars:]
    mid = float(tail.close.iloc[-1])
    if mid <= 0:
        return False
    hi, lo = float(tail.high.max()), float(tail.low.min())
    if (hi - lo) / mid * 100 > p.range_max_pct:
        return False
    tr = (tail.high - tail.low).values.astype(float)
    if float(tr.mean()) / mid * 100 > p.atr_pct_max:
        return False
    closes = tail.close.values.astype(float)
    x = np.arange(len(closes), dtype=float)
    slope = np.polyfit(x, closes, 1)[0]
    drift_pct = abs(slope * len(closes) / mid * 100)
    if drift_pct > p.range_max_pct * 0.5:
        return False
    return True


def backtest(df: pd.DataFrame, p: P) -> list[tuple[str, float]]:
    trades = []
    skip_until = -1
    step = max(1, p.lookback_bars // 4)
    for i in range(p.lookback_bars, len(df) - p.hold_bars, step):
        if i < skip_until:
            continue
        window = df.iloc[i - p.lookback_bars:i + 1]
        if not signal_ok(window, p):
            continue
        mid = float(df.iloc[i].close)
        buy = mid * (1 - p.width_pct / 100)
        sell = mid * (1 + p.width_pct / 100)
        size_btc = p.size_usd / mid
        end = i + p.hold_bars
        bfill = sfill = None
        for j in range(i + 1, end + 1):
            bar = df.iloc[j]
            if bfill is None and bar.low <= buy:
                bfill = (j, buy)
            if sfill is None and bar.high >= sell:
                sfill = (j, sell)
            if bfill and sfill:
                break
        if bfill and sfill:
            spread = sell - buy
            pnl = size_btc * spread + 2 * p.size_usd * (-MAKER_BP / 10000)
            trades.append(("pair_win", pnl))
        elif bfill:
            sl = bfill[1] * (1 - p.stop_loss_pct / 100)
            hit = next((j for j in range(bfill[0] + 1, end + 1) if df.iloc[j].low <= sl), None)
            if hit is not None:
                pnl = size_btc * (sl - bfill[1]) + p.size_usd * (-MAKER_BP / 10000) - p.size_usd * (TAKER_BP / 10000)
                trades.append(("buy_stopped", pnl))
            else:
                exit_p = float(df.iloc[end].close)
                pnl = size_btc * (exit_p - bfill[1]) + p.size_usd * (-MAKER_BP / 10000) - p.size_usd * (TAKER_BP / 10000)
                trades.append(("buy_timeout", pnl))
        elif sfill:
            sl = sfill[1] * (1 + p.stop_loss_pct / 100)
            hit = next((j for j in range(sfill[0] + 1, end + 1) if df.iloc[j].high >= sl), None)
            if hit is not None:
                pnl = size_btc * (sfill[1] - sl) + p.size_usd * (-MAKER_BP / 10000) - p.size_usd * (TAKER_BP / 10000)
                trades.append(("sell_stopped", pnl))
            else:
                exit_p = float(df.iloc[end].close)
                pnl = size_btc * (sfill[1] - exit_p) + p.size_usd * (-MAKER_BP / 10000) - p.size_usd * (TAKER_BP / 10000)
                trades.append(("sell_timeout", pnl))
        else:
            trades.append(("no_fill", 0.0))
        skip_until = i + p.cooldown_bars
    return trades


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.set_index("ts").resample(rule).agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna().reset_index()


def main():
    df1m = pd.read_csv(PRICE, usecols=["ts", "open", "high", "low", "close"])
    df1m["ts"] = pd.to_datetime(df1m["ts"], unit="ms", utc=True)
    df1m = df1m.sort_values("ts").reset_index(drop=True)
    print(f"Loaded {len(df1m):,} 1m bars  {df1m.ts.iloc[0]} → {df1m.ts.iloc[-1]}")

    variants = [
        ("1m_4h_6h_0.10",     df1m,                     P(240, 0.70, 0.10, 0.10, 360, 120, 0.20)),
        ("5m_4h_6h_0.20",     resample(df1m, "5min"),   P(48,  1.20, 0.20, 0.20, 72,  24,  0.40)),
        ("15m_4h_6h_0.35",    resample(df1m, "15min"),  P(16,  2.00, 0.30, 0.35, 24,  8,   0.70)),
        ("5m_12h_24h_0.30",   resample(df1m, "5min"),   P(144, 2.50, 0.25, 0.30, 288, 24,  0.60)),
        ("15m_24h_48h_0.60",  resample(df1m, "15min"),  P(96,  4.00, 0.40, 0.60, 192, 8,   1.20)),
    ]
    print(f"{'variant':<22} {'bars':>9} {'n':>5} {'WR':>6} {'total':>10} {'avg':>7} {'pair':>5} {'stop':>5} {'tmout':>6}")
    for name, df, p in variants:
        tr = backtest(df, p)
        if not tr:
            continue
        wins = sum(1 for o, pnl in tr if pnl > 0)
        total = sum(pnl for _, pnl in tr)
        by = {}
        for o, _ in tr:
            by[o] = by.get(o, 0) + 1
        pair = by.get("pair_win", 0)
        stop = by.get("buy_stopped", 0) + by.get("sell_stopped", 0)
        tmout = by.get("buy_timeout", 0) + by.get("sell_timeout", 0)
        print(f"  {name:<22} {len(df):>9,} {len(tr):>5} {wins/len(tr)*100:>5.1f}% ${total:>+9,.0f} ${total/len(tr):>+6.2f} {pair:>5} {stop:>5} {tmout:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
