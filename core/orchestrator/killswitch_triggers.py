from __future__ import annotations

import logging
from typing import Any

from core.orchestrator.killswitch import trigger_killswitch
from core.orchestrator.portfolio_state import PortfolioStore
from core.pipeline import build_full_snapshot

logger = logging.getLogger(__name__)


def check_margin_drawdown_trigger(initial_balance_usd: float, threshold_pct: float) -> None:
    portfolio = PortfolioStore.instance()
    snapshot = portfolio.get_snapshot()
    total_balance = sum(float(getattr(bot, "balance_usd", 0.0) or 0.0) for bot in snapshot.bots.values())

    if initial_balance_usd <= 0 or total_balance == 0:
        logger.warning("[KILLSWITCH] Баланс портфолио = 0, триггер пропущен.")
        return

    drawdown_pct = ((initial_balance_usd - total_balance) / initial_balance_usd) * 100.0
    if drawdown_pct >= threshold_pct:
        logger.warning("[KILLSWITCH] Просадка маржи: %.2f%% >= %.2f%%", drawdown_pct, threshold_pct)
        trigger_killswitch("MARGIN_DRAWDOWN", round(drawdown_pct, 2))


def check_cascade_trigger() -> None:
    try:
        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime = snapshot.get("regime", {}) if isinstance(snapshot, dict) else {}
        primary = str(regime.get("primary") or "RANGE")
        modifiers = list(regime.get("modifiers") or [])
        if primary in {"CASCADE_DOWN", "CASCADE_UP"} and "LIQUIDATION_CASCADE" in modifiers:
            logger.warning("[KILLSWITCH] Каскад ликвидаций: %s + LIQUIDATION_CASCADE", primary)
            trigger_killswitch("LIQUIDATION_CASCADE", primary)
    except Exception as exc:
        logger.error("[KILLSWITCH] Ошибка проверки каскада: %s", exc)


def check_flash_move_trigger(price_now: float, price_1m_ago: float, threshold_pct: float) -> None:
    if price_1m_ago == 0:
        return
    change_pct = abs((price_now - price_1m_ago) / price_1m_ago) * 100.0
    if change_pct >= threshold_pct:
        logger.warning("[KILLSWITCH] Аномальное движение: ±%.2f%% >= %.2f%%", change_pct, threshold_pct)
        trigger_killswitch("FLASH_MOVE", round(change_pct, 2))


def check_all_killswitch_triggers(config: dict[str, Any]) -> None:
    check_margin_drawdown_trigger(
        initial_balance_usd=float(config.get("KILLSWITCH_INITIAL_BALANCE_USD", 10_000)),
        threshold_pct=float(config.get("KILLSWITCH_DRAWDOWN_THRESHOLD_PCT", 15.0)),
    )
    check_cascade_trigger()
