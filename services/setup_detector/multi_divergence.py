"""Multi-indicator divergence detector — LONG side only.

Backtest-derived (tools/backtest_signals.py, 2026-05-08, 1h BTCUSDT 2y):
  - Bullish multi-indicator divergence (price LL + indicator HL on confluence>=2)
    yields PF=1.66, WR=56.5% over hold_1h on the unfiltered 124-signal sample.
  - Adding a regime guard ('do not fire when 1h AND 4h are both TREND_DOWN')
    blocks 27% of signals (the bear-zone slice underperforms: PF=0.86 hold_1h)
    and lifts remaining-signal performance to PF=2.13, WR=58% on hold_1h.
  - SHORT-side divergence has NO edge on this dataset (bull-biased period); not
    implemented here.

Algorithm:
  1. Find price pivots (swing lows) on 1h frame using a 5-bar lookback.
  2. For each consecutive pair of swing lows where the second is LOWER than
     the first AND within 30 bars of it, count how many indicators
     {RSI, MFI, OBV, CMF, MACD-hist, Stoch} have their OWN pivot-low near
     each price pivot (±3 bars) where second > first (i.e. higher low).
  3. Confluence = count of agreeing indicators. Setup fires when
     confluence >= 2 AND we are not in the double-trend-down regime.
  4. Confirmation bar = second price pivot + lookback (no lookahead).

The detector returns None if any check fails. Side effects: none. Logging
is informational only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from services.setup_detector.models import Setup, SetupBasis, SetupType, make_setup

logger = logging.getLogger(__name__)

# ── Tuned from backtest ────────────────────────────────────────────────────
PIVOT_LOOKBACK = 5            # bars on each side of a price/indicator pivot
DIV_WINDOW_BARS = 30          # max distance between two paired pivots
INDICATOR_PIVOT_TOLERANCE = 3 # indicator pivot may sit ±N bars from price pivot
MIN_CONFLUENCE = 2            # minimum agreeing indicators (backtest sweet spot)
MAX_PATTERN_AGE_BARS = 20     # ignore signals whose confirmation is older than this
SL_PCT = 1.0                  # default stop distance below entry
TP1_RR = 1.0                  # 1:1
TP2_RR = 2.5                  # 1:2.5

# Regime labels treated as "down" by the guard.
_DOWN_REGIME_LABELS = {"trend_down", "impulse_down"}


@dataclass(frozen=True)
class _Pivots:
    highs: list[int]
    lows: list[int]


def _find_pivots(values: pd.Series, lookback: int = PIVOT_LOOKBACK) -> _Pivots:
    """Return indices of strict pivot highs/lows (strict = unique max/min within window)."""
    arr = values.values
    n = len(arr)
    highs: list[int] = []
    lows: list[int] = []
    for i in range(lookback, n - lookback):
        window = arr[i - lookback : i + lookback + 1]
        center = arr[i]
        if center == window.max() and (window == center).sum() == 1:
            highs.append(i)
        if center == window.min() and (window == center).sum() == 1:
            lows.append(i)
    return _Pivots(highs=highs, lows=lows)


def _nearest_pivot_within(pivots: list[int], target: int, tolerance: int) -> int | None:
    """Return the pivot index closest to `target` within ±tolerance, or None."""
    best = None
    best_dist = tolerance + 1
    for p in pivots:
        d = abs(p - target)
        if d <= tolerance and d < best_dist:
            best = p
            best_dist = d
    return best


# ── Indicator computations (lean re-implementations; the harness uses these
# same formulas for consistency between backtest and production) ──

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    typical = (high + low + close) / 3.0
    raw_mf = typical * volume
    pos_mf = raw_mf.where(typical > typical.shift(1), 0.0)
    neg_mf = raw_mf.where(typical < typical.shift(1), 0.0)
    pos_sum = pos_mf.rolling(period).sum()
    neg_sum = neg_mf.rolling(period).sum()
    ratio = pos_sum / neg_sum.replace(0, float("nan"))
    return 100 - (100 / (1 + ratio))


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = pd.Series(0.0, index=close.index)
    diff = close.diff()
    direction[diff > 0] = 1.0
    direction[diff < 0] = -1.0
    return (direction * volume).cumsum()


def _cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20) -> pd.Series:
    hl = (high - low).replace(0, float("nan"))
    mfm = ((close - low) - (high - close)) / hl
    mfv = mfm * volume
    return mfv.rolling(period).sum() / volume.rolling(period).sum()


def _macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> pd.Series:
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    rng = (highest - lowest).replace(0, float("nan"))
    k = (close - lowest) / rng * 100.0
    return k.rolling(d_period).mean()


def _build_indicators(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "RSI":   _rsi(df["close"], 14),
        "MFI":   _mfi(df["high"], df["low"], df["close"], df["volume"], 14),
        "OBV":   _obv(df["close"], df["volume"]),
        "CMF":   _cmf(df["high"], df["low"], df["close"], df["volume"], 20),
        "MACDh": _macd_hist(df["close"], 12, 26, 9),
        "Stoch": _stoch(df["high"], df["low"], df["close"], 14, 3),
    }


def _agreeing_indicators_for_bullish(
    indicators: dict[str, pd.Series],
    pivots_by_indicator: dict[str, _Pivots],
    prev_price_idx: int,
    cur_price_idx: int,
    tolerance: int,
) -> tuple[str, ...]:
    """Return names of indicators where:
       - both price pivots have a near-by indicator pivot-low (within tolerance), and
       - the second indicator pivot value is HIGHER than the first (HL).
    """
    out: list[str] = []
    for name, ind in indicators.items():
        ind_pivots = pivots_by_indicator[name]
        prev_pi = _nearest_pivot_within(ind_pivots.lows, prev_price_idx, tolerance)
        cur_pi = _nearest_pivot_within(ind_pivots.lows, cur_price_idx, tolerance)
        if prev_pi is None or cur_pi is None:
            continue
        prev_val = ind.iloc[prev_pi]
        cur_val = ind.iloc[cur_pi]
        if pd.isna(prev_val) or pd.isna(cur_val):
            continue
        if cur_val > prev_val:
            out.append(name)
    return tuple(out)


def _is_double_trend_down(ctx) -> bool:
    """True iff the regime guard should suppress the signal.

    DetectionContext exposes a single regime_label coming from the live regime
    classifier. We treat it as a 1h proxy. Without an authoritative 4h regime
    in the context, we fall back to the more conservative 1h-only check —
    which still captures the vast majority of the bear zone identified in the
    backtest (1h trend_down covers 29.8% of bars vs 19.4% for the strict
    1h&4h combo). This is intentional over-blocking: better to miss a few
    valid signals than fire bullish setups in the heart of a downtrend.
    """
    return str(ctx.regime_label or "").lower() in _DOWN_REGIME_LABELS


def detect_long_multi_divergence(ctx) -> Setup | None:
    """Bullish multi-indicator divergence on 1h.

    Fires when at least MIN_CONFLUENCE of {RSI, MFI, OBV, CMF, MACD-hist, Stoch}
    agree with a price LL pattern (each indicator independently makes a HL near
    each price pivot). Suppressed by the regime guard during deep downtrends.
    """
    df = ctx.ohlcv_1h
    if df is None or len(df) < 50:
        return None
    if not all(col in df.columns for col in ("high", "low", "close", "volume")):
        return None

    if _is_double_trend_down(ctx):
        return None

    # 1) Price pivot lows.
    price_pivots = _find_pivots(df["low"])
    if len(price_pivots.lows) < 2:
        return None

    # 2) Build indicators + pre-compute their pivots once.
    indicators = _build_indicators(df)
    pivots_by_indicator = {name: _find_pivots(ind) for name, ind in indicators.items()}

    n = len(df)
    last_close = float(df["close"].iloc[-1])

    # 3) Walk price-low pairs from most recent backwards. Return the first
    # confirmed signal whose confirmation bar is recent (≤ MAX_PATTERN_AGE_BARS).
    for j in range(len(price_pivots.lows) - 1, 0, -1):
        cur_idx = price_pivots.lows[j]
        prev_idx = price_pivots.lows[j - 1]
        if cur_idx - prev_idx > DIV_WINDOW_BARS:
            continue
        cur_low = float(df["low"].iloc[cur_idx])
        prev_low = float(df["low"].iloc[prev_idx])
        if cur_low >= prev_low:
            continue  # not LL on price

        # Confirmation lives PIVOT_LOOKBACK bars after the pivot bar.
        conf_idx = cur_idx + PIVOT_LOOKBACK
        if conf_idx >= n:
            return None  # not yet confirmed
        if (n - 1 - conf_idx) > MAX_PATTERN_AGE_BARS:
            return None  # latest fresh pattern is too old; further pairs older still

        agreeing = _agreeing_indicators_for_bullish(
            indicators, pivots_by_indicator,
            prev_idx, cur_idx, INDICATOR_PIVOT_TOLERANCE,
        )
        if len(agreeing) < MIN_CONFLUENCE:
            continue

        # Geometry from the pattern.
        entry = last_close
        stop = entry * (1 - SL_PCT / 100.0)
        risk = entry - stop
        tp1 = entry + risk * TP1_RR
        tp2 = entry + risk * TP2_RR
        rr = (tp1 - entry) / max(entry - stop, 1e-9)

        # Confidence scales with confluence: 2/6 → 60%, 3/6 → 70%, 4+/6 → 80%.
        confidence_pct = 60.0 + (len(agreeing) - MIN_CONFLUENCE) * 10.0
        confidence_pct = min(85.0, confidence_pct)
        strength = 6 + min(3, len(agreeing) - MIN_CONFLUENCE + 1)  # 7..9

        basis_items = [
            SetupBasis("price_LL_prev", round(prev_low, 1), 0.25),
            SetupBasis("price_LL_cur", round(cur_low, 1), 0.25),
            SetupBasis("confluence_count", len(agreeing), 0.30),
            SetupBasis("agreeing_indicators", "+".join(agreeing), 0.20),
        ]

        return make_setup(
            setup_type=SetupType.LONG_MULTI_DIVERGENCE,
            pair=ctx.pair,
            current_price=last_close,
            regime_label=ctx.regime_label,
            session_label=ctx.session_label,
            entry_price=round(entry, 1),
            stop_price=round(stop, 1),
            tp1_price=round(tp1, 1),
            tp2_price=round(tp2, 1),
            risk_reward=round(rr, 2),
            strength=strength,
            confidence_pct=confidence_pct,
            basis=tuple(basis_items),
            cancel_conditions=(
                f"close below {stop:.0f} invalidates divergence",
                f"pattern age > {MAX_PATTERN_AGE_BARS}h",
                f"regime turns trend_down on 1h",
            ),
            window_minutes=240,  # 4h target horizon per backtest
            portfolio_impact_note=(
                f"Bullish divergence: price LL ({prev_low:.0f}->{cur_low:.0f}), "
                f"{len(agreeing)}/6 indicators HL [{'+'.join(agreeing)}]. "
                f"Backtest PF~1.66, WR~56% on hold_1h."
            ),
        )

    return None
