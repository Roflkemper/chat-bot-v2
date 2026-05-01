from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .combo_filter import filter_setups
from .models import Setup
from .setup_types import DETECTOR_REGISTRY, DetectionContext, PortfolioSnapshot
from .storage import SetupStorage
from .telegram_card import format_telegram_card

logger = logging.getLogger(__name__)

_LOOP_INTERVAL_SEC = 300  # 5 min
_MIN_STRENGTH = 6


def _build_detection_context(pair: str = "BTCUSDT") -> DetectionContext | None:
    """Build live DetectionContext from core pipeline. Returns None on failure."""
    try:
        import pandas as pd

        from core.data_loader import load_klines
        from core.pipeline import build_full_snapshot
        from services.advise_v2.regime_adapter import map_regime_dict_to_advise_label
        from services.advise_v2.session_intelligence import compute_session_context

        snapshot = build_full_snapshot(symbol=pair)
        current_price = float(snapshot.get("price", 0.0))
        if current_price <= 0.0:
            logger.warning("setup_detector.build_context: invalid price for %s", pair)
            return None

        regime = snapshot.get("regime", {})
        regime_label = map_regime_dict_to_advise_label(regime)

        now_utc = datetime.now(timezone.utc)
        session_ctx = compute_session_context(now_utc)
        session_label = session_ctx.kz_active

        df_1m: pd.DataFrame = load_klines(symbol=pair, timeframe="1m", limit=200)
        df_1h: pd.DataFrame = load_klines(symbol=pair, timeframe="1h", limit=50)
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
) -> None:
    """5-minute async loop: build context → run detectors → write + notify."""
    store = storage or SetupStorage()

    while not stop_event.is_set():
        for pair in pairs:
            ctx = _build_detection_context(pair)
            if ctx is None:
                continue
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
            card = format_telegram_card(setup)
            try:
                callable(send_fn) and send_fn(card)  # type: ignore[operator]
            except Exception:
                logger.exception("setup_detector.send_failed type=%s", setup.setup_type.value)

    return new_setups
