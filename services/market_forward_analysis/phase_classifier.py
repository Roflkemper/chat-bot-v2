"""Multi-timeframe market phase classifier.

Detects Wyckoff-inspired market phases (ACCUMULATION / MARKUP / DISTRIBUTION /
MARKDOWN / RANGE / TRANSITION) across 1d / 4h / 1h / 15m timeframes.

Each phase output includes:
  - label: one of 6 phase labels
  - confidence: 0-100 (%)
  - key_levels: price levels relevant to the phase
  - bars_in_phase: estimated bars the market has been in this phase
  - direction_bias: +1 (bullish) / -1 (bearish) / 0 (neutral)
  - notes: list of strings explaining the classification

Coherence rule: higher-TF phase wins on conflicts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Phase labels ──────────────────────────────────────────────────────────────

class Phase(str, Enum):
    ACCUMULATION  = "accumulation"   # base forming, smart money absorbing supply
    MARKUP        = "markup"          # trending up with HH/HL structure
    DISTRIBUTION  = "distribution"   # top forming, smart money distributing
    MARKDOWN      = "markdown"        # trending down with LH/LL structure
    RANGE         = "range"           # consolidation, no trend
    TRANSITION    = "transition"      # ambiguous / changing phase


@dataclass
class PhaseResult:
    timeframe: str           # "1d" | "4h" | "1h" | "15m"
    label: Phase
    confidence: float        # 0-100
    direction_bias: int      # +1 / -1 / 0
    bars_in_phase: int       # estimated bars in current phase
    key_levels: dict[str, float]   # {"range_high": X, "range_low": Y, ...}
    notes: list[str] = field(default_factory=list)


@dataclass
class MTFPhaseState:
    """Complete multi-timeframe phase state, ready for downstream consumers."""
    ts: pd.Timestamp
    phases: dict[str, PhaseResult]   # key = timeframe string
    coherent: bool                    # True if all TFs agree on direction
    macro_label: Phase                # 1d phase (highest authority)
    macro_bias: int                   # +1 / -1 / 0 from 1d
    coherence_note: str               # human-readable combined context


# ── Internal helpers ──────────────────────────────────────────────────────────

def _swing_structure(df: pd.DataFrame, swing_n: int = 3) -> tuple[list[float], list[float]]:
    """Return (swing_highs, swing_lows) using pivot-point method."""
    highs: list[float] = []
    lows:  list[float] = []
    if len(df) < swing_n * 2 + 1:
        return highs, lows
    for i in range(swing_n, len(df) - swing_n):
        h = df["high"].iloc[i]
        l = df["low"].iloc[i]
        if all(h >= df["high"].iloc[i - j] and h >= df["high"].iloc[i + j] for j in range(1, swing_n + 1)):
            highs.append(float(h))
        if all(l <= df["low"].iloc[i - j] and l <= df["low"].iloc[i + j] for j in range(1, swing_n + 1)):
            lows.append(float(l))
    return highs, lows


def _hh_hl(highs: list[float], lows: list[float], n: int = 3) -> bool:
    """True if last n swing highs are higher and last n swing lows are higher."""
    if len(highs) < n or len(lows) < n:
        return False
    return all(highs[-i] > highs[-i - 1] for i in range(1, n)) and \
           all(lows[-i]  > lows[-i - 1]  for i in range(1, n))


def _lh_ll(highs: list[float], lows: list[float], n: int = 3) -> bool:
    """True if last n swing highs are lower and last n swing lows are lower."""
    if len(highs) < n or len(lows) < n:
        return False
    return all(highs[-i] < highs[-i - 1] for i in range(1, n)) and \
           all(lows[-i]  < lows[-i - 1]  for i in range(1, n))


def _range_bound(df: pd.DataFrame, lookback: int = 20, range_pct: float = 4.0) -> tuple[bool, float, float]:
    """Return (is_range, range_high, range_low). Range if high-low < range_pct."""
    sub = df.tail(lookback)
    rh = float(sub["high"].max())
    rl = float(sub["low"].min())
    span_pct = (rh - rl) / rl * 100 if rl > 0 else 0.0
    return span_pct < range_pct, rh, rl


def _vol_trend(df: pd.DataFrame, lookback: int = 10) -> float:
    """Return slope of volume over lookback bars normalised to 0-1.
    Positive = increasing volume, negative = decreasing volume."""
    if "volume" not in df.columns or len(df) < lookback:
        return 0.0
    vols = df["volume"].tail(lookback).values
    if vols.std() == 0:
        return 0.0
    xs = np.arange(len(vols))
    slope = float(np.polyfit(xs, vols, 1)[0])
    return float(np.clip(slope / (vols.mean() + 1e-9), -1.0, 1.0))


def _atr_percentile(df: pd.DataFrame, period: int = 14, lookback: int = 100) -> float:
    """Return current ATR percentile (0-100) vs lookback. High = volatile."""
    if len(df) < period + 2:
        return 50.0
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().dropna()
    if len(atr) < 2:
        return 50.0
    current = float(atr.iloc[-1])
    hist = atr.tail(lookback)
    return float((hist < current).mean() * 100)


def _consolidation_depth(df: pd.DataFrame, swing_n: int = 3, lookback: int = 30) -> float:
    """Return ratio of volume in lower half of recent range (accumulation proxy).
    Higher = more absorption at lows (accumulation-like).
    """
    sub = df.tail(lookback)
    rh = float(sub["high"].max())
    rl = float(sub["low"].min())
    mid = (rh + rl) / 2
    if rh == rl or "volume" not in df.columns:
        return 0.5
    vol_lower = float(sub.loc[sub["close"] < mid, "volume"].sum())
    vol_total = float(sub["volume"].sum())
    return vol_lower / vol_total if vol_total > 0 else 0.5


# ── Core classifier ───────────────────────────────────────────────────────────

def classify_phase(df: pd.DataFrame, timeframe: str, lookback_bars: int = 60) -> PhaseResult:
    """Classify the current market phase for a single timeframe.

    Parameters
    ----------
    df:           OHLCV DataFrame (DatetimeIndex, sorted ascending)
    timeframe:    label string ("1d" / "4h" / "1h" / "15m")
    lookback_bars: bars to consider for phase detection
    """
    if df is None or len(df) < 10:
        return PhaseResult(
            timeframe=timeframe,
            label=Phase.RANGE,
            confidence=0.0,
            direction_bias=0,
            bars_in_phase=0,
            key_levels={},
            notes=["insufficient_data"],
        )

    sub = df.tail(lookback_bars).copy()
    notes: list[str] = []

    # Swing structure (use smaller swing_n for faster TFs)
    swing_n = 2 if timeframe in ("15m", "1h") else 3
    highs, lows = _swing_structure(sub, swing_n)

    # Range check first
    range_lookback = min(lookback_bars, 20)
    is_range, rh, rl = _range_bound(sub, lookback=range_lookback)
    span_pct = (rh - rl) / rl * 100 if rl > 0 else 0.0

    # Trend structure — use n=2 for real market data (n=3 too strict; 2 consecutive HH/HL is sufficient signal)
    trending_up   = _hh_hl(highs, lows, n=2)
    trending_down = _lh_ll(highs, lows, n=2)

    # Volume signals
    vol_slope = _vol_trend(sub)
    atr_pct   = _atr_percentile(sub)
    acc_depth = _consolidation_depth(sub)

    # Current price vs recent range
    current_price = float(sub["close"].iloc[-1])
    price_in_upper_quarter = current_price > rl + 0.75 * (rh - rl) if rh > rl else False
    price_in_lower_quarter = current_price < rl + 0.25 * (rh - rl) if rh > rl else False

    # Bars since last phase change (rough estimate from swing count)
    bars_in_phase = min(len(sub), max(5, len(highs) * swing_n * 2))

    key_levels: dict[str, float] = {
        "range_high": round(rh, 2),
        "range_low":  round(rl, 2),
        "current":    round(current_price, 2),
    }

    # ── Classification logic ──────────────────────────────────────────────────

    confidence = 0.0
    label = Phase.RANGE
    direction_bias = 0

    if trending_up and not is_range:
        # Distinguish ACCUMULATION vs MARKUP
        if vol_slope > 0.1 and not price_in_upper_quarter:
            label = Phase.MARKUP
            confidence = 55 + min(30, vol_slope * 30)
            direction_bias = 1
            notes.append(f"HH/HL confirmed, vol_slope={vol_slope:.2f}")
        elif price_in_upper_quarter and atr_pct > 60:
            # High volatility at top — possible distribution starting
            label = Phase.DISTRIBUTION
            confidence = 40
            direction_bias = -1
            notes.append(f"price_in_upper_quarter, atr_pct={atr_pct:.0f}")
        else:
            label = Phase.MARKUP
            confidence = 45
            direction_bias = 1
            notes.append(f"HH/HL, vol_slope={vol_slope:.2f}")

    elif trending_down and not is_range:
        if vol_slope > 0.1 and not price_in_lower_quarter:
            label = Phase.MARKDOWN
            confidence = 55 + min(30, vol_slope * 30)
            direction_bias = -1
            notes.append(f"LH/LL confirmed, vol_slope={vol_slope:.2f}")
        elif price_in_lower_quarter and atr_pct > 60:
            label = Phase.ACCUMULATION
            confidence = 40
            direction_bias = 1
            notes.append(f"price_in_lower_quarter, atr_pct={atr_pct:.0f}")
        else:
            label = Phase.MARKDOWN
            confidence = 45
            direction_bias = -1
            notes.append(f"LH/LL, vol_slope={vol_slope:.2f}")

    elif is_range:
        # Range — distinguish accumulation vs distribution vs neutral
        if price_in_lower_quarter and acc_depth > 0.6:
            label = Phase.ACCUMULATION
            confidence = 50 + acc_depth * 20
            direction_bias = 1
            notes.append(f"range_low, acc_depth={acc_depth:.2f}")
        elif price_in_upper_quarter and acc_depth < 0.4:
            label = Phase.DISTRIBUTION
            confidence = 50 + (1 - acc_depth) * 20
            direction_bias = -1
            notes.append(f"range_high, acc_depth={acc_depth:.2f}")
        else:
            label = Phase.RANGE
            confidence = 40 + (1 - span_pct / 10) * 20  # tighter range = more confident RANGE
            direction_bias = 0
            notes.append(f"span={span_pct:.1f}%")

    else:
        # Neither clear trend nor range — transition
        label = Phase.TRANSITION
        confidence = 30
        direction_bias = 0
        notes.append(f"highs={len(highs)}, lows={len(lows)}, is_range={is_range}")

    confidence = float(np.clip(confidence, 0.0, 95.0))

    return PhaseResult(
        timeframe=timeframe,
        label=label,
        confidence=confidence,
        direction_bias=direction_bias,
        bars_in_phase=bars_in_phase,
        key_levels=key_levels,
        notes=notes,
    )


# ── Multi-timeframe coherence ─────────────────────────────────────────────────

def build_mtf_phase_state(
    frames: dict[str, Optional[pd.DataFrame]],
    now: Optional[pd.Timestamp] = None,
) -> MTFPhaseState:
    """Classify phases for all provided timeframes and assess coherence.

    Parameters
    ----------
    frames:  dict mapping timeframe → DataFrame (OHLCV, DatetimeIndex)
             Expected keys: "1d", "4h", "1h", "15m" (any subset is OK)
    now:     current timestamp (defaults to utcnow)
    """
    if now is None:
        now = pd.Timestamp.utcnow()

    phases: dict[str, PhaseResult] = {}
    for tf, df in frames.items():
        if df is not None and not df.empty:
            phases[tf] = classify_phase(df, tf)
        else:
            phases[tf] = PhaseResult(
                timeframe=tf,
                label=Phase.RANGE,
                confidence=0.0,
                direction_bias=0,
                bars_in_phase=0,
                key_levels={},
                notes=["no_data"],
            )

    # Macro = 1d (fallback to 4h if 1d unavailable)
    if not phases:
        macro = PhaseResult(
            timeframe="none", label=Phase.RANGE, confidence=0.0,
            direction_bias=0, bars_in_phase=0, key_levels={}, notes=["no_data"],
        )
    else:
        macro = phases.get("1d") or phases.get("4h") or next(iter(phases.values()))
    macro_label = macro.label
    macro_bias  = macro.direction_bias

    # Coherence: do 4h and 1h agree with 1d direction?
    sub_tfs = [phases[k] for k in ("4h", "1h") if k in phases]
    if sub_tfs:
        agree = all(
            p.direction_bias == macro_bias or p.direction_bias == 0
            for p in sub_tfs
        )
    else:
        agree = True

    coherent = agree

    # Build coherence note
    label_str = macro_label.value
    sub_notes = " | ".join(
        f"{p.timeframe}:{p.label.value}({p.confidence:.0f}%)"
        for p in phases.values()
    )
    if coherent and macro_bias != 0:
        direction_word = "bullish" if macro_bias > 0 else "bearish"
        coherence_note = f"1d {label_str} + sub-TFs agree: {direction_word}"
    elif not coherent:
        meso_label = phases.get("4h", macro).label.value
        micro_label = phases.get("1h", macro).label.value
        coherence_note = (
            f"1d {label_str} vs 4h {meso_label} vs 1h {micro_label} — "
            f"{'pullback within macro trend' if macro_bias != 0 else 'mixed signals'}"
        )
    else:
        coherence_note = f"1d {label_str} (neutral macro)"

    return MTFPhaseState(
        ts=now,
        phases=phases,
        coherent=coherent,
        macro_label=macro_label,
        macro_bias=macro_bias,
        coherence_note=coherence_note,
    )


# ── Historical phase backtest (for checkpoint 1) ──────────────────────────────

def run_phase_history(
    df_1d: pd.DataFrame,
    df_4h: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    step_bars: int = 1,
    lookback: int = 60,
) -> pd.DataFrame:
    """Run phase classifier over historical data. Returns DataFrame with per-bar phase labels.

    Used for: sanity-checking phase distribution, identifying obvious episodes.

    Parameters
    ----------
    df_1d:       1d OHLCV (DatetimeIndex ascending)
    df_4h:       4h OHLCV (optional)
    df_1h:       1h OHLCV (optional)
    step_bars:   how often to re-classify (1 = every bar, higher = faster)
    lookback:    lookback bars per classification
    """
    if df_1d is None or len(df_1d) < lookback + 1:
        return pd.DataFrame()

    records: list[dict] = []

    for i in range(lookback, len(df_1d), step_bars):
        window_1d = df_1d.iloc[:i + 1]
        ts = df_1d.index[i]

        frames: dict[str, Optional[pd.DataFrame]] = {"1d": window_1d}

        if df_4h is not None:
            mask_4h = df_4h.index <= ts
            frames["4h"] = df_4h[mask_4h].tail(lookback * 6) if mask_4h.any() else None
        if df_1h is not None:
            mask_1h = df_1h.index <= ts
            frames["1h"] = df_1h[mask_1h].tail(lookback * 24) if mask_1h.any() else None

        state = build_mtf_phase_state(frames, now=ts)
        macro = state.phases.get("1d")
        records.append({
            "ts": ts,
            "1d_phase": macro.label.value if macro else "unknown",
            "1d_confidence": macro.confidence if macro else 0.0,
            "4h_phase": state.phases.get("4h", PhaseResult("4h", Phase.RANGE, 0, 0, 0, {})).label.value,
            "1h_phase": state.phases.get("1h", PhaseResult("1h", Phase.RANGE, 0, 0, 0, {})).label.value,
            "coherent": state.coherent,
            "macro_bias": state.macro_bias,
            "coherence_note": state.coherence_note,
            "close": float(df_1d["close"].iloc[i]),
        })

    return pd.DataFrame(records).set_index("ts")
