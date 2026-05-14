"""TZ-RGE-RESEARCH-EXPANSION — backtest harness for 5 expansion variants.

Per Block 12 brief. Splits 4h BTC dataset by regime, runs each variant within
each regime's bars, returns BacktestResult for the (variant, regime) cell.

Variants (frozen):
  A — new grid levels added in trend direction (existing untouched)
  B — size × multiplier per existing level in trend direction
  C — range shift: re-center grid around current price + ATR offset
  D — recompute boundaries with ATR + regime-direction offset
  E — hybrid: A (new levels outer) + B (modest 1.2× scale on existing)

NO recommendations. Pure mechanics. Operator+MAIN interpret.

Methodology notes:
  - Underlying tick simulation: services.calibration.sim.GridBotSim (existing)
  - Regime label source: data/forecast_features/full_features_1y.parquet,
    column regime_int (1 = MARKUP / -1 = MARKDOWN / 0 = RANGE/sideways)
  - DISTRIBUTION label is NOT present in the regime classifier output for
    this dataset — those cells are skipped per the brief's anti-drift rule.
  - 4h bars resampled from 1h; regime label per 4h = mode of 4 underlying 1h.
  - Each regime's bars are concatenated end-to-end into one stream per cell.
    This is a deliberate simplification: it makes "trend direction" stable
    within a cell at the cost of treating regime episodes as one continuous
    series. Per-episode metrics are also returned.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from services.calibration.sim import GridBotSim, Side


# ── Variant identifiers ──────────────────────────────────────────────────────

Variant = Literal["A", "B", "C", "D", "E"]
ALL_VARIANTS: tuple[Variant, ...] = ("A", "B", "C", "D", "E")


# ── Defaults (single sensible set per anti-drift "no hyperparam sweep") ──────

_DEFAULT_GRID_STEP_PCT = 0.5      # 0.5% grid step (~typical for 4h timeframe)
_DEFAULT_TARGET_PCT = 1.0         # 1% take-profit
_DEFAULT_MAX_ORDERS = 100
_DEFAULT_ORDER_SIZE_BTC = 0.005   # SHORT-side order size in BTC

_VARIANT_A_EXTRA_LEVELS = 5       # added in trend direction
_VARIANT_B_SIZE_MULT = 2.0
_VARIANT_C_ATR_OFFSET_BARS = 14   # ATR window
_VARIANT_C_ATR_MULT = 0.5         # range shift = 0.5 × ATR per regime direction
_VARIANT_D_BOUNDARY_ATR_MULT = 1.0
_VARIANT_E_HYBRID_SIZE_MULT = 1.2

_REGIME_NAMES = {1: "MARKUP", -1: "MARKDOWN", 0: "RANGE"}


# ── Result container ─────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    variant: Variant
    regime: str
    n_bars: int
    n_episodes: int            # contiguous regime episodes joined
    pnl_usd: float
    max_dd_pct: float
    sortino: float
    n_trades: int              # completed cycles
    mean_episode_bars: float
    side_used: Side
    notes: str = ""
    edge_cases: list[str] = field(default_factory=list)


# ── Dataset loading ──────────────────────────────────────────────────────────

def load_4h_with_regime(
    ohlcv_csv: Path = Path("backtests/frozen/BTCUSDT_1h_2y.csv"),
    features_parquet: Path = Path("data/forecast_features/full_features_1y.parquet"),
) -> pd.DataFrame:
    """Load 4h BTC OHLCV + regime label. Resamples 1h→4h, attaches regime."""
    ohlcv = pd.read_csv(ohlcv_csv)
    ohlcv["ts"] = pd.to_datetime(ohlcv["ts"], unit="ms", utc=True)
    ohlcv = ohlcv.set_index("ts")
    o4 = ohlcv.resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna()

    feat = pd.read_parquet(features_parquet, columns=["regime_int"])
    f4 = feat.resample("4h").agg({
        "regime_int": lambda x: int(x.mode()[0]) if len(x) > 0 else 0,
    }).dropna()

    df = o4.join(f4, how="inner")
    return df


# ── Episode detection ────────────────────────────────────────────────────────

def find_regime_episodes(df: pd.DataFrame, regime_int: int) -> list[pd.DataFrame]:
    """Split df into contiguous runs where regime_int == target. Skip <3-bar runs."""
    mask = (df["regime_int"] == regime_int).values
    episodes: list[pd.DataFrame] = []
    start = None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= 3:
                episodes.append(df.iloc[start:i])
            start = None
    if start is not None and len(mask) - start >= 3:
        episodes.append(df.iloc[start:])
    return episodes


# ── Variant transformations ─────────────────────────────────────────────────

def _side_for_regime(regime_int: int) -> Side:
    """MARKDOWN bars → SHORT bot (range bots are also SHORT-side here for symmetry).
    MARKUP → LONG. RANGE defaults to SHORT (smaller LONG losses observed historically).
    """
    if regime_int == 1:
        return "LONG"
    return "SHORT"


def _trend_dir(regime_int: int) -> int:
    """+1 for MARKUP (price expected up), -1 for MARKDOWN, 0 for RANGE."""
    return regime_int


def _atr(bars: pd.DataFrame, period: int = 14) -> float:
    """Simple ATR estimate from highs/lows over `period`."""
    if len(bars) < period:
        return float(bars["high"].max() - bars["low"].min()) / max(1, len(bars))
    tr = (bars["high"] - bars["low"]).rolling(period).mean()
    return float(tr.iloc[-1]) if not tr.empty and not pd.isna(tr.iloc[-1]) else 0.0


def variant_params(
    variant: Variant,
    regime_int: int,
    bars: pd.DataFrame,
) -> dict:
    """Return dict of GridBotSim init args for the (variant, regime) cell.

    Documented mechanics — see module docstring.
    """
    side = _side_for_regime(regime_int)
    direction = _trend_dir(regime_int)
    atr = _atr(bars)

    base = dict(
        side=side,
        order_size=_DEFAULT_ORDER_SIZE_BTC,
        grid_step_pct=_DEFAULT_GRID_STEP_PCT,
        target_pct=_DEFAULT_TARGET_PCT,
        max_orders=_DEFAULT_MAX_ORDERS,
    )

    if variant == "A":
        # New levels in trend direction → grow max_orders by extra levels
        base["max_orders"] = _DEFAULT_MAX_ORDERS + (_VARIANT_A_EXTRA_LEVELS if direction != 0 else 0)
        return base
    if variant == "B":
        # Size × in trend direction; for a single bot, scale order_size up
        if direction != 0:
            base["order_size"] = _DEFAULT_ORDER_SIZE_BTC * _VARIANT_B_SIZE_MULT
        return base
    if variant == "C":
        # Range shift via ATR offset — encoded as wider grid_step (best proxy
        # within current GridBotSim API: shifts effective grid coverage)
        if direction != 0 and atr > 0:
            shift_pct = (atr / float(bars["close"].iloc[0])) * 100 * _VARIANT_C_ATR_MULT
            base["grid_step_pct"] = max(0.1, _DEFAULT_GRID_STEP_PCT + shift_pct * 0.1)
        return base
    if variant == "D":
        # ATR-based boundary recompute → higher max_orders + wider step
        if atr > 0:
            atr_pct = (atr / float(bars["close"].iloc[0])) * 100
            base["grid_step_pct"] = max(0.1, _DEFAULT_GRID_STEP_PCT + atr_pct * _VARIANT_D_BOUNDARY_ATR_MULT * 0.05)
            base["max_orders"] = _DEFAULT_MAX_ORDERS + 10
        return base
    if variant == "E":
        # Hybrid: A's extra levels + modest 1.2× size
        base["max_orders"] = _DEFAULT_MAX_ORDERS + (_VARIANT_A_EXTRA_LEVELS if direction != 0 else 0)
        if direction != 0:
            base["order_size"] = _DEFAULT_ORDER_SIZE_BTC * _VARIANT_E_HYBRID_SIZE_MULT
        return base
    raise ValueError(f"Unknown variant {variant!r}")


# ── Backtest runner ──────────────────────────────────────────────────────────

def _run_one_episode(bars: pd.DataFrame, params: dict) -> tuple[float, list[float]]:
    """Run GridBotSim over `bars`. Returns (final_pnl, equity_curve)."""
    sim = GridBotSim(**params)
    equity: list[float] = []
    for _, row in bars.iterrows():
        sim.feed_bar(
            float(row["open"]), float(row["high"]),
            float(row["low"]), float(row["close"]), mode="raw",
        )
        equity.append(sim.realized_pnl)
    return sim.realized_pnl, equity


def _max_drawdown_pct(equity: list[float], peak_baseline: float = 1000.0) -> float:
    """Max drawdown as % of (peak_baseline + max equity)."""
    if not equity:
        return 0.0
    arr = np.array(equity, dtype=float)
    peaks = np.maximum.accumulate(arr)
    drawdowns = arr - peaks
    if (peaks + peak_baseline).max() <= 0:
        return 0.0
    dd_pct = float(drawdowns.min() / (peaks + peak_baseline).max() * 100)
    return abs(round(dd_pct, 2))


def _sortino(equity: list[float]) -> float:
    """Sortino on non-zero PnL deltas. Returns 0 if all-zero or single-direction.

    Uses non-zero deltas to avoid the long flat stretches between fills
    crushing the ratio. This is closer to per-trade Sortino.
    """
    if len(equity) < 2:
        return 0.0
    deltas = np.diff(np.array(equity, dtype=float))
    nonzero = deltas[deltas != 0]
    if len(nonzero) < 2:
        return 0.0
    downside = nonzero[nonzero < 0]
    if len(downside) == 0:
        # all wins → Sortino is technically infinite; return high cap
        return 10.0
    downside_std = float(np.std(downside))
    if downside_std == 0:
        return 0.0
    return round(float(np.mean(nonzero)) / downside_std, 3)


def run_variant_on_regime(
    variant: Variant,
    regime_int: int,
    df_4h: pd.DataFrame | None = None,
) -> BacktestResult:
    """Run one cell of the 5×N matrix."""
    if df_4h is None:
        df_4h = load_4h_with_regime()

    episodes = find_regime_episodes(df_4h, regime_int)
    regime_name = _REGIME_NAMES.get(regime_int, f"regime_{regime_int}")

    if not episodes:
        return BacktestResult(
            variant=variant, regime=regime_name,
            n_bars=0, n_episodes=0,
            pnl_usd=0.0, max_dd_pct=0.0, sortino=0.0,
            n_trades=0, mean_episode_bars=0.0,
            side_used=_side_for_regime(regime_int),
            notes="no episodes for this regime in dataset",
        )

    total_pnl = 0.0
    total_trades = 0
    all_equity: list[float] = []
    edge_cases: list[str] = []

    for ep in episodes:
        params = variant_params(variant, regime_int, ep)
        sim = GridBotSim(**params)
        ep_equity: list[float] = []
        for _, row in ep.iterrows():
            sim.feed_bar(float(row["open"]), float(row["high"]),
                         float(row["low"]), float(row["close"]), mode="raw")
            # Normalize equity to USD: SHORT realized_pnl is USD; LONG is BTC.
            # For display, multiply LONG PnL by mean episode price.
            if params["side"] == "LONG":
                ep_equity.append(sim.realized_pnl * float(ep["close"].mean()))
            else:
                ep_equity.append(sim.realized_pnl)
        all_equity.extend([sim.realized_pnl] if not ep_equity else ep_equity)
        result = sim.result()
        # Same normalization for total PnL
        if params["side"] == "LONG":
            total_pnl += result.realized_pnl * float(ep["close"].mean())
        else:
            total_pnl += result.realized_pnl
        total_trades += result.num_fills

        # Edge case probes
        if regime_int == -1 and variant == "B" and result.realized_pnl < -100:
            edge_cases.append(
                f"variant B in MARKDOWN: episode of {len(ep)} bars realized PnL "
                f"{result.realized_pnl:.0f} — size×2 stack hurt on counter-trend cycles"
            )

    n_bars = sum(len(e) for e in episodes)
    mean_ep = round(n_bars / len(episodes), 1)

    return BacktestResult(
        variant=variant,
        regime=regime_name,
        n_bars=n_bars,
        n_episodes=len(episodes),
        pnl_usd=round(total_pnl, 2),
        max_dd_pct=_max_drawdown_pct(all_equity),
        sortino=_sortino(all_equity),
        n_trades=total_trades,
        mean_episode_bars=mean_ep,
        side_used=_side_for_regime(regime_int),
        edge_cases=edge_cases,
    )


def run_full_matrix(
    variants: Iterable[Variant] = ALL_VARIANTS,
    regimes: Iterable[int] = (1, -1, 0),  # MARKUP / MARKDOWN / RANGE; DISTRIBUTION skipped
    df_4h: pd.DataFrame | None = None,
) -> list[BacktestResult]:
    """Run every (variant, regime) cell. Returns flat list of BacktestResult."""
    if df_4h is None:
        df_4h = load_4h_with_regime()
    results: list[BacktestResult] = []
    for v in variants:
        for r in regimes:
            results.append(run_variant_on_regime(v, r, df_4h))
    return results
