"""Calibration models against GinArea ground truth.

Model A — multiplicative K (Codex engine_v2 output scaled by mean K):
    calibrated_pnl = sim_pnl * K_realized_mean
    Only usable when K_realized verdict is STABLE (no sign flip).

Model B — standalone clean sim (services.calibration.sim):
    Bypasses instop/combo_stop engine bugs. Computes its own K values.
    Two modes: 'raw' (4 ticks/bar) and 'intra_bar' (5 ticks/bar).

Parameter conventions (matching Codex engine_v2 and GinArea JSON):
    grid_step_pct  = stored as 0.03 in JSON → pass as 3.0 to run_sim
    target_pct     = stored as 0.21 in JSON → pass as 0.21 to run_sim
    run_sim divides target_pct by 100 internally → tp_dist = 0.0021
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .sim import SimResult, run_sim, load_ohlcv_bars, Mode

ROOT       = Path(__file__).resolve().parents[2]
OHLCV_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
GT_PATH    = ROOT / "data" / "calibration" / "ginarea_ground_truth_v1.json"

SIM_START = "2025-05-01T00:00:00+00:00"
SIM_END   = "2026-04-29T23:59:59+00:00"


@dataclass
class CalibPoint:
    bot_id: str
    side: str
    target_pct: float           # as stored in JSON (e.g. 0.21)
    sim_realized: float
    sim_volume_usd: float
    sim_fills: int
    sim_unrealized: float
    ga_realized: float
    ga_volume_usd: float
    ga_triggers: Optional[int]
    ga_unrealized: float
    k_realized: float           # ga_realized / sim_realized
    k_volume: float             # ga_volume  / sim_volume
    err_pct: float              # |sim - ga| / |ga| * 100


@dataclass
class GroupStats:
    name: str
    n: int
    k_realized_mean: float
    k_realized_std: float
    k_realized_cv: float
    k_volume_mean: float
    verdict: str                # STABLE | TD-DEPENDENT | FRACTURED | FRACTURED_SIGN_FLIP


def _safe_k(num: float, den: float) -> float:
    if den == 0 or math.isnan(den) or math.isnan(num):
        return math.nan
    return num / den


def _group_stats(name: str, k_realized: list[float], k_volume: list[float]) -> GroupStats:
    ks = [k for k in k_realized if not math.isnan(k)]
    kv = [k for k in k_volume   if not math.isnan(k)]
    if not ks:
        return GroupStats(name, 0, math.nan, math.nan, math.nan, math.nan, "UNKNOWN")
    mean = statistics.mean(ks)
    std  = statistics.stdev(ks) if len(ks) > 1 else 0.0
    cv   = (std / mean * 100) if mean != 0 else math.inf
    if min(ks) < 0 < max(ks):
        verdict = "FRACTURED_SIGN_FLIP"
    elif abs(cv) < 15:
        verdict = "STABLE"
    elif abs(cv) < 35:
        verdict = "TD-DEPENDENT"
    else:
        verdict = "FRACTURED"
    k_vol_mean = statistics.mean(kv) if kv else math.nan
    return GroupStats(name, len(ks), mean, std, cv, k_vol_mean, verdict)


def run_model_b(
    mode: Mode = "raw",
    sides: list[str] | None = None,
) -> tuple[list[CalibPoint], list[GroupStats]]:
    """Run standalone sim against GinArea ground truth points.

    sides: if given, restrict to those sides (e.g. ['LONG']).
    """
    gt   = json.loads(GT_PATH.read_text(encoding="utf-8"))
    bars = load_ohlcv_bars(OHLCV_PATH, SIM_START, SIM_END)
    if len(bars) < 100_000:
        raise RuntimeError(f"Too few OHLCV bars: {len(bars)}")

    short_params = gt["common_short_params"]
    long_params  = gt["common_long_params"]

    filter_sides = {s.upper() for s in sides} if sides else None

    points: list[CalibPoint] = []
    for pt in gt["points"]:
        gres = pt["ginarea_results"]
        side = pt["side"].upper()
        if filter_sides and side not in filter_sides:
            continue

        if side == "SHORT":
            p          = short_params
            order_size = p["order_size_btc"]
            ga_real    = gres["realized_pnl_usd"]
            ga_unreal  = gres["unrealized_pnl_usd"]
        else:
            p          = long_params
            order_size = p["order_size_usd"]
            ga_real    = gres["realized_pnl_btc"]
            ga_unreal  = gres["unrealized_pnl_btc"]

        sim = run_sim(
            bars=bars,
            side=side,
            order_size=order_size,
            grid_step_pct=p["grid_step_pct"],  # 0.03 → sim divides by 100 → 0.0003 (0.03% step)
            target_pct=pt["target_pct"],       # 0.21 → sim divides by 100 → 0.0021 (0.21% target)
            max_orders=p["max_trigger_number"],
            mode=mode,
        )

        k_re  = _safe_k(ga_real, sim.realized_pnl)
        k_vo  = _safe_k(gres["trading_volume_usd"], sim.trading_volume_usd)
        err   = (abs(sim.realized_pnl - ga_real) / abs(ga_real) * 100
                 if ga_real else math.nan)

        points.append(CalibPoint(
            bot_id=pt["id"],
            side=side,
            target_pct=pt["target_pct"],
            sim_realized=sim.realized_pnl,
            sim_volume_usd=sim.trading_volume_usd,
            sim_fills=sim.num_fills,
            sim_unrealized=sim.unrealized_pnl,
            ga_realized=ga_real,
            ga_volume_usd=gres["trading_volume_usd"],
            ga_triggers=gres.get("num_triggers"),
            ga_unrealized=ga_unreal,
            k_realized=k_re,
            k_volume=k_vo,
            err_pct=err,
        ))

    short_pts = [p for p in points if p.side == "SHORT"]
    long_pts  = [p for p in points if p.side == "LONG"]

    groups = [
        _group_stats(
            "SHORT/LINEAR",
            [p.k_realized for p in short_pts],
            [p.k_volume   for p in short_pts],
        ),
        _group_stats(
            "LONG/INVERSE",
            [p.k_realized for p in long_pts],
            [p.k_volume   for p in long_pts],
        ),
    ]
    return points, groups


def apply_model_a(sim_pnl: float, group_k: float) -> float:
    """Model A: scale sim PnL by precomputed K_realized_mean."""
    return sim_pnl * group_k
