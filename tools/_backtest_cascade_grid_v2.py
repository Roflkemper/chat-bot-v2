"""Cascade grid backtest V2 — правильная ladder-по-цене модель.

Operator clarification:
  - 1-й тир открывается когда 30-min range >= 1% (entry = текущая цена)
  - 2-й тир открывается ТОЛЬКО когда цена ушла +2% от точки начала окна
    (то есть entry tier-2 ≠ entry tier-1 — тиры разнесены по цене)
  - 3-й тир — когда цена ушла +3% от точки начала окна
  - У каждого тира свой grid_step и свой target: 1-й самый частый/мелкий,
    3-й самый редкий/крупный.

Тестируем несколько конфигов параметров (grid step, target, sl, size mult)
и несколько вариантов hedge-exit. Цель — найти комбо с PF >= 1.2 на 2y
1m BTCUSDT с walk-forward подтверждением.

Outputs:
  state/cascade_grid_v2_results.csv
  docs/STRATEGIES/CASCADE_GRID_V2_BACKTEST.md
"""
from __future__ import annotations

import itertools
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "CASCADE_GRID_V2_BACKTEST.md"

# Reference point: rolling 30-min window
WINDOW_MIN = 30

# Tier triggers — % move от reference price (open окна) для открытия каждого тира.
# Tier-1: триггер 1%, Tier-2: 2%, Tier-3: 3%.
DEFAULT_TIER_TRIG = [1.0, 2.0, 3.0]

# Per-tier target % (от entry этого тира — то есть от цены в момент его открытия)
# Tier-1 быстрый малый, Tier-3 медленный большой.
DEFAULT_TIER_TP = [0.6, 1.2, 2.0]

# Per-tier SL multiplier (SL = TP * mult)
DEFAULT_SL_MULT = [3.0, 3.0, 3.0]

# Size multipliers (USD = BASE_SIZE * mult)
DEFAULT_SIZE_MULT = [1.0, 1.5, 2.5]

BASE_SIZE = 1000.0
COOLDOWN_MIN = 60
MAX_HOLD_MIN = 24 * 60
FEE_RT_PCT = 0.165

N_FOLDS = 4


@dataclass
class Tier:
    tier: int
    side: str               # long/short
    entry_ts_ms: int
    entry_price: float
    size_usd: float
    tp_price: float
    sl_price: float


@dataclass
class Bundle:
    bundle_id: int
    ref_price: float        # цена в начале окна (база для триггеров)
    side: str               # long fade vs short fade
    started_ts_ms: int
    tier_triggers: list[float]   # % moves of ref_price needed for each tier
    tier_tp: list[float]
    sl_mult: list[float]
    size_mult: list[float]
    tiers_opened: list[Tier] = field(default_factory=list)
    closed: list[dict] = field(default_factory=list)
    dead: bool = False           # cascade aborted (came back / SL on tier-1)

    def has_tier(self, t: int) -> bool:
        return any(g.tier == t for g in self.tiers_opened)

    def closed_tier(self, t: int) -> dict | None:
        for c in self.closed:
            if c["tier"] == t:
                return c
        return None


def _pnl(g: Tier, exit_price: float) -> float:
    if g.side == "long":
        gross_pct = (exit_price - g.entry_price) / g.entry_price * 100
    else:
        gross_pct = (g.entry_price - exit_price) / g.entry_price * 100
    return g.size_usd * (gross_pct - FEE_RT_PCT) / 100


def _open_tier(side: str, tier_idx: int, ref_price: float, current_price: float,
               ts_ms: int, cfg: dict) -> Tier:
    """tier_idx: 0/1/2; entry at current_price (not ref_price)."""
    tp_pct = cfg["tp"][tier_idx]
    sl_pct = tp_pct * cfg["sl_mult"][tier_idx]
    size = BASE_SIZE * cfg["size"][tier_idx]
    if side == "long":
        tp_price = current_price * (1 + tp_pct / 100)
        sl_price = current_price * (1 - sl_pct / 100)
    else:
        tp_price = current_price * (1 - tp_pct / 100)
        sl_price = current_price * (1 + sl_pct / 100)
    return Tier(
        tier=tier_idx + 1, side=side, entry_ts_ms=ts_ms,
        entry_price=current_price, size_usd=size,
        tp_price=tp_price, sl_price=sl_price,
    )


