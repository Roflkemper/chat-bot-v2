"""Liquidation cluster detector — fires LONG when one-sided liquidations
spike (large LONG liquidations = forced sells = bottom signal).

Hypothesis: when $1M+ of LONG liquidations happen in a 5-minute window,
shorts have just received a transfer of stops → likely bounce coming.

This is symmetric — for SHORT bounce signal we'd look at SHORT liquidations
spike, but in current market shorts are crowded so this is mainly LONG side.

Logic:
  Read last 60 minutes of liquidations from market_live/liquidations.csv.
  Sum value_usd over LONG side and SHORT side over last 5min.
  If LONG_liq_5min >= $1M AND SHORT_liq_5min < LONG_liq_5min × 0.3:
    → emit LONG_LIQ_MAGNET (oversold, capitulation done)
  If SHORT_liq_5min >= $1M AND LONG_liq_5min < SHORT_liq_5min × 0.3:
    → emit SHORT_LIQ_MAGNET (top, short squeeze done)

Trade: TP +0.5%, SL -0.4%, hold 60min.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from services.setup_detector.models import (
    Setup,
    SetupBasis,
    SetupType,
    make_setup,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"

LIQ_WINDOW_MIN = 5
LIQ_THRESHOLD_USD = 1_000_000.0  # one side total
LIQ_DOMINANCE_RATIO = 0.3        # other side must be <= this × dominant
TP_PCT = 0.5
SL_PCT = 0.4
HOLD_MIN = 60


def _load_recent_liquidations(window_min: int = LIQ_WINDOW_MIN) -> pd.DataFrame:
    """Load last `window_min` minutes of liquidations from rolling CSV."""
    if not LIQ_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(LIQ_CSV)
    except Exception:
        return pd.DataFrame()
    if "ts_utc" not in df.columns:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df = df.dropna(subset=["price", "qty"])
    df["value_usd"] = df["qty"] * df["price"]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)
    df = df[df["ts"] >= cutoff]
    return df


def detect_long_liq_cluster(ctx) -> Setup | None:
    """LONG bounce after large LONG liquidations cluster."""
    df = _load_recent_liquidations()
    if df.empty: return None
    long_total = float(df.loc[df["side"] == "long", "value_usd"].sum())
    short_total = float(df.loc[df["side"] == "short", "value_usd"].sum())
    if long_total < LIQ_THRESHOLD_USD: return None
    if short_total > long_total * LIQ_DOMINANCE_RATIO: return None

    entry = float(ctx.current_price)
    if entry <= 0: return None
    tp1 = entry * (1 + TP_PCT / 100)
    tp2 = entry * (1 + TP_PCT * 2 / 100)
    sl = entry * (1 - SL_PCT / 100)
    rr = abs(tp1 - entry) / max(abs(entry - sl), 1e-9)

    return make_setup(
        setup_type=SetupType.LONG_LIQ_MAGNET,
        pair=ctx.pair,
        current_price=entry,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        entry_price=entry,
        stop_price=sl,
        tp1_price=tp1,
        tp2_price=tp2,
        risk_reward=round(rr, 2),
        strength=8,
        confidence_pct=70.0,
        basis=(
            SetupBasis(label="long_liq_5m_usd", value=round(long_total, 0), weight=0.5),
            SetupBasis(label="short_liq_5m_usd", value=round(short_total, 0), weight=0.2),
            SetupBasis(label="dominance_ratio",
                       value=round(short_total / max(long_total, 1), 2), weight=0.3),
        ),
        cancel_conditions=(
            f"hold {HOLD_MIN}min — no bounce",
            f"new long liq cluster — re-fire on next 5min window",
        ),
        window_minutes=HOLD_MIN,
        portfolio_impact_note=(
            f"LONG liq cluster ${long_total/1000:.0f}k vs SHORT ${short_total/1000:.0f}k "
            f"in last 5min → bounce probe"
        ),
    )


def detect_short_liq_cluster(ctx) -> Setup | None:
    """SHORT after large SHORT liquidations cluster (squeeze done)."""
    df = _load_recent_liquidations()
    if df.empty: return None
    long_total = float(df.loc[df["side"] == "long", "value_usd"].sum())
    short_total = float(df.loc[df["side"] == "short", "value_usd"].sum())
    if short_total < LIQ_THRESHOLD_USD: return None
    if long_total > short_total * LIQ_DOMINANCE_RATIO: return None

    entry = float(ctx.current_price)
    if entry <= 0: return None
    tp1 = entry * (1 - TP_PCT / 100)
    tp2 = entry * (1 - TP_PCT * 2 / 100)
    sl = entry * (1 + SL_PCT / 100)
    rr = abs(tp1 - entry) / max(abs(entry - sl), 1e-9)

    return make_setup(
        setup_type=SetupType.SHORT_LIQ_MAGNET,
        pair=ctx.pair,
        current_price=entry,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        entry_price=entry,
        stop_price=sl,
        tp1_price=tp1,
        tp2_price=tp2,
        risk_reward=round(rr, 2),
        strength=8,
        confidence_pct=70.0,
        basis=(
            SetupBasis(label="short_liq_5m_usd", value=round(short_total, 0), weight=0.5),
            SetupBasis(label="long_liq_5m_usd", value=round(long_total, 0), weight=0.2),
            SetupBasis(label="dominance_ratio",
                       value=round(long_total / max(short_total, 1), 2), weight=0.3),
        ),
        cancel_conditions=(
            f"hold {HOLD_MIN}min — no fade",
            f"new short liq cluster — re-fire on next 5min window",
        ),
        window_minutes=HOLD_MIN,
        portfolio_impact_note=(
            f"SHORT liq cluster ${short_total/1000:.0f}k vs LONG ${long_total/1000:.0f}k "
            f"→ fade probe"
        ),
    )
