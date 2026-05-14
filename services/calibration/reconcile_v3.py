"""TZ-ENGINE-FIX-RESOLUTION — reconcile v3 with 1s OHLCV.

Two modes:

  * `direct_k`             — sim vs GA realized → K factor.
                              Requires 1s OHLCV covering the **full** GA window
                              (currently 2025-05-01 → 2026-04-30, ~365 days).

  * `resolution_sensitivity` — sim_1s vs sim_1m on the **same overlap window**
                              for every GA config. Returns ratio sim_1s/sim_1m
                              per config + aggregates. Informative probe of
                              intra-minute fill effect on realized PnL.

The current dataset has only ~30 days of 1s OHLCV, so `direct_k` aborts with
DATA_GAP and the operator-facing mode is `resolution_sensitivity`.
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .sim import Side, SimResult, load_ohlcv_bars, run_sim

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GT_PATH = ROOT / "data" / "calibration" / "ginarea_ground_truth_v1.json"
DEFAULT_OHLCV_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
DEFAULT_OHLCV_1S = ROOT / "backtests" / "frozen" / "BTCUSDT_1s_2y.csv"


# ---------------------------------------------------------------------------
# CSV span detection (without loading bars)
# ---------------------------------------------------------------------------

def csv_span_iso(path: Path) -> tuple[str, str]:
    """Return (first_ts_iso, last_ts_iso) by scanning CSV cheaply."""
    if not path.exists():
        raise FileNotFoundError(f"OHLCV file not found: {path}")
    # First data row
    with open(path, "r", encoding="utf-8") as f:
        header = f.readline()
        first = f.readline().strip()
    # Last data row (tail-read)
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(-min(2048, size), 2)
        tail = f.read().decode("utf-8", errors="replace").strip().splitlines()
    last = next(
        (line for line in reversed(tail) if line and not line.startswith("ts")),
        "",
    )

    def _ts_to_iso(line: str) -> str:
        ms = int(float(line.split(",", 1)[0]))
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )

    return _ts_to_iso(first), _ts_to_iso(last)


def overlap_window(
    span_a: tuple[str, str], span_b: tuple[str, str]
) -> tuple[str, str] | None:
    """Intersect two ISO date spans. Return (start, end) or None if disjoint."""
    a_start, a_end = span_a
    b_start, b_end = span_b
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start >= end:
        return None
    return start, end


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GAPoint:
    bot_id: str
    side: Side                # "SHORT" | "LONG"
    target_pct: float         # in percent (e.g. 0.21)
    order_size: float
    grid_step_pct: float
    max_orders: int
    ga_realized: float


@dataclass
class ResolutionResult:
    """One config × two resolutions."""
    point: GAPoint
    window_start: str
    window_end: str
    sim_1m: SimResult
    sim_1s: SimResult

    @property
    def ratio(self) -> float:
        """sim_1s.realized / sim_1m.realized.

        NaN if 1m baseline is zero (avoid div0; surfaces in sanity check).
        """
        if self.sim_1m.realized_pnl == 0:
            return float("nan")
        return self.sim_1s.realized_pnl / self.sim_1m.realized_pnl


@dataclass
class ResolutionAggregate:
    side: Side
    n: int
    ratios: list[float]
    mean: float
    std: float
    cv_pct: float            # 100 * std / |mean|
    median: float
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ground-truth loader
# ---------------------------------------------------------------------------

def load_ga_points(path: Path = DEFAULT_GT_PATH) -> list[GAPoint]:
    """Read ginarea_ground_truth_v1.json → list of GAPoint."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    common_short = raw.get("common_short_params", {})
    common_long = raw.get("common_long_params", {})

    points: list[GAPoint] = []
    for p in raw["points"]:
        side: Side = "SHORT" if p["side"].lower() == "short" else "LONG"
        if side == "SHORT":
            order_size = float(common_short.get("order_size_btc", 0.003))
            ga_realized = float(p["ginarea_results"]["realized_pnl_usd"])
        else:
            # LONG = COIN-M: GA realized denominated in BTC, matches sim's
            # run_sim LONG output (per sim.py docstring: PnL in BTC for LONG).
            order_size = float(common_long.get("order_size_usd", 200.0))
            ga_realized = float(p["ginarea_results"]["realized_pnl_btc"])
        common = common_short if side == "SHORT" else common_long
        points.append(GAPoint(
            bot_id=str(p["id"]),
            side=side,
            target_pct=float(p["target_pct"]),
            order_size=order_size,
            grid_step_pct=float(common.get("grid_step_pct", 0.03)),
            max_orders=int(common.get("max_trigger_number", 800)),
            ga_realized=ga_realized,
        ))
    return points


# ---------------------------------------------------------------------------
# Sensitivity probe
# ---------------------------------------------------------------------------

