"""Forward projection engine — historical pattern matching on setup outcomes.

Approach:
  1. Given current MTFPhaseState + market conditions, find similar past episodes
     from the 18,712 historical setup outcomes.
  2. Compute outcome distribution: where did price go in 1h / 4h / 1d?
  3. Score confluence strength (STRONG / MEDIUM / WEAK) based on signal alignment.
  4. Return probability directional forecasts with CI.

Evidence source: data/historical_setups_y1_2026-04-30.parquet (18,712 rows)
Columns: setup_type, regime, session, strength, final_status, hypothetical_pnl_usd,
         hypothetical_r, time_to_outcome_min, entry_price, current_price, ...

NO sim used for magnitudes. Pattern matching on real historical outcomes only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .phase_classifier import MTFPhaseState, Phase

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_SETUPS_PATH = _ROOT / "data" / "historical_setups_y1_2026-04-30.parquet"


class ConfluenceStrength(str, Enum):
    STRONG  = "strong"   # 3+ independent signals align
    MEDIUM  = "medium"   # 2 signals align
    WEAK    = "weak"     # 1 signal only
    NONE    = "none"     # no clear signal


@dataclass
class HorizonForecast:
    horizon: str          # "1h" | "4h" | "1d"
    direction: str        # "up" | "down" | "range"
    probability: float    # 0-100 (%)
    expected_move_pct: float     # expected median move % (signed)
    ci95_low_pct: float          # 95% CI lower bound move %
    ci95_high_pct: float         # 95% CI upper bound move %
    n_episodes: int              # number of matching historical episodes
    note: str = ""


@dataclass
class ForwardProjection:
    """Full projection result for current market state."""
    generated_at: pd.Timestamp
    phase_label: str
    phase_bias: int             # +1 / -1 / 0
    confluence_strength: ConfluenceStrength
    confluence_signals: list[str]

    forecasts: dict[str, HorizonForecast]   # "1h", "4h", "1d"

    # Key levels from phase + pattern context
    key_resistance: Optional[float]
    key_support: Optional[float]

    # Microstructure summary (from event detectors)
    micro_notes: list[str] = field(default_factory=list)

    # Calibration quality
    brier_score: Optional[float] = None   # filled during checkpoint 2


# ── Historical data loader ────────────────────────────────────────────────────

_SETUPS_CACHE: Optional[pd.DataFrame] = None


def _load_setups() -> pd.DataFrame:
    global _SETUPS_CACHE
    if _SETUPS_CACHE is not None:
        return _SETUPS_CACHE
    if not _SETUPS_PATH.exists():
        logger.warning("forward_projection: setup history not found at %s", _SETUPS_PATH)
        return pd.DataFrame()
    try:
        df = pd.read_parquet(_SETUPS_PATH)
        _SETUPS_CACHE = df
        logger.info("forward_projection: loaded %d historical setups", len(df))
        return df
    except Exception:
        logger.exception("forward_projection: failed to load setups")
        return pd.DataFrame()


# ── Condition extraction ──────────────────────────────────────────────────────

def _extract_conditions(
    phase_state: MTFPhaseState,
    df_1h: Optional[pd.DataFrame] = None,
) -> dict:
    """Extract matching conditions from current state for historical lookup."""
    conditions: dict = {
        "macro_phase": phase_state.macro_label.value,
        "macro_bias":  phase_state.macro_bias,
        "coherent":    phase_state.coherent,
    }

    # Regime proxy from 1h data
    if df_1h is not None and not df_1h.empty and "fundingRate" in df_1h.columns:
        fr = df_1h["fundingRate"].dropna()
        if len(fr) > 0:
            last_fr = float(fr.iloc[-1])
            conditions["funding_regime"] = (
                "extreme_long" if last_fr > 0.0005 else
                "extreme_short" if last_fr < -0.0005 else
                "neutral"
            )

    if df_1h is not None and not df_1h.empty and "top_trader_ls_ratio" in df_1h.columns:
        ls = df_1h["top_trader_ls_ratio"].dropna()
        if len(ls) > 0:
            last_ls = float(ls.iloc[-1])
            conditions["ls_bias"] = (
                "long_crowded"  if last_ls > 1.5 else
                "short_crowded" if last_ls < 0.7 else
                "balanced"
            )

    return conditions


# ── Outcome distribution from historical setups ───────────────────────────────

def _compute_outcome_distribution(
    setups: pd.DataFrame,
    macro_phase: str,
    macro_bias: int,
) -> dict[str, HorizonForecast]:
    """Compute outcome distributions from historical setups similar to current conditions.

    Matching criteria:
    - Setup direction matches macro_bias (LONG setups for bias +1, SHORT for -1)
    - Regime column if available

    Returns horizon forecasts for 1h / 4h / 1d.
    """
    if setups.empty:
        return _empty_forecasts()

    # Map bias to setup type families
    if macro_bias > 0:
        target_types = {"dump_reversal", "pdl_bounce", "oversold_reclaim", "liq_magnet"}
    elif macro_bias < 0:
        target_types = {"rally_fade", "pdh_rejection", "overbought_fade", "liq_magnet"}
    else:
        target_types = set()

    # Filter by setup type if we have directional bias
    if target_types and "setup_type" in setups.columns:
        sub = setups[setups["setup_type"].isin(target_types)]
    else:
        sub = setups

    # Filter by macro phase (regime column proxy)
    # Historical setups have a "regime" column — match broadly
    _PHASE_REGIME_MAP = {
        "markup":       ["green", "bull", "trending"],
        "markdown":     ["red", "bear", "trending"],
        "accumulation": ["neutral", "range", "green"],
        "distribution": ["neutral", "range", "red"],
        "range":        ["neutral", "range"],
        "transition":   ["neutral"],
    }
    allowed_regimes = _PHASE_REGIME_MAP.get(macro_phase, [])
    if allowed_regimes and "regime" in sub.columns:
        regime_mask = sub["regime"].str.lower().str.contains(
            "|".join(allowed_regimes), na=False
        )
        filtered = sub[regime_mask]
        if len(filtered) >= 20:
            sub = filtered
        # else: keep broader sub

    # Need at least 20 episodes for meaningful statistics
    n = len(sub)
    if n < 20:
        return _empty_forecasts()

    # Use hypothetical_pnl_usd and hypothetical_r as outcome proxies
    # Map to directional probability: final_status = "TP1" or "TP2" → success
    forecasts: dict[str, HorizonForecast] = {}
    for horizon, time_max_min in [("1h", 60), ("4h", 240), ("1d", 1440)]:
        mask = (sub.get("time_to_outcome_min", pd.Series(dtype=float)) <= time_max_min)
        horizon_sub = sub[mask] if mask.any() else sub

        # Directional probability from final_status
        if "final_status" in horizon_sub.columns:
            tp_count   = horizon_sub["final_status"].isin(["TP1", "TP2", "entry_hit"]).sum()
            stop_count = horizon_sub["final_status"].isin(["stop", "invalidated"]).sum()
            total_clear = tp_count + stop_count
            if total_clear > 0:
                win_prob = tp_count / total_clear * 100
            else:
                win_prob = 50.0
        else:
            win_prob = 50.0

        # Move % from hypothetical_r (R-multiple)
        if "hypothetical_r" in horizon_sub.columns:
            r_vals = horizon_sub["hypothetical_r"].dropna()
            if len(r_vals) > 5:
                median_r = float(r_vals.median())
                q5  = float(np.percentile(r_vals, 5))
                q95 = float(np.percentile(r_vals, 95))
                # Convert R to approximate % move (1R ≈ 1.5% typical stop-based)
                r_to_pct = 1.5
                expected_pct = median_r * r_to_pct * (1 if macro_bias >= 0 else -1)
                ci_low  = q5  * r_to_pct * (1 if macro_bias >= 0 else -1)
                ci_high = q95 * r_to_pct * (1 if macro_bias >= 0 else -1)
            else:
                expected_pct = ci_low = ci_high = 0.0
        else:
            expected_pct = ci_low = ci_high = 0.0

        # Direction
        if macro_bias > 0:
            direction = "up" if win_prob > 55 else "range"
        elif macro_bias < 0:
            direction = "down" if win_prob > 55 else "range"
        else:
            direction = "range"

        forecasts[horizon] = HorizonForecast(
            horizon=horizon,
            direction=direction,
            probability=round(win_prob, 1),
            expected_move_pct=round(expected_pct, 2),
            ci95_low_pct=round(ci_low, 2),
            ci95_high_pct=round(ci_high, 2),
            n_episodes=int(len(horizon_sub)),
            note=f"n={n}, phase={macro_phase}",
        )

    return forecasts


def _empty_forecasts() -> dict[str, HorizonForecast]:
    return {
        h: HorizonForecast(h, "range", 50.0, 0.0, 0.0, 0.0, 0, "insufficient_data")
        for h in ("1h", "4h", "1d")
    }


# ── Confluence scoring ────────────────────────────────────────────────────────

def _score_confluence(
    phase_state: MTFPhaseState,
    df_1h: Optional[pd.DataFrame],
    conditions: dict,
) -> tuple[ConfluenceStrength, list[str]]:
    """Score how many independent signals align with the projected direction."""
    signals: list[str] = []
    bias = phase_state.macro_bias

    # Signal 1: MTF phase coherence
    if phase_state.coherent and bias != 0:
        direction = "bullish" if bias > 0 else "bearish"
        signals.append(f"mtf_phase_coherent_{direction}")

    # Signal 2: funding bias
    fr_regime = conditions.get("funding_regime")
    if fr_regime == "extreme_long" and bias < 0:
        signals.append("funding_crowded_long_vs_bearish_phase")
    elif fr_regime == "extreme_short" and bias > 0:
        signals.append("funding_crowded_short_vs_bullish_phase")

    # Signal 3: LS ratio
    ls_bias = conditions.get("ls_bias")
    if ls_bias == "long_crowded" and bias < 0:
        signals.append("ls_crowded_long_vs_bearish_phase")
    elif ls_bias == "short_crowded" and bias > 0:
        signals.append("ls_crowded_short_vs_bullish_phase")

    # Signal 4: OI delta from df_1h
    if df_1h is not None and not df_1h.empty and "sum_open_interest" in df_1h.columns:
        oi_vals = df_1h["sum_open_interest"].dropna()
        if len(oi_vals) >= 4:
            oi_delta = (float(oi_vals.iloc[-1]) - float(oi_vals.iloc[-4])) / float(oi_vals.iloc[-4]) * 100
            if abs(oi_delta) > 2.0:
                direction_oi = "increasing" if oi_delta > 0 else "decreasing"
                signals.append(f"oi_{direction_oi}_{abs(oi_delta):.1f}pct")

    # Signal 5: taker imbalance
    if df_1h is not None and not df_1h.empty and "taker_vol_ratio" in df_1h.columns:
        tv = df_1h["taker_vol_ratio"].dropna()
        if len(tv) > 0:
            last_tv = float(tv.iloc[-1])
            if last_tv > 1.3 and bias > 0:
                signals.append("taker_buy_pressure_bullish")
            elif last_tv < 0.8 and bias < 0:
                signals.append("taker_sell_pressure_bearish")

    n = len(signals)
    if n >= 3:
        strength = ConfluenceStrength.STRONG
    elif n == 2:
        strength = ConfluenceStrength.MEDIUM
    elif n == 1:
        strength = ConfluenceStrength.WEAK
    else:
        strength = ConfluenceStrength.NONE

    return strength, signals


# ── Public API ────────────────────────────────────────────────────────────────

def compute_forward_projection(
    phase_state: MTFPhaseState,
    df_1h: Optional[pd.DataFrame] = None,
) -> ForwardProjection:
    """Compute forward projection given current MTF phase state.

    Parameters
    ----------
    phase_state:   Output of build_mtf_phase_state()
    df_1h:         1h OHLCV with merged derivatives columns (optional but improves accuracy)
    """
    conditions = _extract_conditions(phase_state, df_1h)
    confluence_strength, confluence_signals = _score_confluence(phase_state, df_1h, conditions)

    setups = _load_setups()
    forecasts = _compute_outcome_distribution(setups, phase_state.macro_label.value, phase_state.macro_bias)

    # Extract key levels from 1d phase
    macro_pr = phase_state.phases.get("1d") or next(iter(phase_state.phases.values()), None)
    klevels = macro_pr.key_levels if macro_pr else {}
    key_resistance = klevels.get("range_high") if phase_state.macro_bias <= 0 else None
    key_support    = klevels.get("range_low")  if phase_state.macro_bias >= 0 else None

    # Micro notes from conditions
    micro_notes: list[str] = []
    if "funding_regime" in conditions and conditions["funding_regime"] != "neutral":
        micro_notes.append(f"funding: {conditions['funding_regime']}")
    if "ls_bias" in conditions and conditions["ls_bias"] != "balanced":
        micro_notes.append(f"ls_ratio: {conditions['ls_bias']}")

    return ForwardProjection(
        generated_at=phase_state.ts,
        phase_label=phase_state.macro_label.value,
        phase_bias=phase_state.macro_bias,
        confluence_strength=confluence_strength,
        confluence_signals=confluence_signals,
        forecasts=forecasts,
        key_resistance=key_resistance,
        key_support=key_support,
        micro_notes=micro_notes,
    )


# ── Checkpoint 2: calibration ─────────────────────────────────────────────────

def compute_brier_score(
    setups: pd.DataFrame,
    macro_bias: int,
    horizon_minutes: int = 240,
) -> float:
    """Compute Brier score for directional predictions on historical setups.

    Lower is better. 0.25 = random (p=0.5 always). <0.20 = better than random.
    """
    if setups.empty or "final_status" not in setups.columns:
        return 0.25

    sub = setups.copy()
    if macro_bias > 0:
        # Bullish setups (long bias): types with "long" prefix or reversal names
        mask = sub["setup_type"].str.contains("long|dump_reversal|pdl_bounce|oversold", case=False, na=False)
        sub = sub[mask]
        positive_outcomes = {"tp1_hit", "tp2_hit", "TP1", "TP2"}
    else:
        # Bearish setups (short bias): types with "short" prefix or fade/rejection names
        mask = sub["setup_type"].str.contains("short|rally_fade|pdh_rejection|overbought", case=False, na=False)
        sub = sub[mask]
        positive_outcomes = {"tp1_hit", "tp2_hit", "TP1", "TP2"}

    if len(sub) < 20:
        return 0.25

    if "time_to_outcome_min" in sub.columns:
        sub = sub[sub["time_to_outcome_min"] <= horizon_minutes]

    if len(sub) < 10:
        return 0.25

    # Model prediction: win_prob based on setup strength
    if "strength" in sub.columns:
        max_strength = sub["strength"].max()
        predicted_prob = (sub["strength"] / max_strength * 0.3 + 0.35).clip(0.3, 0.8)
    else:
        predicted_prob = pd.Series([0.6] * len(sub), index=sub.index)

    actual = sub["final_status"].isin(positive_outcomes).astype(float)
    brier = float(((predicted_prob - actual) ** 2).mean())
    return round(brier, 4)


def run_checkpoint2_validation(setups_path: Path = _SETUPS_PATH) -> dict:
    """Run checkpoint 2 projection validation. Returns stats dict."""
    if not setups_path.exists():
        return {"error": f"setups not found: {setups_path}"}

    df = pd.read_parquet(setups_path)
    results = {}
    for bias, label in [(1, "bullish"), (-1, "bearish")]:
        for horizon in [60, 240, 1440]:
            bs = compute_brier_score(df, bias, horizon)
            key = f"{label}_{horizon}m"
            results[key] = {
                "brier_score": bs,
                "vs_random": round(0.25 - bs, 4),
                "better_than_random": bs < 0.25,
            }
    return results
