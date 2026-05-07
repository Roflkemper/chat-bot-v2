from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from core.btc_plan import (
    build_btc_forecast_text,
    build_btc_ginarea_text,
    build_btc_long_plan_text,
    build_btc_short_plan_text,
    build_btc_summary_text,
)
from core.execution_plan import (
    build_btc_close_text,
    build_btc_execution_plan_text,
    build_btc_hold_text,
    build_btc_invalidation_text,
    build_btc_wait_text,
)
from core.market_structure import build_btc_structure_text
from core.setup_quality import build_btc_setup_quality_text
from core.trade_flow import build_trade_flow_summary
from core.liquidation_character import analyze_fast_move
from core.execution_advisor import evaluate_entry_window
from core.ux_mode import build_ultra_wait_block, is_no_trade_context
from core.action_authority import build_action_authority
from core.grid_regime_manager_v1689 import derive_v1689_context
from core.telegram_formatter import (
    format_v14_action_text,
    format_v14_best_trade_text,
    format_v14_decision_text,
    format_v14_forecast_text,
    format_v14_ginarea_text,
    format_v14_summary_text,
    format_v14_trade_manager_text,
    format_v16_bots_status_text,
    _derive_clean_bot_context,
    _derive_v16_view,
    _fmt_price,
)
from core.liquidity_lite import build_liquidity_lite_context
from models.responses import BotResponsePayload
from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot
from renderers.telegram_renderers import (
    build_base_analysis_text,
    build_decision_block_text,
    build_exec_plan_brief_text,
    build_help_text,
    build_journal_status_text,
    build_my_position_text,
    build_why_no_trade_text,
)
from services.analysis_service import DEFAULT_TF

logger = logging.getLogger(__name__)
from services.debug_export_service import create_runtime_debug_export
from services.health_service import build_health_status_text
from services.pipeline_sync_service import (
    build_pipeline_bundle,
    build_pipeline_analysis_text,
    build_pipeline_action_text,
    build_pipeline_exit_text,
    build_pipeline_position_text,
)
from services.journal_service import close_position_with_context, open_position_with_journal
from services.response_service import ResponseService
from storage.bot_manager_state import apply_manual_bot_action, format_bot_manager_status, parse_manual_bot_command, sync_bot_manager
from storage.trade_journal import (
    final_close_trade,
    mark_be_moved,
    mark_partial_exit,
    mark_tp1,
    mark_tp2,
)
from storage.transition_alerts import build_transition_alert

try:
    from core.decision_engine import build_decision_summary_text
except Exception:
    build_decision_summary_text = None

try:
    from core.exit_plan import build_btc_smart_exit_text
except Exception:
    build_btc_smart_exit_text = None

try:
    from core.confluence_engine import build_btc_confluence_text
except Exception:
    build_btc_confluence_text = None

try:
    from core.decision_adapter import inject_new_decision
except Exception:
    inject_new_decision = None

try:
    from core.lifecycle_plan import build_btc_lifecycle_text
except Exception:
    build_btc_lifecycle_text = None

try:
    from core.trade_manager import (
        build_btc_be_plan_text,
        build_btc_journal_manager_text,
        build_btc_partial_exit_text,
        build_btc_partial_size_text,
        build_btc_tp_plan_text,
        build_btc_trade_manager_text,
        build_btc_trailing_text,
    )
except Exception:
    build_btc_be_plan_text = None
    build_btc_journal_manager_text = None
    build_btc_partial_exit_text = None
    build_btc_partial_size_text = None
    build_btc_tp_plan_text = None
    build_btc_trade_manager_text = None
    build_btc_trailing_text = None

try:
    from core.tactical_edge import build_tactical_edge
except Exception:
    build_tactical_edge = None

try:
    from advisors.bot_control_advisor import summarize_bot_control
except Exception:
    summarize_bot_control = None


def _format_roadmap_text() -> str:
    """Read ROADMAP.md and return formatted Telegram-ready text (≤4096 chars)."""
    from pathlib import Path
    roadmap_path = Path(__file__).resolve().parents[1] / "docs" / "STATE" / "ROADMAP.md"
    if not roadmap_path.exists():
        return "📍 Roadmap не найден.\n\nЗапусти: python scripts/state_snapshot.py"

    text = roadmap_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    current_phase_lines: list[str] = []
    next_phase_name = ""
    in_current = False
    found_next = False

    for line in lines:
        s = line.strip()
        if s.startswith("### ФАЗА") or s.startswith("### ФА"):
            if in_current:
                next_phase_name = s.lstrip("#").strip()
                found_next = True
                break
            status_ahead = ""
            for ll in lines[lines.index(line):lines.index(line) + 5]:
                if ll.strip().lower().startswith("status:"):
                    status_ahead = ll.strip().split(":", 1)[1].strip().lower()
                    break
            if "in_progress" in status_ahead or "in progress" in status_ahead:
                in_current = True
                current_phase_lines.append(s.lstrip("#").strip())
        elif in_current:
            current_phase_lines.append(line)

    if not current_phase_lines:
        return "📍 Roadmap: нет активной фазы.\n\nПроверь docs/STATE/ROADMAP.md"

    # Build output
    phase_name = current_phase_lines[0]
    out_lines = [f"📍 Текущая фаза: {phase_name}", ""]

    in_tasks = False
    tasks_shown = 0
    for line in current_phase_lines[1:]:
        s = line.strip()
        if "active tasks" in s.lower():
            out_lines.append("Active:")
            in_tasks = True
            continue
        if "exit criteria" in s.lower() or "pre-requisites" in s.lower():
            in_tasks = False
            continue
        if in_tasks and s.startswith("- ") and tasks_shown < 7:
            icon = "✓" if "[DONE" in s else "·"
            out_lines.append(f"  {icon} {s[2:]}")
            tasks_shown += 1

    if next_phase_name:
        out_lines += ["", f"Next: {next_phase_name}"]

    result = "\n".join(out_lines)
    return result[:4090]


