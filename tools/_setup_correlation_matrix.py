"""Stage C2 — Strategy correlation matrix.

For each pair (setup_type_A, setup_type_B), find how often they fire within
±N minutes of each other (default N=60min, configurable).

Output:
  1. Co-fire counts matrix (NxN)
  2. Top-K confluences ranked by:
       - co-fire frequency (>=K_MIN co-fires)
       - WR boost vs baseline (when both fire, WR vs each alone)
  3. Markdown report → docs/STRATEGY_CONFLUENCE_MATRIX.md

Run:
  python tools/_setup_correlation_matrix.py [--window-min 60] [--k-min 5]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SETUPS_PARQUET = ROOT / "data" / "historical_setups_y1_2026-04-30.parquet"
OUT_MD = ROOT / "docs" / "STRATEGY_CONFLUENCE_MATRIX.md"


def _is_win(row) -> bool:
    """Setup considered 'win' if hypothetical_pnl_usd > 0 OR final_status in TP set."""
    status = str(row.get("final_status") or "").lower()
    if status in ("tp1", "tp2"):
        return True
    pnl = row.get("hypothetical_pnl_usd")
    return bool(pnl is not None and float(pnl) > 0)


def _bucket(ts: pd.Timestamp, bucket_min: int) -> int:
    """Round to nearest bucket_min minutes (epoch-based)."""
    epoch_min = int(ts.timestamp()) // (bucket_min * 60)
    return epoch_min


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-min", type=int, default=60,
                    help="Minutes within which two setups count as co-firing")
    ap.add_argument("--k-min", type=int, default=5,
                    help="Min co-fire count to report a pair")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    if not SETUPS_PARQUET.exists():
        print(f"ERR: {SETUPS_PARQUET} not found")
        return 1

    df = pd.read_parquet(SETUPS_PARQUET)
    print(f"loaded {len(df)} historical setups")
    df["detected_at"] = pd.to_datetime(df["detected_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["detected_at", "setup_type"])
    df["bucket"] = df["detected_at"].apply(lambda t: _bucket(t, args.window_min))
    df["win"] = df.apply(_is_win, axis=1)

    # Per-type baseline stats
    baseline: dict[str, dict] = {}
    for stype, sub in df.groupby("setup_type"):
        n = len(sub)
        wins = int(sub["win"].sum())
        baseline[stype] = {
            "n": n,
            "wr_pct": (wins / n * 100) if n else 0.0,
            "avg_pnl": float(sub["hypothetical_pnl_usd"].mean()) if n else 0.0,
        }

    # Group by bucket → for each bucket, list of (setup_type, win, pnl)
    co_fire_count: dict[tuple[str, str], int] = defaultdict(int)
    co_fire_wins: dict[tuple[str, str], int] = defaultdict(int)
    co_fire_pnl_sum: dict[tuple[str, str], float] = defaultdict(float)

    for bucket, sub in df.groupby("bucket"):
        if len(sub) < 2:
            continue
        types_in_bucket = sub["setup_type"].unique().tolist()
        if len(types_in_bucket) < 2:
            continue
        # For each unordered pair within the bucket
        for a, b in combinations(sorted(types_in_bucket), 2):
            key = (a, b)
            co_fire_count[key] += 1
            # Win = both setups in bucket are wins (intersection)
            sub_a = sub[sub["setup_type"] == a]
            sub_b = sub[sub["setup_type"] == b]
            both_win = bool(sub_a["win"].any() and sub_b["win"].any())
            if both_win:
                co_fire_wins[key] += 1
            # PnL = average of both legs PnL within bucket
            pnl = float(sub_a["hypothetical_pnl_usd"].mean()
                        + sub_b["hypothetical_pnl_usd"].mean())
            co_fire_pnl_sum[key] += pnl

    # Build ranked rows
    rows: list[dict] = []
    for (a, b), n_co in co_fire_count.items():
        if n_co < args.k_min:
            continue
        wr_co = co_fire_wins[(a, b)] / n_co * 100
        wr_a_alone = baseline[a]["wr_pct"]
        wr_b_alone = baseline[b]["wr_pct"]
        # "Boost" = how much WR(A & B together) exceeds the higher of WR(A), WR(B)
        boost = wr_co - max(wr_a_alone, wr_b_alone)
        rows.append({
            "type_a": a,
            "type_b": b,
            "n_co_fire": n_co,
            "wr_co_pct": round(wr_co, 1),
            "wr_a_alone_pct": round(wr_a_alone, 1),
            "wr_b_alone_pct": round(wr_b_alone, 1),
            "boost_pct_pts": round(boost, 1),
            "avg_pnl_co": round(co_fire_pnl_sum[(a, b)] / n_co, 2),
            "n_a": baseline[a]["n"],
            "n_b": baseline[b]["n"],
        })

    rows.sort(key=lambda r: (-r["boost_pct_pts"], -r["n_co_fire"]))

    # Build report
    lines: list[str] = []
    lines.append(f"# Strategy Confluence Matrix")
    lines.append(f"")
    lines.append(f"**Source:** `data/historical_setups_y1_2026-04-30.parquet` ({len(df)} setups)")
    lines.append(f"**Bucket:** {args.window_min} min")
    lines.append(f"**Min co-fires to report:** {args.k_min}")
    lines.append(f"")
    lines.append(f"## Top {args.top} confluence pairs by WR boost")
    lines.append(f"")
    lines.append("| # | Type A | Type B | N co-fire | WR(co) | WR(A alone) | WR(B alone) | Boost (pp) | Avg PnL$ |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for i, r in enumerate(rows[:args.top], 1):
        lines.append(
            f"| {i} | {r['type_a']} | {r['type_b']} | {r['n_co_fire']} | "
            f"{r['wr_co_pct']:.1f}% | {r['wr_a_alone_pct']:.1f}% | "
            f"{r['wr_b_alone_pct']:.1f}% | {r['boost_pct_pts']:+.1f} | "
            f"{r['avg_pnl_co']:+.2f} |"
        )
    lines.append(f"")
    lines.append(f"## Per-type baseline")
    lines.append(f"")
    lines.append("| Type | N | WR% | Avg PnL$ |")
    lines.append("|---|---:|---:|---:|")
    for stype, b in sorted(baseline.items(), key=lambda kv: -kv[1]["n"]):
        lines.append(f"| {stype} | {b['n']} | {b['wr_pct']:.1f} | {b['avg_pnl']:+.2f} |")
    lines.append("")
    lines.append("## Reading the boost column")
    lines.append("")
    lines.append("`Boost (pp)` = `WR(co)` − `max(WR(A alone), WR(B alone))`. Positive ")
    lines.append("means the pair confirms each other; firing together has a higher win-rate ")
    lines.append("than the better leg alone. Boost ≥ +10 pp with N ≥ 20 → mega-setup candidate.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)} ({len(rows)} pairs ranked, top {args.top} shown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
