"""TZ-LONG-TP-SWEEP — stress-test LONG bot on 5 target_pct values.

Per Block 13 brief.

Bot config (frozen):
  side=LONG (COIN-M inverse XBTUSD)
  order_size = $100 USD contracts
  max_orders = effectively unlimited (10**9)
  grid_step_pct = 0.03
  no indicator gate, no instop, no out_stop_group
  boundaries disabled (max_orders huge)

TP sweep: 0.21 / 0.25 / 0.29 / 0.34 / 0.40 (percent)
Dataset: 1h BTC, 2025-05-01 → 2026-05-01
Per-regime split: MARKUP / MARKDOWN / RANGE (DISTRIBUTION absent in source)
Commission: 0.05% per cycle on volume (gross + net both reported)

NO winner picked. Pure mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from services.calibration.sim import GridBotSim


# ── Frozen parameters ─────────────────────────────────────────────────────────

TP_VALUES_PCT = (0.21, 0.25, 0.29, 0.34, 0.40)
GRID_STEP_PCT = 0.03
ORDER_SIZE_USD = 100.0
MAX_ORDERS_UNCAPPED = 10**9
COMMISSION_PCT = 0.05  # per cycle (taker/maker mid)

# Stop / instop defaults (documented as Configuration in the report)
INSTOP_PCT = 0.0          # disabled
INDICATOR_PERIOD = 0      # disabled
INDICATOR_THRESHOLD = 0.0 # disabled
USE_OUT_STOP_GROUP = False
MIN_STOP_PCT = 0.0
MAX_STOP_PCT = 0.0


_REGIME_NAMES = {1: "MARKUP", -1: "MARKDOWN", 0: "RANGE"}


# ── Result container ─────────────────────────────────────────────────────────

@dataclass
class TPCellResult:
    tp_pct: float
    period_label: str          # "FULL_YEAR" | "MARKUP" | "MARKDOWN" | "RANGE"
    n_bars: int
    pnl_btc_gross: float       # raw realized in BTC
    pnl_usd_gross: float       # converted via mean close
    pnl_usd_net: float         # gross minus commission
    commission_usd: float
    max_position_btc: float    # peak open_orders qty in BTC equivalent
    max_dd_usd: float          # max drawdown on equity in USD
    n_cycles: int
    avg_cycle_hours: float
    equity_curve_usd: list[float] = field(default_factory=list)
    equity_curve_index: list[str] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)


# ── Dataset loader (1h, full year) ───────────────────────────────────────────

def load_1h_with_regime(
    ohlcv_csv: Path = Path("backtests/frozen/BTCUSDT_1h_2y.csv"),
    features_parquet: Path = Path("data/forecast_features/full_features_1y.parquet"),
) -> pd.DataFrame:
    """Load 1h BTC OHLCV + regime label from features parquet (resampled 5m→1h)."""
    ohlcv = pd.read_csv(ohlcv_csv)
    ohlcv["ts"] = pd.to_datetime(ohlcv["ts"], unit="ms", utc=True)
    ohlcv = ohlcv.set_index("ts")

    feat = pd.read_parquet(features_parquet, columns=["regime_int"])
    feat_1h = feat.resample("1h").agg({
        "regime_int": lambda x: int(x.mode()[0]) if len(x) > 0 else 0,
    })

    df = ohlcv.join(feat_1h, how="inner").dropna(subset=["close"])
    # Restrict to GA window
    mask = (df.index >= pd.Timestamp("2025-05-01", tz="UTC")) & \
           (df.index < pd.Timestamp("2026-05-01", tz="UTC"))
    df = df[mask]
    return df


# ── Single-cell run ──────────────────────────────────────────────────────────

def _run_sim(bars: pd.DataFrame, tp_pct: float) -> tuple[GridBotSim, list[float], list[float]]:
    """Run GridBotSim over `bars`. Returns (sim, equity_usd, max_position_btc_curve)."""
    sim = GridBotSim(
        side="LONG",
        order_size=ORDER_SIZE_USD,
        grid_step_pct=GRID_STEP_PCT,
        target_pct=tp_pct,
        max_orders=MAX_ORDERS_UNCAPPED,
        instop_pct=INSTOP_PCT,
        indicator_period=INDICATOR_PERIOD,
        indicator_threshold_pct=INDICATOR_THRESHOLD,
        use_out_stop_group=USE_OUT_STOP_GROUP,
        max_stop_pct=MAX_STOP_PCT,
        min_stop_pct=MIN_STOP_PCT,
    )
    equity_usd: list[float] = []
    max_pos_btc_curve: list[float] = []

    for _, row in bars.iterrows():
        sim.feed_bar(
            float(row["open"]), float(row["high"]),
            float(row["low"]), float(row["close"]), mode="raw",
        )
        close = float(row["close"])
        # LONG PnL is BTC; multiply by close for USD-equivalent equity
        eq_usd = (sim.realized_pnl + sim._unrealized(close)) * close
        equity_usd.append(eq_usd)
        # Position in BTC = sum of (qty / entry) for open orders (qty in USD contracts)
        pos_btc = sum(o.qty / o.entry for o in sim.open_orders) if sim.open_orders else 0.0
        max_pos_btc_curve.append(pos_btc)

    return sim, equity_usd, max_pos_btc_curve


def _compute_max_dd(equity: list[float]) -> float:
    if not equity:
        return 0.0
    arr = np.array(equity, dtype=float)
    peaks = np.maximum.accumulate(arr)
    dd = peaks - arr  # positive number = how far below peak
    return round(float(dd.max()), 2)


def run_tp_cell(tp_pct: float, bars: pd.DataFrame, period_label: str) -> TPCellResult:
    """Run one TP value over `bars`. Period_label for the report."""
    if len(bars) < 2:
        return TPCellResult(
            tp_pct=tp_pct, period_label=period_label, n_bars=len(bars),
            pnl_btc_gross=0.0, pnl_usd_gross=0.0, pnl_usd_net=0.0,
            commission_usd=0.0, max_position_btc=0.0, max_dd_usd=0.0,
            n_cycles=0, avg_cycle_hours=0.0,
            edge_cases=["insufficient bars"],
        )

    sim, equity_usd, max_pos_curve = _run_sim(bars, tp_pct)
    result = sim.result()

    mean_close = float(bars["close"].mean())
    pnl_btc_gross = result.realized_pnl
    pnl_usd_gross = pnl_btc_gross * mean_close

    commission_usd = result.trading_volume_usd * (COMMISSION_PCT / 100.0)
    pnl_usd_net = pnl_usd_gross - commission_usd

    # Average cycle duration: total bars / cycles, × 1h
    avg_cycle_h = (len(bars) / result.num_fills) if result.num_fills > 0 else 0.0

    edge_cases: list[str] = []
    if result.num_fills == 0:
        edge_cases.append("no completed cycles in this window")
    if max(max_pos_curve, default=0.0) > 10:
        peak_idx = int(np.argmax(max_pos_curve))
        peak_ts = bars.index[peak_idx]
        edge_cases.append(
            f"position accumulated to {max(max_pos_curve):.2f} BTC at {peak_ts.date()}"
        )
    if pnl_usd_net < 0 and pnl_usd_gross > 0:
        edge_cases.append(
            f"commission flipped sign: gross +{pnl_usd_gross:.0f}, net {pnl_usd_net:.0f}"
        )

    # Curve indices as ISO dates (sample every 24 bars to keep size reasonable)
    sample_every = max(1, len(bars) // 200)
    eq_sampled = equity_usd[::sample_every]
    idx_sampled = [str(bars.index[i]) for i in range(0, len(bars), sample_every)]

    return TPCellResult(
        tp_pct=tp_pct,
        period_label=period_label,
        n_bars=len(bars),
        pnl_btc_gross=round(pnl_btc_gross, 6),
        pnl_usd_gross=round(pnl_usd_gross, 2),
        pnl_usd_net=round(pnl_usd_net, 2),
        commission_usd=round(commission_usd, 2),
        max_position_btc=round(max(max_pos_curve, default=0.0), 4),
        max_dd_usd=_compute_max_dd(equity_usd),
        n_cycles=result.num_fills,
        avg_cycle_hours=round(avg_cycle_h, 2),
        equity_curve_usd=[round(v, 2) for v in eq_sampled],
        equity_curve_index=idx_sampled,
        edge_cases=edge_cases,
    )


# ── Period-filter helpers ────────────────────────────────────────────────────

def filter_by_regime(df: pd.DataFrame, regime_int: int) -> pd.DataFrame:
    """Pick only bars with the given regime_int. Note: discontinuous in time."""
    return df[df["regime_int"] == regime_int]


# ── Full sweep runner ────────────────────────────────────────────────────────

def run_full_sweep(df_1h: pd.DataFrame | None = None) -> list[TPCellResult]:
    """5 TP × 4 windows = 20 cells."""
    if df_1h is None:
        df_1h = load_1h_with_regime()
    cells: list[TPCellResult] = []
    for tp in TP_VALUES_PCT:
        cells.append(run_tp_cell(tp, df_1h, "FULL_YEAR"))
        for r_int, r_name in _REGIME_NAMES.items():
            sub = filter_by_regime(df_1h, r_int)
            cells.append(run_tp_cell(tp, sub, r_name))
    return cells
