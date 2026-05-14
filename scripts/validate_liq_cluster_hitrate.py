"""Retro-validation of Phase-1 liq-cluster alert на 7-дневном feed.

Method:
1. Стрим по minutes, simulate `check_and_alert` логику на каждой минуте.
2. Для каждого hypothetical fire: проверить случился ли реальный каскад (>=5 BTC)
   на той же стороне в окне +0..30 мин после fire.
3. Также true-negatives: каскады которые НЕ были предсказаны (missed).

Output:
- count alerts fired
- hit rate (fires followed by cascade within 30 min / total fires)
- miss rate (cascades not preceded by alert within 30 min before / total cascades)
- false positive rate
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"

# Same params as production
WINDOW_MIN = 5
CLUSTER_THRESHOLD = 0.3
CASCADE_SUPPRESS = 5.0
COOLDOWN_SEC = 1800
PREDICTION_WINDOW_MIN = 30  # каскад должен случиться в +0..30 после fire

CASCADE_WINDOW_MIN = 5
CASCADE_THRESHOLD = 5.0


def load_liqs() -> list[tuple[datetime, str, float]]:
    rows = []
    with LIQ_CSV.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                ts = datetime.fromisoformat(r["ts_utc"])
                side = (r["side"] or "").lower()
                qty = float(r["qty"]) if r["qty"] else 0.0
            except (ValueError, KeyError):
                continue
            if qty <= 0 or side not in ("long", "short"):
                continue
            rows.append((ts, side, qty))
    rows.sort(key=lambda x: x[0])
    return rows


def find_cascades(rows):
    """Sliding 5-min window. Returns list of (ts, side, total) — deduped via 30-min per-side cooldown."""
    cascades = []
    last_per_side: dict[str, datetime] = {}
    for i, (ts, _side, _qty) in enumerate(rows):
        window_start = ts - timedelta(minutes=CASCADE_WINDOW_MIN)
        long_t = 0.0
        short_t = 0.0
        j = i
        while j >= 0 and rows[j][0] >= window_start:
            if rows[j][1] == "long":
                long_t += rows[j][2]
            elif rows[j][1] == "short":
                short_t += rows[j][2]
            j -= 1
        for s, total in (("long", long_t), ("short", short_t)):
            if total >= CASCADE_THRESHOLD:
                prev = last_per_side.get(s)
                if prev is None or (ts - prev).total_seconds() >= 1800:
                    cascades.append((ts, s, total))
                    last_per_side[s] = ts
    return cascades


def simulate_alerts(rows):
    """Sweep timeline minute-by-minute, simulate live `check_and_alert` decisions.
    Returns list of (ts, side, qty) for each fire."""
    if not rows:
        return []
    fires = []
    last_alert_per_side: dict[str, datetime] = {}
    start = rows[0][0].replace(second=0, microsecond=0)
    end = rows[-1][0]
    # 1-min cadence (same as production poll = 60s)
    t = start
    # idx pointer
    idx = 0
    while t <= end:
        window_start = t - timedelta(minutes=WINDOW_MIN)
        long_t = 0.0
        short_t = 0.0
        # accumulate events in [window_start, t]
        # naive scan (small enough: <5k events)
        for ts, side, qty in rows:
            if ts < window_start:
                continue
            if ts > t:
                break
            if side == "long":
                long_t += qty
            elif side == "short":
                short_t += qty
        for side, qty in (("long", long_t), ("short", short_t)):
            if qty >= CASCADE_SUPPRESS:
                continue
            if qty < CLUSTER_THRESHOLD:
                continue
            last = last_alert_per_side.get(side)
            if last and (t - last).total_seconds() < COOLDOWN_SEC:
                continue
            fires.append((t, side, qty))
            last_alert_per_side[side] = t
        t += timedelta(minutes=1)
    return fires


def evaluate(fires, cascades):
    """Per-fire: was там каскад same-side в +0..30 мин? Per-cascade: был ли alert в -30..0 same-side?"""
    cascades_by_side = defaultdict(list)
    for ts, side, total in cascades:
        cascades_by_side[side].append(ts)
    fires_by_side = defaultdict(list)
    for ts, side, _qty in fires:
        fires_by_side[side].append(ts)

    # Hit rate: fires followed by cascade within +PRED_WINDOW
    hits = 0
    misses_from_fires = 0
    for ts, side, _qty in fires:
        end_w = ts + timedelta(minutes=PREDICTION_WINDOW_MIN)
        same_side_cascades = cascades_by_side.get(side, [])
        if any(ts <= c <= end_w for c in same_side_cascades):
            hits += 1
        else:
            misses_from_fires += 1

    # Cascade recall: cascades preceded by fire same-side within -PRED_WINDOW..0
    cascades_caught = 0
    cascades_missed = 0
    for ts, side, _total in cascades:
        start_w = ts - timedelta(minutes=PREDICTION_WINDOW_MIN)
        same_side_fires = fires_by_side.get(side, [])
        if any(start_w <= f <= ts for f in same_side_fires):
            cascades_caught += 1
        else:
            cascades_missed += 1

    return {
        "total_fires": len(fires),
        "hits": hits,
        "false_positives": misses_from_fires,
        "hit_rate": hits / len(fires) if fires else 0.0,
        "total_cascades": len(cascades),
        "cascades_caught": cascades_caught,
        "cascades_missed": cascades_missed,
        "recall": cascades_caught / len(cascades) if cascades else 0.0,
    }


def main():
    global CLUSTER_THRESHOLD
    rows = load_liqs()
    print(f"Loaded {len(rows)} liq events from {rows[0][0]} to {rows[-1][0]}")
    print(f"Params: window={WINDOW_MIN}m threshold={CLUSTER_THRESHOLD}BTC "
          f"cascade>=({CASCADE_THRESHOLD}BTC/{CASCADE_WINDOW_MIN}m) "
          f"pred_window=+{PREDICTION_WINDOW_MIN}m cooldown={COOLDOWN_SEC}s")
    print()

    cascades = find_cascades(rows)
    print(f"Real cascades: {len(cascades)}")
    by_side = defaultdict(int)
    for _, s, _ in cascades:
        by_side[s] += 1
    print(f"  LONG: {by_side['long']}, SHORT: {by_side['short']}")
    print()

    fires = simulate_alerts(rows)
    print(f"Hypothetical alerts fired: {len(fires)}")
    fires_by_side = defaultdict(int)
    for _, s, _ in fires:
        fires_by_side[s] += 1
    print(f"  LONG: {fires_by_side['long']}, SHORT: {fires_by_side['short']}")
    print()

    metrics = evaluate(fires, cascades)
    print("=== METRICS ===")
    print(f"Hit rate:  {metrics['hits']}/{metrics['total_fires']} = {metrics['hit_rate']*100:.1f}%")
    print(f"  (fires followed by cascade in +0..{PREDICTION_WINDOW_MIN}m same side)")
    print(f"False positives: {metrics['false_positives']}")
    print()
    print(f"Recall: {metrics['cascades_caught']}/{metrics['total_cascades']} = {metrics['recall']*100:.1f}%")
    print(f"  (cascades preceded by alert in -{PREDICTION_WINDOW_MIN}..0m same side)")
    print(f"Missed cascades: {metrics['cascades_missed']}")
    print()

    # Per-side breakdown
    for side in ("long", "short"):
        side_fires = [f for f in fires if f[1] == side]
        side_cascades = [c for c in cascades if c[1] == side]
        side_metrics = evaluate(side_fires, side_cascades)
        print(f"  [{side.upper()}] hit={side_metrics['hit_rate']*100:.0f}% "
              f"({side_metrics['hits']}/{side_metrics['total_fires']}) | "
              f"recall={side_metrics['recall']*100:.0f}% "
              f"({side_metrics['cascades_caught']}/{side_metrics['total_cascades']})")

    print()
    # Threshold sensitivity sweep
    print("=== THRESHOLD SENSITIVITY (current=0.3) ===")
    saved = CLUSTER_THRESHOLD
    for thr in (0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0):
        CLUSTER_THRESHOLD = thr
        f2 = simulate_alerts(rows)
        m2 = evaluate(f2, cascades)
        print(f"  thr={thr:.2f}BTC: fires={m2['total_fires']:3d} "
              f"hit={m2['hit_rate']*100:.0f}% recall={m2['recall']*100:.0f}% "
              f"fp={m2['false_positives']:3d}")
    CLUSTER_THRESHOLD = saved


if __name__ == "__main__":
    main()
