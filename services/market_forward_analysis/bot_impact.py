"""Bot impact projector — mechanical projection of market moves onto active bot state.

Reads ginarea_live/snapshots.csv, applies forward projection scenarios to each bot,
and classifies per-bot risk (GREEN / YELLOW / ORANGE / RED).

Mechanical chain:
  Market signal → expected price path → bot mechanics → outcome estimate

Evidence anchor: GA backtests from data/calibration/ginarea_ground_truth_v1.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd

from .forward_projection import ForwardProjection, HorizonForecast

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_SNAPSHOTS_CSV = _ROOT / "ginarea_live" / "snapshots.csv"
_GA_BACKTESTS  = _ROOT / "data" / "calibration" / "ginarea_ground_truth_v1.json"


# ── Risk classification ───────────────────────────────────────────────────────

class RiskClass(str, Enum):
    GREEN  = "GREEN"    # EV+ position for projected move
    YELLOW = "YELLOW"   # neutral / unclear
    ORANGE = "ORANGE"   # adverse, manageable
    RED    = "RED"      # critical risk path


# ── Bot state (mirrors exit_advisor.position_state.BotState) ─────────────────

@dataclass
class BotProjection:
    """Per-bot impact projection for a specific price scenario."""
    bot_id: str
    alias: str
    side: str                    # "SHORT" | "LONG"
    position_size: float         # abs BTC
    avg_entry: float
    current_price: float
    liq_price: float
    unrealized_usd: float
    distance_to_liq_pct: float

    # Scenario projections per horizon
    scenarios: dict[str, dict] = field(default_factory=dict)
    # e.g. {"4h": {"projected_price": 74200, "unrealized_delta_usd": -485,
    #               "liq_dist_new_pct": 14.2, "triggers_IN": True, ...}}

    risk_class: RiskClass = RiskClass.YELLOW
    risk_notes: list[str] = field(default_factory=list)
    recommendation: str = ""

    # GA backtest evidence
    ga_evidence: Optional[str] = None


@dataclass
class PortfolioBotImpact:
    """Portfolio-level impact across all active bots."""
    generated_at: pd.Timestamp
    current_price: float
    projection: ForwardProjection
    bot_projections: list[BotProjection]
    portfolio_risk: RiskClass   # worst bot risk class
    summary: str
    portfolio_ga_summary: Optional[str] = None  # GA evidence anchor for session brief


# ── GA backtest evidence loader ───────────────────────────────────────────────

_GA_CACHE: Optional[dict] = None


def _load_ga_evidence() -> dict:
    global _GA_CACHE
    if _GA_CACHE is not None:
        return _GA_CACHE
    if not _GA_BACKTESTS.exists():
        return {}
    try:
        _GA_CACHE = json.loads(_GA_BACKTESTS.read_text(encoding="utf-8"))
        return _GA_CACHE
    except Exception:
        logger.warning("bot_impact: failed to load GA backtests")
        return {}


def _find_ga_evidence(side: str, move_pct: float) -> Optional[str]:
    """Find relevant GA backtest note for similar historical episodes."""
    ga = _load_ga_evidence()
    if not ga:
        return None

    backtests = ga.get("backtests", [])
    if not backtests:
        # Try other keys
        backtests = [v for v in ga.values() if isinstance(v, dict) and "realized_pnl_usd" in v]

    if not backtests:
        return None

    # Filter by side
    relevant = [b for b in backtests if b.get("side", "").upper() == side.upper()]
    if not relevant:
        return None

    # Find backtest with worst loss scenario
    best = relevant[0]
    note = (
        f"GA evidence ({side}): realized={best.get('realized_pnl_usd', 'n/a')}, "
        f"volume={best.get('trading_volume_usd', 'n/a')}, "
        f"triggers={best.get('num_triggers', 'n/a')}"
    )
    return note


# ── Snapshot reader ───────────────────────────────────────────────────────────

def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v not in ("", "None", "nan", None) else default
    except (ValueError, TypeError):
        return default


def _read_active_bots(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    try:
        rows: dict[str, dict] = {}
        with open(csv_path, encoding="utf-8", newline="") as f:
            import csv
            reader = csv.DictReader(f)
            for row in reader:
                bid = row.get("bot_id", "").strip()
                if bid:
                    rows[bid] = row
        # Filter active bots with positions
        active = []
        for row in rows.values():
            status = int(_safe_float(row.get("status", "0")))
            position = _safe_float(row.get("position", "0"))
            if status == 2 and abs(position) > 0.001:
                active.append(row)
        return active
    except Exception:
        logger.exception("bot_impact: failed to read snapshots")
        return []


# ── Mechanical scenario computation ──────────────────────────────────────────

def _project_bot_scenario(
    side: str,
    position_size: float,
    avg_entry: float,
    liq_price: float,
    current_price: float,
    projected_price: float,
) -> dict:
    """Compute mechanical outcomes for a price move to projected_price.

    For SHORT: profit if price falls, loss if price rises.
    For LONG:  profit if price rises, loss if price falls.
    """
    move_pct = (projected_price - current_price) / current_price * 100

    if side == "SHORT":
        # Realized P&L (unrealized becomes realized as TPs trigger)
        pnl_usd = (current_price - projected_price) * position_size
        # Distance to liquidation
        if liq_price > 0 and projected_price > 0:
            new_liq_dist = abs(projected_price - liq_price) / projected_price * 100
        else:
            new_liq_dist = 100.0
        # IN orders: SHORT bots open new IN orders ABOVE current price
        # If price rises, more INs trigger (adverse for short)
        triggers_in = move_pct > 2.0   # rough threshold

    else:  # LONG
        pnl_usd = (projected_price - current_price) * position_size
        if liq_price > 0 and projected_price > 0:
            new_liq_dist = abs(projected_price - liq_price) / projected_price * 100
        else:
            new_liq_dist = 100.0
        # IN orders: LONG bots open new IN orders BELOW current price
        # If price falls, more INs trigger (position grows)
        triggers_in = move_pct < -2.0

    return {
        "projected_price":      round(projected_price, 2),
        "move_pct":             round(move_pct, 2),
        "unrealized_delta_usd": round(pnl_usd, 2),
        "new_liq_dist_pct":    round(new_liq_dist, 1),
        "triggers_in":         triggers_in,
    }


def _classify_risk(
    side: str,
    phase_bias: int,
    scenarios: dict[str, dict],
    liq_dist_pct: float,
) -> tuple[RiskClass, list[str]]:
    """Classify per-bot risk based on projected scenarios."""
    notes: list[str] = []

    # Immediate liq danger
    if liq_dist_pct < 10:
        notes.append(f"liq_danger: {liq_dist_pct:.1f}% distance")
        return RiskClass.RED, notes

    # Check worst-case scenario (4h)
    s4h = scenarios.get("4h", {})
    new_liq = s4h.get("new_liq_dist_pct", 100.0)
    delta = s4h.get("unrealized_delta_usd", 0.0)

    # Is the projected move favorable?
    favorable = (side == "SHORT" and phase_bias < 0) or (side == "LONG" and phase_bias > 0)

    if favorable:
        if new_liq > 15:
            notes.append(f"projected move favorable for {side}")
            return RiskClass.GREEN, notes
        else:
            notes.append(f"favorable direction but liq risk remains: {new_liq:.1f}%")
            return RiskClass.YELLOW, notes
    else:
        # Adverse move
        if new_liq < 8:
            notes.append(f"adverse move, liq_dist will be {new_liq:.1f}% — critical")
            return RiskClass.RED, notes
        if new_liq < 20 or delta < -500:
            notes.append(f"adverse, new_liq_dist={new_liq:.1f}%, delta={delta:+.0f}")
            return RiskClass.ORANGE, notes
        notes.append(f"adverse but manageable, delta={delta:+.0f}")
        return RiskClass.YELLOW, notes


def _make_recommendation(
    risk: RiskClass,
    side: str,
    phase_bias: int,
    scenarios: dict[str, dict],
    alias: str,
) -> str:
    s4h = scenarios.get("4h", {})
    target_price = s4h.get("projected_price", 0)

    if risk == RiskClass.GREEN:
        return f"{alias}: hold — projected move favorable for {side}"

    if risk == RiskClass.YELLOW:
        return f"{alias}: monitor — direction unclear or marginal impact"

    if risk == RiskClass.ORANGE:
        if side == "LONG" and phase_bias < 0:
            return (
                f"{alias} ({side}): consider expanding lower boundary below {target_price:,.0f} "
                f"to prevent excessive IN accumulation in projected target zone"
            )
        if side == "SHORT" and phase_bias > 0:
            return (
                f"{alias} ({side}): consider pausing new IN orders — "
                f"adverse move projected to {target_price:,.0f}"
            )
        return f"{alias}: defensive prep recommended"

    if risk == RiskClass.RED:
        return (
            f"{alias} ({side}): URGENT — liq proximity critical. "
            f"Consider manual stop or boundary adjustment immediately"
        )

    return f"{alias}: monitor"


# ── GA evidence anchor ───────────────────────────────────────────────────────

def _build_portfolio_ga_anchor(
    bots: list,
    phase_label: str,
    phase_bias: int,
) -> Optional[str]:
    """Build a portfolio-level GA evidence anchor for the session brief.

    Summarises historical SHORT/LONG backtest outcomes relevant to current phase.
    Expressed qualitatively — no probability numbers.
    """
    ga = _load_ga_evidence()
    if not ga:
        return None

    backtests = ga.get("backtests", [])
    if not backtests:
        backtests = [v for v in ga.values() if isinstance(v, dict) and "realized_pnl_usd" in v]

    if not backtests:
        return None

    # Determine dominant side in portfolio
    sides = [b.side for b in bots] if bots else []
    short_count = sides.count("SHORT")
    long_count  = sides.count("LONG")
    dominant_side = "SHORT" if short_count >= long_count else "LONG"

    # Find GA evidence for dominant side
    relevant = [b for b in backtests if b.get("side", "").upper() == dominant_side.upper()]
    if not relevant:
        return None

    # Phase alignment: is dominant side aligned with phase bias?
    aligned = (dominant_side == "SHORT" and phase_bias < 0) or (dominant_side == "LONG" and phase_bias > 0)
    alignment_str = "aligned with phase" if aligned else "counter to phase"

    # Build qualitative summary from best-result backtest
    best = max(relevant, key=lambda b: float(b.get("realized_pnl_usd", 0) or 0))
    pnl = best.get("realized_pnl_usd", "n/a")
    vol = best.get("trading_volume_usd", "n/a")
    n_trig = best.get("num_triggers", "n/a")

    if pnl != "n/a":
        try:
            pnl_f = float(pnl)
            pnl_str = f"+${pnl_f:,.0f}" if pnl_f >= 0 else f"-${abs(pnl_f):,.0f}"
        except (ValueError, TypeError):
            pnl_str = str(pnl)
    else:
        pnl_str = "n/a"

    return (
        f"GA evidence ({dominant_side}, {alignment_str} — {phase_label}): "
        f"best backtest realized {pnl_str}, "
        f"vol {vol}, triggers {n_trig}"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def compute_bot_impact(
    projection: ForwardProjection,
    current_price: float,
    snapshots_path: Path = _SNAPSHOTS_CSV,
) -> PortfolioBotImpact:
    """Compute per-bot impact from forward projection.

    Parameters
    ----------
    projection:      Output of compute_forward_projection()
    current_price:   Current BTC price
    snapshots_path:  Path to ginarea_live/snapshots.csv
    """
    now = pd.Timestamp.utcnow()
    rows = _read_active_bots(snapshots_path)

    bot_projections: list[BotProjection] = []

    for row in rows:
        bot_id = row.get("bot_id", "")
        alias  = row.get("alias", "") or row.get("bot_name", "")
        position_btc = _safe_float(row.get("position", "0"))
        avg_entry    = _safe_float(row.get("average_price", "0"))
        liq_price    = _safe_float(row.get("liquidation_price", "0"))
        unrealized   = _safe_float(row.get("current_profit", "0"))
        balance      = _safe_float(row.get("balance", "0"))

        side = "SHORT" if position_btc < 0 else "LONG"
        position_size = abs(position_btc)

        if current_price > 0 and liq_price > 0:
            liq_dist = abs(current_price - liq_price) / current_price * 100
        else:
            liq_dist = 100.0

        # Project scenarios for 1h / 4h / 1d
        scenarios: dict[str, dict] = {}
        for horizon in ("1h", "4h", "1d"):
            fc: HorizonForecast = projection.forecasts.get(horizon)
            if fc is None:
                continue
            # Projected price from expected_move_pct
            projected_price = current_price * (1 + fc.expected_move_pct / 100)
            scenarios[horizon] = _project_bot_scenario(
                side, position_size, avg_entry, liq_price, current_price, projected_price
            )

        risk, risk_notes = _classify_risk(
            side, projection.phase_bias, scenarios, liq_dist
        )
        recommendation = _make_recommendation(
            risk, side, projection.phase_bias, scenarios, alias
        )

        # GA evidence
        move_4h = scenarios.get("4h", {}).get("move_pct", 0.0)
        ga_note = _find_ga_evidence(side, move_4h)

        bot_projections.append(BotProjection(
            bot_id=bot_id,
            alias=alias,
            side=side,
            position_size=position_size,
            avg_entry=avg_entry,
            current_price=current_price,
            liq_price=liq_price,
            unrealized_usd=unrealized,
            distance_to_liq_pct=liq_dist,
            scenarios=scenarios,
            risk_class=risk,
            risk_notes=risk_notes,
            recommendation=recommendation,
            ga_evidence=ga_note,
        ))

    # Portfolio risk = worst individual bot risk
    risk_order = [RiskClass.RED, RiskClass.ORANGE, RiskClass.YELLOW, RiskClass.GREEN]
    if bot_projections:
        portfolio_risk = next(
            (r for r in risk_order if any(b.risk_class == r for b in bot_projections)),
            RiskClass.GREEN,
        )
    else:
        portfolio_risk = RiskClass.GREEN

    # Summary
    red_count    = sum(1 for b in bot_projections if b.risk_class == RiskClass.RED)
    orange_count = sum(1 for b in bot_projections if b.risk_class == RiskClass.ORANGE)
    summary = (
        f"{len(bot_projections)} active bots — "
        f"RED:{red_count} ORANGE:{orange_count} "
        f"phase:{projection.phase_label} bias:{'+' if projection.phase_bias > 0 else ''}{projection.phase_bias}"
    )

    # Portfolio GA evidence anchor
    # Summarise what GA backtests say about the dominant bot side in current phase
    portfolio_ga_summary = _build_portfolio_ga_anchor(
        bot_projections, projection.phase_label, projection.phase_bias
    )

    return PortfolioBotImpact(
        generated_at=now,
        current_price=current_price,
        projection=projection,
        bot_projections=bot_projections,
        portfolio_risk=portfolio_risk,
        summary=summary,
        portfolio_ga_summary=portfolio_ga_summary,
    )
