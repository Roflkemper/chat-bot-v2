"""Compute regime time-spent + episode + transition stats on 1y BTC."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "forecast_features" / "full_features_1y.parquet"

REGIME_NAMES = {1: "MARKUP", -1: "MARKDOWN", 0: "RANGE"}


def main() -> int:
    df = pd.read_parquet(FEATURES, columns=["close", "regime_int"])
    # Resample to 1h: regime label = mode of underlying 5m
    df_1h = df.resample("1h").agg({
        "close": "last",
        "regime_int": lambda x: int(x.mode()[0]) if len(x) > 0 else 0,
    }).dropna()

    n_total = len(df_1h)
    out = {
        "window_start": str(df_1h.index[0]),
        "window_end": str(df_1h.index[-1]),
        "n_hours_total": n_total,
    }

    # Time spent per regime
    counts = df_1h["regime_int"].value_counts().to_dict()
    time_spent = {}
    for k, name in REGIME_NAMES.items():
        h = int(counts.get(k, 0))
        time_spent[name] = {
            "hours": h, "pct": round(h / n_total * 100, 2),
        }
    out["time_spent_per_regime"] = time_spent

    # Episodes: contiguous runs of same label
    labels = df_1h["regime_int"].values
    timestamps = df_1h.index
    episodes_by_regime: dict[str, list[int]] = {n: [] for n in REGIME_NAMES.values()}
    transitions: dict[str, int] = {}
    transitions_with_hour: list[tuple[str, str, int]] = []

    cur_label = labels[0]
    cur_len = 1
    for i in range(1, len(labels)):
        if labels[i] == cur_label:
            cur_len += 1
        else:
            episodes_by_regime[REGIME_NAMES[int(cur_label)]].append(cur_len)
            from_name = REGIME_NAMES[int(cur_label)]
            to_name = REGIME_NAMES[int(labels[i])]
            key = f"{from_name}->{to_name}"
            transitions[key] = transitions.get(key, 0) + 1
            transitions_with_hour.append((from_name, to_name, timestamps[i].hour))
            cur_label = labels[i]
            cur_len = 1
    episodes_by_regime[REGIME_NAMES[int(cur_label)]].append(cur_len)

    # Episode duration distribution per regime
    episode_stats = {}
    for name, durations in episodes_by_regime.items():
        if not durations:
            episode_stats[name] = {"count": 0}
            continue
        arr = np.array(durations)
        episode_stats[name] = {
            "count": int(len(arr)),
            "mean_h": round(float(arr.mean()), 1),
            "median_h": int(np.median(arr)),
            "p25_h": int(np.percentile(arr, 25)),
            "p75_h": int(np.percentile(arr, 75)),
            "p90_h": int(np.percentile(arr, 90)),
            "max_h": int(arr.max()),
        }
    out["episodes"] = episode_stats

    # Transition matrix
    out["transitions"] = transitions

    # Time-of-day analysis
    hour_buckets = Counter([h for _, _, h in transitions_with_hour])
    out["transitions_by_hour_utc"] = dict(sorted(hour_buckets.items()))

    # Per-month breakdown
    df_1h["month"] = df_1h.index.strftime("%Y-%m")
    by_month = {}
    for month, sub in df_1h.groupby("month"):
        n_m = len(sub)
        c = sub["regime_int"].value_counts().to_dict()
        by_month[month] = {
            REGIME_NAMES[k]: round(int(c.get(k, 0)) / n_m * 100, 1)
            for k in REGIME_NAMES
        }
    out["per_month_pct"] = by_month

    json_out = json.dumps(out, ensure_ascii=False, indent=2)
    Path("docs/RESEARCH").mkdir(parents=True, exist_ok=True)
    Path("docs/RESEARCH/_regime_periods_raw.json").write_text(json_out, encoding="utf-8")
    sys.stdout.buffer.write((json_out + "\n").encode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
