"""Stage E1+ — Multi-asset GA detector search (BTC + ETH + XRP).

Extends tools/_genetic_detector_search.py with cross-asset features:
  - eth_corr_30h    (BTC↔ETH 30-bar Pearson on close)
  - xrp_corr_30h    (BTC↔XRP)
  - eth_lead_signal (ETH same indicator triggered within ±2 bars)

Genome adds 3 fields:
  use_eth_corr_gate (bool) + eth_corr_min (0.0..0.95)
  use_xrp_lead      (bool) — require XRP same-direction signal in last 4 bars
  asset             ("BTC" only — primary signal source) — multi-asset
                    serves as confirmation, not standalone signal source.

Compute is ~3x base GA: each genome eval reads BTC + ETH + XRP fold data.
With dedup cache → ~50min total on 50×100 population.

Run:
  python tools/_genetic_detector_search_multi.py \
    --population 50 --generations 100 \
    --output state/ga_multi_results.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from backtest_signals import (  # noqa: E402  type: ignore
    rsi, mfi, obv, cmf, macd_hist,
)
# Re-use base eval helpers
from _genetic_detector_search import (  # noqa: E402
    Genome as BaseGenome, _crossover, _rand_genome,
    _mutate as _base_mutate,
    FEE_PCT_PER_SIDE, COOLDOWN_BARS, SIGNAL_DEDUP_BARS,
)


DATA_BTC = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"
DATA_ETH = ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv"
DATA_XRP = ROOT / "backtests" / "frozen" / "XRPUSDT_1h_2y.csv"
DEFAULT_OUT = ROOT / "state" / "ga_multi_results.jsonl"


@dataclass
class MultiGenome:
    # Inherit all base fields plus multi-asset
    primary_ind: str = "RSI"
    primary_threshold: float = 35.0
    primary_direction: str = "below"
    pivot_lookback: int = 5
    div_window_bars: int = 25
    confluence_min: int = 2
    use_ema_gate: bool = True
    ema_fast: int = 50
    ema_slow: int = 200
    use_volume_filter: bool = False
    vol_z_min: float = 1.0
    sl_pct: float = 0.8
    tp1_rr: float = 2.0
    hold_horizon_h: int = 12
    direction: str = "long"
    # Multi-asset extension
    use_eth_corr_gate: bool = False
    eth_corr_min: float = 0.7
    use_xrp_lead: bool = False

    def serialize(self) -> dict:
        return asdict(self)


def _rand_multi_genome(rng: random.Random) -> MultiGenome:
    base = _rand_genome(rng)
    return MultiGenome(
        **asdict(base),
        use_eth_corr_gate=rng.choice([True, False]),
        eth_corr_min=round(rng.uniform(0.0, 0.95), 2),
        use_xrp_lead=rng.choice([True, False]),
    )


def _mutate_multi(g: MultiGenome, rate: float, rng: random.Random) -> MultiGenome:
    if rng.random() > rate:
        return g
    field_names = list(g.serialize().keys())
    field_to_mut = rng.choice(field_names)
    base = _rand_multi_genome(rng)
    return replace(g, **{field_to_mut: getattr(base, field_to_mut)})


def _crossover_multi(a: MultiGenome, b: MultiGenome, rng: random.Random) -> MultiGenome:
    child_fields: dict = {}
    for fn in a.serialize().keys():
        child_fields[fn] = rng.choice([getattr(a, fn), getattr(b, fn)])
    return MultiGenome(**child_fields)


def _compute_indicator(df: pd.DataFrame, ind_name: str) -> pd.Series:
    close = df["close"]
    if ind_name == "RSI":
        return rsi(close, 14)
    if ind_name == "MFI":
        return mfi(df["high"], df["low"], close, df["volume"], 14)
    if ind_name == "OBV":
        raw = obv(close, df["volume"])
        m = raw.rolling(50, min_periods=1).mean()
        s = raw.rolling(50, min_periods=1).std().replace(0, 1.0)
        return ((raw - m) / s) * 50 + 50
    if ind_name == "CMF":
        return cmf(df["high"], df["low"], close, df["volume"], 20) * 100 + 50
    # MACD
    h = macd_hist(close)
    m = h.rolling(50, min_periods=1).mean()
    s = h.rolling(50, min_periods=1).std().replace(0, 1.0)
    return ((h - m) / s) * 50 + 50


def _eval_fold_multi(g: MultiGenome, df_btc: pd.DataFrame,
                      df_eth: pd.DataFrame, df_xrp: pd.DataFrame) -> dict:
    """Multi-asset fold eval: BTC primary, ETH/XRP gates."""
    if len(df_btc) < 250:
        return {"PF": 0.0, "N": 0, "WR": 0.0, "mean_pct": 0.0}

    close = df_btc["close"]
    high = df_btc["high"]
    low = df_btc["low"]

    # Primary indicator on BTC
    ind = _compute_indicator(df_btc, g.primary_ind)
    if g.primary_direction == "below":
        primary_signal = ind < g.primary_threshold
    else:
        primary_signal = ind > g.primary_threshold

    # EMA gate
    if g.use_ema_gate:
        e_fast = close.ewm(span=g.ema_fast, adjust=False).mean()
        e_slow = close.ewm(span=g.ema_slow, adjust=False).mean()
        if g.direction == "long":
            gate = (e_fast > e_slow) & (close > e_fast)
        else:
            gate = (e_fast < e_slow) & (close < e_fast)
        signal = primary_signal & gate
    else:
        signal = primary_signal

    # Volume filter
    if g.use_volume_filter:
        v_mean = df_btc["volume"].rolling(20, min_periods=1).mean()
        v_std = df_btc["volume"].rolling(20, min_periods=1).std().replace(0, 1.0)
        v_z = (df_btc["volume"] - v_mean) / v_std
        signal = signal & (v_z >= g.vol_z_min)

    # ETH correlation gate (rolling 30h Pearson)
    if g.use_eth_corr_gate and df_eth is not None and len(df_eth) >= len(df_btc):
        eth_close_aligned = df_eth["close"].iloc[: len(df_btc)].reset_index(drop=True)
        btc_close_aligned = df_btc["close"].reset_index(drop=True)
        corr = btc_close_aligned.rolling(30, min_periods=10).corr(eth_close_aligned)
        signal = signal & (corr >= g.eth_corr_min)

    # XRP lead signal: XRP shows same indicator trigger within ±2 bars
    if g.use_xrp_lead and df_xrp is not None and len(df_xrp) >= len(df_btc):
        xrp_aligned = df_xrp.iloc[: len(df_btc)].reset_index(drop=True)
        xrp_ind = _compute_indicator(xrp_aligned, g.primary_ind)
        if g.primary_direction == "below":
            xrp_signal = xrp_ind < g.primary_threshold
        else:
            xrp_signal = xrp_ind > g.primary_threshold
        # XRP signal active in last 4 bars window
        xrp_lead = xrp_signal.rolling(4, min_periods=1).max().fillna(False).astype(bool)
        signal = signal & xrp_lead.values[:len(signal)]

    sig = signal.fillna(False).values
    close_np = close.values
    high_np = high.values
    low_np = low.values

    bars = np.where(sig)[0]
    if len(bars) == 0:
        return {"PF": 0.0, "N": 0, "WR": 0.0, "mean_pct": 0.0}

    deduped: list[int] = []
    last_kept = -10**9
    for b in bars:
        if b - last_kept >= SIGNAL_DEDUP_BARS:
            deduped.append(int(b))
            last_kept = b
    bars = deduped

    horizon = g.hold_horizon_h
    sl_pct = g.sl_pct / 100.0
    tp_rr = g.tp1_rr
    fee = FEE_PCT_PER_SIDE / 100.0

    pnls: list[float] = []
    cooldown_until = -1
    n_bars_arr = len(close_np)

    for b in bars:
        if b < cooldown_until:
            continue
        if b + horizon >= n_bars_arr:
            break
        entry = float(close_np[b])
        if entry <= 0:
            continue

        if g.direction == "long":
            sl_price = entry * (1 - sl_pct)
            tp_price = entry * (1 + sl_pct * tp_rr)
        else:
            sl_price = entry * (1 + sl_pct)
            tp_price = entry * (1 - sl_pct * tp_rr)

        outcome_pct: float | None = None
        for k in range(1, horizon + 1):
            j = b + k
            if j >= n_bars_arr:
                break
            hi = float(high_np[j])
            lo = float(low_np[j])
            if g.direction == "long":
                if lo <= sl_price:
                    outcome_pct = -sl_pct * 100
                    break
                if hi >= tp_price:
                    outcome_pct = sl_pct * tp_rr * 100
                    break
            else:
                if hi >= sl_price:
                    outcome_pct = -sl_pct * 100
                    break
                if lo <= tp_price:
                    outcome_pct = sl_pct * tp_rr * 100
                    break

        if outcome_pct is None:
            exit_p = float(close_np[b + horizon])
            if g.direction == "long":
                outcome_pct = (exit_p - entry) / entry * 100
            else:
                outcome_pct = (entry - exit_p) / entry * 100

        outcome_pct -= 2 * fee * 100
        pnls.append(outcome_pct)
        cooldown_until = b + max(COOLDOWN_BARS, 1)

    if not pnls:
        return {"PF": 0.0, "N": 0, "WR": 0.0, "mean_pct": 0.0}

    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (999.0 if wins.sum() > 0 else 0.0)
    return {
        "PF": pf,
        "N": len(arr),
        "WR": float(len(wins) / len(arr) * 100),
        "mean_pct": float(arr.mean()),
    }


def _evaluate_multi(g: MultiGenome, df_btc: pd.DataFrame,
                     df_eth: pd.DataFrame, df_xrp: pd.DataFrame,
                     n_folds: int = 4) -> dict:
    fold_size = len(df_btc) // n_folds
    fold_metrics: list[dict] = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else len(df_btc)
        fold_btc = df_btc.iloc[start:end].reset_index(drop=True)
        fold_eth = df_eth.iloc[start:end].reset_index(drop=True) if df_eth is not None else None
        fold_xrp = df_xrp.iloc[start:end].reset_index(drop=True) if df_xrp is not None else None
        fold_metrics.append(_eval_fold_multi(g, fold_btc, fold_eth, fold_xrp))

    fold_pfs = [m["PF"] for m in fold_metrics]
    fold_ns = [m["N"] for m in fold_metrics]
    fold_wrs = [m["WR"] for m in fold_metrics]
    fold_means = [m["mean_pct"] for m in fold_metrics]

    avg_pf = float(np.mean([p for p in fold_pfs if p < 999])) if fold_pfs else 0.0
    avg_n = float(np.mean(fold_ns))
    avg_wr = float(np.mean(fold_wrs))
    avg_mean_pct = float(np.mean(fold_means))
    positive = sum(1 for pf, n in zip(fold_pfs, fold_ns) if pf >= 1.5 and n >= 10)
    stability = 1.0 if positive >= 3 else 0.5 if positive >= 2 else 0.0
    fitness = avg_pf * np.log(1 + avg_n) * stability

    verdict = "STABLE" if positive >= 3 else "MARGINAL" if positive >= 2 else "OVERFIT"

    return {
        "fitness": float(fitness),
        "all_period_pf": avg_pf,
        "all_period_n": int(avg_n * n_folds),
        "all_period_wr": avg_wr,
        "all_period_mean_pct": avg_mean_pct,
        "fold_metrics": [
            {"pf": m["PF"], "n": m["N"], "wr": m["WR"], "mean_pct": m["mean_pct"]}
            for m in fold_metrics
        ],
        "positive_folds": positive,
        "verdict": verdict,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=50)
    ap.add_argument("--generations", type=int, default=100)
    ap.add_argument("--mutation-rate", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    if not DATA_BTC.exists():
        print(f"ERR: {DATA_BTC} not found", file=sys.stderr)
        return 1

    print(f"[ga-multi] loading 3 datasets...")
    df_btc = pd.read_csv(DATA_BTC).reset_index(drop=True)
    df_eth = pd.read_csv(DATA_ETH).reset_index(drop=True) if DATA_ETH.exists() else None
    df_xrp = pd.read_csv(DATA_XRP).reset_index(drop=True) if DATA_XRP.exists() else None
    print(f"[ga-multi] BTC={len(df_btc)} ETH={len(df_eth) if df_eth is not None else 0} "
          f"XRP={len(df_xrp) if df_xrp is not None else 0}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    population: list[MultiGenome] = [_rand_multi_genome(rng) for _ in range(args.population)]
    fitness_cache: dict[str, dict] = {}
    out_fh = args.output.open("a", encoding="utf-8")

    def _eval_and_log(g: MultiGenome, gen_idx: int) -> dict:
        key = json.dumps(g.serialize(), sort_keys=True)
        if key in fitness_cache:
            return fitness_cache[key]
        t0 = time.time()
        m = _evaluate_multi(g, df_btc, df_eth, df_xrp)
        elapsed = time.time() - t0
        rec = {
            "gen": gen_idx,
            "elapsed_sec": round(elapsed, 2),
            "genome": g.serialize(),
            "metrics": m,
            "fitness": m["fitness"],
        }
        out_fh.write(json.dumps(rec) + "\n")
        out_fh.flush()
        fitness_cache[key] = m
        return m

    for gen in range(args.generations):
        scores: list[tuple[float, MultiGenome]] = []
        for g in population:
            m = _eval_and_log(g, gen)
            scores.append((m["fitness"], g))
        scores.sort(key=lambda s: -s[0])
        best = scores[0]
        verdict = fitness_cache.get(json.dumps(best[1].serialize(), sort_keys=True), {}).get("verdict")
        print(f"[ga-multi] gen {gen+1}/{args.generations}  best fitness={best[0]:.3f}  verdict={verdict}")

        next_pop: list[MultiGenome] = [s[1] for s in scores[:5]]
        while len(next_pop) < args.population:
            t = rng.sample(scores, k=min(3, len(scores)))
            t.sort(key=lambda s: -s[0])
            parent_a = t[0][1]
            t2 = rng.sample(scores, k=min(3, len(scores)))
            t2.sort(key=lambda s: -s[0])
            parent_b = t2[0][1]
            child = _crossover_multi(parent_a, parent_b, rng)
            child = _mutate_multi(child, args.mutation_rate, rng)
            next_pop.append(child)
        population = next_pop

    out_fh.close()
    print(f"[ga-multi] done. Results: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