def simulate(df: pd.DataFrame, cfg: dict, hedge_variant: str) -> dict:
    """Run V2 cascade simulation.

    cfg: {"trig": [1,2,3], "tp": [0.6,1.2,2.0], "sl_mult": [3,3,3], "size": [1,1.5,2.5]}
    hedge_variant:
       "none"   — каждый тир выходит сам по SL/TP/timeout
       "A"      — закрываем тир-1 когда тир-2 в +0.5×TP2
       "B"      — закрываем тир-1 когда тир-2 закрылся в TP
       "C"      — закрываем тир-1 и тир-2 когда тир-3 в +0.3×TP3
       "trail"  — после открытия тир-2, тир-1 SL подтягиваем к breakeven
    """
    df = df.reset_index(drop=True)
    n = len(df)

    ts_arr = df["ts"].values.astype("int64")
    open_arr = df["open"].values
    high_arr = df["high"].values
    low_arr = df["low"].values
    close_arr = df["close"].values

    # Reference: open at i-WINDOW+1
    ref_open = pd.Series(open_arr).shift(WINDOW_MIN - 1).values

    open_bundles: list[Bundle] = []
    closed_bundles: list[Bundle] = []
    last_open_ts_ms = 0
    bundle_id = 0

    for i in range(WINDOW_MIN, n):
        ts_ms = int(ts_arr[i])
        hi = float(high_arr[i])
        lo = float(low_arr[i])
        cl = float(close_arr[i])

        # 1. Exit checks для всех открытых тиров
        for b in open_bundles[:]:
            if b.dead:
                continue
            for g in list(b.tiers_opened):
                if b.closed_tier(g.tier) is not None:
                    continue
                outcome = None
                ep = 0.0
                if g.side == "long":
                    if hi >= g.tp_price:
                        outcome, ep = "TP", g.tp_price
                    elif lo <= g.sl_price:
                        outcome, ep = "SL", g.sl_price
                else:
                    if lo <= g.tp_price:
                        outcome, ep = "TP", g.tp_price
                    elif hi >= g.sl_price:
                        outcome, ep = "SL", g.sl_price
                if outcome is None and (ts_ms - g.entry_ts_ms) > MAX_HOLD_MIN * 60_000:
                    outcome, ep = "TIMEOUT", cl
                if outcome is None:
                    continue
                b.closed.append({
                    "tier": g.tier, "outcome": outcome, "exit_price": ep,
                    "pnl_usd": _pnl(g, ep), "entry_price": g.entry_price,
                    "size_usd": g.size_usd, "side": g.side,
                    "entry_ts_ms": g.entry_ts_ms, "exit_ts_ms": ts_ms,
                })

            # 2. Hedge exit logic
            t1_obj = next((g for g in b.tiers_opened if g.tier == 1), None)
            t2_obj = next((g for g in b.tiers_opened if g.tier == 2), None)
            t3_obj = next((g for g in b.tiers_opened if g.tier == 3), None)
            t1_closed = b.closed_tier(1) is not None
            t2_closed = b.closed_tier(2)
            t3_closed = b.closed_tier(3)

            if hedge_variant == "A":
                # close t1 when t2 in profit >= 0.5 * tp2
                if t1_obj and not t1_closed and t2_obj and t2_closed is None:
                    t2_tp_pct = cfg["tp"][1]
                    target_move = t2_tp_pct * 0.5 / 100
                    if t2_obj.side == "long":
                        target = t2_obj.entry_price * (1 + target_move)
                        hit = cl >= target
                    else:
                        target = t2_obj.entry_price * (1 - target_move)
                        hit = cl <= target
                    if hit:
                        b.closed.append({
                            "tier": 1, "outcome": "HEDGE_A", "exit_price": cl,
                            "pnl_usd": _pnl(t1_obj, cl), "entry_price": t1_obj.entry_price,
                            "size_usd": t1_obj.size_usd, "side": t1_obj.side,
                            "entry_ts_ms": t1_obj.entry_ts_ms, "exit_ts_ms": ts_ms,
                        })
            elif hedge_variant == "B":
                if t1_obj and not t1_closed and t2_closed and t2_closed["outcome"] == "TP":
                    b.closed.append({
                        "tier": 1, "outcome": "HEDGE_B", "exit_price": cl,
                        "pnl_usd": _pnl(t1_obj, cl), "entry_price": t1_obj.entry_price,
                        "size_usd": t1_obj.size_usd, "side": t1_obj.side,
                        "entry_ts_ms": t1_obj.entry_ts_ms, "exit_ts_ms": ts_ms,
                    })
            elif hedge_variant == "C":
                # close t1+t2 when t3 in +0.3*tp3
                if t3_obj and t3_closed is None:
                    t3_tp_pct = cfg["tp"][2]
                    target_move = t3_tp_pct * 0.3 / 100
                    if t3_obj.side == "long":
                        target = t3_obj.entry_price * (1 + target_move)
                        hit = cl >= target
                    else:
                        target = t3_obj.entry_price * (1 - target_move)
                        hit = cl <= target
                    if hit:
                        for tobj, closed_flag in [(t1_obj, t1_closed),
                                                   (t2_obj, t2_closed is not None)]:
                            if tobj and not closed_flag:
                                b.closed.append({
                                    "tier": tobj.tier, "outcome": "HEDGE_C",
                                    "exit_price": cl, "pnl_usd": _pnl(tobj, cl),
                                    "entry_price": tobj.entry_price,
                                    "size_usd": tobj.size_usd, "side": tobj.side,
                                    "entry_ts_ms": tobj.entry_ts_ms, "exit_ts_ms": ts_ms,
                                })
            elif hedge_variant == "trail":
                # after t2 opens, raise t1 SL to breakeven (entry_price + fee buffer)
                if t1_obj and not t1_closed and t2_obj is not None:
                    be = t1_obj.entry_price * (1 + FEE_RT_PCT / 100) if t1_obj.side == "long" \
                         else t1_obj.entry_price * (1 - FEE_RT_PCT / 100)
                    if t1_obj.side == "long" and t1_obj.sl_price < be:
                        t1_obj.sl_price = be
                    elif t1_obj.side == "short" and t1_obj.sl_price > be:
                        t1_obj.sl_price = be

            # 3. Cascade tier-2 / tier-3 opening logic
            # Только если bundle ещё активен и tier-1 не закрылся в SL
            if not b.dead and not t1_closed:
                # tier-2: opens when цена прошла trig[1] от ref_price
                if not b.has_tier(2):
                    trig2_pct = b.tier_triggers[1]
                    if b.side == "long":
                        # long fade: ждём ещё большего down-move от ref
                        target = b.ref_price * (1 - trig2_pct / 100)
                        if lo <= target:
                            g = _open_tier("long", 1, b.ref_price, target, ts_ms, cfg)
                            b.tiers_opened.append(g)
                    else:
                        target = b.ref_price * (1 + trig2_pct / 100)
                        if hi >= target:
                            g = _open_tier("short", 1, b.ref_price, target, ts_ms, cfg)
                            b.tiers_opened.append(g)
                # tier-3
                if b.has_tier(2) and not b.has_tier(3):
                    trig3_pct = b.tier_triggers[2]
                    if b.side == "long":
                        target = b.ref_price * (1 - trig3_pct / 100)
                        if lo <= target:
                            g = _open_tier("long", 2, b.ref_price, target, ts_ms, cfg)
                            b.tiers_opened.append(g)
                    else:
                        target = b.ref_price * (1 + trig3_pct / 100)
                        if hi >= target:
                            g = _open_tier("short", 2, b.ref_price, target, ts_ms, cfg)
                            b.tiers_opened.append(g)

            # cascade finished?
            opened_tiers = {g.tier for g in b.tiers_opened}
            closed_tiers = {c["tier"] for c in b.closed}
            # bundle is done if all opened tiers are closed AND we can't open more
            # We say "can't open more" if t1 already closed (cascade aborted) OR
            # if MAX_HOLD passed since bundle start.
            bundle_age = ts_ms - b.started_ts_ms
            if bundle_age > MAX_HOLD_MIN * 60_000 or (t1_closed and len(opened_tiers) == 1):
                # close any still-open tiers at market
                for g in b.tiers_opened:
                    if g.tier not in closed_tiers:
                        b.closed.append({
                            "tier": g.tier, "outcome": "EOD", "exit_price": cl,
                            "pnl_usd": _pnl(g, cl), "entry_price": g.entry_price,
                            "size_usd": g.size_usd, "side": g.side,
                            "entry_ts_ms": g.entry_ts_ms, "exit_ts_ms": ts_ms,
                        })
                b.dead = True
                open_bundles.remove(b)
                closed_bundles.append(b)
            elif opened_tiers == closed_tiers and len(opened_tiers) >= 1:
                # all opened tiers closed — but maybe could still open more?
                # If t1 closed in TP and we never opened t2/t3 — bundle done.
                if t1_closed:
                    b.dead = True
                    open_bundles.remove(b)
                    closed_bundles.append(b)

        # 4. New cascade trigger
        if open_bundles:
            continue
        if (ts_ms - last_open_ts_ms) < COOLDOWN_MIN * 60_000:
            continue
        ref = ref_open[i]
        if np.isnan(ref) or ref <= 0:
            continue
        # range over window
        win_hi = float(np.max(high_arr[i - WINDOW_MIN + 1:i + 1]))
        win_lo = float(np.min(low_arr[i - WINDOW_MIN + 1:i + 1]))
        rng_pct = (win_hi - win_lo) / ref * 100
        if rng_pct < cfg["trig"][0]:
            continue
        # direction: which extreme was last?
        last_hi_idx = i - WINDOW_MIN + 1 + int(np.argmax(high_arr[i - WINDOW_MIN + 1:i + 1]))
        last_lo_idx = i - WINDOW_MIN + 1 + int(np.argmin(low_arr[i - WINDOW_MIN + 1:i + 1]))
        if last_hi_idx > last_lo_idx:
            side = "short"   # fade up-move
        else:
            side = "long"

        bundle_id += 1
        b = Bundle(
            bundle_id=bundle_id, ref_price=float(ref), side=side,
            started_ts_ms=ts_ms, tier_triggers=cfg["trig"],
            tier_tp=cfg["tp"], sl_mult=cfg["sl_mult"], size_mult=cfg["size"],
        )
        t1 = _open_tier(side, 0, float(ref), cl, ts_ms, cfg)
        b.tiers_opened.append(t1)
        open_bundles.append(b)
        last_open_ts_ms = ts_ms

    # EOD close remaining
    for b in open_bundles:
        last_close = float(close_arr[-1])
        for g in b.tiers_opened:
            if b.closed_tier(g.tier) is None:
                b.closed.append({
                    "tier": g.tier, "outcome": "EOD", "exit_price": last_close,
                    "pnl_usd": _pnl(g, last_close), "entry_price": g.entry_price,
                    "size_usd": g.size_usd, "side": g.side,
                    "entry_ts_ms": g.entry_ts_ms, "exit_ts_ms": int(ts_arr[-1]),
                })
        closed_bundles.append(b)

    # metrics
    all_trades = []
    bundle_pnls = []
    tier_pnls = {1: [], 2: [], 3: []}
    for b in closed_bundles:
        bp = sum(c["pnl_usd"] for c in b.closed)
        bundle_pnls.append(bp)
        for c in b.closed:
            all_trades.append({"bundle_id": b.bundle_id, **c})
            tier_pnls[c["tier"]].append(c["pnl_usd"])

    if not all_trades:
        return {"n_trades": 0, "n_bundles": 0, "pnl_usd": 0, "pf": 0,
                "wr": 0, "max_dd": 0, "trades": [], "tier_breakdown": {}}

    pnls = [t["pnl_usd"] for t in all_trades]
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100

    # max drawdown over bundle PnL series
    eq = np.cumsum(bundle_pnls)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = float(np.max(dd)) if len(dd) else 0.0

    return {
        "n_trades": len(all_trades), "n_bundles": len(closed_bundles),
        "pnl_usd": float(sum(pnls)), "pf": pf, "wr": wr, "max_dd": max_dd,
        "trades": all_trades,
        "tier_breakdown": {
            t: {"n": len(v), "pnl": float(sum(v)),
                "wr": sum(1 for p in v if p > 0) / len(v) * 100 if v else 0}
            for t, v in tier_pnls.items()
        },
    }


