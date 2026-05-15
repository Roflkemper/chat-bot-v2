"""Range Hunter walk-forward + fill-rate sensitivity.

Walk-forward:
  4 хронологических fold'a на 2y данных. Каждый fold = одна полугодовая
  тренировочная "наблюдательная" зона + следующее полугодие тест. Мы не
  фитим параметры — просто прогоняем фиксированный лучший конфиг на каждом
  отрезке и смотрим стабильность.

Fill-rate sensitivity:
  Симулирует maker fill probability p в [0.5..1.0]. Каждая нога: с
  вероятностью p — fill (как в идеальном бэктесте), иначе — не fill
  (даже если low <= level). Распределение исходов сдвигается:
    - pair_win: p²
    - single-leg → stop/timeout: 2p(1-p)
    - no_fill: (1-p)²
  Запускаем реальную симуляцию (не аналитическую) — так точнее.

Usage:
    python scripts/range_hunter_walkforward.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import range_hunter_backtest as rh

ROOT = Path(__file__).resolve().parents[1]
PRICE_CSV = ROOT / "backtests/frozen/BTCUSDT_1m_2y.csv"

# Лучший конфиг из свипа
BEST = dict(
    lookback_h=4, range_max_pct=0.70, atr_pct_max=0.10, cooldown_h=2,
    width_pct=0.10, hold_h=6, size_usd=10000.0, stop_loss_pct=0.20, contract="linear",
)


def load_price() -> pd.DataFrame:
    df = pd.read_csv(PRICE_CSV, usecols=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def fold_slice(df: pd.DataFrame, fold_idx: int, n_folds: int) -> pd.DataFrame:
    """Возвращает chronological slice [fold_idx/n_folds .. (fold_idx+1)/n_folds]."""
    n = len(df)
    a = n * fold_idx // n_folds
    b = n * (fold_idx + 1) // n_folds
    return df.iloc[a:b].reset_index(drop=True)


def run_with_fill_rate(df: pd.DataFrame, p: rh.Params, fill_prob: float = 1.0, seed: int = 42) -> dict:
    """Wrapped: повторяет логику simulate_trade, но с маркером 'orders missed' по fill_prob.

    Per signal: каждая нога независимо с вероятностью fill_prob СМОГЛА быть в стакане
    у фронта очереди. Если повезло — fill случается по правилу low/high; нет — leg
    считается не fill'нутой даже если bar её задел.
    """
    rng = random.Random(seed)
    trades = []
    skip_until_idx = -1

    for hour_start in range(p.lookback_h * 60, len(df) - p.hold_h * 60, 60):
        if hour_start < skip_until_idx:
            continue
        window = df.iloc[hour_start - p.lookback_h * 60: hour_start + 1]
        if not rh.compute_signal(window, p):
            continue
        # Маркеры удачи fill'а для каждой ноги
        buy_can_fill = rng.random() < fill_prob
        sell_can_fill = rng.random() < fill_prob

        # Перерисовываем simulate_trade с учётом этих маркеров
        mid0 = df.iloc[hour_start]["close"]
        buy = mid0 * (1 - p.width_pct / 100)
        sell = mid0 * (1 + p.width_pct / 100)
        end_idx = hour_start + p.hold_h * 60

        buy_filled_at = sell_filled_at = None
        buy_fill_price = sell_fill_price = None
        for i in range(hour_start + 1, end_idx + 1):
            bar = df.iloc[i]
            if buy_can_fill and buy_filled_at is None and bar["low"] <= buy:
                buy_filled_at, buy_fill_price = i, buy
            if sell_can_fill and sell_filled_at is None and bar["high"] >= sell:
                sell_filled_at, sell_fill_price = i, sell
            if buy_filled_at and sell_filled_at:
                break

        size_btc = p.size_usd / mid0
        maker_pct = rh.MAKER_BP[p.contract] / 10000.0
        taker_pct = rh.TAKER_BP[p.contract] / 10000.0

        def pair_pnl(b, s):
            return size_btc * (s - b) + 2 * p.size_usd * (-maker_pct)

        def single_taker(side, fp, ep):
            base = size_btc * ((ep - fp) if side == "buy" else (fp - ep))
            return base + p.size_usd * (-maker_pct) - p.size_usd * taker_pct

        out = {"ts_signal": df.iloc[hour_start]["ts"]}
        if buy_filled_at and sell_filled_at:
            out.update(outcome="pair_win", pnl_usd=pair_pnl(buy_fill_price, sell_fill_price))
        elif buy_filled_at:
            sl_price = buy_fill_price * (1 - p.stop_loss_pct / 100)
            hit = None
            for j in range(buy_filled_at + 1, end_idx + 1):
                if df.iloc[j]["low"] <= sl_price:
                    hit = j; break
            if hit:
                out.update(outcome="buy_stopped", pnl_usd=single_taker("buy", buy_fill_price, sl_price))
            else:
                out.update(outcome="buy_timeout", pnl_usd=single_taker("buy", buy_fill_price, df.iloc[end_idx]["close"]))
        elif sell_filled_at:
            sl_price = sell_fill_price * (1 + p.stop_loss_pct / 100)
            hit = None
            for j in range(sell_filled_at + 1, end_idx + 1):
                if df.iloc[j]["high"] >= sl_price:
                    hit = j; break
            if hit:
                out.update(outcome="sell_stopped", pnl_usd=single_taker("sell", sell_fill_price, sl_price))
            else:
                out.update(outcome="sell_timeout", pnl_usd=single_taker("sell", sell_fill_price, df.iloc[end_idx]["close"]))
        else:
            out.update(outcome="no_fills", pnl_usd=0.0)
        trades.append(out)
        skip_until_idx = hour_start + p.cooldown_h * 60

    tdf = pd.DataFrame(trades)
    if len(tdf) == 0:
        return {"n": 0}
    return {
        "n": len(tdf),
        "wr": float((tdf.pnl_usd > 0).mean() * 100),
        "total": float(tdf.pnl_usd.sum()),
        "avg": float(tdf.pnl_usd.mean()),
        "best": float(tdf.pnl_usd.max()),
        "worst": float(tdf.pnl_usd.min()),
        "dd": float((tdf.pnl_usd.cumsum() - tdf.pnl_usd.cumsum().cummax()).min()),
        "outcomes": tdf.outcome.value_counts().to_dict(),
    }


def main():
    df = load_price()
    print(f"Loaded {len(df):,} bars  {df.ts.iloc[0]} → {df.ts.iloc[-1]}")
    p = rh.Params(**BEST)

    # ─── 1. Walk-forward 4 folds ─────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  WALK-FORWARD (4 chronological folds, no parameter refitting)")
    print("=" * 80)
    print(f"  fixed config: width=±{p.width_pct}%  hold={p.hold_h}h  range≤{p.range_max_pct}%  SL={p.stop_loss_pct}%  size=${p.size_usd}")
    print(f"  {'fold':<8} {'window':<35} {'n':>5} {'WR':>6} {'PnL':>10} {'avg':>7} {'DD':>9}")
    fold_results = []
    for k in range(4):
        sub = fold_slice(df, k, 4)
        label = f"{sub.ts.iloc[0].strftime('%Y-%m-%d')} → {sub.ts.iloc[-1].strftime('%Y-%m-%d')}"
        r = rh.backtest(sub, p)
        if r["n_trades"] == 0:
            print(f"  fold_{k+1:<3} {label:<35}  (no signals)")
            continue
        fold_results.append(r)
        print(f"  fold_{k+1:<3} {label:<35} {r['n_trades']:>5} {r['win_rate_pct']:>5.1f}% ${r['total_pnl_usd']:>+9.0f} ${r['avg_pnl_per_trade_usd']:>+6.2f} ${r['max_drawdown_usd']:>+8.0f}")
    # consistency
    if fold_results:
        wrs = [r["win_rate_pct"] for r in fold_results]
        pnls = [r["total_pnl_usd"] for r in fold_results]
        print(f"\n  WR диапазон по фолдам: {min(wrs):.1f}%–{max(wrs):.1f}%  std={np.std(wrs):.2f}")
        print(f"  PnL диапазон по фолдам: ${min(pnls):+,.0f}..${max(pnls):+,.0f}  все положительные: {all(x > 0 for x in pnls)}")

    # ─── 2. Fill-rate sensitivity ────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  FILL-RATE SENSITIVITY (per leg)")
    print("=" * 80)
    print("  Каждая нога fill'ится с вероятностью p (random seed=42); если не повезло — leg не исполняется")
    print(f"  {'p':>5} {'n':>5} {'WR':>7} {'total':>10} {'avg':>7} {'dd':>8} | {'pair_win':>9} {'stop':>6} {'timeout':>8} {'no_fill':>8}")
    for p_fill in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]:
        r = run_with_fill_rate(df, p, fill_prob=p_fill, seed=42)
        if r["n"] == 0:
            continue
        oc = r["outcomes"]
        pair = oc.get("pair_win", 0)
        stop = oc.get("buy_stopped", 0) + oc.get("sell_stopped", 0)
        timeout = oc.get("buy_timeout", 0) + oc.get("sell_timeout", 0)
        nf = oc.get("no_fills", 0)
        print(f"  {p_fill:>5.2f} {r['n']:>5} {r['wr']:>6.1f}% ${r['total']:>+9.0f} ${r['avg']:>+6.2f} ${r['dd']:>+7.0f} | {pair:>9} {stop:>6} {timeout:>8} {nf:>8}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
