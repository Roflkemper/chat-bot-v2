from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import datetime, timezone
from pathlib import Path

from .combo_filter import filter_setups
from .ict_context import ICT_CONTEXT_COLS, ICTContextReader
from .models import Setup
from .setup_types import DETECTOR_REGISTRY, DetectionContext, PortfolioSnapshot
from .storage import SetupStorage
from .telegram_card import format_telegram_card

logger = logging.getLogger(__name__)

_LOOP_INTERVAL_SEC = 300  # 5 min
_MIN_STRENGTH = 6
_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ICT_PARQUET = _ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"


def _simple_session_label(now_utc: datetime) -> str:
    """Fallback session label without advise_v2 dependency."""
    h = now_utc.hour
    if 0 <= h < 8:
        return "asia"
    if 8 <= h < 13:
        return "london"
    if 13 <= h < 17:
        return "ny_am"
    if 17 <= h < 21:
        return "ny_pm"
    return "asia"


def _simple_regime_label(snapshot: dict) -> str:
    """Map raw regime to a simple label without advise_v2."""
    regime = snapshot.get("regime") or {}
    primary = regime.get("primary") or "RANGE"
    mapping = {
        "TREND_UP": "trend_up", "CASCADE_UP": "impulse_up",
        "TREND_DOWN": "trend_down", "CASCADE_DOWN": "impulse_down",
        "RANGE": "range_wide", "COMPRESSION": "consolidation",
    }
    return mapping.get(primary, "range_wide")


def _build_detection_context(pair: str = "BTCUSDT") -> DetectionContext | None:
    """Build live DetectionContext from core pipeline. Returns None on failure.

    No longer depends on services.advise_v2 (which crashed on missing pydantic).
    """
    try:
        import pandas as pd

        from core.data_loader import load_klines
        from core.pipeline import build_full_snapshot

        snapshot = build_full_snapshot(symbol=pair)
        current_price = float(snapshot.get("price", 0.0))
        if current_price <= 0.0:
            logger.warning("setup_detector.build_context: invalid price for %s", pair)
            return None

        regime_label = _simple_regime_label(snapshot)
        now_utc = datetime.now(timezone.utc)
        session_label = _simple_session_label(now_utc)

        df_1m: pd.DataFrame = load_klines(symbol=pair, timeframe="1m", limit=200)
        df_1h: pd.DataFrame = load_klines(symbol=pair, timeframe="1h", limit=50)
        # 15m frame for fast-reaction detectors. limit=200 = ~50h of history,
        # enough for divergence detection (needs >=50 bars). Failure here is
        # non-fatal — detectors that need it guard for empty df_15m.
        try:
            df_15m: pd.DataFrame = load_klines(symbol=pair, timeframe="15m", limit=200)
        except Exception:
            logger.exception("setup_detector.build_context.15m_load_failed pair=%s", pair)
            df_15m = pd.DataFrame()
        if df_1m.empty or df_1h.empty:
            return None

        portfolio = _build_portfolio_snapshot(snapshot)

        return DetectionContext(
            pair=pair,
            current_price=current_price,
            regime_label=regime_label,
            session_label=session_label,
            ohlcv_1m=df_1m,
            ohlcv_1h=df_1h,
            portfolio=portfolio,
            ict_context={},
            ohlcv_15m=df_15m,
        )
    except Exception:
        logger.exception("setup_detector.build_context_failed pair=%s", pair)
        return None


def _build_portfolio_snapshot(snapshot: dict) -> PortfolioSnapshot:
    try:
        state_exposure = snapshot.get("exposure", {})
        free_margin = float(state_exposure.get("free_margin_pct", 100.0) or 100.0)
        net_btc = float(state_exposure.get("net_btc", 0.0) or 0.0)
        return PortfolioSnapshot(free_margin_pct=free_margin, net_btc=net_btc)
    except Exception:
        return PortfolioSnapshot()


async def setup_detector_loop(
    stop_event: asyncio.Event,
    *,
    storage: SetupStorage | None = None,
    send_fn: object = None,
    pairs: tuple[str, ...] = ("BTCUSDT",),
    interval_sec: float = _LOOP_INTERVAL_SEC,
    ict_parquet: str | Path | None = None,
) -> None:
    """5-minute async loop: build context → run detectors → write + notify."""
    store = storage or SetupStorage()
    ict_reader = ICTContextReader.load(ict_parquet or _DEFAULT_ICT_PARQUET)
    if ict_reader.is_loaded():
        logger.info("setup_detector_loop.ict_reader_ready")
    else:
        logger.warning("setup_detector_loop.ict_reader_empty — ICT context will be blank")

    while not stop_event.is_set():
        now_utc = datetime.now(timezone.utc)
        for pair in pairs:
            ctx = _build_detection_context(pair)
            if ctx is None:
                continue
            ctx.ict_context = ict_reader.lookup(now_utc)
            _run_detectors_once(ctx, store, send_fn)

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass


def _run_detectors_once(
    ctx: DetectionContext,
    store: SetupStorage,
    send_fn: object,
) -> list[Setup]:
    """Run all detectors, apply combo filter, store and notify allowed setups."""
    candidates: list[Setup] = []
    ict_ctx = ctx.ict_context  # captured once per tick

    for detector in DETECTOR_REGISTRY:
        try:
            setup = detector(ctx)
            if setup is None:
                continue
            if setup.strength < _MIN_STRENGTH:
                logger.debug(
                    "setup_detector.below_threshold type=%s strength=%d",
                    setup.setup_type.value, setup.strength,
                )
                continue
            # Attach ICT context to each setup (frozen dataclass → use replace)
            if ict_ctx:
                setup = dataclasses.replace(setup, ict_context=ict_ctx)
            candidates.append(setup)
        except Exception:
            logger.exception("setup_detector.detector_failed fn=%s", detector.__name__)

    allowed, blocked = filter_setups(candidates)

    for s in blocked:
        logger.info(
            "setup_detector.combo_blocked type=%s regime=%s pair=%s",
            s.setup_type.value, s.regime_label, s.pair,
        )

    new_setups: list[Setup] = []
    for setup in allowed:
        store.write(setup)
        new_setups.append(setup)
        logger.info(
            "setup_detector.new_setup type=%s pair=%s strength=%d confidence=%.0f%%",
            setup.setup_type.value, setup.pair, setup.strength, setup.confidence_pct,
        )
        if send_fn is not None:
            # If setup qualifies for propose-confirm flow, create a proposal
            # token + send a propose-card; otherwise send the regular setup card.
            try:
                from services.setup_detector.proposals import (
                    create_proposal, format_proposal_card, should_propose,
                )
                use_proposal = should_propose(setup)
            except Exception:
                logger.exception("setup_detector.propose_check_failed")
                use_proposal = False

            try:
                if use_proposal:
                    proposal = create_proposal(setup)
                    card = format_proposal_card(proposal)
                    logger.info(
                        "setup_detector.proposal_created token=%s type=%s conf=%.0f",
                        proposal.token, setup.setup_type.value, setup.confidence_pct,
                    )
                else:
                    card = format_telegram_card(setup)
                # Send via either signature.
                if callable(send_fn):
                    try:
                        send_fn(card, setup)  # type: ignore[call-arg]
                    except TypeError:
                        send_fn(card)  # type: ignore[operator]
            except Exception:
                logger.exception("setup_detector.send_failed type=%s", setup.setup_type.value)

    return new_setups
