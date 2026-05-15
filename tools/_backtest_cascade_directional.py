"""Cascade-followup directional backtest.

Идея: после каскада LONG-ликвидаций (продажи в стоплоссы), цена часто
отскакивает вверх — потому что long-позиции уже выбиты, давление продаж
исчезло. Trade: LONG после large cascade, hold N часов.

Аналогично SHORT: каскад SHORT-ликвидаций (откуп шортов) → цена может
продолжать вниз (sell-pressure высокое).

Период: 2024-02-12 → 2024-06-02 (~4 мес, in-sample)
Liq data: data/historical/bybit_liquidations_2024.parquet (30k events)
Price data: backtests/frozen/BTCUSDT_1m_2y.csv

Sweep:
- threshold_btc: [2, 3, 5, 7, 10] (размер каскада)
- window_min: [3, 5, 10]
- hold_hrs: [4, 8, 12, 24]
- sl_pct: [0.5, 1.0, 1.5, 2.0]
- tp_pct: [0.5, 1.0, 1.5, 2.0, off]
- side: [long_on_long_casc, long_on_short_casc, short_on_long_casc, short_on_short_casc]

Total: 5×3×4×4×5×4 = 4800 combos. Walk-forward 4 folds.

Output: state/cascade_directional_results.csv
Запуск: python tools/_backtest_cascade_directional.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICE_CSV = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
LIQ_PARQUET = ROOT / "data" / "historical" / "bybit_liquidations_2024.parquet"
OUT_CSV = ROOT / "state" / "cascade_directional_results.csv"

FEE_RT_PCT = 0.17  # round-trip including slippage
SIZE_USD = 1000.0
N_FOLDS = 4


def load_price() -> pd.DataFrame:
    print(f"Loading {PRICE_CSV}...", file=sys.stderr)
    df = pd.read_csv(PRICE_CSV)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    print(f"  loaded {len(df):,} 1m bars from {df.index[0]} to {df.index[-1]}", file=sys.stderr)
    return df


def load_liquidations() -> pd.DataFrame:
    print(f"Loading {LIQ_PARQUET}...", file=sys.stderr)
    df = pd.read_parquet(LIQ_PARQUET)
    # Bybit `side` = "Buy" means buy-side liq = LIQUIDATED SHORT (forced buy to close)
    # `side` = "Sell" means sell-side liq = LIQUIDATED LONG
    # Normalize: liq_side = position that got liquidated
    df["liq_side"] = df["side"].apply(lambda x: "long" if x == "Sell" else "short")
    df = df.set_index("ts").sort_index()
    print(f"  loaded {len(df):,} liquidation events", file=sys.stderr)
    print(f"  LONG liq events: {(df['liq_side']=='long').sum()}", file=sys.stderr)
    print(f"  SHORT liq events: {(df['liq_side']=='short').sum()}", file=sys.stderr)
    return df


def detect_cascades(liq_df: pd.DataFrame, *, threshold_btc: float,
                    window_min: int) -> list[tuple[pd.Timestamp, str, float]]:
    """Sliding window — find moments where sum(qty) on one side exceeds threshold.

    Returns list of (ts, side, total_qty). De-duplicates: 30min cooldown per side.
    """
    cascades = []
    last_per_side: dict[str, pd.Timestamp] = {}
    window = pd.Timedelta(minutes=window_min)

    # Group by 1-min bucket first для скорости
    liq_df = liq_df.copy()
    liq_df["bucket"] = liq_df.index.floor("1min")

    # Per side resample
    for side in ("long", "short"):
        side_df = liq_df[liq_df["liq_side"] == side]
        if side_df.empty:
            continue
        # Sum qty per minute
        per_min = side_df.groupby("bucket")["qty"].sum().sort_index()
        # Sliding sum over window_min minutes
        rolling = per_min.rolling(f"{window_min}min").sum()
        for ts, total in rolling.items():
            if total >= threshold_btc:
                prev = last_per_side.get(side)
                if prev is None or (ts - prev) >= pd.Timedelta(minutes=30):
                    cascades.append((ts, side, float(total)))
                    last_per_side[side] = ts
    return sorted(cascades, key=lambda x: x[0])


@dataclass
class Trade:
    entry_ts: pd.Timestamp
    side: str
    entry: float
    exit_ts: Optional[pd.Timestamp] = None
    exit: Optional[float] = None
    reason: str = ""

    @property
    def pnl_pct(self) -> float:
        if self.exit is None:
            return 0.0
        sign = 1 if self.side == "long" else -1
        return sign * (self.exit - self.entry) / self.entry * 100 - FEE_RT_PCT

    @property
    def pnl_usd(self) -> float:
        return self.pnl_pct / 100 * SIZE_USD


def simulate_trade(price_df: pd.DataFrame, entry_ts: pd.Timestamp, side: str,
                   hold_hrs: int, sl_pct: float, tp_pct: Optional[float]) -> Optional[Trade]:
    """Simulate one trade with intra-bar SL/TP check on 1m data."""
    # Find entry: first bar at or after entry_ts
    try:
        entry_idx = price_df.index.get_indexer([entry_ts], method="bfill")[0]
        if entry_idx < 0 or entry_idx >= len(price_df):
            return None
    except Exception:
        return None
    entry_row = price_df.iloc[entry_idx]
    entry = float(entry_row["close"])
    sl = entry * (1 - sl_pct/100) if side == "long" else entry * (1 + sl_pct/100)
    tp = None
    if tp_pct is not None:
        tp = entry * (1 + tp_pct/100) if side == "long" else entry * (1 - tp_pct/100)

    trade = Trade(entry_ts=entry_row.name, side=side, entry=entry)
    end_idx = min(entry_idx + hold_hrs * 60, len(price_df) - 1)

    for i in range(entry_idx + 1, end_idx + 1):
        bar = price_df.iloc[i]
        hi, lo = float(bar["high"]), float(bar["low"])
        if side == "long":
            if lo <= sl:
                trade.exit_ts = bar.name; trade.exit = sl; trade.reason = "SL"; return trade
            if tp and hi >= tp:
                trade.exit_ts = bar.name; trade.exit = tp; trade.reason = "TP"; return trade
        else:
            if hi >= sl:
                trade.exit_ts = bar.name; trade.exit = sl; trade.reason = "SL"; return trade
            if tp and lo <= tp:
                trade.exit_ts = bar.name; trade.exit = tp; trade.reason = "TP"; return trade

    last = price_df.iloc[end_idx]
    trade.exit_ts = last.name; trade.exit = float(last["close"]); trade.reason = "timeout"
    return trade


def trades_metrics(trades: list[Trade], folds_starts: list[pd.Timestamp]) -> dict:
    if not trades:
        return {"n": 0, "pnl_usd": 0, "pf": 0, "wr": 0, "avg": 0, "max_dd": 0, "pos_folds": "0/0"}
    pnls = [t.pnl_usd for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / len(pnls) * 100
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    cum = np.cumsum(pnls)
    max_dd = (np.maximum.accumulate(cum) - cum).max() if len(cum) else 0
    fold_pnls = []
    for i, fold_start in enumerate(folds_starts):
        fold_end = folds_starts[i+1] if i+1 < len(folds_starts) else trades[-1].entry_ts + pd.Timedelta(days=1)
        fp = sum(t.pnl_usd for t in trades if fold_start <= t.entry_ts < fold_end)
        fold_pnls.append(fp)
    pos_folds = sum(1 for fp in fold_pnls if fp > 0)
    return {
        "n": len(pnls), "pnl_usd": round(sum(pnls), 1),
        "pf": round(pf, 2),
        "wr": round(wr, 1), "avg": round(np.mean(pnls), 2),
        "max_dd": round(max_dd, 1),
        "pos_folds": f"{pos_folds}/{len(fold_pnls)}",
    }


# ───────────────────── Sweep ─────────────────────

def run_sweep(price_df: pd.DataFrame, liq_df: pd.DataFrame):
    # Walk-forward 4 folds на периоде liq_df
    folds_starts = pd.date_range(liq_df.index[0], liq_df.index[-1], periods=N_FOLDS+1)[:-1].tolist()
    results = []

    thresholds = [2, 3, 5, 7, 10]
    windows = [3, 5, 10]
    holds = [4, 8, 12, 24]
    sls = [0.5, 1.0, 1.5, 2.0]
    tps = [0.5, 1.0, 1.5, 2.0, None]  # None = no TP (hold to timeout)
    casc_sides = ["long", "short"]   # side of cascade
    trade_sides = ["long", "short"]  # which direction to trade

    total_combos = len(thresholds) * len(windows) * len(holds) * len(sls) * len(tps) * len(casc_sides) * len(trade_sides)
    print(f"\nRunning {total_combos} combinations...", file=sys.stderr)
    done = 0

    # Кэш: cascade detection by (threshold, window) — это дорого
    cascades_cache: dict[tuple, list] = {}
    for thr in thresholds:
        for win in windows:
            cascades_cache[(thr, win)] = detect_cascades(liq_df, threshold_btc=thr, window_min=win)
            print(f"  detected {len(cascades_cache[(thr, win)])} cascades for thr={thr}BTC win={win}min", file=sys.stderr)

    for thr in thresholds:
        for win in windows:
            cascades = cascades_cache[(thr, win)]
            for casc_side in casc_sides:
                side_cascades = [c for c in cascades if c[1] == casc_side]
                if not side_cascades:
                    continue
                for trade_side in trade_sides:
                    for hold in holds:
                        for sl in sls:
                            for tp in tps:
                                trades = []
                                for ts, _, _ in side_cascades:
                                    t = simulate_trade(price_df, ts, trade_side, hold, sl, tp)
                                    if t and t.exit is not None:
                                        trades.append(t)
                                m = trades_metrics(trades, folds_starts)
                                results.append({
                                    "casc_side": casc_side, "thr_btc": thr, "win_min": win,
                                    "trade_side": trade_side, "hold_h": hold,
                                    "sl_pct": sl, "tp_pct": tp if tp else "off",
                                    **m,
                                })
                                done += 1
                                if done % 200 == 0:
                                    print(f"  ...{done}/{total_combos}", file=sys.stderr)
    return results


def write_results(results: list[dict]):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nResults CSV: {OUT_CSV}", file=sys.stderr)
    print(f"\n=== TOP-15 BY PnL (n>=20) ===", file=sys.stderr)
    filt = df[df["n"] >= 20]
    if not filt.empty:
        top = filt.sort_values("pnl_usd", ascending=False).head(15)
        print(top.to_string(index=False), file=sys.stderr)

    print(f"\n=== TOP-15 BY PF (n>=30, pos_folds>=3/4) ===", file=sys.stderr)
    df["_pos"] = df["pos_folds"].astype(str).str.split("/").str[0].astype(int)
    df["_pf_num"] = pd.to_numeric(df["pf"], errors="coerce")
    filt = df[(df["n"] >= 30) & (df["_pos"] >= 3)]
    if not filt.empty:
        top_pf = filt.sort_values("_pf_num", ascending=False).head(15)
        print(top_pf.to_string(index=False), file=sys.stderr)
    else:
        print("(no candidates with n>=30 & pos_folds>=3/4)", file=sys.stderr)


def main():
    price_df = load_price()
    liq_df = load_liquidations()
    # Clip price to liq period (4 months)
    price_df = price_df.loc[liq_df.index[0]:liq_df.index[-1]]
    print(f"Price clipped to liq period: {len(price_df):,} 1m bars", file=sys.stderr)

    results = run_sweep(price_df, liq_df)
    write_results(results)
    print("\nDONE.", file=sys.stderr)


if __name__ == "__main__":
    main()
