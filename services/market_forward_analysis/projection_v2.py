"""Multi-signal projection engine v2.

Replaces setup-type string matching (Brier 0.31-0.38) with 5 independent
signal voters, each producing (direction, magnitude, confidence), combined
via configurable weighted ensemble.

Signal classes:
  A. PHASE COHERENCE — MTF alignment score
  B. DERIVATIVES DIVERGENCE — OI-price divergence + taker imbalance
  C. POSITIONING EXTREME — LS ratio + funding crowding (contrarian)
  D. STRUCTURAL CONTEXT — ICT levels (premium/discount, OB proximity, PDH/PDL)
  E. MOMENTUM EXHAUSTION — RSI + volume profile + candle pattern

Each signal: direction ∈ {-1, 0, +1}, magnitude ∈ [0, 1], confidence ∈ [0, 1]

Ensemble → probability distribution: [p_strong_down, p_mild_down, p_range, p_mild_up, p_strong_up]
→ Horizon-specific weights: 1h leans micro+deriv, 4h leans phase+struct, 1d leans phase+macro
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .phase_classifier import MTFPhaseState, Phase

logger = logging.getLogger(__name__)


# ── Signal output ─────────────────────────────────────────────────────────────

@dataclass
class SignalVote:
    name: str
    direction: int     # +1 / 0 / -1
    magnitude: float   # 0-1: how strong is the signal
    confidence: float  # 0-1: how reliable is this signal class
    note: str = ""


@dataclass
class EnsembleResult:
    """Output of the multi-signal ensemble."""
    direction: int           # net bias: +1 / 0 / -1
    net_score: float         # weighted score ∈ [-1, +1]
    prob_down: float         # probability price moves down >1% in horizon
    prob_range: float        # probability price stays within ±1%
    prob_up: float           # probability price moves up >1% in horizon
    confidence: float        # ensemble confidence 0-1
    votes: list[SignalVote] = field(default_factory=list)
    note: str = ""


# ── Per-horizon ensemble weights ──────────────────────────────────────────────
# Each row: [phase_coh, deriv_div, positioning, structural, momentum]

_HORIZON_WEIGHTS: dict[str, list[float]] = {
    "1h":  [0.15, 0.30, 0.20, 0.20, 0.15],
    "4h":  [0.30, 0.25, 0.20, 0.20, 0.05],
    "1d":  [0.40, 0.20, 0.25, 0.15, 0.00],
}


# ── Signal A: Phase coherence ─────────────────────────────────────────────────

def _signal_phase_coherence(phase_state: MTFPhaseState, features: Optional[pd.Series] = None) -> SignalVote:
    """A: MTF alignment score → directional bias."""
    macro_bias = phase_state.macro_bias
    macro_conf = 0.0
    sub_agree = 0
    sub_total = 0

    for tf, p in phase_state.phases.items():
        if p.confidence > 0:
            if tf == "1d":
                macro_conf = p.confidence / 100.0
            else:
                sub_total += 1
                if (p.direction_bias == macro_bias) or (macro_bias == 0):
                    sub_agree += 1

    align_ratio = sub_agree / sub_total if sub_total > 0 else 0.5
    magnitude = macro_conf * align_ratio
    confidence = 0.7 if phase_state.coherent else 0.3

    return SignalVote(
        name="phase_coherence",
        direction=macro_bias,
        magnitude=float(np.clip(magnitude, 0, 1)),
        confidence=confidence,
        note=f"macro_bias={macro_bias} coherent={phase_state.coherent} align={align_ratio:.2f}",
    )


# ── Signal B: Derivatives divergence ─────────────────────────────────────────

def _signal_derivatives_divergence(features: pd.Series) -> SignalVote:
    """B: OI-price divergence + taker imbalance.

    OI growing while price flat/down → smart money buying (bullish) or
    OI growing while price rising + taker sell → distribution (bearish).
    Contrarian when OI rises into opposing taker flow.
    """
    oi_div_z = float(features.get("oi_price_div_4h_z", 0.0))
    taker_1h  = float(features.get("taker_imbalance_1h", 0.0))
    funding_z = float(features.get("funding_z", 0.0))

    # OI-price divergence: positive = OI rising faster than price
    # Combined with taker: if OI up AND taker buy → bullish momentum
    #                       if OI up AND taker sell → bearish divergence
    if abs(oi_div_z) < 0.5:
        # No significant divergence
        direction = 0
        magnitude = 0.1
        note = "no_oi_divergence"
    elif oi_div_z > 0.5:
        # OI rising relative to price
        if taker_1h > 0.05:
            direction = 1   # OI up + buy aggression = bullish
            magnitude = min(0.9, abs(oi_div_z) * 0.3 + taker_1h * 0.5)
            note = f"oi_div_bullish oi_z={oi_div_z:.2f} taker={taker_1h:.2f}"
        elif taker_1h < -0.05:
            direction = -1  # OI up + sell aggression = bearish divergence
            magnitude = min(0.9, abs(oi_div_z) * 0.3 + abs(taker_1h) * 0.5)
            note = f"oi_div_bearish oi_z={oi_div_z:.2f} taker={taker_1h:.2f}"
        else:
            direction = 0
            magnitude = 0.2
            note = "oi_rising_taker_neutral"
    else:
        # OI falling relative to price: deleveraging
        direction = -1 if taker_1h < 0 else 0
        magnitude = min(0.6, abs(oi_div_z) * 0.2)
        note = f"oi_div_deleverage oi_z={oi_div_z:.2f}"

    # Funding skew: extreme positive funding = crowded long → bearish bias
    if abs(funding_z) > 1.5:
        funding_dir = -1 if funding_z > 0 else 1  # contrarian
        if funding_dir == direction:
            magnitude = min(1.0, magnitude + 0.15)
            note += f" funding_confirm z={funding_z:.2f}"
        elif direction == 0:
            direction = funding_dir
            magnitude = 0.25
            note += f" funding_only z={funding_z:.2f}"

    confidence = min(0.8, 0.4 + abs(oi_div_z) * 0.1 + abs(taker_1h) * 0.3)

    return SignalVote(
        name="deriv_divergence",
        direction=direction,
        magnitude=float(np.clip(magnitude, 0, 1)),
        confidence=float(np.clip(confidence, 0, 1)),
        note=note,
    )


# ── Signal C: Positioning extreme (contrarian) ────────────────────────────────

def _signal_positioning_extreme(features: pd.Series) -> SignalVote:
    """C: LS ratio crowding + funding → contrarian bias when extreme.

    When top traders are >70% long (ls_top_traders > 2.33) and funding is
    positive → crowded long → fade = bearish signal.
    """
    ls_top = float(features.get("ls_top_traders", 1.0))
    ls_global = float(features.get("ls_global", 1.0))
    funding_z = float(features.get("funding_z", 0.0))
    ls_long_extreme = int(features.get("ls_long_extreme", 0))
    ls_short_extreme = int(features.get("ls_short_extreme", 0))

    direction = 0
    magnitude = 0.0
    note = "positioning_neutral"

    if ls_long_extreme:
        # >70% long among top traders — crowded; fade = bearish
        direction = -1
        magnitude = 0.5
        if funding_z > 1.0:
            magnitude = min(0.9, magnitude + 0.2)  # funding confirms crowding
            note = f"crowded_long_fade ls={ls_top:.2f} fund_z={funding_z:.2f}"
        else:
            note = f"ls_long_extreme ls={ls_top:.2f}"

    elif ls_short_extreme:
        # <30% long → crowded short; fade = bullish
        direction = 1
        magnitude = 0.5
        if funding_z < -1.0:
            magnitude = min(0.9, magnitude + 0.2)
            note = f"crowded_short_fade ls={ls_top:.2f} fund_z={funding_z:.2f}"
        else:
            note = f"ls_short_extreme ls={ls_top:.2f}"

    else:
        # Mild lean: ls_top > 1.5 = moderate long lean
        if ls_top > 1.5:
            direction = -1
            magnitude = (ls_top - 1.5) / (2.33 - 1.5) * 0.3
            note = f"mild_long_lean ls={ls_top:.2f}"
        elif ls_top < 0.67:
            direction = 1
            magnitude = (0.67 - ls_top) / (0.67 - 0.43) * 0.3
            note = f"mild_short_lean ls={ls_top:.2f}"

    confidence = 0.6 if (ls_long_extreme or ls_short_extreme) else 0.3

    return SignalVote(
        name="positioning_extreme",
        direction=direction,
        magnitude=float(np.clip(magnitude, 0, 1)),
        confidence=confidence,
        note=note,
    )


# ── Signal D: Structural context (ICT levels) ─────────────────────────────────

def _signal_structural_context(features: pd.Series) -> SignalVote:
    """D: ICT level proximity — premium/discount + PDH/PDL + unmitigated levels.

    Price in premium zone near PDH/unmitigated high → bearish structural.
    Price in discount zone near PDL/unmitigated low → bullish structural.
    """
    in_premium   = int(features.get("in_premium_zone", 0))
    dist_pdh_pct = float(features.get("dist_to_pdh_pct", 0.0))
    dist_pdl_pct = float(features.get("dist_to_pdl_pct", 0.0))
    dist_pwh_pct = float(features.get("dist_to_pwh_pct", 0.0))
    dist_pwl_pct = float(features.get("dist_to_pwl_pct", 0.0))
    dist_nh_pct  = float(features.get("dist_to_nearest_unmitigated_high_pct", 99.0))
    dist_nl_pct  = float(features.get("dist_to_nearest_unmitigated_low_pct", 99.0))
    nh_age_h     = float(features.get("nearest_unmitigated_high_above_age_h", 99.0))
    nl_age_h     = float(features.get("nearest_unmitigated_low_below_age_h", 99.0))

    bearish_score = 0.0
    bullish_score = 0.0
    notes = []

    # Premium zone near resistance → bearish
    if in_premium:
        bearish_score += 0.2
        notes.append("premium_zone")

    # Near PDH (within 0.5%) → resistance overhead → bearish
    if 0 <= dist_pdh_pct < 0.5:
        bearish_score += 0.3
        notes.append(f"near_pdh {dist_pdh_pct:.2f}%")
    elif 0 <= dist_pdh_pct < 1.5:
        bearish_score += 0.15

    # Near PDL (within 0.5%) → support below → bullish
    if 0 >= dist_pdl_pct > -0.5:
        bullish_score += 0.3
        notes.append(f"near_pdl {dist_pdl_pct:.2f}%")
    elif 0 >= dist_pdl_pct > -1.5:
        bullish_score += 0.15

    # Near weekly high/low
    if 0 <= dist_pwh_pct < 1.0:
        bearish_score += 0.15
        notes.append("near_pwh")
    if 0 >= dist_pwl_pct > -1.0:
        bullish_score += 0.15
        notes.append("near_pwl")

    # Fresh unmitigated high above (< 24h old, < 2% away) → bearish OB
    if dist_nh_pct < 2.0 and nh_age_h < 24:
        bearish_score += 0.25
        notes.append(f"fresh_nh {dist_nh_pct:.1f}% {nh_age_h:.0f}h")

    # Fresh unmitigated low below → bullish OB
    if dist_nl_pct < 2.0 and nl_age_h < 24:
        bullish_score += 0.25
        notes.append(f"fresh_nl {dist_nl_pct:.1f}% {nl_age_h:.0f}h")

    net = bearish_score - bullish_score
    if abs(net) < 0.1:
        direction = 0
        magnitude = 0.1
    elif net > 0:
        direction = -1
        magnitude = min(0.9, net)
    else:
        direction = 1
        magnitude = min(0.9, -net)

    confidence = min(0.7, 0.3 + abs(net) * 0.5)

    return SignalVote(
        name="structural_context",
        direction=direction,
        magnitude=magnitude,
        confidence=confidence,
        note=" | ".join(notes) if notes else "no_struct_signal",
    )


# ── Signal E: Momentum exhaustion ────────────────────────────────────────────

def _signal_momentum_exhaustion(features: pd.Series) -> SignalVote:
    """E: RSI extremes + volume + candle pattern.

    Extreme RSI + high rvol + bearish candles → exhaustion signal.
    """
    rsi_14   = float(features.get("rsi_14", 50.0))
    rsi_50   = float(features.get("rsi_50", 50.0))
    rvol     = float(features.get("rvol_20", 1.0))
    body_ratio = float(features.get("body_to_range", 0.5))
    uw_dom   = float(features.get("upper_wick_dominance", 0.0))
    lw_dom   = float(features.get("lower_wick_dominance", 0.0))
    tick_pres = float(features.get("tick_pressure", 0.0))
    vol_acc  = float(features.get("volume_acceleration", 0.0))
    close_h20 = float(features.get("close_higher_20", 10.0))

    direction = 0
    magnitude = 0.0
    notes = []

    # RSI overbought + high rvol + upper wick → exhaustion top
    if rsi_14 > 75:
        direction = -1
        magnitude += 0.3
        notes.append(f"rsi_ob={rsi_14:.0f}")
        if rvol > 1.5:
            magnitude += 0.15
            notes.append("high_rvol")
        if uw_dom > 0.4:  # upper wick > 40% of range → rejection
            magnitude += 0.15
            notes.append("uw_rejection")
        if close_h20 > 15:  # 15+ of last 20 closes higher → overbought momentum
            magnitude += 0.1
            notes.append(f"c_high={close_h20:.0f}/20")

    # RSI oversold + high rvol + lower wick → exhaustion bottom
    elif rsi_14 < 25:
        direction = 1
        magnitude += 0.3
        notes.append(f"rsi_os={rsi_14:.0f}")
        if rvol > 1.5:
            magnitude += 0.15
            notes.append("high_rvol")
        if lw_dom > 0.4:  # lower wick → support reaction
            magnitude += 0.15
            notes.append("lw_support")
        if close_h20 < 5:  # < 5 of last 20 closes higher → oversold
            magnitude += 0.1
            notes.append(f"c_high={close_h20:.0f}/20")

    # Moderate: RSI 65-75 or 25-35, confirmed by volume
    elif rsi_14 > 65 and vol_acc > 0.5:
        direction = -1
        magnitude = 0.2
        notes.append(f"rsi_mod_ob={rsi_14:.0f} vol_acc={vol_acc:.1f}")
    elif rsi_14 < 35 and vol_acc > 0.5:
        direction = 1
        magnitude = 0.2
        notes.append(f"rsi_mod_os={rsi_14:.0f} vol_acc={vol_acc:.1f}")

    confidence = 0.5 if abs(rsi_14 - 50) > 25 else 0.3

    return SignalVote(
        name="momentum_exhaustion",
        direction=direction,
        magnitude=float(np.clip(magnitude, 0, 1)),
        confidence=confidence,
        note=" | ".join(notes) if notes else "no_momentum_signal",
    )


# ── Ensemble ──────────────────────────────────────────────────────────────────

def _ensemble_votes(votes: list[SignalVote], horizon: str = "4h") -> EnsembleResult:
    """Combine 5 signal votes into horizon-specific probability distribution."""
    weights = _HORIZON_WEIGHTS.get(horizon, _HORIZON_WEIGHTS["4h"])
    assert len(weights) == 5, f"Expected 5 weights, got {len(weights)}"

    # Weighted net score: each vote contributes direction × magnitude × confidence × weight
    net_score = 0.0
    total_weight = 0.0
    avg_confidence = 0.0

    for i, (vote, w) in enumerate(zip(votes, weights)):
        contribution = vote.direction * vote.magnitude * vote.confidence * w
        net_score += contribution
        total_weight += w
        avg_confidence += vote.confidence * w

    if total_weight > 0:
        net_score /= total_weight
        avg_confidence /= total_weight

    net_score = float(np.clip(net_score, -1.0, 1.0))

    # Convert net score to probability distribution
    # net_score ∈ [-1, +1]; sigmoid-like mapping to probs
    # p_up = sigmoid of positive net_score
    def _prob_up(score: float) -> float:
        return float(1 / (1 + np.exp(-score * 4)))

    pu = _prob_up(net_score)
    pd_val = 1.0 - pu

    # Split into strong/mild/range based on magnitude
    magnitude = abs(net_score)
    if magnitude < 0.15:
        prob_range = 0.60
        prob_up = pu * 0.40
        prob_down = pd_val * 0.40
    elif magnitude < 0.35:
        prob_range = 0.30
        prob_up = pu * 0.70
        prob_down = pd_val * 0.70
    else:
        prob_range = 0.15
        prob_up = pu * 0.85
        prob_down = pd_val * 0.85

    # Normalize
    total = prob_up + prob_down + prob_range
    prob_up /= total
    prob_down /= total
    prob_range /= total

    direction = 1 if net_score > 0.1 else (-1 if net_score < -0.1 else 0)

    return EnsembleResult(
        direction=direction,
        net_score=round(net_score, 4),
        prob_down=round(prob_down, 4),
        prob_range=round(prob_range, 4),
        prob_up=round(prob_up, 4),
        confidence=round(float(avg_confidence), 4),
        votes=votes,
        note=f"horizon={horizon} net={net_score:.3f}",
    )


# ── Top-level compute ─────────────────────────────────────────────────────────

def compute_projection_v2(
    phase_state: MTFPhaseState,
    features: pd.Series,
    horizons: tuple[str, ...] = ("1h", "4h", "1d"),
) -> dict[str, EnsembleResult]:
    """Compute multi-signal ensemble projection for each horizon.

    Parameters
    ----------
    phase_state:  MTFPhaseState from phase_classifier
    features:     Single-row Series from full_features_1y.parquet (or live features)
    horizons:     Which horizons to compute

    Returns
    -------
    dict mapping horizon → EnsembleResult
    """
    # Compute 5 signal votes (same for all horizons — weights differ per horizon)
    vote_a = _signal_phase_coherence(phase_state, features)
    vote_b = _signal_derivatives_divergence(features)
    vote_c = _signal_positioning_extreme(features)
    vote_d = _signal_structural_context(features)
    vote_e = _signal_momentum_exhaustion(features)

    votes = [vote_a, vote_b, vote_c, vote_d, vote_e]

    results = {}
    for horizon in horizons:
        results[horizon] = _ensemble_votes(votes, horizon)

    return results


# ── Signal contribution analysis (CHECKPOINT 2) ───────────────────────────────

def signal_contribution_report(
    features_df: pd.DataFrame,
    phase_states: Optional[list[MTFPhaseState]] = None,
    sample_n: int = 1000,
) -> dict:
    """Analyze signal contributions across a sample of feature rows.

    Used for CHECKPOINT 2: when does each signal fire, in which direction?
    Are signals correlated or independent?
    """
    # Sample evenly
    step = max(1, len(features_df) // sample_n)
    sample = features_df.iloc[::step].head(sample_n)

    # Use a dummy phase_state (neutral) if not provided
    from .phase_classifier import build_mtf_phase_state
    dummy_phase = build_mtf_phase_state({})

    signal_names = ["phase_coherence", "deriv_divergence", "positioning_extreme",
                    "structural_context", "momentum_exhaustion"]
    signal_fns = [
        lambda f: _signal_phase_coherence(dummy_phase, f),
        _signal_derivatives_divergence,
        _signal_positioning_extreme,
        _signal_structural_context,
        _signal_momentum_exhaustion,
    ]

    # Collect per-signal directions
    records: list[dict] = []
    for _, row in sample.iterrows():
        rec = {}
        for name, fn in zip(signal_names, signal_fns):
            try:
                vote = fn(row)
                rec[f"{name}_dir"] = vote.direction
                rec[f"{name}_mag"] = vote.magnitude
            except Exception:
                rec[f"{name}_dir"] = 0
                rec[f"{name}_mag"] = 0.0
        records.append(rec)

    df_signals = pd.DataFrame(records)

    report = {}

    # Per-signal: fire rate (non-zero direction), directional bias
    for name in signal_names:
        dir_col = f"{name}_dir"
        mag_col = f"{name}_mag"
        if dir_col not in df_signals.columns:
            continue
        dirs = df_signals[dir_col]
        mags = df_signals[mag_col]
        report[name] = {
            "fire_rate_pct": round(float((dirs != 0).mean() * 100), 1),
            "bullish_pct":   round(float((dirs == 1).mean() * 100), 1),
            "bearish_pct":   round(float((dirs == -1).mean() * 100), 1),
            "neutral_pct":   round(float((dirs == 0).mean() * 100), 1),
            "mean_magnitude": round(float(mags.mean()), 3),
        }

    # Signal-to-signal correlation (by direction)
    dir_cols = [f"{n}_dir" for n in signal_names if f"{n}_dir" in df_signals.columns]
    if len(dir_cols) > 1:
        corr = df_signals[dir_cols].corr()
        high_corr = []
        for i in range(len(dir_cols)):
            for j in range(i + 1, len(dir_cols)):
                c = float(corr.iloc[i, j])
                if abs(c) > 0.4:
                    high_corr.append((dir_cols[i], dir_cols[j], round(c, 3)))
        report["signal_correlations"] = {
            "high_corr_pairs": high_corr,
            "verdict": "correlated" if any(abs(c) > 0.6 for _, _, c in high_corr) else "independent",
        }

    return report
