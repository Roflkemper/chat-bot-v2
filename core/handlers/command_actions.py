from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from core.btc_plan import (
    build_btc_forecast_text,
    build_btc_ginarea_text,
    build_btc_long_plan_text,
    build_btc_short_plan_text,
    build_btc_summary_text,
)
from core.confluence_engine import build_btc_confluence_text
from core.decision_adapter import inject_new_decision
from core.execution_plan import (
    build_btc_close_text,
    build_btc_execution_plan_text,
    build_btc_hold_text,
    build_btc_invalidation_text,
    build_btc_wait_text,
)
from core.exit_plan import build_btc_smart_exit_text
from core.lifecycle_plan import build_btc_lifecycle_text
from core.market_structure import build_btc_structure_text
from core.setup_quality import build_btc_setup_quality_text
from core.trade_manager import (
    build_btc_be_plan_text,
    build_btc_journal_manager_text,
    build_btc_partial_exit_text,
    build_btc_partial_size_text,
    build_btc_tp_plan_text,
    build_btc_trade_manager_text,
    build_btc_trailing_text,
)
from core.trade_flow import build_trade_flow_summary
from core.liquidation_character import analyze_fast_move
from core.execution_advisor import evaluate_entry_window
from core.tactical_edge import build_tactical_edge
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
from advisors.bot_control_advisor import summarize_bot_control
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

    def bot_manual_action(self) -> BotResponsePayload:
        bot_key, action = parse_manual_bot_command(self.ctx.command)
        if not bot_key or not action:
            return self.ctx.plain(
                "Не понял команду ручного ведения бота.\n\nПример: BOT CT LONG SMALL\nИли: BOT RANGE SHORT CANCEL"
            )
        state = apply_manual_bot_action(bot_key, action)
        return self.ctx.plain(format_bot_manager_status(state))


def build_action_map(ctx: CommandActionContext) -> dict[str, Callable[[], BotResponsePayload]]:
    actions = CommandActions(ctx)
    return {
        '_cmd_help': actions.help,
        '_cmd_analysis': actions.analysis,
        '_cmd_system_status': actions.system_status,
        '_cmd_action_now': actions.action_now,
        '_cmd_debug_export': actions.debug_export,
        '_cmd_save_case': actions.save_case,
        '_cmd_summary': actions.summary,
        '_cmd_forecast': actions.forecast,
        '_cmd_ginarea': actions.ginarea,
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
    }