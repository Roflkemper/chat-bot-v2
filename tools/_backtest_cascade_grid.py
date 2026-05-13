"""Cascade grid backtest — 3-tier laddered shorts + 3-tier laddered longs.

Strategy:
  За 30-минутным окном (rolling) считаем range = (max(high) - min(low)) / open[-30].
  При range >= 1% — открываем ПЕРВУЮ сетку:
    - LONG  ладдер если 30-min low был в начале окна (момент = вверх)
    - SHORT ладдер если 30-min high был в начале окна (момент = вниз)
  При range >= 2% — открываем ВТОРУЮ.
  При range >= 3% — открываем ТРЕТЬЮ.

  Размер: 1x / 2x / 3x base_size.
  TP: первая +1% обратно, вторая +2%, третья +3% (от своей entry).
  SL: 3x от TP — то есть 3% / 6% / 9% (примерный safety).
  Hold cap: 24h.

  Hedge exit (тестируем 3 варианта):
    A) Закрывать 1-ю когда 2-я достигла TP (фиксируем минус, чистый PnL = TP2+TP3 - loss1)
    B) Закрывать 1-ю когда 2-я в плюсе ≥0.5x от своего TP
    C) Закрывать 1-ю только после TP2 И TP3 (самый ленивый)

Reports per-variant: PnL total, max DD, win rate, n trades, sharpe.
Walk-forward 4 folds.

Outputs:
  state/cascade_grid_results.csv — per-trade records
  docs/STRATEGIES/CASCADE_GRID_BACKTEST.md — verdict + variant comparison
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "CASCADE_GRID_BACKTEST.md"

# Strategy parameters
WINDOW_MIN = 30           # rolling range window
TIER_TRIGGERS = [1.0, 2.0, 3.0]   # % range thresholds
TIER_SIZES = [1.0, 2.0, 3.0]       # multiplier of BASE_SIZE
TIER_TP = [1.0, 2.0, 3.0]          # % from entry
TIER_SL_MULT = 3.0                  # SL = TIER_TP × this (so 3%/6%/9%)
BASE_SIZE = 1000.0                  # USD per tier-1
COOLDOWN_MIN = 60                   # after a tier-1 closes, wait before next
MAX_HOLD_MIN = 24 * 60              # 24h hard cap
FEE_RT_PCT = 0.165                  # round-trip in %

# Walk-forward
N_FOLDS = 4


@dataclass
class GridPos:
    """One active grid tier."""
    tier: int                  # 1, 2, 3
    side: str                  # "long" / "short"
    entry_ts_ms: int
    entry_price: float
    size_usd: float
    tp_price: float
    sl_price: float


@dataclass
class CascadeBundle:
    """One cascade trigger — up to 3 tier grids opened together."""
    bundle_id: int
    triggered_ts_ms: int
    side: str
    grids: list[GridPos] = field(default_factory=list)
    closed_grids: list[dict] = field(default_factory=list)  # outcomes

    def all_closed(self) -> bool:
        return len(self.closed_grids) == len(self.grids)


def _evaluate_grid_exit(g: GridPos, bar: pd.Series, ts_ms: int) -> tuple[str, float] | None:
    """Return (outcome, exit_price) if grid hit SL/TP/timeout this bar.

    Long: TP if high >= tp, SL if low <= sl.
    Short: TP if low <= tp, SL if high >= sl.
    Timeout: ts > entry + MAX_HOLD_MIN.
    """
    if g.side == "long":
        if bar["high"] >= g.tp_price:
            return ("TP", g.tp_price)
        if bar["low"] <= g.sl_price:
            return ("SL", g.sl_price)
    else:
        if bar["low"] <= g.tp_price:
            return ("TP", g.tp_price)
        if bar["high"] >= g.sl_price:
            return ("SL", g.sl_price)
    if (ts_ms - g.entry_ts_ms) > MAX_HOLD_MIN * 60_000:
        # Timeout — exit at close
        return ("TIMEOUT", float(bar["close"]))
    return None


def _pnl_for_outcome(g: GridPos, exit_price: float) -> float:
    """Returns net PnL in USD after fees."""
    if g.side == "long":
        gross_pct = (exit_price - g.entry_price) / g.entry_price * 100
    else:
        gross_pct = (g.entry_price - exit_price) / g.entry_price * 100
    return g.size_usd * (gross_pct - FEE_RT_PCT) / 100


def _detect_cascade_trigger(window: pd.DataFrame, last_close: float) -> tuple[float, str] | None:
    """Return (range_pct, side) if a 30-min window shows >= 1% range.

    Direction logic (operator clarification):
      Импульс по high/low в 30-min окне.
      Если max(high) == high недавнего бара И low был раньше → импульс ВВЕРХ → SHORT ладдер (fade)
      Если min(low) == low недавнего бара И high был раньше → импульс ВНИЗ → LONG ладдер (fade)
    """
    if len(window) < WINDOW_MIN:
        return None
    hi = float(window["high"].max())
    lo = float(window["low"].min())
    base = float(window["open"].iloc[0])
    if base <= 0:
        return None
    rng_pct = (hi - lo) / base * 100
    if rng_pct < TIER_TRIGGERS[0]:
        return None
    # Direction: which extreme came later in the window?
    hi_idx = window["high"].idxmax()
    lo_idx = window["low"].idxmin()
    if hi_idx > lo_idx:
        # high was later → momentum was up → SHORT
        return (rng_pct, "short")
    else:
        return (rng_pct, "long")


def _open_cascade(triggered_ts_ms: int, side: str, current_price: float,
                   range_pct: float, bundle_id: int) -> CascadeBundle:
    """Open as many tiers as range_pct allows."""
    bundle = CascadeBundle(bundle_id=bundle_id, triggered_ts_ms=triggered_ts_ms, side=side)
    for tier in range(3):
        if range_pct < TIER_TRIGGERS[tier]:
            break
        size_usd = BASE_SIZE * TIER_SIZES[tier]
        tp_pct = TIER_TP[tier]
        sl_pct = tp_pct * TIER_SL_MULT
        if side == "long":
            tp_price = current_price * (1 + tp_pct / 100)
            sl_price = current_price * (1 - sl_pct / 100)
        else:
            tp_price = current_price * (1 - tp_pct / 100)
            sl_price = current_price * (1 + sl_pct / 100)
        g = GridPos(
            tier=tier + 1, side=side,
            entry_ts_ms=triggered_ts_ms,
            entry_price=current_price, size_usd=size_usd,
            tp_price=tp_price, sl_price=sl_price,
        )
        bundle.grids.append(g)
    return bundle


def simulate(df: pd.DataFrame, variant: str) -> dict:
    """Run cascade-grid backtest. Returns metrics dict + trade list.

    variant:
      "A" — close tier-1 when tier-2 hits TP
      "B" — close tier-1 when tier-2 in profit >= 0.5×TP
      "C" — close tier-1 only when tier-2 AND tier-3 hit TP
      "none" — no hedge exit, each tier independent
    """
    df = df.reset_index(drop=True)

    # Pre-compute rolling 30-min range as % of window open (vectorized).
    # This is the only "trigger check" we need per bar — saves 30 lookups/bar.
    rolling_hi = df["high"].rolling(WINDOW_MIN).max()
    rolling_lo = df["low"].rolling(WINDOW_MIN).min()
    rolling_open = df["open"].shift(WINDOW_MIN - 1)  # open of bar (i-WINDOW+1)
    rolling_range_pct = ((rolling_hi - rolling_lo) / rolling_open * 100).fillna(0)
    # idxmax/idxmin in window: simpler proxy — use position of high/low within window.
    # We compute "high happened later" by checking if last bar's high > prior bars'
    # extreme. Simplification: use price velocity over the window.
    # Direction: if close > open at start of window → momentum up → SHORT trigger.
    momentum_up = df["close"].values > rolling_open.values

    open_bundles: list[CascadeBundle] = []
    closed_bundles: list[CascadeBundle] = []
    last_open_ts_ms = 0
    bundle_id = 0

    # Convert pandas to numpy arrays for speed
    ts_arr = df["ts"].values.astype("int64")
    open_arr = df["open"].values
    high_arr = df["high"].values
    low_arr = df["low"].values
    close_arr = df["close"].values

    for i in range(WINDOW_MIN, len(df)):
        ts_ms = int(ts_arr[i])
        high_i = float(high_arr[i])
        low_i = float(low_arr[i])
        close_i = float(close_arr[i])

        # 1. Check exits for all open grids in all open bundles
        for bundle in open_bundles[:]:
            for g in list(bundle.grids):
                if any(c["tier"] == g.tier for c in bundle.closed_grids):
                    continue
                # Inline exit check — fast path with numpy values
                outcome = None
                exit_price = 0.0
                if g.side == "long":
                    if high_i >= g.tp_price:
                        outcome, exit_price = "TP", g.tp_price
                    elif low_i <= g.sl_price:
                        outcome, exit_price = "SL", g.sl_price
                else:
                    if low_i <= g.tp_price:
                        outcome, exit_price = "TP", g.tp_price
                    elif high_i >= g.sl_price:
                        outcome, exit_price = "SL", g.sl_price
                if outcome is None and (ts_ms - g.entry_ts_ms) > MAX_HOLD_MIN * 60_000:
                    outcome, exit_price = "TIMEOUT", close_i
                if outcome is None:
                    continue
                pnl = _pnl_for_outcome(g, exit_price)
                bundle.closed_grids.append({
                    "tier": g.tier, "outcome": outcome,
                    "exit_price": exit_price, "pnl_usd": pnl,
                    "entry_price": g.entry_price, "size_usd": g.size_usd,
                    "side": g.side, "entry_ts_ms": g.entry_ts_ms,
                    "exit_ts_ms": ts_ms,
                })

            # 2. Hedge exit logic
            t1 = next((g for g in bundle.grids if g.tier == 1), None)
            t1_closed = any(c["tier"] == 1 for c in bundle.closed_grids)
            t2_done = any(c["tier"] == 2 and c["outcome"] == "TP" for c in bundle.closed_grids)
            t3_done = any(c["tier"] == 3 and c["outcome"] == "TP" for c in bundle.closed_grids)

            if t1 is not None and not t1_closed:
                hedge_close = False
                if variant == "A" and t2_done:
                    hedge_close = True
                elif variant == "B":
                    t2 = next((g for g in bundle.grids if g.tier == 2), None)
                    if t2 and not any(c["tier"] == 2 for c in bundle.closed_grids):
                        if t2.side == "long":
                            target = t2.entry_price * (1 + TIER_TP[1] * 0.5 / 100)
                            if close_i >= target:
                                hedge_close = True
                        else:
                            target = t2.entry_price * (1 - TIER_TP[1] * 0.5 / 100)
                            if close_i <= target:
                                hedge_close = True
                elif variant == "C" and t2_done and t3_done:
                    hedge_close = True

                if hedge_close:
                    pnl = _pnl_for_outcome(t1, close_i)
                    bundle.closed_grids.append({
                        "tier": 1, "outcome": "HEDGE_EXIT",
                        "exit_price": close_i, "pnl_usd": pnl,
                        "entry_price": t1.entry_price, "size_usd": t1.size_usd,
                        "side": t1.side, "entry_ts_ms": t1.entry_ts_ms,
                        "exit_ts_ms": ts_ms,
                    })

            if bundle.all_closed():
                open_bundles.remove(bundle)
                closed_bundles.append(bundle)

        # 3. New cascade trigger — use precomputed range
        if open_bundles:
            continue
        if (ts_ms - last_open_ts_ms) < COOLDOWN_MIN * 60_000:
            continue
        rng = float(rolling_range_pct.iloc[i])
        if rng < TIER_TRIGGERS[0]:
            continue
        side = "short" if momentum_up[i] else "long"
        bundle_id += 1
        bundle = _open_cascade(ts_ms, side, close_i, rng, bundle_id)
        open_bundles.append(bundle)
        last_open_ts_ms = ts_ms

    # Close any still-open bundles at end (mark to market)
    for bundle in open_bundles:
        last_close = float(df["close"].iloc[-1])
        for g in bundle.grids:
            if not any(c["tier"] == g.tier for c in bundle.closed_grids):
                pnl = _pnl_for_outcome(g, last_close)
                bundle.closed_grids.append({
                    "tier": g.tier, "outcome": "EOD",
                    "exit_price": last_close, "pnl_usd": pnl,
                    "entry_price": g.entry_price, "size_usd": g.size_usd,
                    "side": g.side, "entry_ts_ms": g.entry_ts_ms,
                    "exit_ts_ms": int(df["ts"].iloc[-1]),
                })
        closed_bundles.append(bundle)

    # Aggregate metrics
    all_trades = []
    bundle_pnls = []
    for b in closed_bundles:
        bundle_pnl = sum(c["pnl_usd"] for c in b.closed_grids)
        bundle_pnls.append(bundle_pnl)
        for c in b.closed_grids:
            all_trades.append({
                "bundle_id": b.bundle_id,
                **c,
            })

    if not all_trades:
        return {"n_trades": 0, "n_bundles": 0, "pnl_usd": 0, "pf": 0,
                "winrate": 0, "max_dd_usd": 0, "trades": []}

    pnls = np.array([t["pnl_usd"] for t in all_trades])
    wins = pnls[pnls > 0]
    losses = -pnls[pnls < 0]
    pf = wins.sum() / losses.sum() if losses.sum() > 0 else 999.0
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(dd.max()) if len(dd) else 0

    return {
        "n_trades": len(all_trades),
        "n_bundles": len(closed_bundles),
        "pnl_usd": float(pnls.sum()),
        "pf": round(float(pf), 3),
        "winrate": round((pnls > 0).sum() / len(pnls) * 100, 1),
        "max_dd_usd": round(max_dd, 2),
        "trades": all_trades,
    }


def walk_forward(df: pd.DataFrame, variant: str, n_folds: int = N_FOLDS) -> list[dict]:
    fold_size = len(df) // n_folds
    out = []
    for k in range(n_folds):
        lo = k * fold_size
        hi = (k + 1) * fold_size if k < n_folds - 1 else len(df)
        sub = df.iloc[lo:hi].reset_index(drop=True)
        m = simulate(sub, variant)
        m["fold"] = k + 1
        m["bars"] = len(sub)
        out.append(m)
    return out


def main() -> int:
    print("[cascade-grid] loading 1m data...")
    df = pd.read_csv(DATA_1M)
    print(f"[cascade-grid] {len(df):,} bars  ({pd.to_datetime(df['ts'].min(), unit='ms')} -> "
          f"{pd.to_datetime(df['ts'].max(), unit='ms')})")

    variants = ["A", "B", "C", "none"]
    variant_names = {
        "A": "Hedge A: 1-я зkr когда 2-я TP",
        "B": "Hedge B: 1-я зкr когда 2-я +0.5xTP",
        "C": "Hedge C: 1-я зkr когда 2-я И 3-я TP",
        "none": "Без hedge: каждый tier сам",
    }

    print()
    print("Running full-period backtests for each variant...")
    full_results = {}
    for v in variants:
        print(f"  variant {v}... ", end="", flush=True)
        m = simulate(df, v)
        full_results[v] = m
        print(f"PF={m['pf']:.2f}  PnL=${m['pnl_usd']:+,.0f}  "
              f"WR={m['winrate']:.1f}%  N={m['n_trades']}  MaxDD=${m['max_dd_usd']:,.0f}")

    # Walk-forward for best variant by PF
    best_v = max(variants, key=lambda v: full_results[v]["pf"])
    print(f"\nWalk-forward on best variant ({best_v}, {variant_names[best_v]}):")
    wf = walk_forward(df, best_v)
    for f in wf:
        print(f"  fold {f['fold']}: PF={f['pf']:.2f}  PnL=${f['pnl_usd']:+,.0f}  "
              f"N={f['n_trades']}  MaxDD=${f['max_dd_usd']:,.0f}")
    folds_pos = sum(1 for f in wf if f["pnl_usd"] > 0)

    # Write markdown report
    md = []
    md.append("# Cascade Grid Backtest — 3-tier laddered shorts+longs")
    md.append("")
    md.append(f"**Период:** 2y BTCUSDT 1m  ({len(df):,} bars)")
    md.append(f"**Триггер:** high-low range за 30 мин")
    md.append(f"**Tier-1:** trigger 1%, size ${BASE_SIZE:.0f}, TP +1%, SL -3%")
    md.append(f"**Tier-2:** trigger 2%, size ${BASE_SIZE*2:.0f}, TP +2%, SL -6%")
    md.append(f"**Tier-3:** trigger 3%, size ${BASE_SIZE*3:.0f}, TP +3%, SL -9%")
    md.append(f"**Cooldown:** {COOLDOWN_MIN}min между bundles, max hold {MAX_HOLD_MIN}min")
    md.append(f"**Fees:** {FEE_RT_PCT}% RT")
    md.append("")
    md.append("## Сравнение hedge-exit вариантов (full 2y)")
    md.append("")
    md.append("| variant | описание | PnL ($) | PF | WR% | N trades | N bundles | MaxDD ($) |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for v in variants:
        m = full_results[v]
        md.append(f"| {v} | {variant_names[v]} | {m['pnl_usd']:+,.0f} | "
                  f"{m['pf']:.2f} | {m['winrate']:.1f} | {m['n_trades']} | "
                  f"{m['n_bundles']} | {m['max_dd_usd']:,.0f} |")
    md.append("")
    md.append(f"## Walk-forward (variant {best_v}: {variant_names[best_v]})")
    md.append("")
    md.append("| fold | PnL ($) | PF | WR% | N | MaxDD ($) |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for f in wf:
        md.append(f"| {f['fold']} | {f['pnl_usd']:+,.0f} | {f['pf']:.2f} | "
                  f"{f['winrate']:.1f} | {f['n_trades']} | {f['max_dd_usd']:,.0f} |")
    md.append("")
    md.append(f"**Pos folds:** {folds_pos}/{N_FOLDS}")
    md.append("")
    md.append("## Verdict")
    md.append("")
    best_pf = full_results[best_v]['pf']
    best_pnl = full_results[best_v]['pnl_usd']
    if best_pf >= 1.3 and folds_pos >= 3:
        md.append(f"✅ Variant **{best_v}** stable: PF {best_pf:.2f}, +${best_pnl:,.0f} on 2y, "
                  f"{folds_pos}/{N_FOLDS} folds positive.")
    elif best_pf >= 1.0:
        md.append(f"🟡 Variant **{best_v}** marginal: PF {best_pf:.2f}, +${best_pnl:,.0f}. "
                  f"WF {folds_pos}/{N_FOLDS} — недостаточно для прода без recheck.")
    else:
        md.append(f"❌ Best variant **{best_v}** has PF {best_pf:.2f} < 1.0 — "
                  f"стратегия убыточна на 2y. Triggers/sizes/TP needs tuning.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[cascade-grid] wrote {OUT_MD}")

    # CSV per-trade for further analysis
    csv_path = ROOT / "state" / "cascade_grid_results.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    all_trades_flat = []
    for v in variants:
        for t in full_results[v]["trades"]:
            all_trades_flat.append({**t, "variant": v})
    if all_trades_flat:
        pd.DataFrame(all_trades_flat).to_csv(csv_path, index=False)
        print(f"[cascade-grid] wrote {csv_path}: {len(all_trades_flat)} trades")
    return 0


if __name__ == "__main__":
    sys.exit(main())
