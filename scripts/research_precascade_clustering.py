"""R&D: проверить кластеризуются ли мелкие liq за 10-30 мин до каскада >=5 BTC.

Цель: ответить на вопрос — есть ли predictable signal **до** каскада?

Метод:
1. Найти все каскады (>=5 BTC за 5 мин окно) в liquidations.csv.
2. Для каждого — посчитать кумулятивные liq по 5-мин bucket'ам за -30..0 мин до каскада.
3. Сравнить с baseline (random 5-мин окна без каскада).
4. Если concentration в pre-window > baseline на 2σ — есть signal.

Запуск:
    python scripts/research_precascade_clustering.py
"""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"

CASCADE_THRESHOLD_BTC = 5.0
CASCADE_WINDOW_MIN = 5
PRE_WINDOW_MIN = 30
BUCKET_MIN = 5


def load_liqs() -> list[tuple[datetime, str, float]]:
    rows = []
    with LIQ_CSV.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                ts = datetime.fromisoformat(r["ts_utc"])
                side = r["side"].lower()
                qty = float(r["qty"]) if r["qty"] else 0.0
            except (ValueError, KeyError):
                continue
            if qty <= 0:
                continue
            rows.append((ts, side, qty))
    rows.sort(key=lambda x: x[0])
    return rows


def find_cascades(rows: list[tuple[datetime, str, float]]) -> list[tuple[datetime, str, float]]:
    """Slide 5-min window, find peaks where qty>=threshold per side."""
    cascades = []
    last_cascade_per_side: dict[str, datetime] = {}
    for i, (ts, side, _) in enumerate(rows):
        window_start = ts - timedelta(minutes=CASCADE_WINDOW_MIN)
        total_long = 0.0
        total_short = 0.0
        j = i
        while j >= 0 and rows[j][0] >= window_start:
            if rows[j][1] == "long":
                total_long += rows[j][2]
            elif rows[j][1] == "short":
                total_short += rows[j][2]
            j -= 1
        for s, total in (("long", total_long), ("short", total_short)):
            if total >= CASCADE_THRESHOLD_BTC:
                # dedup — не считать тот же каскад дважды (cooldown 30min)
                prev = last_cascade_per_side.get(s)
                if prev is None or (ts - prev).total_seconds() >= 1800:
                    cascades.append((ts, s, total))
                    last_cascade_per_side[s] = ts
    return cascades


def pre_window_buckets(rows, cascade_ts, side, *, pre_min=PRE_WINDOW_MIN, bucket_min=BUCKET_MIN):
    """Return cumulative BTC per N-min bucket in [cascade-pre_min, cascade)."""
    start = cascade_ts - timedelta(minutes=pre_min)
    end = cascade_ts
    buckets = defaultdict(float)
    for ts, s, qty in rows:
        if ts < start or ts >= end:
            continue
        if s != side:
            continue
        # bucket index 0..pre_min/bucket_min-1 (oldest..newest)
        bucket_idx = int((ts - start).total_seconds() // (bucket_min * 60))
        buckets[bucket_idx] += qty
    return [buckets[i] for i in range(pre_min // bucket_min)]


def baseline_buckets(rows, cascade_times: set, n_samples: int = 100,
                     *, pre_min=PRE_WINDOW_MIN, bucket_min=BUCKET_MIN):
    """Sample random non-cascade windows."""
    import random
    if not rows:
        return []
    random.seed(42)
    start_ts = rows[0][0]
    end_ts = rows[-1][0]
    span = (end_ts - start_ts).total_seconds()
    samples_buckets = {s: [] for s in ("long", "short")}
    tries = 0
    while sum(len(v) for v in samples_buckets.values()) < n_samples * 2 and tries < n_samples * 20:
        tries += 1
        off = random.random() * span
        sample_ts = start_ts + timedelta(seconds=off)
        # skip if within pre_min of any real cascade
        too_close = any(abs((sample_ts - ct).total_seconds()) < pre_min * 60 for ct in cascade_times)
        if too_close:
            continue
        for s in ("long", "short"):
            samples_buckets[s].append(pre_window_buckets(rows, sample_ts, s,
                                                        pre_min=pre_min, bucket_min=bucket_min))
    return samples_buckets


def stat(name, values):
    if not values:
        return f"{name}: no data"
    if len(values) < 2:
        return f"{name}: n={len(values)} mean={values[0]:.3f}"
    return f"{name}: n={len(values)} mean={statistics.mean(values):.3f} sd={statistics.pstdev(values):.3f} max={max(values):.3f}"


def main():
    rows = load_liqs()
    print(f"Loaded {len(rows)} liquidations from {rows[0][0]} to {rows[-1][0]}")
    cascades = find_cascades(rows)
    print(f"Found {len(cascades)} cascades >= {CASCADE_THRESHOLD_BTC} BTC")
    for ts, s, total in cascades[:10]:
        print(f"  {ts} {s} {total:.2f} BTC")
    if len(cascades) > 10:
        print(f"  ... and {len(cascades)-10} more")
    print()

    if not cascades:
        print("No cascades found — cannot do pre-window analysis.")
        return

    # Per-side pre-window analysis
    cascade_times = set(c[0] for c in cascades)
    baseline = baseline_buckets(rows, cascade_times, n_samples=100)

    for side in ("long", "short"):
        side_cascades = [c for c in cascades if c[1] == side]
        if not side_cascades:
            continue
        print(f"=== {side.upper()} cascades (n={len(side_cascades)}) ===")
        pre = [pre_window_buckets(rows, ts, side) for ts, _, _ in side_cascades]
        bl = baseline.get(side, [])
        n_buckets = PRE_WINDOW_MIN // BUCKET_MIN
        for b in range(n_buckets):
            pre_vals = [p[b] for p in pre]
            bl_vals = [b_[b] for b_ in bl] if bl else []
            label = f"  bucket {-PRE_WINDOW_MIN + b*BUCKET_MIN}..{-PRE_WINDOW_MIN + (b+1)*BUCKET_MIN} min"
            print(f"{label}")
            print(f"    {stat('pre', pre_vals)}")
            print(f"    {stat('bl ', bl_vals)}")
            if bl_vals and len(bl_vals) >= 2 and pre_vals:
                bl_mean = statistics.mean(bl_vals)
                bl_sd = statistics.pstdev(bl_vals) or 1e-9
                pre_mean = statistics.mean(pre_vals)
                z = (pre_mean - bl_mean) / bl_sd
                print(f"    z-score: {z:.2f}{'  *** SIGNAL' if abs(z) > 2 else ''}")
        print()


if __name__ == "__main__":
    main()
