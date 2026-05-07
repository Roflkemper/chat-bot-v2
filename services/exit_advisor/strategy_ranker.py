"""Strategy ranker: given a PositionStateSnapshot, return ranked exit recommendations.

Data source: data/historical_setups_y1_2026-04-30.parquet
  Columns: setup_type, regime, session, strength, final_status,
           hypothetical_pnl_usd, hypothetical_r, time_to_outcome_min

Strategy families map to what_if actions (from src/whatif/action_simulator.py):
  A — partial_close    (A-CLOSE-PARTIAL, fractions 25/50/75/100%)
  B — counter_hedge    (A-LAUNCH-COUNTER-LONG, size x TTL combos)
  C — boundary_adjust  (A-RAISE-BOUNDARY, offset_pct 0.3..1.0)
  D — grid_tighten     (A-ADAPTIVE-GRID, target_factor x gs_factor)
  F — combination      (A-RAISE-AND-STACK-SHORT or composite)

For each scenario class we define applicable families + param combos,
then look up outcome statistics from the historical parquet.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd

from .position_state import PositionStateSnapshot, ScenarioClass

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_HISTORICAL_SETUPS = _ROOT / "data" / "historical_setups_y1_2026-04-30.parquet"

_MIN_N_SAMPLES = 5          # below this: LOW confidence
_MIN_N_MEDIUM = 10          # MEDIUM confidence threshold
_MIN_N_HIGH = 30            # HIGH confidence threshold


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ExitFamily(str, Enum):
    A = "A"   # partial_close
    B = "B"   # counter_hedge
    C = "C"   # boundary_adjust
    D = "D"   # grid_tighten
    F = "F"   # combination


@dataclass
class RankedStrategy:
    rank: int
    family: ExitFamily
    action_name: str
    params: dict
    confidence: ConfidenceLevel
    n_samples: int

    # EV statistics from historical parquet (or rule-based defaults)
    mean_pnl_usd: float
    win_rate_pct: float
    ci_lower_usd: float
    ci_upper_usd: float

    # Execution specifics
    description: str
    size_btc: Optional[float] = None
    size_pct: Optional[float] = None     # fraction for partial_close
    ttl_min: Optional[int] = None        # TTL for counter_hedge
    offset_pct: Optional[float] = None  # boundary adjust offset
    target_factor: Optional[float] = None
    gs_factor: Optional[float] = None
    margin_required_usd: float = 0.0
    reversible: bool = True


# ── Strategy templates per scenario class ─────────────────────────────────────

# Each entry: (family, action_name, params_dict, description_template)
_SCENARIO_STRATEGIES: dict[ScenarioClass, list[tuple]] = {
    ScenarioClass.EARLY_INTERVENTION: [
        (ExitFamily.C, "A-RAISE-BOUNDARY",      {"offset_pct": 0.5},
         "Raise boundary +0.5% — blocks new IN during continued rise"),
        (ExitFamily.C, "A-RAISE-BOUNDARY",      {"offset_pct": 0.7},
         "Raise boundary +0.7% — wider buffer, lower IN frequency"),
        (ExitFamily.D, "A-ADAPTIVE-GRID",        {"target_factor": 0.7, "gs_factor": 0.75},
         "Tighten grid (target x0.7, step x0.75) — faster exits on small moves"),
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 25},
         "Close 25% of SHORT position at current price"),
    ],
    ScenarioClass.CYCLE_DEATH: [
        (ExitFamily.B, "A-LAUNCH-COUNTER-LONG",  {"size_btc": 0.05, "ttl_min": 60},
         "Counter-hedge 0.05 BTC LONG, TTL 1h — hedge short during bounce"),
        (ExitFamily.B, "A-LAUNCH-COUNTER-LONG",  {"size_btc": 0.05, "ttl_min": 120},
         "Counter-hedge 0.05 BTC LONG, TTL 2h — longer window hedge"),
        (ExitFamily.C, "A-RAISE-BOUNDARY",       {"offset_pct": 1.0},
         "Raise boundary +1.0% — aggressive stop on new shorts"),
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 50},
         "Close 50% of SHORT — significant derisking"),
        (ExitFamily.D, "A-ADAPTIVE-GRID",        {"target_factor": 0.6, "gs_factor": 0.67},
         "Tighten grid (target x0.6, step x0.67) — tested P-12 params"),
        (ExitFamily.F, "A-RAISE-AND-STACK-SHORT", {"offset_pct": 0.5, "size_btc": 0.05},
         "Composite: raise boundary + add SHORT at resistance — improve entry avg"),
    ],
    ScenarioClass.MODERATE: [
        (ExitFamily.B, "A-LAUNCH-COUNTER-LONG",  {"size_btc": 0.10, "ttl_min": 60},
         "Counter-hedge 0.10 BTC LONG, TTL 1h — larger hedge for bigger DD"),
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 50},
         "Close 50% of SHORT — halve exposure now"),
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 75},
         "Close 75% of SHORT — major derisking, keep small runner"),
        (ExitFamily.B, "A-LAUNCH-COUNTER-LONG",  {"size_btc": 0.05, "ttl_min": 30},
         "Counter-hedge 0.05 BTC LONG, TTL 30min — scalp hedge"),
        (ExitFamily.C, "A-RAISE-BOUNDARY",       {"offset_pct": 1.0},
         "Raise boundary +1.0% — stop all new SHORT IN orders"),
        (ExitFamily.D, "A-ADAPTIVE-GRID",        {"target_factor": 0.5, "gs_factor": 0.6},
         "Aggressively tighten grid — maximize exit fills"),
    ],
    ScenarioClass.SEVERE: [
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 75},
         "Close 75% of SHORT — protect most of remaining capital"),
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 100},
         "Close 100% of SHORT — full exit, reset"),
        (ExitFamily.B, "A-LAUNCH-COUNTER-LONG",  {"size_btc": 0.10, "ttl_min": 120},
         "Counter-hedge 0.10 BTC LONG, TTL 2h — large hedge for severe DD"),
        (ExitFamily.F, "A-RAISE-AND-STACK-SHORT", {"offset_pct": 1.0, "size_btc": 0.10},
         "Composite: raise + stack at HOD — compound at peak"),
    ],
    ScenarioClass.CRITICAL: [
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 100},
         "Close ALL SHORT — emergency full exit"),
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 75},
         "Close 75% SHORT — heavy cut, keep 25% for recovery"),
        (ExitFamily.B, "A-LAUNCH-COUNTER-LONG",  {"size_btc": 0.10, "ttl_min": 60},
         "Counter-hedge 0.10 BTC LONG, TTL 1h — last-resort hedge"),
    ],
    ScenarioClass.URGENT_PROTECTION: [
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 100},
         "EMERGENCY: Close ALL SHORT — liquidation imminent"),
        (ExitFamily.A, "A-CLOSE-PARTIAL",        {"fraction": 75},
         "URGENT: Close 75% SHORT — pull back from liquidation"),
        (ExitFamily.C, "A-RAISE-BOUNDARY",       {"offset_pct": 2.0},
         "Emergency boundary raise +2.0% — no new IN orders at any cost"),
    ],
    ScenarioClass.MONITORING: [],  # no recommendations when healthy
}


def _load_historical_stats(parquet_path: Path) -> pd.DataFrame | None:
    """Load and cache historical setup outcomes for EV lookup."""
    if not parquet_path.exists():
        return None
    try:
        df = pd.read_parquet(parquet_path)
        df = df[df["final_status"].notna()].copy()
        df["win"] = df["final_status"] == "tp1_hit"
        return df
    except Exception:
        logger.warning("exit_advisor.ranker: failed to load %s", parquet_path)
        return None


def _compute_ev_from_history(
    df: pd.DataFrame,
    regime: str,
    session: str,
) -> tuple[float, float, int, float, float]:
    """Lookup mean PnL, win_rate, n from historical setups for regime/session.

    Returns (mean_pnl, win_rate_pct, n, ci_lower, ci_upper).
    Falls back progressively: regime+session → regime only → overall.
    """
    import numpy as np

    def _stats(subset: pd.DataFrame):
        pnl = subset["hypothetical_pnl_usd"].dropna()
        if len(pnl) < 2:
            return None
        mean = float(pnl.mean())
        std = float(pnl.std())
        n = len(pnl)
        sem = std / (n ** 0.5) if n > 1 else std
        ci_l = mean - 1.96 * sem
        ci_u = mean + 1.96 * sem
        wr = float((subset["win"] == True).mean() * 100)
        return mean, wr, n, ci_l, ci_u

    for mask in [
        (df["regime"] == regime) & (df["session"] == session),
        (df["regime"] == regime),
        pd.Series([True] * len(df), index=df.index),
    ]:
        sub = df[mask]
        result = _stats(sub)
        if result is not None:
            return result

    return 0.0, 50.0, 0, -999.0, 999.0


class StrategyRanker:
    def __init__(self, parquet_path: Path = _HISTORICAL_SETUPS) -> None:
        self._df = _load_historical_stats(parquet_path)

    def rank(
        self,
        state: PositionStateSnapshot,
        regime: str = "unknown",
        session: str = "NONE",
        max_results: int = 6,
        min_free_margin_usd: float = 0.0,
    ) -> list[RankedStrategy]:
        """Return top-N ranked strategies for the current position state."""
        templates = _SCENARIO_STRATEGIES.get(state.scenario_class, [])
        if not templates:
            return []

        strategies: list[RankedStrategy] = []

        for family, action_name, params, description in templates:
            # Get EV from historical data if available
            if self._df is not None:
                mean_pnl, wr, n, ci_l, ci_u = _compute_ev_from_history(
                    self._df, regime, session
                )
            else:
                mean_pnl, wr, n, ci_l, ci_u = 0.0, 50.0, 0, -999.0, 999.0

            # Confidence level
            if n >= _MIN_N_HIGH and ci_l > 0:
                confidence = ConfidenceLevel.HIGH
            elif n >= _MIN_N_MEDIUM:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

            # Size extraction
            size_btc = params.get("size_btc")
            fraction = params.get("fraction")
            ttl = params.get("ttl_min")
            offset = params.get("offset_pct")
            tf = params.get("target_factor")
            gs = params.get("gs_factor")

            s = RankedStrategy(
                rank=0,  # assigned below
                family=family,
                action_name=action_name,
                params=params,
                confidence=confidence,
                n_samples=n,
                mean_pnl_usd=mean_pnl,
                win_rate_pct=wr,
                ci_lower_usd=ci_l,
                ci_upper_usd=ci_u,
                description=description,
                size_btc=size_btc,
                size_pct=fraction,
                ttl_min=ttl,
                offset_pct=offset,
                target_factor=tf,
                gs_factor=gs,
                reversible=family in (ExitFamily.C, ExitFamily.D),
            )
            strategies.append(s)

        # Sort: confidence tier first, then mean_pnl descending
        _conf_order = {ConfidenceLevel.HIGH: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.LOW: 2}
        strategies.sort(key=lambda s: (_conf_order[s.confidence], -s.mean_pnl_usd))

        for i, s in enumerate(strategies[:max_results], start=1):
            s.rank = i

        return strategies[:max_results]
