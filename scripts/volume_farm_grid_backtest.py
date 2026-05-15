"""Volume-farm grid backtest для BitMEX (XBTUSD inverse / XBTUSDT linear).

Симулирует post-only grid market-making бота на 2y BTC 1m данных:
- центрируется по mid; ре-anchor при drift>X% или каждые N мин
- симметричные buy-ниже/sell-выше уровни (step = range/levels)
- fill происходит если 1m свеча задела уровень
- inventory cap → перестаёт котировать в сторону при превышении
- ведёт inventory PnL (mark-to-market) + maker rebates

Считает обе модели:
  LINEAR  (XBTUSDT): PnL_USD = qty_btc * (exit - entry); fees в USDT
  INVERSE (XBTUSD):  PnL_BTC = qty_usd * (1/entry - 1/exit); fees в BTC

BitMEX базовые fee (Tier 1):
  XBTUSD  inverse:  maker -0.010%, taker +0.050%
  XBTUSDT linear:   maker -0.020%, taker +0.075%
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRICE_CSV = ROOT / "backtests/frozen/BTCUSDT_1m_2y.csv"

# BitMEX базовые рейты Tier 1 (отрицательный maker = ребейт)
FEES = {
    "linear": {"maker_bp": -2.0, "taker_bp": 7.5, "label": "XBTUSDT (USDT-margined linear)"},
    "inverse": {"maker_bp": -1.0, "taker_bp": 5.0, "label": "XBTUSD (BTC-margined inverse)"},
}


@dataclass
class Params:
    contract: str = "inverse"            # 'inverse' | 'linear'
    capital_usd: float = 15_000.0
    leverage: float = 3.0
    grid_range_pct: float = 0.6          # ±0.6% от anchor
    grid_levels: int = 60                # всего уровней (30 BUY + 30 SELL)
    order_size_usd: float = 400.0        # размер каждого ордера
    reanchor_drift_pct: float = 0.3      # mid отъехал от anchor больше чем на N% от range → ре-anchor
    reanchor_interval_min: int = 30
    inventory_cap_btc: float = 0.15      # |position| > cap → стоп котировать в эту сторону
    # маркер для рисковых событий
    hard_stop_unrealized_usd: float = -2_000.0  # mark-to-market < этого → полный exit


@dataclass
class State:
    anchor: float = 0.0
    last_reanchor_min: int = 0
    pos_btc: float = 0.0                  # long > 0, short < 0
    avg_entry: float = 0.0
    cash_usd: float = 0.0                 # реализованная часть (без учёта inventory)
    rebates_usd: float = 0.0
    fills: int = 0
    volume_usd: float = 0.0
    daily: list = field(default_factory=list)
    halted: bool = False


def fee_usd(notional_usd: float, contract: str) -> float:
    """Maker rebate (negative = доход)."""
    return notional_usd * FEES[contract]["maker_bp"] / 10000.0


def step_fill(state: State, p: Params, side: str, level: float, mark: float) -> None:
    """Один fill: side='buy'|'sell', level — цена fill."""
    qty_btc = p.order_size_usd / level
    # apply inventory cap pre-fill
    if side == "buy" and state.pos_btc >= p.inventory_cap_btc:
        return
    if side == "sell" and state.pos_btc <= -p.inventory_cap_btc:
        return

    signed_qty = qty_btc if side == "buy" else -qty_btc
    new_pos = state.pos_btc + signed_qty

    # Среднее по позиции (классическое VWAP)
    if state.pos_btc == 0 or (state.pos_btc > 0 and signed_qty > 0) or (state.pos_btc < 0 and signed_qty < 0):
        # увеличение или открытие
        notional_old = state.avg_entry * abs(state.pos_btc)
        notional_new = level * abs(signed_qty)
        if abs(new_pos) > 0:
            state.avg_entry = (notional_old + notional_new) / abs(new_pos)
    else:
        # уменьшение / переворот → реализуем часть
        closed_qty = min(abs(state.pos_btc), abs(signed_qty))
        if p.contract == "linear":
            # PnL_USD = closed_qty * (exit - entry) * sign_old_pos
            sign_old = 1 if state.pos_btc > 0 else -1
            realized = closed_qty * (level - state.avg_entry) * sign_old
        else:
            # inverse: PnL_BTC = qty_usd * (1/entry - 1/exit), затем переводим в USD по level
            qty_usd = closed_qty * state.avg_entry
            sign_old = 1 if state.pos_btc > 0 else -1
            pnl_btc = qty_usd * (1.0 / state.avg_entry - 1.0 / level) * sign_old
            realized = pnl_btc * level
        state.cash_usd += realized
        if abs(signed_qty) > abs(state.pos_btc):
            # перевернулись — оставшийся объём становится новым средним
            state.avg_entry = level

    state.pos_btc = new_pos
    if abs(state.pos_btc) < 1e-9:
        state.pos_btc = 0.0
        state.avg_entry = 0.0
    state.fills += 1
    state.volume_usd += p.order_size_usd
    state.rebates_usd -= fee_usd(p.order_size_usd, p.contract)  # rebate отрицательный fee → доход


def unrealized_usd(state: State, mark: float, contract: str) -> float:
    if state.pos_btc == 0:
        return 0.0
    if contract == "linear":
        return state.pos_btc * (mark - state.avg_entry)
    else:
        qty_usd = abs(state.pos_btc) * state.avg_entry
        sign = 1 if state.pos_btc > 0 else -1
        pnl_btc = qty_usd * (1.0 / state.avg_entry - 1.0 / mark) * sign
        return pnl_btc * mark


def close_all(state: State, p: Params, mark: float) -> None:
    """Принудительное закрытие как taker."""
    if state.pos_btc == 0:
        return
    notional = abs(state.pos_btc) * mark
    if p.contract == "linear":
        sign_old = 1 if state.pos_btc > 0 else -1
        realized = abs(state.pos_btc) * (mark - state.avg_entry) * sign_old
    else:
        qty_usd = abs(state.pos_btc) * state.avg_entry
        sign_old = 1 if state.pos_btc > 0 else -1
        pnl_btc = qty_usd * (1.0 / state.avg_entry - 1.0 / mark) * sign_old
        realized = pnl_btc * mark
    taker_fee = notional * FEES[p.contract]["taker_bp"] / 10000.0
    state.cash_usd += realized - taker_fee
    state.pos_btc = 0.0
    state.avg_entry = 0.0


def run(df: pd.DataFrame, p: Params) -> dict:
    s = State()
    s.anchor = float(df.iloc[0]["close"])
    s.last_reanchor_min = 0

    half = p.grid_levels // 2
    step_pct = p.grid_range_pct / half  # в процентах
    last_day = None
    day_start_cash = 0.0
    day_start_vol = 0.0
    day_start_rebates = 0.0
    day_start_fills = 0

    for i, row in enumerate(df.itertuples(index=False)):
        ts, o, h, l, c = row.ts, row.open, row.high, row.low, row.close
        mid = c

        # суточная разметка
        day = ts.date()
        if last_day is None:
            last_day = day
            day_start_cash = s.cash_usd
            day_start_vol = s.volume_usd
            day_start_rebates = s.rebates_usd
            day_start_fills = s.fills
        if day != last_day:
            unr = unrealized_usd(s, mid, p.contract)
            s.daily.append({
                "date": last_day,
                "volume_usd": s.volume_usd - day_start_vol,
                "rebates_usd": s.rebates_usd - day_start_rebates,
                "realized_usd": s.cash_usd - day_start_cash,
                "fills": s.fills - day_start_fills,
                "pos_btc_eod": s.pos_btc,
                "unrealized_usd_eod": unr,
            })
            last_day = day
            day_start_cash = s.cash_usd
            day_start_vol = s.volume_usd
            day_start_rebates = s.rebates_usd
            day_start_fills = s.fills

        # hard stop по unrealized
        unr_now = unrealized_usd(s, mid, p.contract)
        if not s.halted and unr_now < p.hard_stop_unrealized_usd:
            close_all(s, p, mid)
            s.halted = True
            continue
        if s.halted:
            # после стопа возобновим через 60 мин
            if (i - s.last_reanchor_min) > 60:
                s.halted = False
                s.anchor = mid
                s.last_reanchor_min = i
            else:
                continue

        # ре-anchor
        drift = abs(mid - s.anchor) / s.anchor * 100  # %
        if drift > p.reanchor_drift_pct or (i - s.last_reanchor_min) >= p.reanchor_interval_min:
            s.anchor = mid
            s.last_reanchor_min = i

        # активные уровни на этом баре
        # BUY уровни: anchor*(1 - k*step_pct/100) для k=1..half
        # SELL уровни: anchor*(1 + k*step_pct/100) для k=1..half
        # fill: low <= buy_level и sell_level <= high
        for k in range(1, half + 1):
            buy = s.anchor * (1 - k * step_pct / 100.0)
            if l <= buy <= s.anchor:
                step_fill(s, p, "buy", buy, mid)
            sell = s.anchor * (1 + k * step_pct / 100.0)
            if s.anchor <= sell <= h:
                step_fill(s, p, "sell", sell, mid)

    # финальный день
    last_row = df.iloc[-1]
    final_mid = float(last_row["close"])
    unr_final = unrealized_usd(s, final_mid, p.contract)
    s.daily.append({
        "date": last_day,
        "volume_usd": s.volume_usd - day_start_vol,
        "rebates_usd": s.rebates_usd - day_start_rebates,
        "realized_usd": s.cash_usd - day_start_cash,
        "fills": s.fills - day_start_fills,
        "pos_btc_eod": s.pos_btc,
        "unrealized_usd_eod": unr_final,
    })

    days = pd.DataFrame(s.daily)
    days["net_usd"] = days["rebates_usd"] + days["realized_usd"] + days["unrealized_usd_eod"].diff().fillna(days["unrealized_usd_eod"])
    return {
        "params": vars(p),
        "fee_struct": FEES[p.contract],
        "total_days": len(days),
        "total_volume_usd": float(days.volume_usd.sum()),
        "total_rebates_usd": float(days.rebates_usd.sum()),
        "total_realized_usd": float(days.realized_usd.sum()),
        "total_unrealized_eod_usd": float(unr_final),
        "total_net_usd": float(days.rebates_usd.sum() + days.realized_usd.sum() + unr_final),
        "avg_daily_volume_usd": float(days.volume_usd.mean()),
        "median_daily_volume_usd": float(days.volume_usd.median()),
        "days_hit_1m_volume": int((days.volume_usd >= 1_000_000).sum()),
        "days_hit_500k_volume": int((days.volume_usd >= 500_000).sum()),
        "avg_daily_net_usd": float(days.net_usd.mean()),
        "median_daily_net_usd": float(days.net_usd.median()),
        "best_day_net": float(days.net_usd.max()),
        "worst_day_net": float(days.net_usd.min()),
        "days_neg_net": int((days.net_usd < 0).sum()),
        "days_pos_net": int((days.net_usd > 0).sum()),
        "max_drawdown_in_run_usd": float((days.net_usd.cumsum() - days.net_usd.cumsum().cummax()).min()),
        "days_df": days,
    }


def print_report(r: dict, label: str) -> None:
    p = r["params"]
    f = r["fee_struct"]
    print(f"\n{'=' * 70}")
    print(f"  {label}  ({f['label']})")
    print(f"  maker rebate: {f['maker_bp']:+.3f}bp   taker fee: {f['taker_bp']:+.3f}bp")
    print(f"  capital ${p['capital_usd']:,}  lev {p['leverage']}×  range ±{p['grid_range_pct']}%  levels {p['grid_levels']}  size ${p['order_size_usd']}")
    print(f"  inventory cap ±{p['inventory_cap_btc']} BTC  hard-stop ${p['hard_stop_unrealized_usd']}")
    print(f"{'=' * 70}")
    print(f"  Дней:                       {r['total_days']:,}")
    print(f"  Средний дневной volume:     ${r['avg_daily_volume_usd']:>14,.0f}")
    print(f"  Медиана дневного volume:    ${r['median_daily_volume_usd']:>14,.0f}")
    print(f"  Дней с volume >= $1M:       {r['days_hit_1m_volume']:>14,} ({r['days_hit_1m_volume']/r['total_days']*100:.0f}%)")
    print(f"  Дней с volume >= $500K:     {r['days_hit_500k_volume']:>14,} ({r['days_hit_500k_volume']/r['total_days']*100:.0f}%)")
    print(f"  TOTAL volume за период:     ${r['total_volume_usd']:>14,.0f}")
    print(f"  TOTAL rebates:              ${r['total_rebates_usd']:>+14,.0f}")
    print(f"  TOTAL realized:             ${r['total_realized_usd']:>+14,.0f}")
    print(f"  Final unrealized:           ${r['total_unrealized_eod_usd']:>+14,.0f}")
    print(f"  TOTAL NET:                  ${r['total_net_usd']:>+14,.0f}")
    print(f"  Среднее за день NET:        ${r['avg_daily_net_usd']:>+14,.2f}")
    print(f"  Медиана за день NET:        ${r['median_daily_net_usd']:>+14,.2f}")
    print(f"  Best/Worst день NET:        ${r['best_day_net']:>+14,.0f}  /  ${r['worst_day_net']:>+14,.0f}")
    print(f"  Дней + / -:                 {r['days_pos_net']:>6} / {r['days_neg_net']:>6}")
    print(f"  Max drawdown (cum NET):     ${r['max_drawdown_in_run_usd']:>+14,.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", default="both", choices=["linear", "inverse", "both"])
    ap.add_argument("--range-pct", type=float, default=0.6)
    ap.add_argument("--levels", type=int, default=60)
    ap.add_argument("--order-size", type=float, default=400.0)
    ap.add_argument("--inv-cap", type=float, default=0.15)
    ap.add_argument("--reanchor-min", type=int, default=30)
    ap.add_argument("--reanchor-drift", type=float, default=0.3)
    ap.add_argument("--capital", type=float, default=15_000.0)
    ap.add_argument("--leverage", type=float, default=3.0)
    ap.add_argument("--days", type=int, default=None, help="tail N days only (для быстрого прогона)")
    args = ap.parse_args()

    print(f"Loading {PRICE_CSV.name}...")
    df = pd.read_csv(PRICE_CSV, usecols=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    if args.days:
        cutoff = df.ts.iloc[-1] - pd.Timedelta(days=args.days)
        df = df[df.ts >= cutoff].reset_index(drop=True)
    print(f"  bars: {len(df):,}  range: {df.ts.iloc[0]} → {df.ts.iloc[-1]}")

    contracts = ["linear", "inverse"] if args.contract == "both" else [args.contract]
    results = {}
    for c in contracts:
        p = Params(
            contract=c,
            capital_usd=args.capital,
            leverage=args.leverage,
            grid_range_pct=args.range_pct,
            grid_levels=args.levels,
            order_size_usd=args.order_size,
            inventory_cap_btc=args.inv_cap,
            reanchor_interval_min=args.reanchor_min,
            reanchor_drift_pct=args.reanchor_drift,
        )
        print(f"\nRunning {c}...")
        r = run(df, p)
        results[c] = r
        print_report(r, f"BACKTEST [{c.upper()}]")

    # Сравнение
    if len(contracts) == 2:
        print("\n" + "=" * 70)
        print("  СРАВНЕНИЕ LINEAR vs INVERSE")
        print("=" * 70)
        print(f"  {'метрика':<28} {'linear':>15} {'inverse':>15}")
        keys = [
            ("avg_daily_volume_usd", "Avg daily volume"),
            ("median_daily_volume_usd", "Median daily volume"),
            ("days_hit_1m_volume", "Days hit $1M vol"),
            ("total_rebates_usd", "Total rebates"),
            ("total_realized_usd", "Total realized PnL"),
            ("total_net_usd", "Total NET"),
            ("avg_daily_net_usd", "Avg daily NET"),
            ("worst_day_net", "Worst day"),
            ("max_drawdown_in_run_usd", "Max drawdown"),
        ]
        for k, label in keys:
            l_val = results["linear"][k]
            i_val = results["inverse"][k]
            fmt = lambda x: f"{x:>+15,.2f}" if isinstance(x, float) else f"{x:>15,}"
            print(f"  {label:<28} {fmt(l_val)} {fmt(i_val)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
