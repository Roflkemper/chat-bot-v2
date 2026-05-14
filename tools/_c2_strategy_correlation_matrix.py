"""C2 — Strategy correlation matrix from setups.jsonl.

Question: which detector pairs fire **simultaneously** within the same N-minute
window? High co-firing rate = these detectors are not independent — they cover
the same regime/signal. Low co-firing = orthogonal — combining them gives true
signal confluence.

Output:
  - count matrix: how often pair (A, B) fired within ±W minutes
  - pmi matrix: log( count(A,B) / (count(A) × count(B) / total) )
  - top-3 confluence pairs by combined frequency × edge
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

SETUPS_JSONL = ROOT / "state" / "setups.jsonl"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "C2_STRATEGY_CORRELATION.md"

WINDOW_MIN = 30  # ±30min co-firing window


def main() -> int:
    print("[c2] loading setups.jsonl...")
    setups = []
    with SETUPS_JSONL.open(encoding="utf-8") as f:
        for line in f:
            try:
                setups.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"[c2] {len(setups)} setups loaded")

    df = pd.DataFrame(setups)
    df["detected_at"] = pd.to_datetime(df["detected_at"], utc=True)
    df = df.sort_values("detected_at").reset_index(drop=True)

    setup_types = sorted(df["setup_type"].dropna().unique().tolist())
    print(f"[c2] {len(setup_types)} unique setup_types")

    # Per-type counts
    counts = df["setup_type"].value_counts().to_dict()
    total = len(df)

    # Co-firing matrix
    cofire = defaultdict(int)
    for i, row in df.iterrows():
        ts = row["detected_at"]
        ty = row["setup_type"]
        nearby = df[
            (df["detected_at"] >= ts - pd.Timedelta(minutes=WINDOW_MIN)) &
            (df["detected_at"] <= ts + pd.Timedelta(minutes=WINDOW_MIN)) &
            (df.index != i)
        ]
        for _, n in nearby.iterrows():
            ny = n["setup_type"]
            if ty < ny:
                cofire[(ty, ny)] += 1
            elif ty > ny:
                cofire[(ny, ty)] += 1

    # Halve because we counted each pair twice (once per direction)
    cofire = {k: v // 2 for k, v in cofire.items()}

    print(f"[c2] {len(cofire)} pair combinations with co-firing")

    # PMI: log2( P(A,B) / (P(A) × P(B)) )
    pmi_rows = []
    for (a, b), n_ab in cofire.items():
        p_a = counts.get(a, 0) / total
        p_b = counts.get(b, 0) / total
        p_ab = n_ab / total
        if p_a > 0 and p_b > 0 and p_ab > 0:
            pmi = float(np.log2(p_ab / (p_a * p_b)))
        else:
            pmi = float("nan")
        pmi_rows.append({
            "type_a": a, "type_b": b,
            "n_a": counts.get(a, 0), "n_b": counts.get(b, 0),
            "n_cofire": n_ab,
            "p_cofire_%": round(p_ab * 100, 2),
            "expected_indep_%": round(p_a * p_b * 100, 3),
            "pmi": round(pmi, 2) if not np.isnan(pmi) else None,
        })
    pmi_df = pd.DataFrame(pmi_rows).sort_values("n_cofire", ascending=False)

    # Most-confluent pairs (high co-firing + above-random)
    independent_count = []
    for r in pmi_rows:
        independent_count.append({
            "type_a": r["type_a"], "type_b": r["type_b"],
            "n_cofire": r["n_cofire"], "pmi": r["pmi"],
        })
    indep_df = pd.DataFrame(independent_count).sort_values(
        ["n_cofire", "pmi"], ascending=[False, False]
    )

    # Write report
    md = []
    md.append(f"# C2 — Strategy correlation matrix")
    md.append("")
    md.append(f"**Source:** {SETUPS_JSONL.name} ({total} setups, "
              f"{df['detected_at'].min()} → {df['detected_at'].max()})")
    md.append(f"**Window:** ±{WINDOW_MIN} min co-firing")
    md.append(f"**Unique setup_types:** {len(setup_types)}")
    md.append("")
    md.append("## Per-type firing counts")
    md.append("")
    md.append(pd.DataFrame(
        sorted(counts.items(), key=lambda x: -x[1]), columns=["setup_type", "count"]
    ).to_markdown(index=False))
    md.append("")
    md.append("## Top co-firing pairs (sorted by n_cofire desc)")
    md.append("")
    md.append("**PMI** (Pointwise Mutual Information) > 0 means pair fires "
              "MORE than independent random; < 0 means LESS (orthogonal).")
    md.append("")
    if len(pmi_df) > 0:
        md.append(pmi_df.head(20).to_markdown(index=False))
    else:
        md.append("_no co-firing pairs found_")

    md.append("")
    md.append("## Mega-setup candidates (3-detector confluence)")
    md.append("")
    # Triple co-firing — find triples that all fired in same ±30min window
    triple_count = defaultdict(int)
    for i, row in df.iterrows():
        ts = row["detected_at"]
        nearby = df[
            (df["detected_at"] >= ts - pd.Timedelta(minutes=WINDOW_MIN)) &
            (df["detected_at"] <= ts + pd.Timedelta(minutes=WINDOW_MIN))
        ]
        types_present = nearby["setup_type"].unique().tolist()
        for triple in combinations(sorted(types_present), 3):
            triple_count[triple] += 1
    triple_df = pd.DataFrame([
        {"a": t[0], "b": t[1], "c": t[2], "n": n}
        for t, n in sorted(triple_count.items(), key=lambda x: -x[1])
    ])
    if len(triple_df) > 0:
        md.append(triple_df.head(15).to_markdown(index=False))
    else:
        md.append("_no triples found_")

    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("- **Pairs with PMI > 1** are highly correlated — likely measuring "
              "same regime. Combining them gives no extra signal.")
    md.append("- **Pairs with PMI < -1** never co-fire — true orthogonal "
              "indicators. Combining them is meaningful confluence.")
    md.append("- **Triples that fired N≥5 times** are the practical "
              "mega-setups: 3 independent signals agreeing.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[c2] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
