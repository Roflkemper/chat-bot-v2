from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BootstrapCI:
    mean: float
    ci_low: float
    ci_high: float
    n: int


def bootstrap_ci95(
    values: pd.Series,
    *,
    n_resamples: int = 5000,
    seed: int = 42,
) -> BootstrapCI:
    values = pd.to_numeric(values, errors="coerce").dropna()
    n = int(len(values))
    if n == 0:
        raise ValueError("Cannot bootstrap empty series")
    if n == 1:
        m = float(values.iloc[0])
        return BootstrapCI(mean=m, ci_low=m, ci_high=m, n=1)

    rng = np.random.default_rng(seed)
    arr = values.to_numpy(dtype=float)
    idx = rng.integers(0, n, size=(n_resamples, n))
    means = arr[idx].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return BootstrapCI(mean=float(arr.mean()), ci_low=float(low), ci_high=float(high), n=n)


def write_real_summary(
    *,
    output_path: Path,
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        f"# REAL_SUMMARY_{meta.get('date', '')}".strip("_"),
        "",
        "```json",
        json.dumps(meta, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    if not rows:
        output_path.write_text("\n".join(header + ["_no rows_"]), encoding="utf-8")
        return
    df = pd.DataFrame(rows)
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        vals = []
        for col in cols:
            v = row[col]
            if isinstance(v, float) and not math.isnan(v):
                vals.append(f"{v:.4f}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    output_path.write_text("\n".join(header + lines), encoding="utf-8")

