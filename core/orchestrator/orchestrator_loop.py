from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timezone
from typing import Any

from core.orchestrator.command_dispatcher import dispatch_orchestrator_decisions
from core.orchestrator.killswitch_triggers import check_all_killswitch_triggers
from core.orchestrator.portfolio_state import PortfolioStore
from core.pipeline import build_full_snapshot
from services.telegram_alert_service import send_daily_report, send_telegram_alert

logger = logging.getLogger(__name__)


class OrchestratorLoop:
    """
    Background asyncio loop for the orchestrator MVP.
    It checks regime state, killswitch triggers, applies actions, and emits alerts.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config or {})
        self.interval_sec = int(self.config.get("ORCHESTRATOR_LOOP_INTERVAL_SEC", 300))
        self.daily_report_time = str(self.config.get("ORCHESTRATOR_DAILY_REPORT_TIME", "09:00"))
        self.enable_auto_alerts = bool(self.config.get("ORCHESTRATOR_ENABLE_AUTO_ALERTS", True))
        self._running = False
        self._last_daily_report_date: date | None = None

    async def start(self) -> None:
        logger.info("[ORCHESTRATOR LOOP] Starting")
        self._running = True
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("[ORCHESTRATOR LOOP] Tick failed")
            if not self._running:
                break
            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        logger.info("[ORCHESTRATOR LOOP] Stopping")
        self._running = False

    async def _tick(self) -> None:
        logger.debug("[ORCHESTRATOR LOOP] Tick")
        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime = snapshot.get("regime", {}) if isinstance(snapshot, dict) else {}

        check_all_killswitch_triggers(self.config)

        store = PortfolioStore.instance()
        result = dispatch_orchestrator_decisions(store, regime)

        if self.enable_auto_alerts:
            for change in list(result.changed or []):
                await send_telegram_alert(self._format_change_alert(change, regime))
            for alert in list(result.alerts or []):
                await send_telegram_alert(str(alert.text))

        await self._maybe_send_daily_report()

    def _format_change_alert(self, change: Any, regime: dict[str, Any]) -> str:
        from core.orchestrator.i18n_ru import ACTION_RU, CATEGORY_RU, tr

        lines = [
            "🔄 ОРКЕСТРАТОР: ИЗМЕНЕНИЕ",
            "",
            f"Категория: {tr(change.category_key, CATEGORY_RU)}",
            f"Действие: {tr(change.from_action, ACTION_RU)} → {tr(change.to_action, ACTION_RU)}",
            f"Причина: {change.reason_ru}",
            "",
            f"Режим: {regime.get('primary', 'UNKNOWN')}",
        ]
        modifiers = list(regime.get("modifiers") or [])
        if modifiers:
            lines.append(f"Модификаторы: {', '.join(modifiers)}")
        affected_bots = list(getattr(change, "affected_bots", []) or [])
        if affected_bots:
            lines.extend(["", f"Боты: {', '.join(affected_bots)}"])
        return "\n".join(lines)

    async def _maybe_send_daily_report(self) -> None:
        now = datetime.now(timezone.utc)
        try:
            target_time = time.fromisoformat(self.daily_report_time)
        except Exception:
            logger.error("[ORCHESTRATOR LOOP] Invalid daily report time: %s", self.daily_report_time)
            return

        current_seconds = now.hour * 3600 + now.minute * 60 + now.second
        target_seconds = target_time.hour * 3600 + target_time.minute * 60 + target_time.second
        if abs(current_seconds - target_seconds) >= self.interval_sec:
            return

        today = now.date()
        if self._last_daily_report_date == today:
            return

        await send_daily_report(today)
        self._last_daily_report_date = today