def run_resolution_sensitivity(
    ga_points: list[GAPoint],
    ohlcv_1m: Path = DEFAULT_OHLCV_1M,
    ohlcv_1s: Path = DEFAULT_OHLCV_1S,
) -> tuple[list[ResolutionResult], dict[Side, ResolutionAggregate], dict]:
    """Run sim on 1m and 1s data over their overlapping window for each config.

    Returns (per_config_results, per_side_aggregate, meta).
    """
    span_1m = csv_span_iso(ohlcv_1m)
    span_1s = csv_span_iso(ohlcv_1s)
    overlap = overlap_window(span_1m, span_1s)
    if overlap is None:
        raise RuntimeError(
            f"1m and 1s CSV spans do not overlap. "
            f"1m={span_1m}, 1s={span_1s}"
        )
    win_start, win_end = overlap

    # Load both datasets once
    bars_1m = load_ohlcv_bars(ohlcv_1m, win_start, win_end)
    bars_1s = load_ohlcv_bars(ohlcv_1s, win_start, win_end)

    if not bars_1m or not bars_1s:
        raise RuntimeError(
            f"Empty bar set in overlap window {win_start} → {win_end}. "
            f"1m={len(bars_1m)} bars, 1s={len(bars_1s)} bars"
        )

    results: list[ResolutionResult] = []
    for p in ga_points:
        sim_1m = run_sim(
            bars_1m, p.side, p.order_size, p.grid_step_pct,
            p.target_pct, p.max_orders, mode="raw",
        )
        sim_1s = run_sim(
            bars_1s, p.side, p.order_size, p.grid_step_pct,
            p.target_pct, p.max_orders, mode="raw",
        )
        results.append(ResolutionResult(
            point=p,
            window_start=win_start,
            window_end=win_end,
            sim_1m=sim_1m,
            sim_1s=sim_1s,
        ))

    aggregates = _aggregate_by_side(results)
    meta = {
        "window_start": win_start,
        "window_end": win_end,
        "ga_period_used": "n/a (sensitivity probe — not direct K)",
        "ohlcv_1m_span": span_1m,
        "ohlcv_1s_span": span_1s,
        "ga_period": "see ground_truth.json (1y, NOT covered by 1s window)",
        "n_configs": len(ga_points),
        "n_bars_1m": len(bars_1m),
        "n_bars_1s": len(bars_1s),
    }
    return results, aggregates, meta


def _aggregate_by_side(
    results: list[ResolutionResult],
) -> dict[Side, ResolutionAggregate]:
    out: dict[Side, ResolutionAggregate] = {}
    for side in ("SHORT", "LONG"):
        subset = [r for r in results if r.point.side == side]
        ratios = [r.ratio for r in subset if not math.isnan(r.ratio)]
        notes: list[str] = []
        n_zero = sum(1 for r in subset if math.isnan(r.ratio))
        if n_zero:
            notes.append(
                f"{n_zero} config(s) had zero 1m-baseline realized — excluded from ratio."
            )
        if not ratios:
            out[side] = ResolutionAggregate(
                side=side, n=0, ratios=[], mean=float("nan"),
                std=float("nan"), cv_pct=float("nan"),
                median=float("nan"), notes=notes + ["no usable points"],
            )
            continue
        mean = statistics.fmean(ratios)
        std = statistics.pstdev(ratios) if len(ratios) > 1 else 0.0
        cv_pct = (std / abs(mean) * 100.0) if mean != 0 else float("nan")
        median = statistics.median(ratios)
        out[side] = ResolutionAggregate(
            side=side, n=len(ratios), ratios=ratios,
            mean=mean, std=std, cv_pct=cv_pct,
            median=median, notes=notes,
        )
    return out


# ---------------------------------------------------------------------------
# Direct-K mode (gated on data range)
# ---------------------------------------------------------------------------

def check_direct_k_feasible(
    ga_period: tuple[str, str],
    ohlcv_1s_span: tuple[str, str],
    *,
    min_coverage_pct: float = 95.0,
) -> tuple[bool, str]:
    """Verify 1s OHLCV covers the GA period. Returns (ok, reason)."""
    ga_start, ga_end = ga_period
    s_start, s_end = ohlcv_1s_span
    overlap = overlap_window((ga_start, ga_end), (s_start, s_end))
    if overlap is None:
        return False, (
            f"1s OHLCV ({s_start}..{s_end}) does not overlap GA period "
            f"({ga_start}..{ga_end})"
        )
    # Coverage: how much of GA period is covered by the 1s span
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    try:
        ga_start_dt = datetime.fromisoformat(ga_start.replace("Z", "+00:00"))
        ga_end_dt = datetime.fromisoformat(ga_end.replace("Z", "+00:00"))
        ov_start_dt = datetime.fromisoformat(overlap[0].replace("Z", "+00:00"))
        ov_end_dt = datetime.fromisoformat(overlap[1].replace("Z", "+00:00"))
    except ValueError as exc:
        return False, f"date parse error: {exc}"

    ga_secs = (ga_end_dt - ga_start_dt).total_seconds()
    ov_secs = (ov_end_dt - ov_start_dt).total_seconds()
    coverage = (ov_secs / ga_secs * 100.0) if ga_secs > 0 else 0.0
    if coverage < min_coverage_pct:
        return False, (
            f"1s OHLCV covers only {coverage:.1f}% of GA period "
            f"(need >= {min_coverage_pct}%). 1s span={s_start}..{s_end}, "
            f"GA={ga_start}..{ga_end}."
        )
    return True, f"coverage {coverage:.1f}%"


def k_factor(ga_realized: float, sim_realized: float) -> float:
    """K = ga_realized / sim_realized. NaN on zero sim baseline."""
    if sim_realized == 0:
        return float("nan")
    return ga_realized / sim_realized
