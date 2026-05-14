"""Stage C4 — walk-forward across all 14 detectors using historical_setups parquet.

Source data: `data/historical_setups_y1_2026-04-30.parquet` (18712 setups
with outcomes already computed). 1 year of detector emissions across all
setup_types — much faster than re-running detectors per fold.

Method:
  - Split by detected_at into N folds (default 4 × ~3 mo each)
  - For each (setup_type, fold): compute N, WR%, PF, avg PnL
  - Verdict per detector:
      STABLE   — ≥3/4 folds with PF≥1.5 AND N≥10
      MARGINAL — ≥2/4 folds with PF≥1.5
      OVERFIT  — fewer

Outcome: docs/STRATEGY_LEADERBOARD.md (sortable table per detector)
         + verdicts ready for next-session decisions on which detectors
         to disable.

Run:
  python tools/_walkfwd_historical_setups.py [--folds 4]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SETUPS_PARQUET = ROOT / "data" / "historical_setups_y1_2026-04-30.parquet"
OUT_MD = ROOT / "docs" / "STRATEGY_LEADERBOARD.md"


def _is_win(row) -> bool:
    """A setup is a 'win' if its hypothetical PnL is positive (TP partial reach
    on expiry counts; full SL hit doesn't). final_status values seen:
    'tp1_hit' (full win), 'stop_hit' (full loss), 'expired' (partial — sign of
    hypothetical_pnl_usd determines win/loss)."""
    pnl = row.get("hypothetical_pnl_usd")
    if pnl is None:
        return False
    try:
        return float(pnl) > 0
    except (TypeError, ValueError):
        return False


def _metrics(rows: pd.DataFrame) -> dict:
    n = len(rows)
    if n == 0:
        return {"N": 0, "WR": 0.0, "PF": 0.0, "avg_pnl": 0.0}
    wins = rows[rows["win"] == True]   # noqa: E712
    losses = rows[rows["win"] == False]  # noqa: E712
    pnl = pd.to_numeric(rows["hypothetical_pnl_usd"], errors="coerce").dropna()
    wr = len(wins) / n * 100
    sum_w = pnl[pnl > 0].sum()
    sum_l = -pnl[pnl < 0].sum()
    pf = float(sum_w / sum_l) if sum_l > 0 else (999.0 if sum_w > 0 else 0.0)
    return {
        "N": n,
        "WR": round(wr, 1),
        "PF": round(pf, 2),
        "avg_pnl": round(float(pnl.mean()) if not pnl.empty else 0.0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--min-n", type=int, default=10,
                    help="Min N per fold to count as 'positive PF≥1.5'")
    ap.add_argument("--min-pf", type=float, default=1.5)
    args = ap.parse_args()

    if not SETUPS_PARQUET.exists():
        print(f"ERR: {SETUPS_PARQUET} not found")
        return 1

    df = pd.read_parquet(SETUPS_PARQUET)
    df["detected_at"] = pd.to_datetime(df["detected_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["detected_at", "setup_type"]).sort_values("detected_at")
    df["win"] = df.apply(_is_win, axis=1)
    print(f"loaded {len(df)} setups across {df['setup_type'].nunique()} types")
    print(f"period: {df['detected_at'].min()} -> {df['detected_at'].max()}")

    # Split into N equal-time folds
    t_min = df["detected_at"].min()
    t_max = df["detected_at"].max()
    span = (t_max - t_min) / args.folds
    fold_edges = [t_min + span * k for k in range(args.folds + 1)]

    types = sorted(df["setup_type"].unique().tolist())
    rows: list[dict] = []
    for stype in types:
        sub = df[df["setup_type"] == stype]
        per_fold = []
        for k in range(args.folds):
            t0, t1 = fold_edges[k], fold_edges[k + 1]
            fold = sub[(sub["detected_at"] >= t0) & (sub["detected_at"] < t1)]
            m = _metrics(fold)
            m["fold"] = k + 1
            per_fold.append(m)
        positive = sum(1 for f in per_fold
                       if f["PF"] >= args.min_pf and f["N"] >= args.min_n)
        verdict = ("STABLE" if positive >= 3
                   else "MARGINAL" if positive >= 2
                   else "OVERFIT" if any(f["N"] >= args.min_n for f in per_fold)
                   else "TOO_FEW_SAMPLES")
        all_m = _metrics(sub)
        rows.append({
            "type": stype,
            "all_N": all_m["N"],
            "all_WR": all_m["WR"],
            "all_PF": all_m["PF"],
            "all_avg_pnl": all_m["avg_pnl"],
            "positive_folds": positive,
            "verdict": verdict,
            "per_fold": per_fold,
        })

    # Sort by verdict + PF
    verdict_rank = {"STABLE": 0, "MARGINAL": 1, "OVERFIT": 2, "TOO_FEW_SAMPLES": 3}
    rows.sort(key=lambda r: (verdict_rank[r["verdict"]], -r["all_PF"]))

    # Build markdown
    lines: list[str] = []
    lines.append("# Strategy Leaderboard — walk-forward verdict")
    lines.append("")
    lines.append(f"**Source:** `data/historical_setups_y1_2026-04-30.parquet` ({len(df)} setups)")
    lines.append(f"**Period:** {df['detected_at'].min().date()} → {df['detected_at'].max().date()}")
    lines.append(f"**Folds:** {args.folds} × ~{(span.days)}d each")
    lines.append(f"**Verdict thresholds:** PF≥{args.min_pf} AND N≥{args.min_n} per fold; "
                 f"≥3/4 → STABLE, ≥2/4 → MARGINAL, else OVERFIT")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Detector | All N | All WR% | All PF | Avg PnL$ | Positive folds | Verdict |")
    lines.append("|---|---:|---:|---:|---:|:---:|:---:|")
    for r in rows:
        lines.append(
            f"| `{r['type']}` | {r['all_N']} | {r['all_WR']:.1f} | "
            f"{r['all_PF']:.2f} | {r['all_avg_pnl']:+.2f} | "
            f"{r['positive_folds']}/{args.folds} | **{r['verdict']}** |"
        )
    lines.append("")

    # Per-detector fold breakdown
    lines.append("## Per-detector fold breakdown")
    lines.append("")
    for r in rows:
        lines.append(f"### `{r['type']}` — {r['verdict']}")
        lines.append("")
        lines.append("| Fold | N | WR% | PF | Avg PnL$ |")
        lines.append("|---|---:|---:|---:|---:|")
        for f in r["per_fold"]:
            pf_str = f"{f['PF']:.2f}" if f["PF"] < 999 else "inf"
            lines.append(f"| {f['fold']} | {f['N']} | {f['WR']:.1f} | "
                         f"{pf_str} | {f['avg_pnl']:+.2f} |")
        lines.append("")

    lines.append("## Verdict actions")
    lines.append("")
    overfit = [r for r in rows if r["verdict"] == "OVERFIT"]
    stable = [r for r in rows if r["verdict"] == "STABLE"]
    if overfit:
        lines.append("### OVERFIT — candidates for **disable**:")
        for r in overfit:
            lines.append(f"  - `{r['type']}` (only {r['positive_folds']}/{args.folds} "
                         f"folds positive, all-period PF={r['all_PF']:.2f})")
        lines.append("")
    if stable:
        lines.append("### STABLE — keep + monitor:")
        for r in stable:
            lines.append(f"  - `{r['type']}` (PF={r['all_PF']:.2f}, N={r['all_N']})")
        lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)} ({len(rows)} detectors evaluated)")
    print()
    print(f"  STABLE:   {len(stable)}")
    print(f"  MARGINAL: {sum(1 for r in rows if r['verdict']=='MARGINAL')}")
    print(f"  OVERFIT:  {len(overfit)}")
    print(f"  TOO_FEW:  {sum(1 for r in rows if r['verdict']=='TOO_FEW_SAMPLES')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
