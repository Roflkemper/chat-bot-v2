"""Honest backtest for trade-emitting detectors on calibrated 1m engine.

Симулирует **торговые сделки** с реальными fills по entry/SL/TP1/TP2 на
1-минутных барах — а не close-to-close forward returns как старый
backtest_signals.score_signals.

Fee model (как в P-15 v2):
  IN (limit):  maker rebate -0.0125% (бот ПОЛУЧАЕТ)
  OUT (market): taker 0.075% + slippage 0.02%
  → round-trip 0.165%

Подход:
  Для каждого 1m бара:
    1. Создаём DetectionContext (1h+15m+1m slice)
    2. Зовём detector → если эмитит Setup — записываем
    3. Симулируем сделку: ждём entry fill (limit), потом intra-bar SL/TP race
    4. Запись результата (TP1/TP2/SL/EXPIRE)

Walk-forward: 4 folds × 6 mo. Verdict:
  STABLE   — PF >= 1.5 на 3+/4 folds, N >= 20 per fold
  MARGINAL — PF >= 1.5 на 2/4 folds
  OVERFIT  — иначе

Run: python tools/_backtest_detectors_honest.py [--detectors d1 d2]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "DETECTORS_HONEST_BACKTEST.md"
OUT_CSV = ROOT / "state" / "detectors_honest_runs.csv"

# Realistic fee model (same as P15 v2)
MAKER_REBATE = -0.0125 / 100
TAKER_FEE = 0.075 / 100
SLIPPAGE = 0.02 / 100

# Backtest constants
WINDOW_HOURS_DEFAULT = 240   # 4h default expiration
DETECTION_FREQ_BARS = 60     # check detectors every 60 1m bars (= 1h)
EVAL_PERIOD_BARS = 14400     # последний год для скорости (60×24×30×~12)


@dataclass
class TradeResult:
    detector: str
    setup_type: str
    side: str
    entry_ts: int
    entry: float
    sl: float
    tp1: float
    tp2: float
    outcome: str  # TP1 / TP2 / SL / EXPIRE
    exit_price: float
    bars_held: int
    pnl_usd: float
    pnl_pct: float


@dataclass
class DetectorStats:
    detector: str
    n_trades: int
    n_tp1: int
    n_tp2: int
    n_sl: int
    n_expire: int
    win_rate: float       # TP1+TP2 / total
    pf: float
    avg_pnl: float
    total_pnl: float
    median_hold_bars: float


# -- Stub detection context

@dataclass
class _StubCtx:
    pair: str
    current_price: float
    regime_label: str
    session_label: str
    ohlcv_1m: pd.DataFrame
    ohlcv_1h: pd.DataFrame
    ohlcv_15m: pd.DataFrame
    portfolio: object = None
    ict_context: dict = None

    def __post_init__(self):
        if self.ict_context is None:
            self.ict_context = {}


def _build_aggregations(df_1m: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build 15m + 1h from 1m once (faster than per-bar resample)."""
    df_1m = df_1m.copy()
    df_1m["ts_dt"] = pd.to_datetime(df_1m["ts"], unit="ms", utc=True)
    df_1m_idx = df_1m.set_index("ts_dt")

    df_15m = df_1m_idx.resample("15min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()
    df_1h = df_1m_idx.resample("1h").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    return df_15m.reset_index(drop=True), df_1h.reset_index(drop=True)


def _emit_setups(detector, df_1m: pd.DataFrame, df_15m: pd.DataFrame,
                  df_1h: pd.DataFrame, freq_bars: int = DETECTION_FREQ_BARS) -> list[dict]:
    """Run detector at every freq_bars on the 1m data, collect emitted setups."""
    emits = []
    n = len(df_1m)
    # Need at least 250 1h bars for indicators warmup
    min_1h_bars = 250
    min_15m_bars = 100

    # Pre-computed lookup: 1m_idx → 1h_idx and 15m_idx
    ts_1m = df_1m["ts"].values
    ts_1h = df_1h["ts"].values
    ts_15m = df_15m["ts"].values

    for i in range(0, n, freq_bars):
        if i < 60 * 24:  # ≥ 1 day warmup
            continue
        # Find latest 1h bar at-or-before this 1m
        h_idx = np.searchsorted(ts_1h, ts_1m[i], side="right") - 1
        if h_idx < min_1h_bars:
            continue
        m15_idx = np.searchsorted(ts_15m, ts_1m[i], side="right") - 1
        if m15_idx < min_15m_bars:
            continue

        sub_1h = df_1h.iloc[max(0, h_idx - min_1h_bars):h_idx + 1].reset_index(drop=True)
        sub_15m = df_15m.iloc[max(0, m15_idx - min_15m_bars):m15_idx + 1].reset_index(drop=True)
        sub_1m = df_1m.iloc[max(0, i - 200):i + 1].reset_index(drop=True)

        ctx = _StubCtx(
            pair="BTCUSDT",
            current_price=float(df_1m["close"].iloc[i]),
            regime_label="range_wide",  # упрощение
            session_label="ny_am",
            ohlcv_1m=sub_1m,
            ohlcv_1h=sub_1h,
            ohlcv_15m=sub_15m,
        )
        try:
            setup = detector(ctx)
        except Exception:
            continue
        if setup is None:
            continue
        # Skip P-15 lifecycle setups (separate validation)
        if setup.setup_type.value.startswith("p15_"):
            continue
        # Skip non-trade
        if setup.entry_price is None or setup.stop_price is None or setup.tp1_price is None:
            continue

        emits.append({
            "bar_idx": i,
            "ts": int(df_1m["ts"].iloc[i]),
            "setup_type": setup.setup_type.value,
            "side": "long" if "long" in setup.setup_type.value or
                    setup.setup_type.value.startswith("long_") else "short",
            "entry": float(setup.entry_price),
            "sl": float(setup.stop_price),
            "tp1": float(setup.tp1_price),
            "tp2": float(setup.tp2_price) if setup.tp2_price else float(setup.tp1_price),
            "window_min": int(setup.window_minutes or 240),
        })
    return emits


def _simulate_trade(setup: dict, df_1m: pd.DataFrame) -> TradeResult:
    """Симуляция жизненного цикла одной сделки.

    1. Wait limit fill at entry (within 24h window, иначе EXPIRE)
    2. Intra-bar race: SL vs TP1 (приоритет SL для консервативности)
    3. После TP1 — переключение на breakeven SL и охота за TP2
    4. Если EXPIRE до fill — null trade
    """
    bar_idx = setup["bar_idx"]
    side = setup["side"]
    entry = setup["entry"]
    sl = setup["sl"]
    tp1 = setup["tp1"]
    tp2 = setup["tp2"]
    window_min = setup["window_min"]

    base_size_usd = 1000.0
    qty_btc = base_size_usd / entry

    # Phase 1: wait limit fill (max 24h = 1440 bars)
    fill_bar = None
    for j in range(bar_idx, min(bar_idx + 1440, len(df_1m))):
        h = float(df_1m["high"].iloc[j])
        l = float(df_1m["low"].iloc[j])
        if side == "long":
            # Long entry — limit BELOW market, fills if low <= entry
            if l <= entry:
                fill_bar = j
                break
        else:
            # Short entry — limit ABOVE market, fills if high >= entry
            if h >= entry:
                fill_bar = j
                break
    if fill_bar is None:
        # Never filled
        return TradeResult(
            detector=setup.get("detector", ""),
            setup_type=setup["setup_type"], side=side,
            entry_ts=setup["ts"], entry=entry, sl=sl, tp1=tp1, tp2=tp2,
            outcome="NO_FILL", exit_price=entry, bars_held=0,
            pnl_usd=0, pnl_pct=0,
        )

    # Phase 2: race SL/TP1/TP2 from fill_bar to fill_bar + window_min
    end_bar = min(fill_bar + window_min, len(df_1m) - 1)
    tp1_hit = False
    outcome = "EXPIRE"
    exit_price = entry  # default
    exit_bar = end_bar

    for j in range(fill_bar + 1, end_bar + 1):
        h = float(df_1m["high"].iloc[j])
        l = float(df_1m["low"].iloc[j])

        if side == "long":
            sl_check = sl
            tp1_check = tp1
            tp2_check = tp2
            sl_hit_intra = l <= sl_check
            tp1_hit_intra = h >= tp1_check
            tp2_hit_intra = h >= tp2_check
        else:
            sl_check = sl
            tp1_check = tp1
            tp2_check = tp2
            sl_hit_intra = h >= sl_check
            tp1_hit_intra = l <= tp1_check
            tp2_hit_intra = l <= tp2_check

        # Conservative: if SL and TP both hit on same bar — assume SL first
        if not tp1_hit and sl_hit_intra:
            outcome = "SL"
            exit_price = sl_check
            exit_bar = j
            break
        if not tp1_hit and tp1_hit_intra:
            tp1_hit = True
            # After TP1 we move SL to breakeven (entry)
            sl = entry
        if tp1_hit and tp2_hit_intra:
            outcome = "TP2"
            exit_price = tp2_check
            exit_bar = j
            break
        # If after TP1 price comes back to breakeven SL — exit at entry
        if tp1_hit:
            be_hit_intra = (l <= entry) if side == "long" else (h >= entry)
            if be_hit_intra:
                outcome = "TP1"  # TP1 was hit, exited at BE → still profit from TP1 partial
                exit_price = entry
                exit_bar = j
                break

    # If loop ended without break — outcome is EXPIRE
    if outcome == "EXPIRE":
        exit_price = float(df_1m["close"].iloc[end_bar])
        if tp1_hit:
            outcome = "TP1"  # TP1 was hit, exited at expiry

    # Compute PnL with fees
    if side == "long":
        gross = qty_btc * (exit_price - entry)
    else:
        gross = qty_btc * (entry - exit_price)
    fee_in = entry * qty_btc * MAKER_REBATE  # negative = rebate
    fee_out = exit_price * qty_btc * (TAKER_FEE + SLIPPAGE)
    pnl_usd = gross - fee_in - fee_out
    pnl_pct = pnl_usd / base_size_usd * 100

    bars_held = exit_bar - fill_bar
    return TradeResult(
        detector=setup.get("detector", ""),
        setup_type=setup["setup_type"], side=side,
        entry_ts=setup["ts"], entry=entry, sl=sl, tp1=tp1, tp2=tp2,
        outcome=outcome, exit_price=exit_price, bars_held=bars_held,
        pnl_usd=round(pnl_usd, 2), pnl_pct=round(pnl_pct, 4),
    )


def _stats(trades: list[TradeResult]) -> DetectorStats:
    n = len(trades)
    if n == 0:
        return DetectorStats(detector="", n_trades=0, n_tp1=0, n_tp2=0,
                             n_sl=0, n_expire=0, win_rate=0, pf=0,
                             avg_pnl=0, total_pnl=0, median_hold_bars=0)
    n_tp1 = sum(1 for t in trades if t.outcome == "TP1")
    n_tp2 = sum(1 for t in trades if t.outcome == "TP2")
    n_sl = sum(1 for t in trades if t.outcome == "SL")
    n_expire = sum(1 for t in trades if t.outcome == "EXPIRE")
    pnls = np.array([t.pnl_usd for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    holds = np.array([t.bars_held for t in trades])
    return DetectorStats(
        detector=trades[0].detector,
        n_trades=n, n_tp1=n_tp1, n_tp2=n_tp2, n_sl=n_sl, n_expire=n_expire,
        win_rate=round((n_tp1 + n_tp2) / n * 100, 1),
        pf=round(pf, 2), avg_pnl=round(float(pnls.mean()), 2),
        total_pnl=round(float(pnls.sum()), 2),
        median_hold_bars=round(float(np.median(holds)), 1),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detectors", nargs="*", default=None,
                    help="Limit to specific detector names")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--freq-bars", type=int, default=DETECTION_FREQ_BARS,
                    help="Run detectors every N bars (default 60 = hourly)")
    args = ap.parse_args()

    # Load detectors
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    NON_TRADE = {
        "detect_grid_raise_boundary", "detect_grid_pause_entries",
        "detect_grid_booster_activate", "detect_grid_adaptive_tighten",
        "detect_defensive_margin_low",
    }
    P15 = {"detect_p15_long", "detect_p15_short"}
    detectors = [d for d in DETECTOR_REGISTRY
                 if d.__name__ not in NON_TRADE and d.__name__ not in P15]
    if args.detectors:
        detectors = [d for d in detectors if d.__name__ in args.detectors]
    print(f"[detectors] {len(detectors)} trade-emitting detectors selected")

    # Load 1m data
    print(f"[detectors] loading {DATA_1M}...")
    df = pd.read_csv(DATA_1M)
    print(f"[detectors] {len(df):,} 1m bars total")
    # Use full dataset

    print(f"[detectors] using all {len(df):,} bars (~{len(df)/60/24:.0f} days)")
    print("[detectors] building 15m + 1h aggregations...")
    df_15m, df_1h = _build_aggregations(df)
    print(f"[detectors]   15m: {len(df_15m):,}  1h: {len(df_1h):,}")

    # Walk-forward
    fold_size = len(df) // args.folds
    all_runs: list[dict] = []

    for det in detectors:
        det_name = det.__name__
        print(f"\n[detectors] === {det_name} ===")
        t0 = time.time()
        emits = _emit_setups(det, df, df_15m, df_1h, args.freq_bars)
        for e in emits:
            e["detector"] = det_name
        elapsed = time.time() - t0
        print(f"  emits: {len(emits)} (за {elapsed:.1f}s)")

        if not emits:
            print(f"  → 0 эмитов, skip")
            continue

        # Simulate trades
        trades = []
        for e in emits:
            r = _simulate_trade(e, df)
            r.detector = det_name
            trades.append(r)

        # Per-fold stats
        for k in range(args.folds):
            start_bar = k * fold_size
            end_bar = (k + 1) * fold_size if k < args.folds - 1 else len(df)
            fold_trades = [t for t in trades
                           if start_bar <= [e for e in emits if e["setup_type"] == t.setup_type and
                                            e["entry"] == t.entry][0]["bar_idx"] < end_bar]
            # Simpler: filter by entry_ts vs fold ts range
            ts_start = int(df["ts"].iloc[start_bar])
            ts_end = int(df["ts"].iloc[end_bar - 1])
            fold_trades = [t for t in trades if ts_start <= t.entry_ts <= ts_end]
            stats = _stats(fold_trades)
            all_runs.append({
                "detector": det_name, "fold": k + 1,
                "n_trades": stats.n_trades, "win_rate": stats.win_rate,
                "pf": stats.pf, "avg_pnl": stats.avg_pnl,
                "total_pnl": stats.total_pnl, "median_hold_bars": stats.median_hold_bars,
                "n_tp1": stats.n_tp1, "n_tp2": stats.n_tp2,
                "n_sl": stats.n_sl, "n_expire": stats.n_expire,
            })
            print(f"  fold {k+1}: N={stats.n_trades:>4}  WR={stats.win_rate:>5.1f}%  "
                  f"PF={stats.pf:>5.2f}  PnL=${stats.total_pnl:>+8.0f}  "
                  f"avg=${stats.avg_pnl:>+6.2f}")

        # Aggregate
        all_stats = _stats(trades)
        print(f"  TOTAL: N={all_stats.n_trades:>4}  WR={all_stats.win_rate:.1f}%  "
              f"PF={all_stats.pf:.2f}  PnL=${all_stats.total_pnl:+.0f}  "
              f"TP1/TP2/SL/EXP={all_stats.n_tp1}/{all_stats.n_tp2}/{all_stats.n_sl}/{all_stats.n_expire}")

    # Save
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if all_runs:
        df_out = pd.DataFrame(all_runs)
        df_out.to_csv(OUT_CSV, index=False)
        print(f"\n[detectors] CSV → {OUT_CSV.relative_to(ROOT)}")

    # Verdicts
    print(f"\n{'='*80}")
    print("VERDICTS (PF >= 1.5 + N >= 20 на 3+/4 folds = STABLE)")
    print(f"{'='*80}")
    if all_runs:
        df_out = pd.DataFrame(all_runs)
        verdicts: list[dict] = []
        for det_name, group in df_out.groupby("detector"):
            pos_folds = sum(1 for _, row in group.iterrows()
                            if row["pf"] >= 1.5 and row["n_trades"] >= 20)
            total_n = group["n_trades"].sum()
            total_pnl = group["total_pnl"].sum()
            avg_pf = group[group["pf"] < 99]["pf"].mean()
            if pos_folds >= 3:
                verdict = "STABLE"
            elif pos_folds >= 2:
                verdict = "MARGINAL"
            elif total_n >= 20:
                verdict = "OVERFIT"
            else:
                verdict = "TOO_FEW"
            verdicts.append({
                "detector": det_name, "total_n": total_n,
                "total_pnl": total_pnl, "avg_pf": round(avg_pf, 2) if not np.isnan(avg_pf) else 0,
                "pos_folds": pos_folds, "verdict": verdict,
            })
        verdicts.sort(key=lambda r: (r["verdict"], -r["total_pnl"]))
        for v in verdicts:
            print(f"  {v['detector']:<40} N={v['total_n']:>4} "
                  f"PF={v['avg_pf']:>5.2f} pos={v['pos_folds']}/4 "
                  f"PnL=${v['total_pnl']:>+9.0f}  → {v['verdict']}")

        # MD report
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        with OUT_MD.open("w", encoding="utf-8") as f:
            f.write("# Detectors honest backtest — 2026-05-09\n\n")
            f.write(f"**Engine:** intra-bar SL/TP simulator on 1m data\n")
            f.write(f"**Fee model:** maker rebate -0.0125% IN + taker 0.075% OUT + 0.02% slippage\n")
            f.write(f"**Period:** last {len(df):,} 1m bars (~{len(df)/60/24:.0f} days)\n")
            f.write(f"**Folds:** {args.folds} × ~{fold_size:,} bars\n\n")
            f.write("## Verdicts\n\n")
            f.write("| Detector | N total | Avg PF | Pos folds | Total PnL | Verdict |\n")
            f.write("|---|---:|---:|:---:|---:|:---:|\n")
            for v in verdicts:
                f.write(f"| `{v['detector']}` | {v['total_n']} | "
                        f"{v['avg_pf']} | {v['pos_folds']}/{args.folds} | "
                        f"${v['total_pnl']:+,.0f} | **{v['verdict']}** |\n")
            f.write("\n## Per-fold details\n\n")
            f.write("| Detector | Fold | N | WR% | PF | Total PnL | Avg PnL |\n")
            f.write("|---|:---:|---:|---:|---:|---:|---:|\n")
            for r in all_runs:
                f.write(f"| `{r['detector']}` | {r['fold']} | {r['n_trades']} | "
                        f"{r['win_rate']} | {r['pf']} | "
                        f"${r['total_pnl']:+,.0f} | ${r['avg_pnl']:+.2f} |\n")
        print(f"\n[detectors] MD → {OUT_MD.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
