"""Stage E1 — Genetic detector search.

GA for finding new detector candidates by evolving over (indicator, threshold,
gate, horizon) parameter space. Fitness = walk-forward PF on BTC 1h 2y data.

Run: see docs/STAGE_E1_GENETIC_SEARCH.md

This file contains the framework — actual indicator computations are
delegated to existing tools/backtest_signals.py helpers. A full population
evaluation takes ~24h on a typical workstation; do not run during live
session — separate execution recommended.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from backtest_signals import (  # noqa: E402  type: ignore
    rsi, mfi, obv, cmf, macd_hist,
    score_signals, compute_metrics,
)


DATA_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"
DEFAULT_OUT = ROOT / "state" / "ga_results.jsonl"

INDICATORS = ("RSI", "MFI", "OBV", "CMF", "MACD")
DIRECTIONS = ("below", "above")
SIDES = ("long", "short")


@dataclass
class Genome:
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

    def serialize(self) -> dict:
        return asdict(self)


def _rand_genome(rng: random.Random) -> Genome:
    return Genome(
        primary_ind=rng.choice(INDICATORS),
        primary_threshold=round(rng.uniform(20, 80), 1),
        primary_direction=rng.choice(DIRECTIONS),
        pivot_lookback=rng.randint(3, 15),
        div_window_bars=rng.randint(10, 50),
        confluence_min=rng.randint(1, 5),
        use_ema_gate=rng.choice([True, False]),
        ema_fast=rng.randint(20, 100),
        ema_slow=rng.randint(100, 300),
        use_volume_filter=rng.choice([True, False]),
        vol_z_min=round(rng.uniform(0.5, 3.0), 2),
        sl_pct=round(rng.uniform(0.3, 1.5), 2),
        tp1_rr=round(rng.uniform(1.2, 4.0), 2),
        hold_horizon_h=rng.choice([1, 4, 12, 24, 48]),
        direction=rng.choice(SIDES),
    )


def _crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    child = {}
    for field_name in a.serialize().keys():
        child[field_name] = (rng.choice([getattr(a, field_name), getattr(b, field_name)]))
    return Genome(**child)


def _mutate(g: Genome, rate: float, rng: random.Random) -> Genome:
    if rng.random() > rate:
        return g
    field_to_mut = rng.choice(list(g.serialize().keys()))
    base = _rand_genome(rng)
    return replace(g, **{field_to_mut: getattr(base, field_to_mut)})


def _evaluate(genome: Genome, df: pd.DataFrame, n_folds: int = 4) -> dict:
    """Return fitness + metrics dict for genome on `df`. Walk-forward fold split."""
    fold_size = len(df) // n_folds
    fold_metrics: list[dict] = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else len(df)
        fold = df.iloc[start:end].reset_index(drop=True)
        fold_metrics.append(_eval_fold(genome, fold))

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


FEE_PCT_PER_SIDE = 0.05  # 0.05% taker fee per side (legacy, kept for backward compat)
# 2026-05-10: A3 honest fee model — match P15/A1 honest backtest assumptions.
# IN (limit/maker): -0.0125% rebate. OUT (market): 0.075% taker + 0.02% slip.
# Round-trip net: 0.165% vs old 0.10% = 65% more conservative.
HONEST_RT_PCT = 0.165
HONEST_FEE = bool(int(__import__("os").environ.get("GA_HONEST_FEE", "0")))
COOLDOWN_BARS = 4         # don't open another trade for N bars after a fire
SIGNAL_DEDUP_BARS = 3     # collapse consecutive signal bars to one entry


def _eval_fold(g: Genome, df: pd.DataFrame) -> dict:
    """Run one fold with realistic intra-bar SL/TP simulation.

    For each signal bar, walk forward up to `hold_horizon_h` bars checking
    each bar's high/low against SL price and TP1 price. First touched wins.
    If neither is touched, exit at horizon close. Fees applied both sides.

    Returns: {PF, N, WR, mean_pct, sharpe}.
    """
    if len(df) < 250:
        return {"PF": 0.0, "N": 0, "WR": 0.0, "mean_pct": 0.0, "sharpe": 0.0}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    if g.primary_ind == "RSI":
        ind = rsi(close, 14)
    elif g.primary_ind == "MFI":
        ind = mfi(high, low, close, volume, 14)
    elif g.primary_ind == "OBV":
        raw = obv(close, volume)
        m = raw.rolling(50, min_periods=1).mean()
        s = raw.rolling(50, min_periods=1).std().replace(0, 1.0)
        ind = ((raw - m) / s) * 50 + 50
    elif g.primary_ind == "CMF":
        ind = cmf(high, low, close, volume, 20) * 100 + 50
    else:  # MACD
        h = macd_hist(close)
        m = h.rolling(50, min_periods=1).mean()
        s = h.rolling(50, min_periods=1).std().replace(0, 1.0)
        ind = ((h - m) / s) * 50 + 50

    if g.primary_direction == "below":
        primary_signal = ind < g.primary_threshold
    else:
        primary_signal = ind > g.primary_threshold

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

    if g.use_volume_filter:
        v_mean = volume.rolling(20, min_periods=1).mean()
        v_std = volume.rolling(20, min_periods=1).std().replace(0, 1.0)
        v_z = (volume - v_mean) / v_std
        signal = signal & (v_z >= g.vol_z_min)

    # Convert to numpy for speed
    sig = signal.fillna(False).values
    close_np = close.values
    high_np = high.values
    low_np = low.values

    bars = np.where(sig)[0]
    if len(bars) == 0:
        return {"PF": 0.0, "N": 0, "WR": 0.0, "mean_pct": 0.0, "sharpe": 0.0}

    # Apply signal-dedup: collapse runs of consecutive signal bars (within
    # SIGNAL_DEDUP_BARS) to the first one — avoids 50 trades from one
    # extended condition (e.g. RSI stays >55 for 30 hours → just 1 entry).
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
    n_bars = len(close_np)

    for b in bars:
        if b < cooldown_until:
            continue
        if b + horizon >= n_bars:
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
            if j >= n_bars:
                break
            hi = float(high_np[j])
            lo = float(low_np[j])
            if g.direction == "long":
                # SL hit takes priority on the same bar (conservative)
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
            # Exit at horizon close
            exit_p = float(close_np[b + horizon])
            if g.direction == "long":
                outcome_pct = (exit_p - entry) / entry * 100
            else:
                outcome_pct = (entry - exit_p) / entry * 100

        # Apply fees. Honest mode (env GA_HONEST_FEE=1): RT 0.165% from
        # maker rebate IN + taker+slippage OUT. Default mode: 2*0.05% = 0.10%.
        if HONEST_FEE:
            outcome_pct -= HONEST_RT_PCT
        else:
            outcome_pct -= 2 * fee * 100
        pnls.append(outcome_pct)
        cooldown_until = b + max(COOLDOWN_BARS, 1)

    if not pnls:
        return {"PF": 0.0, "N": 0, "WR": 0.0, "mean_pct": 0.0, "sharpe": 0.0}

    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (999.0 if wins.sum() > 0 else 0.0)
    std = arr.std(ddof=1) if len(arr) > 1 else 1.0
    return {
        "PF": pf,
        "N": len(arr),
        "WR": float(len(wins) / len(arr) * 100),
        "mean_pct": float(arr.mean()),
        "sharpe": float(arr.mean() / std) if std > 0 else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=50)
    ap.add_argument("--generations", type=int, default=100)
    ap.add_argument("--mutation-rate", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--resume", type=Path, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    if not DATA_PATH.exists():
        print(f"ERR: {DATA_PATH} not found", file=sys.stderr)
        return 1

    print(f"[ga] loading {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH).reset_index(drop=True)
    print(f"[ga] loaded {len(df)} 1h bars")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    seen_keys: set[str] = set()
    if args.resume and args.resume.exists():
        with args.resume.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    seen_keys.add(json.dumps(rec.get("genome", {}), sort_keys=True))
                except (ValueError, TypeError):
                    continue
        print(f"[ga] resumed: {len(seen_keys)} genomes already evaluated")

    # Initial population
    population: list[Genome] = [_rand_genome(rng) for _ in range(args.population)]
    fitness_cache: dict[str, dict] = {}

    out_fh = args.output.open("a", encoding="utf-8")

    def _eval_and_log(g: Genome, gen_idx: int) -> dict:
        key = json.dumps(g.serialize(), sort_keys=True)
        if key in fitness_cache:
            return fitness_cache[key]
        if key in seen_keys:
            # Skip — already done in resumed file. Re-read on demand if needed.
            return {"fitness": 0.0, "verdict": "SKIPPED"}
        t0 = time.time()
        m = _evaluate(g, df)
        elapsed = time.time() - t0
        rec = {
            "gen": gen_idx,
            "elapsed_sec": round(elapsed, 1),
            "genome": g.serialize(),
            "metrics": m,
            "fitness": m["fitness"],
        }
        out_fh.write(json.dumps(rec) + "\n")
        out_fh.flush()
        fitness_cache[key] = m
        return m

    for gen in range(args.generations):
        # Score current population
        scores: list[tuple[float, Genome]] = []
        for g in population:
            m = _eval_and_log(g, gen)
            scores.append((m["fitness"], g))

        scores.sort(key=lambda s: -s[0])
        best = scores[0]
        print(f"[ga] gen {gen+1}/{args.generations}  best fitness={best[0]:.3f}  "
              f"verdict={fitness_cache.get(json.dumps(best[1].serialize(), sort_keys=True), {}).get('verdict')}")

        # Build next gen via tournament + crossover + mutation
        next_pop: list[Genome] = [s[1] for s in scores[:5]]  # elitism
        while len(next_pop) < args.population:
            # Tournament k=3
            tournament = rng.sample(scores, k=min(3, len(scores)))
            tournament.sort(key=lambda s: -s[0])
            parent_a = tournament[0][1]
            tournament2 = rng.sample(scores, k=min(3, len(scores)))
            tournament2.sort(key=lambda s: -s[0])
            parent_b = tournament2[0][1]
            child = _crossover(parent_a, parent_b, rng)
            child = _mutate(child, args.mutation_rate, rng)
            next_pop.append(child)
        population = next_pop

    out_fh.close()
    print(f"[ga] done. Results: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