@dataclass
class CommandActionContext:
    command: str
    timeframe: str
    snapshot_loader: Callable[[str], AnalysisSnapshot]
    request_context: object | None = None
    journal_loader: Callable[[], JournalSnapshot] | None = None
    position_loader: Callable[[], PositionSnapshot] | None = None
    trace: object | None = None
    prefetched_snapshots: dict[str, AnalysisSnapshot] = field(default_factory=dict)
    prefetched_journal: JournalSnapshot | None = None
    prefetched_position: PositionSnapshot | None = None
    original_command: str = ""

    def get_snapshot(self, timeframe: str | None = None, *, refresh: bool = False) -> AnalysisSnapshot:
        tf = timeframe or self.timeframe
        if refresh or tf not in self.prefetched_snapshots:
            self.prefetched_snapshots[tf] = self.snapshot_loader(tf)
        return self.prefetched_snapshots[tf]

    def get_journal_snapshot(self, *, refresh: bool = False) -> JournalSnapshot:
        if self.journal_loader is None:
            raise RuntimeError('journal_loader is not configured')
        if refresh or self.prefetched_journal is None:
            self.prefetched_journal = self.journal_loader()
        return self.prefetched_journal

    def get_position_snapshot(self, *, refresh: bool = False) -> PositionSnapshot:
        if self.position_loader is None:
            raise RuntimeError('position_loader is not configured')
        if refresh or self.prefetched_position is None:
            self.prefetched_position = self.position_loader()
        return self.prefetched_position

    def plain(
        self,
        body: str,
        *,
        analysis_snapshot: AnalysisSnapshot | None = None,
        journal: JournalSnapshot | None = None,
        position: PositionSnapshot | None = None,
        timeframe: str | None = None,
    ) -> BotResponsePayload:
        return ResponseService.plain_text(
            self.command,
            body,
            analysis_snapshot=analysis_snapshot,
            journal_snapshot=journal,
            position_snapshot=position,
            timeframe=timeframe,
        )

    def legacy_payload(
        self,
        builder,
        *,
        timeframe: str,
        analysis_tf: str | None = None,
        journal: JournalSnapshot | None = None,
        position: PositionSnapshot | None = None,
        **kwargs,
    ) -> BotResponsePayload:
        analysis_snapshot = self.get_snapshot(analysis_tf or timeframe)
        return ResponseService.render_text(
            self.command,
            text_builder=builder,
            analysis_snapshot=analysis_snapshot,
            journal_snapshot=journal,
            position_snapshot=position,
            timeframe=timeframe,
            **kwargs,
        )