def walk_forward(df: pd.DataFrame, cfg: dict, hedge: str, n_folds: int = N_FOLDS) -> list[dict]:
    chunk = len(df) // n_folds
    out = []
    for k in range(n_folds):
        sub = df.iloc[k * chunk:(k + 1) * chunk]
        m = simulate(sub, cfg, hedge)
        out.append({"fold": k + 1, **{k2: m[k2] for k2 in ("pnl_usd", "pf", "wr", "n_trades", "max_dd")}})
    return out


def main() -> int:
    print("[cascade-grid-v2] loading 1m data...")
    df = pd.read_csv(DATA_1M)
    df = df.sort_values("ts").reset_index(drop=True)
    print(f"[cascade-grid-v2] {len(df):,} bars  "
          f"({pd.to_datetime(df['ts'].min(), unit='ms')} -> "
          f"{pd.to_datetime(df['ts'].max(), unit='ms')})")
    print()

    # Configs to test (param grid).
    # tp tuples = (tier1, tier2, tier3) — tier-1 малый/быстрый, tier-3 крупный/редкий
    configs = {
        "default":  {"trig": [1.0, 2.0, 3.0], "tp": [0.6, 1.2, 2.0],
                     "sl_mult": [3.0, 3.0, 3.0], "size": [1.0, 1.5, 2.5]},
        "tight":    {"trig": [1.0, 2.0, 3.0], "tp": [0.4, 0.8, 1.5],
                     "sl_mult": [3.0, 3.0, 3.0], "size": [1.0, 1.5, 2.5]},
        "wide":     {"trig": [1.0, 2.0, 3.0], "tp": [0.8, 1.6, 2.5],
                     "sl_mult": [3.0, 3.0, 3.0], "size": [1.0, 1.5, 2.5]},
        "tight_sl": {"trig": [1.0, 2.0, 3.0], "tp": [0.6, 1.2, 2.0],
                     "sl_mult": [2.0, 2.5, 3.0], "size": [1.0, 1.5, 2.5]},
        "big_t3":   {"trig": [1.0, 2.0, 3.0], "tp": [0.5, 1.0, 2.5],
                     "sl_mult": [2.5, 2.5, 3.0], "size": [1.0, 1.5, 3.0]},
        "agg_trig": {"trig": [0.7, 1.5, 2.5], "tp": [0.5, 1.0, 1.8],
                     "sl_mult": [3.0, 3.0, 3.0], "size": [1.0, 1.5, 2.5]},
    }
    hedges = ["none", "A", "B", "C", "trail"]

    results = []
    print("Running param grid (configs × hedges)...")
    for cfg_name, cfg in configs.items():
        for hv in hedges:
            print(f"  {cfg_name:<10} hedge={hv:<5} ...", end="", flush=True)
            m = simulate(df, cfg, hv)
            print(f"  PF={m['pf']:.2f}  PnL=${m['pnl_usd']:+,.0f}  "
                  f"WR={m['wr']:.0f}%  N={m['n_trades']}  DD=${m['max_dd']:,.0f}")
            results.append({"config": cfg_name, "hedge": hv, **m})

    # best by PF
    results_sorted = sorted(results, key=lambda r: r["pf"], reverse=True)
    best = results_sorted[0]
    print(f"\nBest combo: {best['config']} + hedge={best['hedge']}  "
          f"(PF {best['pf']:.2f}, PnL ${best['pnl_usd']:+,.0f})")

    # walk-forward on best
    best_cfg = configs[best["config"]]
    print(f"\nWalk-forward on best ({best['config']} / hedge={best['hedge']}):")
    wf = walk_forward(df, best_cfg, best["hedge"])
    for f in wf:
        print(f"  fold {f['fold']}: PF={f['pf']:.2f}  PnL=${f['pnl_usd']:+,.0f}  "
              f"N={f['n_trades']}  DD=${f['max_dd']:,.0f}")

    # write report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = []
    md.append("# Cascade Grid V2 — ladder-по-цене модель")
    md.append("")
    md.append(f"**Период:** 2y BTCUSDT 1m  ({len(df):,} bars)")
    md.append("**Модель:** tier-2 открывается когда цена ушла +trig[1]% от ref_price (open окна), "
              "tier-3 — +trig[2]%. У каждого тира свои entry, TP, SL.")
    md.append(f"**Cooldown:** {COOLDOWN_MIN}min, max hold {MAX_HOLD_MIN}min, "
              f"fees {FEE_RT_PCT}% RT")
    md.append("")
    md.append("## Все комбо (config × hedge)")
    md.append("")
    md.append("| config | hedge | PnL ($) | PF | WR% | N trades | N bundles | MaxDD ($) |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in results_sorted:
        md.append(f"| {r['config']} | {r['hedge']} | {r['pnl_usd']:+,.0f} | "
                  f"{r['pf']:.2f} | {r['wr']:.1f} | {r['n_trades']} | "
                  f"{r['n_bundles']} | {r['max_dd']:,.0f} |")
    md.append("")
    md.append(f"## Best combo: **{best['config']} / hedge={best['hedge']}**")
    md.append("")
    md.append("### Tier breakdown")
    md.append("| tier | trades | PnL ($) | WR% |")
    md.append("|---|---:|---:|---:|")
    for t, info in best["tier_breakdown"].items():
        md.append(f"| {t} | {info['n']} | {info['pnl']:+,.0f} | {info['wr']:.1f} |")
    md.append("")
    md.append("### Walk-forward (4 folds)")
    md.append("| fold | PnL ($) | PF | WR% | N | MaxDD ($) |")
    md.append("|---|---:|---:|---:|---:|---:|")
    pos = 0
    for f in wf:
        md.append(f"| {f['fold']} | {f['pnl_usd']:+,.0f} | {f['pf']:.2f} | "
                  f"{f['wr']:.1f} | {f['n_trades']} | {f['max_dd']:,.0f} |")
        if f["pnl_usd"] > 0:
            pos += 1
    md.append("")
    md.append(f"**Pos folds:** {pos}/{N_FOLDS}")
    md.append("")
    md.append("## Verdict")
    if best["pf"] >= 1.2 and pos >= 3:
        md.append(f"✅ **{best['config']}+{best['hedge']}** даёт PF {best['pf']:.2f} с "
                  f"{pos}/{N_FOLDS} положительных фолдов — кандидат на paper trading.")
    elif best["pf"] >= 1.0:
        md.append(f"⚠️ **{best['config']}+{best['hedge']}** на грани (PF {best['pf']:.2f}). "
                  "Нужно больше валидации.")
    else:
        md.append(f"❌ Лучшее PF {best['pf']:.2f} < 1.0 — модель не работает на 2y BTC.")
    md.append("")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[cascade-grid-v2] wrote {OUT_MD}")

    # dump CSV
    csv_path = ROOT / "state" / "cascade_grid_v2_results.csv"
    rows = []
    for r in results:
        for t in r["trades"]:
            rows.append({"config": r["config"], "hedge": r["hedge"], **t})
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    print(f"[cascade-grid-v2] wrote {csv_path}: {len(rows)} trade rows")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
