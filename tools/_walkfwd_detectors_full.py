"""Stage C4 — full walk-forward through DetectionContext for all detectors.

KNOWN LIMITATION (2026-05-09): with 1m data loaded for the full 2y window
(1.17M bars × ts-filtered slice per fold-bar), this can OOM on memory-
limited machines for full 18-detector × 4-fold runs. Workarounds:
  - Run with fewer detectors at a time: --detectors d1 d2 d3
  - Reduce 1m lookback in _build_ctx_at_bar (currently 120 bars)
  - Use --folds 1 first to validate which detectors work
Next-session improvement: pre-compute ts_to_index lookup, swap pandas
slicing for numpy indexing.


Direct walk-forward (not via parquet of past emits): drives BTC 1h 2y bars
through DetectorContext, calls each detector at each bar, collects emits,
scores forward returns at horizons {1h, 4h, 12h, 24h}.

Coverage:
  - 18 trade-emitting detectors from DETECTOR_REGISTRY
  - grid_*/defensive_* skipped (they emit operational actions, not trades)

Per detector × per fold × per horizon:
  N, WR%, PF, mean_pct, sharpe (after 2 × 0.05% fee)

Verdict per detector:
  STABLE   — best horizon's PF >= 1.5 with N >= 10 in >=3/4 folds
  MARGINAL — same in >=2/4 folds
  OVERFIT  — fewer

Output: docs/STRATEGY_LEADERBOARD_FULL.md

Run:
  python tools/_walkfwd_detectors_full.py [--folds 4]

Compute: ~30 min — 24 detectors × 4 folds × ~4400 bars/fold × O(detect call).
Most detectors short-circuit early on guards, so realistic average is
~5 ms/bar/detector. Total ~24×4×4400×0.005 = 2100s ≈ 35 min.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.setup_detector.setup_types import DETECTOR_REGISTRY  # noqa: E402
from services.setup_detector.models import Setup  # noqa: E402

DATA_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"
DATA_15M = ROOT / "backtests" / "frozen" / "BTCUSDT_15m_2y.csv"
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_MD = ROOT / "docs" / "STRATEGY_LEADERBOARD_FULL.md"

FEE_PCT_PER_SIDE = 0.05
HORIZONS = (1, 4, 12, 24)
WARMUP_BARS = 250

# Detectors that emit non-trade events (grid actions, defensive margin alerts)
NON_TRADE_DETECTORS = {
    "detect_grid_raise_boundary",
    "detect_grid_pause_entries",
    "detect_grid_booster_activate",
    "detect_grid_adaptive_tighten",
    "detect_defensive_margin_low",
}

# P-15 detectors are stateful (multi-stage lifecycle, persists state) and
# the first emit comes only after warmup; treat separately or skip from
# vanilla walk-forward (their backtest already lives in
# tools/_backtest_p15_*.py with proper state simulation).
STATEFUL_DETECTORS = {
    "detect_p15_long",
    "detect_p15_short",
}


@dataclasses.dataclass
class _Ctx:
    """Minimal stub of DetectionContext sufficient for most detectors.

    Real DetectionContext is from services.setup_detector.setup_types:
    we mimic its shape with the fields detectors actually read.
    """
    pair: str
    current_price: float
    regime_label: str
    session_label: str
    ohlcv_1m: pd.DataFrame
    ohlcv_1h: pd.DataFrame
    ohlcv_15m: pd.DataFrame
    portfolio: object = None
    ict_context: dict = dataclasses.field(default_factory=dict)


def _build_ctx_at_bar(df_1h: pd.DataFrame, df_15m: pd.DataFrame,
                     df_1m: pd.DataFrame,
                     bar_idx: int, regime_label: str = "range_wide") -> _Ctx:
    """Construct a DetectionContext as it would look at `bar_idx` of 1h frame.
    Cuts all frames to data up to and including bar_idx (no lookahead)."""
    sub_1h = df_1h.iloc[: bar_idx + 1].reset_index(drop=True)
    target_ts = df_1h.iloc[bar_idx]["ts"] if "ts" in df_1h.columns else None
    if target_ts is not None and len(df_15m) and "ts" in df_15m.columns:
        sub_15m = df_15m[df_15m["ts"] <= target_ts].iloc[-300:].reset_index(drop=True)
    else:
        end = min(len(df_15m), bar_idx * 4)
        sub_15m = df_15m.iloc[max(0, end - 300): end].reset_index(drop=True)

    if target_ts is not None and len(df_1m) and "ts" in df_1m.columns:
        # 1m frames are large; take only last 120 bars relative to bar's ts
        sub_1m = df_1m[df_1m["ts"] <= target_ts].iloc[-120:].reset_index(drop=True)
    else:
        end = min(len(df_1m), bar_idx * 60)
        sub_1m = df_1m.iloc[max(0, end - 120): end].reset_index(drop=True)

    return _Ctx(
        pair="BTCUSDT",
        current_price=float(df_1h.iloc[bar_idx]["close"]),
        regime_label=regime_label,
        session_label="ny_am",
        ohlcv_1m=sub_1m,
        ohlcv_1h=sub_1h,
        ohlcv_15m=sub_15m,
        ict_context={},
    )


def _score_setup(setup: Setup, fold_df: pd.DataFrame, fire_idx: int,
                 horizons: tuple[int, ...]) -> dict[int, float]:
    """Score a setup across each horizon: realised return % at horizon (after
    fees). Honors SL/TP if setup has them; otherwise just close-to-close.
    """
    out: dict[int, float] = {}
    if setup.entry_price is None or setup.entry_price <= 0:
        for h in horizons:
            out[h] = 0.0
        return out

    direction_long = "long" in setup.setup_type.value or "bullish" in setup.setup_type.value
    entry = float(setup.entry_price)
    sl = float(setup.stop_price) if setup.stop_price else None
    tp1 = float(setup.tp1_price) if setup.tp1_price else None

    fee = FEE_PCT_PER_SIDE / 100.0

    for h in horizons:
        outcome_pct: float | None = None
        for k in range(1, h + 1):
            j = fire_idx + k
            if j >= len(fold_df):
                break
            hi = float(fold_df.iloc[j]["high"])
            lo = float(fold_df.iloc[j]["low"])
            if direction_long:
                if sl is not None and lo <= sl:
                    outcome_pct = (sl - entry) / entry * 100
                    break
                if tp1 is not None and hi >= tp1:
                    outcome_pct = (tp1 - entry) / entry * 100
                    break
            else:
                if sl is not None and hi >= sl:
                    outcome_pct = (sl - entry) / entry * 100
                    break
                if tp1 is not None and lo <= tp1:
                    outcome_pct = (tp1 - entry) / entry * 100
                    break

        if outcome_pct is None:
            j = min(fire_idx + h, len(fold_df) - 1)
            exit_p = float(fold_df.iloc[j]["close"])
            if direction_long:
                outcome_pct = (exit_p - entry) / entry * 100
            else:
                outcome_pct = (entry - exit_p) / entry * 100

        outcome_pct -= 2 * fee * 100
        out[h] = outcome_pct

    return out


def _metrics(returns: list[float]) -> dict:
    if not returns:
        return {"N": 0, "WR": 0.0, "PF": 0.0, "mean_pct": 0.0}
    arr = np.array(returns)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (999.0 if wins.sum() > 0 else 0.0)
    return {
        "N": len(arr),
        "WR": round(float((arr > 0).mean() * 100), 1),
        "PF": round(min(pf, 99.9), 2),
        "mean_pct": round(float(arr.mean()), 3),
    }


def _run_fold(detectors: list, fold_1h: pd.DataFrame, fold_15m: pd.DataFrame,
              fold_1m: pd.DataFrame, fold_label: str) -> dict[str, dict[int, dict]]:
    """For each detector × horizon, return metrics on this fold.

    Returns: {detector_name: {horizon: {N, WR, PF, mean_pct}}}
    """
    # detector_name -> horizon -> list of returns
    returns: dict[str, dict[int, list[float]]] = {
        d.__name__: {h: [] for h in HORIZONS} for d in detectors
    }
    n_bars = len(fold_1h)

    # Walk forward through fold
    last_progress = -1
    t_start = time.time()
    for bar_idx in range(WARMUP_BARS, n_bars - max(HORIZONS)):
        if bar_idx - WARMUP_BARS > 0 and (bar_idx - WARMUP_BARS) % 1000 == 0:
            elapsed = time.time() - t_start
            pct = (bar_idx - WARMUP_BARS) / (n_bars - WARMUP_BARS) * 100
            if int(pct) // 10 != last_progress:
                last_progress = int(pct) // 10
                print(f"    {fold_label}: bar {bar_idx}/{n_bars}  ({pct:.0f}%, {elapsed:.0f}s)")
        ctx = _build_ctx_at_bar(fold_1h, fold_15m, fold_1m, bar_idx)
        for det in detectors:
            try:
                setup = det(ctx)
            except Exception:
                continue
            if setup is None:
                continue
            scored = _score_setup(setup, fold_1h, bar_idx, HORIZONS)
            for h, pct in scored.items():
                returns[det.__name__][h].append(pct)

    # Aggregate
    out: dict[str, dict[int, dict]] = {}
    for name, by_h in returns.items():
        out[name] = {h: _metrics(by_h[h]) for h in HORIZONS}
    return out


def _verdict_for(per_fold_metrics: list[dict[int, dict]],
                 min_pf: float = 1.5, min_n: int = 10) -> tuple[str, int, dict]:
    """For a single detector across folds: pick best horizon (max avg PF
    across folds), count positive folds in that horizon, verdict."""
    best_h = HORIZONS[0]
    best_avg_pf = -1.0
    for h in HORIZONS:
        pfs = [pf["PF"] for pf in (m[h] for m in per_fold_metrics)]
        avg = float(np.mean([p for p in pfs if p < 99]))
        if avg > best_avg_pf:
            best_avg_pf = avg
            best_h = h

    pos = 0
    for fold in per_fold_metrics:
        m = fold[best_h]
        if m["PF"] >= min_pf and m["N"] >= min_n:
            pos += 1

    verdict = "STABLE" if pos >= 3 else "MARGINAL" if pos >= 2 else (
        "OVERFIT" if any(fold[best_h]["N"] >= min_n for fold in per_fold_metrics)
        else "TOO_FEW"
    )
    return verdict, pos, {"best_horizon": best_h, "avg_pf_at_best_h": round(best_avg_pf, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--detectors", nargs="*", default=None,
                    help="Optionally limit to specific detector names (debug)")
    args = ap.parse_args()

    if not DATA_1H.exists():
        print(f"ERR: {DATA_1H} not found")
        return 1

    print(f"[walkfwd] loading {DATA_1H}...")
    df_1h = pd.read_csv(DATA_1H).reset_index(drop=True)
    df_15m = pd.read_csv(DATA_15M).reset_index(drop=True) if DATA_15M.exists() else pd.DataFrame()
    df_1m = pd.read_csv(DATA_1M).reset_index(drop=True) if DATA_1M.exists() else pd.DataFrame()
    print(f"[walkfwd] loaded 1h: {len(df_1h)} bars  15m: {len(df_15m)} bars  1m: {len(df_1m)} bars")

    # Filter to trade-emitting detectors only
    detectors = [d for d in DETECTOR_REGISTRY
                 if d.__name__ not in NON_TRADE_DETECTORS
                 and d.__name__ not in STATEFUL_DETECTORS]
    if args.detectors:
        detectors = [d for d in detectors if d.__name__ in args.detectors]
    print(f"[walkfwd] running {len(detectors)} detectors")

    # Split into N folds
    fold_size = len(df_1h) // args.folds
    fold_results: list[dict[str, dict[int, dict]]] = []
    for k in range(args.folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < args.folds - 1 else len(df_1h)
        fold_1h = df_1h.iloc[start:end].reset_index(drop=True)
        # Match 15m + 1m folds by ts range
        if "ts" in fold_1h.columns and len(df_15m) and "ts" in df_15m.columns:
            t0, t1 = fold_1h["ts"].iloc[0], fold_1h["ts"].iloc[-1]
            fold_15m = df_15m[(df_15m["ts"] >= t0) & (df_15m["ts"] <= t1)].reset_index(drop=True)
        else:
            fold_15m = df_15m
        if "ts" in fold_1h.columns and len(df_1m) and "ts" in df_1m.columns:
            t0, t1 = fold_1h["ts"].iloc[0], fold_1h["ts"].iloc[-1]
            fold_1m = df_1m[(df_1m["ts"] >= t0) & (df_1m["ts"] <= t1)].reset_index(drop=True)
        else:
            fold_1m = df_1m
        print(f"[walkfwd] fold {k+1}/{args.folds}: {len(fold_1h)} 1h bars, {len(fold_1m)} 1m bars")
        fold_results.append(_run_fold(detectors, fold_1h, fold_15m, fold_1m, f"fold{k+1}"))

    # Build report
    print(f"[walkfwd] writing {OUT_MD}")
    lines = ["# Strategy Leaderboard — full walk-forward (DetectionContext)",
             ""]
    lines.append(f"**Source:** {DATA_1H.name}, {len(df_1h)} 1h bars over 2y")
    lines.append(f"**Folds:** {args.folds} × ~{fold_size}h each  "
                 f"**Horizons:** {HORIZONS}h  **Fee:** {FEE_PCT_PER_SIDE*2}%/round-trip")
    lines.append("")
    lines.append("Verdict at best per-detector horizon (PF≥1.5, N≥10 per fold; "
                 "≥3/4 folds → STABLE, ≥2/4 → MARGINAL, else OVERFIT/TOO_FEW)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Detector | Best H | Avg PF | Pos folds | Verdict |")
    lines.append("|---|:---:|---:|:---:|:---:|")

    summary: list[tuple[str, str, int, dict]] = []
    for det in detectors:
        per_fold_for_det = [fr[det.__name__] for fr in fold_results]
        verdict, pos, extra = _verdict_for(per_fold_for_det)
        summary.append((det.__name__, verdict, pos, extra))

    verdict_rank = {"STABLE": 0, "MARGINAL": 1, "OVERFIT": 2, "TOO_FEW": 3}
    summary.sort(key=lambda r: (verdict_rank[r[1]], -r[3]["avg_pf_at_best_h"]))

    for name, verdict, pos, extra in summary:
        lines.append(f"| `{name}` | {extra['best_horizon']}h | "
                     f"{extra['avg_pf_at_best_h']:.2f} | "
                     f"{pos}/{args.folds} | **{verdict}** |")
    lines.append("")

    # Per-detector full breakdown
    lines.append("## Per-detector × per-fold × per-horizon")
    lines.append("")
    for name, verdict, pos, extra in summary:
        lines.append(f"### `{name}` — {verdict} (best h={extra['best_horizon']}h)")
        lines.append("")
        lines.append("| Fold | h | N | WR% | PF | Mean% |")
        lines.append("|:---:|:---:|---:|---:|---:|---:|")
        for fi, fr in enumerate(fold_results, 1):
            for h in HORIZONS:
                m = fr[name][h]
                pf_str = f"{m['PF']:.2f}" if m["PF"] < 99 else "inf"
                lines.append(f"| {fi} | {h}h | {m['N']} | "
                             f"{m['WR']:.1f} | {pf_str} | {m['mean_pct']:+.2f} |")
        lines.append("")

    # Recommendations
    overfit = [s for s in summary if s[1] == "OVERFIT"]
    stable = [s for s in summary if s[1] == "STABLE"]
    too_few = [s for s in summary if s[1] == "TOO_FEW"]
    lines.append("## Recommendations")
    lines.append("")
    if stable:
        lines.append("### STABLE — keep + monitor")
        for name, _, pos, extra in stable:
            lines.append(f"- `{name}` (best h={extra['best_horizon']}h, "
                         f"avg PF={extra['avg_pf_at_best_h']:.2f}, {pos}/{args.folds})")
        lines.append("")
    if overfit:
        lines.append("### OVERFIT — candidates to disable")
        for name, _, pos, extra in overfit:
            lines.append(f"- `{name}` (best h={extra['best_horizon']}h, "
                         f"avg PF={extra['avg_pf_at_best_h']:.2f}, "
                         f"only {pos}/{args.folds} folds positive)")
        lines.append("")
    if too_few:
        lines.append("### TOO_FEW — re-evaluate after more data")
        for name, _, _, _ in too_few:
            lines.append(f"- `{name}`")
        lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    try:
        print(f"[walkfwd] wrote {OUT_MD.relative_to(ROOT)}")
    except UnicodeEncodeError:
        print(f"[walkfwd] wrote (path encoding issue)")
    print(f"  STABLE:   {len(stable)}")
    print(f"  MARGINAL: {sum(1 for s in summary if s[1]=='MARGINAL')}")
    print(f"  OVERFIT:  {len(overfit)}")
    print(f"  TOO_FEW:  {len(too_few)}")
    return 0


if __name__ == "__main__":
    # Force utf-8 stdout/stderr on Windows so progress prints don't crash
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                       line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                       line_buffering=True)
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