class CommandActions:
    def __init__(self, ctx: CommandActionContext) -> None:
        self.ctx = ctx

    @staticmethod
    def _current_regime_context() -> tuple[str, list[str]]:
        try:
            from core.pipeline import build_full_snapshot

            snapshot = build_full_snapshot(symbol="BTCUSDT")
            regime = snapshot.get("regime", {}) if isinstance(snapshot, dict) else {}
            return str(regime.get("primary") or "RANGE"), list(regime.get("modifiers") or [])
        except Exception:
            logger.exception("command.current_regime_context_failed")
            return "RANGE", []

    def _log_manual_command(self, *, category_key: str | None = None, action: str | None = None) -> None:
        try:
            from core.orchestrator.calibration_log import CalibrationLog

            regime, modifiers = self._current_regime_context()
            CalibrationLog.instance().log_manual_command(
                command=self.ctx.command,
                category_key=category_key,
                action=action,
                regime=regime,
                modifiers=modifiers,
            )
        except Exception:
            logger.exception("command.manual_log_failed command=%s", self.ctx.command)

    def _attach_transition_alert(self, payload: BotResponsePayload, analysis: AnalysisSnapshot | None) -> BotResponsePayload:
        if analysis is None:
            return payload
        try:
            alert_text = build_transition_alert(analysis)
        except Exception:
            logger.exception('command.transition_alert_failed command=%s tf=%s', self.ctx.command, getattr(analysis, 'timeframe', self.ctx.timeframe))
            return payload
        if not alert_text:
            return payload
        body = payload.text or ""
        payload.text = (alert_text + "\n\n" + body) if body else alert_text
        return payload


    @staticmethod
    def _inject_decision_safe(snapshot: AnalysisSnapshot, timeframe: str) -> AnalysisSnapshot:
        """
        V16+: decision уже должен приходить из analysis_service/action_engine_v16.
        Здесь намеренно ничего не перезаписываем, чтобы не убивать новый runtime-output
        старым legacy decision adapter.
        """
        return snapshot

    def help(self) -> BotResponsePayload:
        return self.ctx.plain(build_help_text())

    def system_status(self) -> BotResponsePayload:
        return self.ctx.plain(build_health_status_text())

    def debug_export(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        position = self.ctx.get_position_snapshot()
        zip_path = create_runtime_debug_export(
            trace=self.ctx.trace,
            ctx=self.ctx.request_context,
            command=self.ctx.command,
            timeframe=self.ctx.timeframe,
            journal_snapshot=journal,
            position_snapshot=position,
            case_mode=False,
        )
        return ResponseService.file_response(
            self.ctx.command,
            '📦 DEBUG EXPORT готов. Бот отправил архив документом.',
            file_path=str(zip_path),
            file_caption='DEBUG EXPORT 2.0',
            journal_snapshot=journal,
            position_snapshot=position,
        )

    def save_case(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        position = self.ctx.get_position_snapshot()
        zip_path = create_runtime_debug_export(
            trace=self.ctx.trace,
            ctx=self.ctx.request_context,
            command=self.ctx.command,
            timeframe=self.ctx.timeframe,
            journal_snapshot=journal,
            position_snapshot=position,
            case_mode=True,
        )
        return ResponseService.file_response(
            self.ctx.command,
            '🧩 Кейс сохранён. Бот отправил архив документом.',
            file_path=str(zip_path),
            file_caption='CASE EXPORT 2.0',
            journal_snapshot=journal,
            position_snapshot=position,
        )

    def analysis(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(self.ctx.timeframe)
        analysis = self._inject_decision_safe(analysis, self.ctx.timeframe)
        if str(self.ctx.timeframe).lower() == DEFAULT_TF:
            pipeline_snapshot = build_pipeline_bundle('BTCUSDT')
            payload = self.ctx.plain(
                build_pipeline_analysis_text(pipeline_snapshot),
                analysis_snapshot=analysis,
                timeframe=self.ctx.timeframe,
            )
            return self._attach_transition_alert(payload, analysis)
        payload = self.ctx.plain(
            build_base_analysis_text(analysis),
            analysis_snapshot=analysis,
            timeframe=self.ctx.timeframe,
        )
        return self._attach_transition_alert(payload, analysis)

    def summary(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        payload_dict = analysis.to_dict() if hasattr(analysis, 'to_dict') else {}
        payload = self.ctx.plain(
            format_v14_summary_text(payload_dict, '📘 BTC SUMMARY [1h]'),
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
        )
        return self._attach_transition_alert(payload, analysis)

    def forecast(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        payload_dict = analysis.to_dict() if hasattr(analysis, 'to_dict') else {}
        payload = self.ctx.plain(
            format_v14_forecast_text(payload_dict, '🔮 BTC FORECAST [1h]'),
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
        )
        return self._attach_transition_alert(payload, analysis)

    def ginarea(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        payload_dict = analysis.to_dict() if hasattr(analysis, 'to_dict') else {}
        payload = self.ctx.plain(
            format_v14_ginarea_text(payload_dict, '🧩 BTC GINAREA [1h]'),
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
        )
        return self._attach_transition_alert(payload, analysis)

    def portfolio(self) -> BotResponsePayload:
        from telegram_ui.portfolio.command import handle_portfolio_command
        return self.ctx.plain(handle_portfolio_command())

    def state(self) -> BotResponsePayload:
        from telegram_ui.state.command import handle_state_command
        return self.ctx.plain(handle_state_command())

    def advise(self) -> BotResponsePayload:
        # /advise — алиас на v2 (рынок + сетапы + paper trades).
        # Legacy v0.1 ("ADVISOR v2 — multi-asset / cold start") отключён по
        # требованию оператора 2026-05-07: давать выводы и сетапы, а не "cold start".
        try:
            from services.advisor import build_advisor_v2_text
            text = build_advisor_v2_text()
        except Exception as exc:
            logger.exception("advise.failed")
            return self.ctx.plain(f"❌ advise failed: {exc}")
        self._log_manual_command(action="ADVISOR_V2")
        return self.ctx.plain(text)

    def regime(self) -> BotResponsePayload:
        from core.pipeline import build_full_snapshot
        from renderers.grid_renderer import render_regime_details

        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime_dict = snapshot.get("regime", {}) if isinstance(snapshot, dict) else {}
        return self.ctx.plain(render_regime_details(regime_dict))

    def category(self) -> BotResponsePayload:
        from core.orchestrator.portfolio_state import PortfolioStore
        from renderers.grid_renderer import render_category

        parts = self.ctx.command.strip().split(maxsplit=1)
        if len(parts) < 2:
            return self.ctx.plain("Использование: /category <ключ>\nПример: /category btc_short")

        key = parts[1].strip().lower()
        store = PortfolioStore.instance()
        category = store.get_category(key)
        if category is None:
            available = ", ".join(cat.key for cat in store.list_categories())
            return self.ctx.plain(f"Категория '{key}' не найдена. Доступные:\n{available}")

        bots = store.get_bots_in_category(key)
        return self.ctx.plain(render_category(category, bots))

    def bot(self) -> BotResponsePayload:
        from core.orchestrator.portfolio_state import PortfolioStore
        from renderers.grid_renderer import render_bot

        parts = self.ctx.command.strip().split(maxsplit=1)
        if len(parts) < 2:
            return self.ctx.plain("Использование: /bot <ключ>")

        key = parts[1].strip().lower()
        store = PortfolioStore.instance()
        bot = store.get_bot(key)
        if bot is None:
            available = ", ".join(item.key for item in store.list_bots())
            return self.ctx.plain(f"Бот '{key}' не найден. Доступные:\n{available}")

        category = store.get_category(bot.category)
        return self.ctx.plain(render_bot(bot, category))

    def pause(self) -> BotResponsePayload:
        from core.orchestrator.i18n_ru import CATEGORY_RU, tr
        from core.orchestrator.portfolio_state import PortfolioStore

        parts = self.ctx.command.strip().split(maxsplit=1)
        if len(parts) < 2:
            return self.ctx.plain("Использование: /pause <категория>\nПример: /pause btc_long")

        key = parts[1].strip().lower()
        store = PortfolioStore.instance()
        cat = store.get_category(key)
        if cat is None:
            available = ", ".join(item.key for item in store.list_categories())
            return self.ctx.plain(f"Категория '{key}' не найдена. Доступные:\n{available}")

        changed = []
        for bot in store.get_bots_in_category(key):
            if bot.state != "PAUSED_MANUAL":
                store.set_bot_state(bot.key, "PAUSED_MANUAL")
                changed.append(bot.key)

        if not changed:
            return self.ctx.plain(f"Все боты категории {key} уже на ручной паузе.")

        self._log_manual_command(category_key=key, action="PAUSE")
        return self.ctx.plain(
            f"⏸ РУЧНАЯ ПАУЗА: {tr(key, CATEGORY_RU)}\n\n"
            f"Боты на паузе: {', '.join(changed)}\n"
            f"Авто-решения оркестратора игнорируются до /resume {key}"
        )

    def resume(self) -> BotResponsePayload:
        from core.orchestrator.i18n_ru import CATEGORY_RU, tr
        from core.orchestrator.portfolio_state import PortfolioStore

        parts = self.ctx.command.strip().split(maxsplit=1)
        if len(parts) < 2:
            return self.ctx.plain("Использование: /resume <категория>\nПример: /resume btc_long")

        key = parts[1].strip().lower()
        store = PortfolioStore.instance()
        cat = store.get_category(key)
        if cat is None:
            available = ", ".join(item.key for item in store.list_categories())
            return self.ctx.plain(f"Категория '{key}' не найдена. Доступные:\n{available}")

        changed = []
        target_state = "READY" if cat.orchestrator_action == "ARM" else "ACTIVE"
        for bot in store.get_bots_in_category(key):
            if bot.state == "PAUSED_MANUAL":
                store.set_bot_state(bot.key, target_state)
                changed.append(bot.key)

        if not changed:
            return self.ctx.plain(f"В категории {key} нет ботов на ручной паузе.")

        self._log_manual_command(category_key=key, action="RESUME")
        return self.ctx.plain(
            f"▶️ ВОЗОБНОВЛЕНО: {tr(key, CATEGORY_RU)}\n\n"
            f"Боты: {', '.join(changed)}\n"
            f"Снова действует оркестратор: {cat.orchestrator_action}"
        )

    def bot_add(self) -> BotResponsePayload:
        from core.orchestrator.portfolio_state import Bot, PortfolioStore

        parts = self.ctx.command.strip().split()
        if len(parts) < 4:
            return self.ctx.plain("Использование: /bot_add <key> <category> <strategy_type>")

        _, key, category_key, strategy_type = parts[:4]
        key = key.lower()
        category_key = category_key.lower()
        strategy_type = strategy_type.upper()

        store = PortfolioStore.instance()
        if store.get_bot(key) is not None:
            return self.ctx.plain(f"Бот '{key}' уже существует.")
        category = store.get_category(category_key)
        if category is None:
            available = ", ".join(item.key for item in store.list_categories())
            return self.ctx.plain(f"Категория '{category_key}' не найдена. Доступные:\n{available}")
        if strategy_type not in {"GRID_L1", "GRID_L2_IMPULSE"}:
            return self.ctx.plain("Недопустимый strategy_type. Разрешено: GRID_L1, GRID_L2_IMPULSE")

        initial_state = "READY" if category.orchestrator_action == "ARM" else "ACTIVE"
        bot = Bot(
            key=key,
            category=category_key,
            label=key,
            strategy_type=strategy_type,
            stage="LIVE",
            state=initial_state,
            params={},
        )
        store.add_bot(bot)
        self._log_manual_command(category_key=category_key, action="BOT_ADD")
        return self.ctx.plain(
            f"✅ БОТ ДОБАВЛЕН: {key}\n\n"
            f"Категория: {category_key}\n"
            f"Стратегия: {strategy_type}\n"
            f"Статус: {initial_state}\n\n"
            f"Настрой параметры бота в GinArea, затем смени статус в боте командой /bot {key}"
        )

    def bot_remove(self) -> BotResponsePayload:
        from core.orchestrator.portfolio_state import PortfolioStore

        parts = self.ctx.command.strip().split(maxsplit=1)
        if len(parts) < 2:
            return self.ctx.plain("Использование: /bot_remove <key>")

        key = parts[1].strip().lower()
        store = PortfolioStore.instance()
        if store.get_bot(key) is None:
            available = ", ".join(item.key for item in store.list_bots())
            return self.ctx.plain(f"Бот '{key}' не найден. Доступные:\n{available}")
        store.remove_bot(key)
        self._log_manual_command(action="BOT_REMOVE")
        return self.ctx.plain(f"🗃 БОТ АРХИВИРОВАН: {key}")

    def papertrader(self) -> BotResponsePayload:
        """Paper trader stats — open trades + recent performance.

        See TZ-PAPER-TRADER (2026-05-07).
        """
        try:
            from services.paper_trader import journal, daily_summary, PAPER_NOTIONAL_USD, CONFIDENCE_THRESHOLD
        except Exception as exc:
            logger.exception("papertrader.import_failed")
            return self.ctx.plain(f"❌ paper trader недоступен: {exc}")

        opens = journal.open_trades()
        summary_24h = daily_summary(days_back=1)
        summary_7d = daily_summary(days_back=7)

        lines = [
            "📊 PAPER TRADER v0.1",
            f"Notional per trade: ${PAPER_NOTIONAL_USD:,.0f} | Conf threshold: {CONFIDENCE_THRESHOLD:.0f}%",
            "",
            f"Open trades: {len(opens)}",
        ]
        for tr in opens[:5]:
            side = "LONG" if tr.get("side") == "long" else "SHORT"
            entry = tr.get("entry") or 0
            sl = tr.get("sl") or 0
            tp1 = tr.get("tp1") or 0
            stype = tr.get("setup_type", "?")
            lines.append(f"  • {side} @ {entry:.0f} | SL {sl:.0f} | TP1 {tp1:.0f} | {stype}")
        if len(opens) > 5:
            lines.append(f"  ... +{len(opens)-5} more")
        lines.append("")
        lines.append("24h:")
        lines.append(
            f"  opens={summary_24h['n_opens']} closes={summary_24h['n_closes']} "
            f"wins={summary_24h['n_wins']} losses={summary_24h['n_losses']}"
        )
        lines.append(
            f"  net=${summary_24h['net_pnl_usd']:+.0f} | win_rate={summary_24h['win_rate_pct']}% | avg_rr={summary_24h['avg_rr']}"
        )
        lines.append("")
        lines.append("7d:")
        lines.append(
            f"  opens={summary_7d['n_opens']} closes={summary_7d['n_closes']} "
            f"wins={summary_7d['n_wins']} losses={summary_7d['n_losses']}"
        )
        lines.append(
            f"  net=${summary_7d['net_pnl_usd']:+.0f} | win_rate={summary_7d['win_rate_pct']}% | avg_rr={summary_7d['avg_rr']}"
        )
        if summary_7d.get("by_setup_type"):
            lines.append("")
            lines.append("7d by setup type:")
            for stype, n in sorted(summary_7d["by_setup_type"].items(), key=lambda x: -x[1])[:8]:
                lines.append(f"  {stype}: {n}")
        self._log_manual_command(action="PAPERTRADER")
        return self.ctx.plain("\n".join(lines))

    def regime_v2(self) -> BotResponsePayload:
        """Multi-timeframe regime view: 4h + 1h + 15m simultaneously.

        Solves the META-issue where v1 classifier marks bull-drift as RANGE
        because ADX>25 strict criterion fails inside short pullbacks.
        v2 introduces SLOW_UP/SLOW_DOWN/DRIFT_UP/DRIFT_DOWN states that
        catch this case (calibrated on 1y data + verified on operator window).
        """
        try:
            from services.regime_classifier_v2 import build_multi_timeframe_view
            v = build_multi_timeframe_view()
        except Exception as exc:
            logger.exception("regime_v2.failed")
            return self.ctx.plain(f"❌ regime_v2 failed: {exc}")

        lines = ["🌡️ REGIME v2 — мульти-таймфрейм"]
        lines.append("")
        for tf_name, bar in [("4h", v.bar_4h), ("1h", v.bar_1h), ("15m", v.bar_15m)]:
            if bar is None:
                lines.append(f"  {tf_name}: НЕТ ДАННЫХ")
                continue
            ind = bar.indicators
            lines.append(f"  {tf_name}: **{bar.state_v2}** → {bar.state_3state}")
            close = bar.last_bar_close
            ema200 = ind.get("ema200")
            dist = ind.get("dist_to_ema200_pct") or 0
            slope = ind.get("ema50_slope_pct") or 0
            atr = ind.get("atr_pct") or 0
            move_24h = ind.get("move_24h_pct") or 0
            ema200_str = f"{ema200:.0f}" if ema200 is not None else "n/a"
            lines.append(
                f"    close={close:.0f} ema200={ema200_str} dist={dist:+.2f}% slope_12h={slope:+.3f}%"
            )
            lines.append(
                f"    atr={atr:.2f}% 24h_move={move_24h:+.2f}%"
            )
        lines.append("")
        if v.macro_micro_diverge:
            lines.append("⚠️ MACRO ≠ MICRO — 4h и 15m показывают разные направления")
        else:
            lines.append("✓ Macro и micro согласованы")
        lines.append("")
        lines.append("Состояния v2:")
        lines.append("  STRONG_*  — сильный тренд (ADX>25)")
        lines.append("  SLOW_*    — слабый тренд (EMA stack + slope)")
        lines.append("  DRIFT_*   — низковолатильный grind")
        lines.append("  CASCADE_* — быстрое движение")
        lines.append("  RANGE/COMPRESSION — без направления")

        self._log_manual_command(action="REGIME_V2")
        return self.ctx.plain("\n".join(lines))

    def advisor(self) -> BotResponsePayload:
        """Advisor v0.2 — рыночный анализ с выводами и торговыми сетапами.

        Без позиции, без distance to liquidation. С verdict, multi-TF
        regime, momentum, flow, OI/funding, session levels, активные
        setup'ы, paper trades. См. TZ-ADVISOR-V0_2 (2026-05-07).
        """
        try:
            from services.advisor import build_advisor_v2_text
            text = build_advisor_v2_text()
        except Exception as exc:
            logger.exception("advisor.failed")
            return self.ctx.plain(f"❌ advisor failed: {exc}")
        self._log_manual_command(action="ADVISOR_V2")
        return self.ctx.plain(text)

    def margin(self) -> BotResponsePayload:
        """Operator-supplied margin data for Decision Layer M-* family.

        Usage: /margin <coefficient> <available_margin_usd> <distance_to_liq_pct>
        Example: /margin 0.97 20434 18.0

        Validates ranges, appends to state/manual_overrides/margin_overrides.jsonl,
        replies with confirmation. See TZ-MARGIN-COEFFICIENT-INPUT-WIRE 2026-05-06.
        """
        from services.margin import (
            MarginCommandError,
            append_override,
            parse_override_command,
        )

        try:
            record = parse_override_command(self.ctx.command)
        except MarginCommandError as exc:
            return self.ctx.plain(f"❌ {exc}")
        try:
            append_override(record)
        except OSError as exc:
            return self.ctx.plain(f"❌ Не удалось записать override: {exc}")
        self._log_manual_command(action="MARGIN_OVERRIDE")
        return self.ctx.plain(
            "✅ MARGIN OVERRIDE СОХРАНЁН\n"
            f"coefficient: {record.coefficient:.4f}\n"
            f"available_margin: {record.available_margin_usd:,.0f} USD\n"
            f"distance_to_liq: {record.distance_to_liquidation_pct:.1f}%\n"
            f"ts: {record.ts}\n"
            f"source: {record.source}"
        )

    def blackout(self) -> BotResponsePayload:
        from core.orchestrator.regime_classifier import RegimeStateStore

        parts = self.ctx.command.strip().split(maxsplit=1)
        if len(parts) < 2:
            return self.ctx.plain("Использование: /blackout <hours>\nПример: /blackout 2")

        try:
            hours = float(parts[1].strip().replace(",", "."))
        except ValueError:
            return self.ctx.plain("Некорректное число часов для blackout.")

        store = RegimeStateStore()
        if hours <= 0:
            store.set_blackout(None)
            self._log_manual_command(action="BLACKOUT_RESET")
            return self.ctx.plain("🔄 БЛЭКАУТ СБРОШЕН")

        until = datetime.now(timezone.utc) + timedelta(hours=hours)
        store.set_blackout(until)
        self._log_manual_command(action="BLACKOUT")
        return self.ctx.plain(f"🛑 БЛЭКАУТ ВКЛЮЧЁН на {hours:g}ч\nДо: {until.strftime('%d.%m.%Y %H:%M UTC')}")

    def apply(self) -> BotResponsePayload:
        from core.orchestrator.command_dispatcher import dispatch_orchestrator_decisions
        from core.orchestrator.killswitch import KillswitchStore
        from core.orchestrator.portfolio_state import PortfolioStore
        from core.pipeline import build_full_snapshot
        from core.orchestrator.i18n_ru import ACTION_RU, CATEGORY_RU, tr

        ks = KillswitchStore.instance()
        if ks.is_active():
            return self.ctx.plain(
                "🚨 KILLSWITCH АКТИВЕН\n\n"
                "Автоприменение правил заблокировано.\n"
                "Для проверки статуса: /killswitch status\n"
                "Для снятия: /killswitch off"
            )

        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime = snapshot.get("regime", {}) if isinstance(snapshot, dict) else {}
        store = PortfolioStore.instance()
        result = dispatch_orchestrator_decisions(store, regime)

        lines = ["🔄 ПРИМЕНЕНИЕ ПРАВИЛ ОРКЕСТРАТОРА", ""]
        lines.append(f"Изменено категорий: {len(result.changed)}")
        for change in result.changed:
            lines.append(
                f"  • {tr(change.category_key, CATEGORY_RU)}: "
                f"{tr(change.from_action, ACTION_RU)} → {tr(change.to_action, ACTION_RU)}"
            )
            lines.append(f"    причина: {change.reason_ru}")
        lines.append("")
        lines.append(f"Без изменений: {len(result.unchanged)}")

        if result.alerts:
            lines.append("")
            lines.append("АЛЕРТЫ:")
            for alert in result.alerts:
                lines.append("")
                lines.append(alert.text)

        self._log_manual_command(action="APPLY")
        return self.ctx.plain("\n".join(lines))

    def killswitch(self) -> BotResponsePayload:
        from core.orchestrator.killswitch import KillswitchStore, trigger_killswitch

        parts = self.ctx.command.strip().split(maxsplit=2)
        if len(parts) < 2:
            return self.killswitch_status()

        command = parts[1].strip().lower()
        store = KillswitchStore.instance()

        if command == "on":
            reason_text = parts[2].strip() if len(parts) > 2 else "Оператор"
            return self.ctx.plain(trigger_killswitch("MANUAL", reason_text))

        if command == "off":
            if not store.is_active():
                return self.ctx.plain("✅ KILLSWITCH уже отключён.")
            store.disable(operator="operator")
            self._log_manual_command(action="KILLSWITCH_OFF")
            return self.ctx.plain(
                "✅ KILLSWITCH ОТКЛЮЧЁН\n\n"
                "Режим снят оператором.\n"
                "Боты можно возобновить через /apply."
            )

        if command == "status":
            return self.killswitch_status()

        return self.ctx.plain(
            "❌ Неизвестная команда.\n"
            "Использование:\n"
            "  /killswitch on [причина]\n"
            "  /killswitch off\n"
            "  /killswitch status"
        )

    def killswitch_status(self) -> BotResponsePayload:
        from core.orchestrator.killswitch import KillswitchStore

        store = KillswitchStore.instance()
        lines = ["🔐 СТАТУС KILLSWITCH", ""]
        if store.is_active():
            event = store.get_current_event() or {}
            lines.append("Текущее состояние: ⚠️ АКТИВЕН")
            lines.append("")
            lines.append(f"Сработал: {event.get('triggered_at')}")
            lines.append(f"Причина: {event.get('reason')}")
            lines.append(f"Значение: {event.get('reason_value')}")
            lines.append("")
            lines.append("Для отключения: /killswitch off")
        else:
            lines.append("Текущее состояние: ✅ Неактивен")

        history = store.get_history(limit=5)
        if history:
            lines.append("")
            lines.append("История срабатываний (последние 5):")
            for idx, event in enumerate(history, start=1):
                lines.append(f"{idx}. {event.get('triggered_at')}")
                lines.append(f"   Причина: {event.get('reason')} ({event.get('reason_value')})")
                if event.get("disabled_at"):
                    lines.append(f"   Снят: {event.get('disabled_at')} ({event.get('disabled_by')})")

        return self.ctx.plain("\n".join(lines))

    def daily_report(self) -> BotResponsePayload:
        from core.orchestrator.calibration_log import CalibrationLog
        from renderers.calibration_renderer import render_daily_report

        parts = self.ctx.command.strip().split(maxsplit=1)
        target_day = date.today()
        if len(parts) > 1:
            raw = parts[1].strip().lower()
            if raw == "yesterday":
                target_day = date.today() - timedelta(days=1)
            else:
                try:
                    target_day = date.fromisoformat(parts[1].strip())
                except ValueError:
                    return self.ctx.plain("?????????????: /daily_report [yesterday|YYYY-MM-DD]")

        summary = CalibrationLog.instance().summarize_day(target_day)
        return self.ctx.plain(render_daily_report(summary))

    def decision(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        payload_dict = analysis.to_dict() if hasattr(analysis, 'to_dict') else {}
        payload = self.ctx.plain(
            format_v14_decision_text(payload_dict, '🧠 FINAL DECISION'),
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
        )
        return self._attach_transition_alert(payload, analysis)

    def why_no_trade(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return self.ctx.plain(
            build_why_no_trade_text(analysis),
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
        )

    def exec_plan_brief(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return self.ctx.plain(
            build_exec_plan_brief_text(analysis),
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
        )

    def long_plan_default(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_long_plan_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
        )

    def short_plan_default(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_short_plan_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
        )

    def execution_plan(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        payload = ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_execution_plan_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
        )
        return self._attach_transition_alert(payload, analysis)

    def lifecycle(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        position = self.ctx.get_position_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_lifecycle_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            position_snapshot=position,
            timeframe=timeframe,
        )

    def smart_exit(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        if str(timeframe).lower() == DEFAULT_TF:
            pipeline_snapshot = build_pipeline_bundle('BTCUSDT')
            return self.ctx.plain(
                build_pipeline_exit_text(pipeline_snapshot, journal_side=journal.side),
                analysis_snapshot=analysis,
                journal=journal,
                timeframe=timeframe,
            )
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_smart_exit_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            timeframe=timeframe,
        )

    def structure(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_structure_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            timeframe=timeframe,
            side='AUTO',
        )

    def setup_quality(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_setup_quality_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            timeframe=timeframe,
            side='AUTO',
        )

    def confluence(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_confluence_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            timeframe=timeframe,
            side='AUTO',
        )

    def invalidation(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_invalidation_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
        )

    def long_plan_tf(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(self.ctx.timeframe)
        analysis = self._inject_decision_safe(analysis, self.ctx.timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_long_plan_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=self.ctx.timeframe,
        )

    def short_plan_tf(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(self.ctx.timeframe)
        analysis = self._inject_decision_safe(analysis, self.ctx.timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_short_plan_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=self.ctx.timeframe,
        )

    def hold_auto(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_hold_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
            side='AUTO',
        )

    def close_btc(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_close_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
        )

    def wait_btc(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_wait_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
        )

    def hold_long(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_hold_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
            side='LONG',
        )

    def hold_short(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_hold_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
            side='SHORT',
        )

    def trade_manager_auto(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        journal = self.ctx.get_journal_snapshot()
        payload_dict = analysis.to_dict() if hasattr(analysis, 'to_dict') else {}
        payload = self.ctx.plain(
            format_v14_trade_manager_text(payload_dict, '🛠 BTC TRADE MANAGER [1h]'),
            analysis_snapshot=analysis,
            journal=journal,
            timeframe=DEFAULT_TF,
        )
        return payload

    def tp_plan(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_tp_plan_text,
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
            side='AUTO',
        )

    def be_plan(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_be_plan_text,
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
            side='AUTO',
        )

    def partial_exit(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_partial_exit_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
            side='AUTO',
        )

    def partial_size(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_partial_size_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            timeframe=timeframe,
            side='AUTO',
        )

    def trailing(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_trailing_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            timeframe=timeframe,
            side='AUTO',
        )

    def manage_long(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_trade_manager_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
            side='LONG',
        )

    def manage_short(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_trade_manager_text,
            analysis_snapshot=analysis,
            journal_snapshot=self.ctx.get_journal_snapshot(),
            timeframe=DEFAULT_TF,
            side='SHORT',
        )

    def open_long(self) -> BotResponsePayload:
        message = open_position_with_journal('LONG', self.ctx.get_snapshot(DEFAULT_TF), DEFAULT_TF)
        position = self.ctx.get_position_snapshot(refresh=True)
        journal = self.ctx.get_journal_snapshot(refresh=True)
        return self.ctx.plain(message, position=position, journal=journal)

    def open_short(self) -> BotResponsePayload:
        message = open_position_with_journal('SHORT', self.ctx.get_snapshot(DEFAULT_TF), DEFAULT_TF)
        position = self.ctx.get_position_snapshot(refresh=True)
        journal = self.ctx.get_journal_snapshot(refresh=True)
        return self.ctx.plain(message, position=position, journal=journal)

    def my_position(self) -> BotResponsePayload:
        position = self.ctx.get_position_snapshot()
        pipeline_snapshot = build_pipeline_bundle('BTCUSDT')
        return self.ctx.plain(build_pipeline_position_text(pipeline_snapshot, position), position=position)

    def close_position(self) -> BotResponsePayload:
        current_position = self.ctx.get_position_snapshot()
        journal = self.ctx.get_journal_snapshot()
        close_tf = current_position.timeframe or journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(close_tf) if current_position.has_position else None
        message = close_position_with_context('position_closed_manually', analysis)
        position = self.ctx.get_position_snapshot(refresh=True)
        journal = self.ctx.get_journal_snapshot(refresh=True)
        return self.ctx.plain(message, analysis_snapshot=analysis, position=position, journal=journal)

    def journal_status(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        return self.ctx.plain(build_journal_status_text(journal), journal=journal)

    def mark_tp1(self) -> BotResponsePayload:
        mark_tp1()
        journal = self.ctx.get_journal_snapshot()
        return self.ctx.plain('✅ TP1 отмечен.\n\n' + build_journal_status_text(journal), journal=journal)

    def mark_tp2(self) -> BotResponsePayload:
        mark_tp2()
        journal = self.ctx.get_journal_snapshot()
        return self.ctx.plain('✅ TP2 отмечен.\n\n' + build_journal_status_text(journal), journal=journal)

    def move_be(self) -> BotResponsePayload:
        mark_be_moved()
        journal = self.ctx.get_journal_snapshot()
        return self.ctx.plain('✅ BE MOVE отмечен.\n\n' + build_journal_status_text(journal), journal=journal)

    def partial_done(self) -> BotResponsePayload:
        mark_partial_exit()
        journal = self.ctx.get_journal_snapshot()
        return self.ctx.plain('✅ PARTIAL EXIT отмечен.\n\n' + build_journal_status_text(journal), journal=journal)

    def final_close(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        analysis = self.ctx.get_snapshot(journal.timeframe or DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, journal.timeframe or DEFAULT_TF)
        final_close_trade(reason='final_close_button', exit_price=analysis.price, close_context_snapshot=analysis.to_dict())
        updated = self.ctx.get_journal_snapshot(refresh=True)
        close_text = close_position_with_context('final_close_button', analysis)
        return self.ctx.plain(close_text + '\n\n' + build_journal_status_text(updated), journal=updated, analysis_snapshot=analysis)

    def journal_manager(self) -> BotResponsePayload:
        journal = self.ctx.get_journal_snapshot()
        timeframe = journal.timeframe or DEFAULT_TF
        analysis = self.ctx.get_snapshot(timeframe)
        analysis = self._inject_decision_safe(analysis, timeframe)
        return ResponseService.render_text(
            self.ctx.command,
            text_builder=build_btc_journal_manager_text,
            analysis_snapshot=analysis,
            journal_snapshot=journal,
            timeframe=timeframe,
        )

    def best_trade(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        payload_dict = analysis.to_dict() if hasattr(analysis, 'to_dict') else {}
        journal = self.ctx.get_journal_snapshot()
        return self.ctx.plain(
            format_v14_best_trade_text(payload_dict, '🏆 ЛУЧШАЯ СДЕЛКА'),
            analysis_snapshot=analysis,
            journal=journal,
            timeframe=DEFAULT_TF,
        )

    def action_now(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        journal = self.ctx.get_journal_snapshot()
        pipeline_snapshot = build_pipeline_bundle('BTCUSDT')
        return self.ctx.plain(
            build_pipeline_action_text(pipeline_snapshot),
            analysis_snapshot=analysis,
            journal=journal,
            timeframe=DEFAULT_TF,
        )



    def bots_status(self) -> BotResponsePayload:
        analysis = self.ctx.get_snapshot(DEFAULT_TF)
        analysis = self._inject_decision_safe(analysis, DEFAULT_TF)
        payload = analysis.to_dict() if hasattr(analysis, 'to_dict') else {}
        return self.ctx.plain(
            format_v16_bots_status_text(payload, '🤖 СТАТУС БОТОВ'),
            analysis_snapshot=analysis,
            timeframe=DEFAULT_TF,
        )

    def bot_help(self) -> BotResponsePayload:
        return self.ctx.plain(format_bot_manager_status())

    def roadmap(self) -> BotResponsePayload:
        return self.ctx.plain(_format_roadmap_text())

    def bot_manual_action(self) -> BotResponsePayload:
        bot_key, action = parse_manual_bot_command(self.ctx.command)
        if not bot_key or not action:
            return self.ctx.plain(
                "Не понял команду ручного ведения бота.\n\nПример: BOT CT LONG SMALL\nИли: BOT RANGE SHORT CANCEL"
            )
        state = apply_manual_bot_action(bot_key, action)
        return self.ctx.plain(format_bot_manager_status(state))

    def log_decision(self) -> BotResponsePayload:
        from services.decision_command import (
            HELP_TEXT, append_decision, build_confirmation_reply,
            build_decision_record, parse_decision_command,
        )
        original = self.ctx.original_command or self.ctx.command
        action, notes, warning = parse_decision_command(original)
        if action is None:
            return self.ctx.plain(HELP_TEXT)
        record = build_decision_record(action, notes)
        append_decision(record)
        return self.ctx.plain(build_confirmation_reply(record, warning))

    def list_decisions(self) -> BotResponsePayload:
        from services.decision_command import build_decisions_list_text
        parts = (self.ctx.original_command or self.ctx.command).strip().split()
        n = 5
        if len(parts) >= 3 and parts[2].isdigit():
            n = max(1, min(int(parts[2]), 50))
        return self.ctx.plain(build_decisions_list_text(n))

    def decisions_stats(self) -> BotResponsePayload:
        from services.decision_command import build_decisions_stats_text
        return self.ctx.plain(build_decisions_stats_text())


def build_action_map(ctx: CommandActionContext) -> dict[str, Callable[[], BotResponsePayload]]:
    actions = CommandActions(ctx)
    return {
        '_cmd_help': actions.help,
        '_cmd_state': actions.state,
        '_cmd_analysis': actions.analysis,
        '_cmd_system_status': actions.system_status,
        '_cmd_action_now': actions.action_now,
        '_cmd_debug_export': actions.debug_export,
        '_cmd_save_case': actions.save_case,
        '_cmd_summary': actions.summary,
        '_cmd_forecast': actions.forecast,
        '_cmd_ginarea': actions.ginarea,
        '_cmd_portfolio': actions.portfolio,
        '_cmd_advise': actions.advise,
        '_cmd_regime': actions.regime,
        '_cmd_category': actions.category,
        '_cmd_bot': actions.bot,
        '_cmd_pause': actions.pause,
        '_cmd_resume': actions.resume,
        '_cmd_bot_add': actions.bot_add,
        '_cmd_bot_remove': actions.bot_remove,
        '_cmd_blackout': actions.blackout,
        '_cmd_margin': actions.margin,
        '_cmd_advisor': actions.advisor,
        '_cmd_regime_v2': actions.regime_v2,
        '_cmd_papertrader': actions.papertrader,
        '_cmd_apply': actions.apply,
        '_cmd_killswitch': actions.killswitch,
        '_cmd_killswitch_status': actions.killswitch_status,
        '_cmd_daily_report': actions.daily_report,
        '_cmd_decision': actions.decision,
        '_cmd_why_no_trade': actions.why_no_trade,
        '_cmd_exec_plan_brief': actions.exec_plan_brief,
        '_cmd_long_plan_default': actions.long_plan_default,
        '_cmd_short_plan_default': actions.short_plan_default,
        '_cmd_execution_plan': actions.execution_plan,
        '_cmd_lifecycle': actions.lifecycle,
        '_cmd_smart_exit': actions.smart_exit,
        '_cmd_structure': actions.structure,
        '_cmd_setup_quality': actions.setup_quality,
        '_cmd_confluence': actions.confluence,
        '_cmd_invalidation': actions.invalidation,
        '_cmd_long_plan_tf': actions.long_plan_tf,
        '_cmd_short_plan_tf': actions.short_plan_tf,
        '_cmd_hold_auto': actions.hold_auto,
        '_cmd_close_btc': actions.close_btc,
        '_cmd_wait_btc': actions.wait_btc,
        '_cmd_hold_long': actions.hold_long,
        '_cmd_hold_short': actions.hold_short,
        '_cmd_trade_manager_auto': actions.trade_manager_auto,
        '_cmd_best_trade': actions.best_trade,
        '_cmd_tp_plan': actions.tp_plan,
        '_cmd_be_plan': actions.be_plan,
        '_cmd_partial_exit': actions.partial_exit,
        '_cmd_partial_size': actions.partial_size,
        '_cmd_trailing': actions.trailing,
        '_cmd_manage_long': actions.manage_long,
        '_cmd_manage_short': actions.manage_short,
        '_cmd_open_long': actions.open_long,
        '_cmd_open_short': actions.open_short,
        '_cmd_my_position': actions.my_position,
        '_cmd_close_position': actions.close_position,
        '_cmd_journal_status': actions.journal_status,
        '_cmd_mark_tp1': actions.mark_tp1,
        '_cmd_mark_tp2': actions.mark_tp2,
        '_cmd_move_be': actions.move_be,
        '_cmd_partial_done': actions.partial_done,
        '_cmd_final_close': actions.final_close,
        '_cmd_journal_manager': actions.journal_manager,
        '_cmd_bots_status': actions.bots_status,
        '_cmd_bot_help': actions.bot_help,
        '_cmd_bot_manual_action': actions.bot_manual_action,
        '_cmd_roadmap': actions.roadmap,
        '_cmd_log_decision': actions.log_decision,
        '_cmd_list_decisions': actions.list_decisions,
        '_cmd_decisions_stats': actions.decisions_stats,
    }
