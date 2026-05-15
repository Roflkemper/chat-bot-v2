"""Range Hunter — бэктест полу-ручной стратегии "сидим в ренже".

Идея:
1. Раз в час бот смотрит последние N часов: если волатильность низкая И диапазон
   узкий И тренд отсутствует → сигнал "сейчас ренж, лови".
2. Бот шлёт в TG: "RANGE LONG/SHORT BUY=X / SELL=Y / Exit by T".
3. Ты руками ставишь 2 лимитки: BUY ниже mid, SELL выше mid.
4. Ждёшь:
   - Оба исполнились в окне → закрыли позу со связкой fill'ов = ловишь спред.
   - Только один → держишь до timeout, на timeout рыночный exit (или ждёшь
     противоположный TP-уровень).
5. Если до timeout оба не пробились → отменили оба ордера, 0 fills.

Backtest симулирует это на 1m данных:
- Per-hour сигнал в часовой сетке
- Симуляция fill'ов по 1m свечам
- Учёт maker rebate / taker fee при разных exit-режимах
- Аггрегация: win rate, avg PnL/trade, daily, sharpe, max DD

Запуск:
    python scripts/range_hunter_backtest.py
    python scripts/range_hunter_backtest.py --sweep
    python scripts/range_hunter_backtest.py --days 365 --width 0.30 --hold 4
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRICE_CSV = ROOT / "backtests/frozen/BTCUSDT_1m_2y.csv"

# BitMEX Tier 1
MAKER_BP = {"linear": -2.0, "inverse": -1.0}
TAKER_BP = {"linear": 7.5, "inverse": 5.0}


@dataclass
class Params:
    # сигнал ренжа
    lookback_h: int = 4
    range_max_pct: float = 0.50      # max-min за lookback < этого %
    atr_pct_max: float = 0.10        # средний true-range 1m в % < этого
    adx_max: float = 22.0            # ADX 1h < этого (нет тренда)
    cooldown_h: int = 2              # после сигнала пауза N часов (избегаем перекрытий)
    # ордера
    width_pct: float = 0.30          # ±0.30% от mid
    hold_h: int = 4                  # окно жизни сделки
    size_usd: float = 2000.0
    # exit
    stop_loss_pct: float = 0.60      # если single-leg и mid убежал на это от entry — taker exit
    contract: str = "linear"


# ─── индикаторы ─────────────────────────────────────────────────────────────────

def true_range(high, low, close_prev):
    return max(high - low, abs(high - close_prev), abs(low - close_prev))


def compute_signal(window: pd.DataFrame, p: Params) -> bool:
    """Возвращает True если на конце window условия ренжа выполнены."""
    if len(window) < 60:
        return False
    hi = window["high"].max()
    lo = window["low"].min()
    mid = window["close"].iloc[-1]
    range_pct = (hi - lo) / mid * 100.0
    if range_pct > p.range_max_pct:
        return False
    # ATR_1m в %
    tr = (window["high"] - window["low"]).values
    atr_pct = tr.mean() / mid * 100.0
    if atr_pct > p.atr_pct_max:
        return False
    # ADX подобие на 1m → дешёвая прокси: |slope| / std
    closes = window["close"].values
    x = np.arange(len(closes))
    slope = np.polyfit(x, closes, 1)[0]
    drift_pct_per_h = abs(slope * 60) / mid * 100
    if drift_pct_per_h > 0.10:  # дрифт > 0.1%/час → намёк на тренд
        return False
    return True


# ─── симуляция одной сделки ─────────────────────────────────────────────────────

def simulate_trade(df: pd.DataFrame, start_idx: int, p: Params) -> dict | None:
    """Симулирует сетап от bar[start_idx] до start+hold_h*60 минут.

    Размещение: BUY @ mid*(1 - width), SELL @ mid*(1 + width). Maker.
    Логика fill: на каждом 1m баре смотрим low/high. Считаем что мы стояли
    на этих уровнях с момента сигнала.
    """
    if start_idx + p.hold_h * 60 >= len(df):
        return None
    mid0 = df.iloc[start_idx]["close"]
    buy = mid0 * (1 - p.width_pct / 100)
    sell = mid0 * (1 + p.width_pct / 100)
    end_idx = start_idx + p.hold_h * 60

    # Проход по барам — ищем когда сработала каждая нога
    buy_filled_at = None
    sell_filled_at = None
    buy_fill_price = None
    sell_fill_price = None

    for i in range(start_idx + 1, end_idx + 1):
        bar = df.iloc[i]
        if buy_filled_at is None and bar["low"] <= buy:
            buy_filled_at = i
            buy_fill_price = buy
        if sell_filled_at is None and bar["high"] >= sell:
            sell_filled_at = i
            sell_fill_price = sell
        if buy_filled_at and sell_filled_at:
            break

    # Развязываем сценарии
    size_btc = p.size_usd / mid0
    maker_rebate_pct = MAKER_BP[p.contract] / 10000.0  # отрицательный
    taker_fee_pct = TAKER_BP[p.contract] / 10000.0

    def calc_pair_pnl(buy_px, sell_px):
        # обе ноги maker. Spread = sell_px - buy_px
        # PnL (linear) = size_btc * (sell - buy); plus 2 maker rebates (как gain)
        pnl_spread = size_btc * (sell_px - buy_px)
        rebate = 2 * p.size_usd * (-maker_rebate_pct)  # rebate отрицательный fee → +доход
        return pnl_spread + rebate

    def calc_single_taker_exit(side_leg_filled, fill_price, exit_price):
        # одна нога maker, exit рыночный (taker)
        if side_leg_filled == "buy":
            pnl = size_btc * (exit_price - fill_price)
        else:  # sell
            pnl = size_btc * (fill_price - exit_price)
        maker = p.size_usd * (-maker_rebate_pct)
        taker = p.size_usd * taker_fee_pct
        return pnl + maker - taker

    outcome = {
        "ts_signal": df.iloc[start_idx]["ts"],
        "mid_signal": float(mid0),
        "buy_level": float(buy),
        "sell_level": float(sell),
        "buy_filled": buy_filled_at is not None,
        "sell_filled": sell_filled_at is not None,
    }

    if buy_filled_at and sell_filled_at:
        # Идеальный исход: обе ноги fill'нулись в окне
        pnl = calc_pair_pnl(buy_fill_price, sell_fill_price)
        outcome.update({"outcome": "pair_win", "pnl_usd": pnl, "exit_idx": max(buy_filled_at, sell_filled_at)})
    elif buy_filled_at and not sell_filled_at:
        # Filled только BUY → стоп-лосс или timeout
        # Проверим достигли ли стопа в окне
        sl_price = buy_fill_price * (1 - p.stop_loss_pct / 100)
        sl_hit_idx = None
        for j in range(buy_filled_at + 1, end_idx + 1):
            if df.iloc[j]["low"] <= sl_price:
                sl_hit_idx = j
                break
        if sl_hit_idx:
            pnl = calc_single_taker_exit("buy", buy_fill_price, sl_price)
            outcome.update({"outcome": "buy_stopped", "pnl_usd": pnl, "exit_idx": sl_hit_idx})
        else:
            exit_price = df.iloc[end_idx]["close"]
            pnl = calc_single_taker_exit("buy", buy_fill_price, exit_price)
            outcome.update({"outcome": "buy_timeout", "pnl_usd": pnl, "exit_idx": end_idx})
    elif sell_filled_at and not buy_filled_at:
        sl_price = sell_fill_price * (1 + p.stop_loss_pct / 100)
        sl_hit_idx = None
        for j in range(sell_filled_at + 1, end_idx + 1):
            if df.iloc[j]["high"] >= sl_price:
                sl_hit_idx = j
                break
        if sl_hit_idx:
            pnl = calc_single_taker_exit("sell", sell_fill_price, sl_price)
            outcome.update({"outcome": "sell_stopped", "pnl_usd": pnl, "exit_idx": sl_hit_idx})
        else:
            exit_price = df.iloc[end_idx]["close"]
            pnl = calc_single_taker_exit("sell", sell_fill_price, exit_price)
            outcome.update({"outcome": "sell_timeout", "pnl_usd": pnl, "exit_idx": end_idx})
    else:
        # Никто не fill'нулся — оба ордера отменены, профит = 0
        outcome.update({"outcome": "no_fills", "pnl_usd": 0.0, "exit_idx": end_idx})

    return outcome


# ─── main loop ──────────────────────────────────────────────────────────────────

def backtest(df: pd.DataFrame, p: Params) -> dict:
    """Проход по часам, генерируем сигналы, симулируем сделки, агрегируем."""
    trades = []
    skip_until_idx = -1
    # iterate every 60 min (hourly check)
    for hour_start in range(p.lookback_h * 60, len(df) - p.hold_h * 60, 60):
        if hour_start < skip_until_idx:
            continue
        window = df.iloc[hour_start - p.lookback_h * 60 : hour_start + 1]
        if not compute_signal(window, p):
            continue
        trade = simulate_trade(df, hour_start, p)
        if trade is None:
            continue
        trades.append(trade)
        skip_until_idx = hour_start + p.cooldown_h * 60

    if not trades:
        return {"n_trades": 0, "params": vars(p)}

    tdf = pd.DataFrame(trades)
    tdf["ts_signal"] = pd.to_datetime(tdf["ts_signal"])
    tdf["date"] = tdf["ts_signal"].dt.date
    by_outcome = tdf.groupby("outcome").agg(n=("pnl_usd", "size"), pnl_sum=("pnl_usd", "sum"), pnl_avg=("pnl_usd", "mean")).round(2)
    daily = tdf.groupby("date")["pnl_usd"].agg(["sum", "size"]).reset_index()
    daily.columns = ["date", "pnl", "n"]

    total = float(tdf.pnl_usd.sum())
    n = len(tdf)
    wins = int((tdf.pnl_usd > 0).sum())
    losses = int((tdf.pnl_usd < 0).sum())
    zeros = int((tdf.pnl_usd == 0).sum())

    days_total = (tdf.ts_signal.max() - tdf.ts_signal.min()).total_seconds() / 86400
    cum = tdf.pnl_usd.cumsum()
    drawdown = float((cum - cum.cummax()).min())
    sharpe = (tdf.pnl_usd.mean() / tdf.pnl_usd.std() * np.sqrt(252 * n / max(days_total, 1))) if tdf.pnl_usd.std() > 0 else 0.0

    return {
        "params": vars(p),
        "n_trades": n,
        "avg_signals_per_day": n / max(days_total, 1),
        "wins": wins, "losses": losses, "zeros": zeros,
        "win_rate_pct": wins / n * 100,
        "total_pnl_usd": total,
        "avg_pnl_per_trade_usd": float(tdf.pnl_usd.mean()),
        "median_pnl_per_trade_usd": float(tdf.pnl_usd.median()),
        "best_trade": float(tdf.pnl_usd.max()),
        "worst_trade": float(tdf.pnl_usd.min()),
        "max_drawdown_usd": drawdown,
        "sharpe_approx": float(sharpe),
        "by_outcome": by_outcome.to_dict("index"),
        "trades_df": tdf,
        "daily_df": daily,
    }


def print_report(r: dict, label: str = "") -> None:
    if r["n_trades"] == 0:
        print(f"[{label}] no signals")
        return
    p = r["params"]
    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"  range≤{p['range_max_pct']}% / atr≤{p['atr_pct_max']}% / lookback={p['lookback_h']}h / cooldown={p['cooldown_h']}h")
    print(f"  width=±{p['width_pct']}% / hold={p['hold_h']}h / size=${p['size_usd']} / SL={p['stop_loss_pct']}% / {p['contract']}")
    print(f"{'─' * 70}")
    print(f"  Trades:         {r['n_trades']:>8}    Signals/день: {r['avg_signals_per_day']:.2f}")
    print(f"  Win/Loss/Zero:  {r['wins']:>4}/{r['losses']:>4}/{r['zeros']:>4}    Winrate: {r['win_rate_pct']:.1f}%")
    print(f"  Total PnL:      ${r['total_pnl_usd']:>+10,.2f}    Avg/trade: ${r['avg_pnl_per_trade_usd']:>+7.2f}    Median: ${r['median_pnl_per_trade_usd']:>+7.2f}")
    print(f"  Best / Worst:   ${r['best_trade']:>+8.2f} / ${r['worst_trade']:>+7.2f}    Max DD: ${r['max_drawdown_usd']:>+9.2f}")
    print(f"  Sharpe (approx):  {r['sharpe_approx']:>5.2f}")
    print(f"  По исходам:")
    for outcome, data in r["by_outcome"].items():
        print(f"    {outcome:<15} n={int(data['n']):>4}  total=${data['pnl_sum']:>+9.2f}  avg=${data['pnl_avg']:>+7.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--contract", default="linear", choices=["linear", "inverse"])
    ap.add_argument("--width", type=float, default=0.30)
    ap.add_argument("--hold", type=int, default=4)
    ap.add_argument("--range-max", type=float, default=0.50)
    ap.add_argument("--atr-max", type=float, default=0.10)
    ap.add_argument("--lookback", type=int, default=4)
    ap.add_argument("--cooldown", type=int, default=2)
    ap.add_argument("--size", type=float, default=2000.0)
    ap.add_argument("--sl", type=float, default=0.60)
    ap.add_argument("--sweep", action="store_true", help="parameter sweep")
    args = ap.parse_args()

    print(f"Loading {PRICE_CSV.name}...")
    df = pd.read_csv(PRICE_CSV, usecols=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    if args.days:
        cutoff = df.ts.iloc[-1] - pd.Timedelta(days=args.days)
        df = df[df.ts >= cutoff].reset_index(drop=True)
    print(f"  bars: {len(df):,}  range: {df.ts.iloc[0]} → {df.ts.iloc[-1]}")

    if args.sweep:
        results = []
        # sweep grid: width × hold × atr_max × range_max
        widths = [0.15, 0.20, 0.30, 0.40, 0.50]
        holds = [2, 3, 4, 6]
        atrs = [0.06, 0.08, 0.10, 0.13]
        ranges = [0.30, 0.40, 0.50, 0.70]
        print(f"\nSweeping {len(widths)}×{len(holds)}×{len(atrs)}×{len(ranges)} = {len(widths)*len(holds)*len(atrs)*len(ranges)} configs...")
        for w, h, a, rg in product(widths, holds, atrs, ranges):
            p = Params(
                lookback_h=args.lookback, range_max_pct=rg, atr_pct_max=a,
                cooldown_h=args.cooldown, width_pct=w, hold_h=h,
                size_usd=args.size, stop_loss_pct=args.sl, contract=args.contract,
            )
            r = backtest(df, p)
            if r["n_trades"] < 20:
                continue
            results.append({
                "width": w, "hold": h, "atr_max": a, "range_max": rg,
                "n": r["n_trades"], "winrate": round(r["win_rate_pct"], 1),
                "total_pnl": round(r["total_pnl_usd"], 0),
                "avg_pnl": round(r["avg_pnl_per_trade_usd"], 2),
                "dd": round(r["max_drawdown_usd"], 0),
                "sharpe": round(r["sharpe_approx"], 2),
                "n_per_day": round(r["avg_signals_per_day"], 2),
            })
        sdf = pd.DataFrame(results).sort_values("total_pnl", ascending=False).head(20)
        print(f"\n=== TOP 20 по total_pnl (n>=20 trades) ===")
        print(sdf.to_string(index=False))
        print(f"\n=== TOP 10 по sharpe (n>=50 trades) ===")
        print(sdf[sdf.n >= 50].sort_values("sharpe", ascending=False).head(10).to_string(index=False))
    else:
        p = Params(
            lookback_h=args.lookback, range_max_pct=args.range_max, atr_pct_max=args.atr_max,
            cooldown_h=args.cooldown, width_pct=args.width, hold_h=args.hold,
            size_usd=args.size, stop_loss_pct=args.sl, contract=args.contract,
        )
        r = backtest(df, p)
        print_report(r, label="RANGE HUNTER")

    return 0


if __name__ == "__main__":
    sys.exit(main())
