from __future__ import annotations

import logging
import time
from typing import Callable

from handlers.action_execution import execute_action_safely
from handlers.command_actions import CommandActionContext, build_action_map
from handlers.command_registry import CommandCapabilities, CommandRegistry
from handlers.command_validation import validate_command_context
from models.responses import BotResponsePayload
from models.snapshots import JournalSnapshot, PositionSnapshot
from services.analysis_service import AnalysisRequestContext, DEFAULT_TF, normalize_tf
from storage.position_store import load_position_state
from storage.trade_journal import load_trade_journal
from utils.observability import RequestTrace

logger = logging.getLogger(__name__)
_BUNDLE_TTL_SEC = 15.0
_BATCH_LOCK_SEC = 3.0


class CommandHandler:
    def __init__(self, responder: Callable[[int, BotResponsePayload | str], None]) -> None:
        self.responder = responder
        self.registry = self._build_registry()
        self._bundle_cache: dict[int, dict[str, object]] = {}
        self._batch_state: dict[int, dict[str, float]] = {}


    def _get_bundle_cache(self, chat_id: int) -> dict[str, object] | None:
        cached = self._bundle_cache.get(chat_id)
        if not cached:
            return None
        expires_at = float(cached.get("expires_at") or 0.0)
        if time.time() > expires_at:
            self._bundle_cache.pop(chat_id, None)
            return None
        return cached

    def _get_batch_state(self, chat_id: int) -> dict[str, float] | None:
        state = self._batch_state.get(chat_id)
        if not state:
            return None
        if time.time() > float(state.get("expires_at") or 0.0):
            self._batch_state.pop(chat_id, None)
            return None
        return state

    def _touch_batch_state(self, chat_id: int) -> dict[str, float]:
        now = time.time()
        state = self._get_batch_state(chat_id) or {"started_at": now}
        state["last_at"] = now
        state["expires_at"] = now + _BATCH_LOCK_SEC
        self._batch_state[chat_id] = state
        return state

    def _save_bundle_cache(
        self,
        chat_id: int,
        *,
        snapshots: dict[str, object],
        journal: object | None,
        position: object | None,
    ) -> None:
        batch = self._get_batch_state(chat_id)
        ttl = _BUNDLE_TTL_SEC
        if batch is not None:
            ttl = max(ttl, float(batch.get("expires_at") or 0.0) - time.time() + _BUNDLE_TTL_SEC)
        self._bundle_cache[chat_id] = {
            "expires_at": time.time() + ttl,
            "snapshots": dict(snapshots or {}),
            "journal": journal,
            "position": position,
        }

    def _invalidate_bundle_cache(self, chat_id: int) -> None:
        self._bundle_cache.pop(chat_id, None)

    @staticmethod
    def _is_mutating_handler(handler_name: str) -> bool:
        return handler_name in {
            '_cmd_open_long', '_cmd_open_short', '_cmd_close_btc', '_cmd_close_position',
            '_cmd_mark_tp1', '_cmd_mark_tp2', '_cmd_move_be', '_cmd_partial_done', '_cmd_final_close',
            '_cmd_bot_manual_action', '_cmd_save_case'
        }

    @staticmethod
    def _build_registry() -> CommandRegistry:
        registry = CommandRegistry()
        analysis_tf = CommandCapabilities(requires_analysis=True, supports_timeframe=True, renderer='analysis')
        default_analysis = CommandCapabilities(requires_analysis=True, default_timeframe=DEFAULT_TF, renderer='analysis')
        analysis_with_journal = CommandCapabilities(requires_analysis=True, requires_journal=True, default_timeframe=DEFAULT_TF, renderer='analysis')
        help_capabilities = CommandCapabilities(renderer='help')

        registry.register('HELP', '_cmd_help', capabilities=help_capabilities)
        registry.register('ПОМОЩЬ', '_cmd_help', capabilities=help_capabilities)
        registry.register_many(['BTC 5M', 'BTC 15M', 'BTC 1H', 'BTC 4H', 'BTC 1D'], '_cmd_analysis', capabilities=analysis_tf)
        registry.register('BTC GINAREA', '_cmd_ginarea', capabilities=analysis_with_journal)
        registry.register('/portfolio', '_cmd_portfolio', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('ПОРТФЕЛЬ', '_cmd_portfolio', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('/state', '_cmd_state', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('СТЕЙТ', '_cmd_state', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('/advise', '_cmd_advise', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('СОВЕТ', '_cmd_advise', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('/regime', '_cmd_regime', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('РЕЖИМ', '_cmd_regime', capabilities=CommandCapabilities(renderer='grid'))
        registry.register_prefix(
            '/category <key>',
            lambda t: t.upper().startswith('/CATEGORY '),
            '_cmd_category',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            '/bot <key>',
            lambda t: t.upper().startswith('/BOT '),
            '_cmd_bot',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            '/pause <key>',
            lambda t: t.startswith('/PAUSE '),
            '_cmd_pause',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            '/resume <key>',
            lambda t: t.startswith('/RESUME '),
            '_cmd_resume',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            '/bot_add <key> <category> <strategy_type>',
            lambda t: t.startswith('/BOT_ADD '),
            '_cmd_bot_add',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            '/bot_remove <key>',
            lambda t: t.startswith('/BOT_REMOVE '),
            '_cmd_bot_remove',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            '/blackout <hours>',
            lambda t: t.startswith('/BLACKOUT '),
            '_cmd_blackout',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register('/killswitch', '_cmd_killswitch', capabilities=CommandCapabilities(renderer='grid'))
        registry.register_prefix(
            '/killswitch <mode>',
            lambda t: t.startswith('/KILLSWITCH '),
            '_cmd_killswitch',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register('/killswitch_status', '_cmd_killswitch_status', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('/apply', '_cmd_apply', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('/sync', '_cmd_apply', capabilities=CommandCapabilities(renderer='grid'))
        registry.register('/daily_report', '_cmd_daily_report', capabilities=CommandCapabilities(renderer='grid'))
        registry.register_prefix(
            '/daily_report <day>',
            lambda t: t.startswith('/DAILY_REPORT '),
            '_cmd_daily_report',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            'ПАУЗА <key>',
            lambda t: t.startswith('ПАУЗА '),
            '_cmd_pause',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            'ВОЗОБНОВИТЬ <key>',
            lambda t: t.startswith('ВОЗОБНОВИТЬ '),
            '_cmd_resume',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            'ДОБАВИТЬ БОТ <key> <category> <strategy_type>',
            lambda t: t.startswith('ДОБАВИТЬ БОТ '),
            '_cmd_bot_add',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            'УДАЛИТЬ БОТ <key>',
            lambda t: t.startswith('УДАЛИТЬ БОТ '),
            '_cmd_bot_remove',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register_prefix(
            'БЛЭКАУТ <hours>',
            lambda t: t.startswith('БЛЭКАУТ '),
            '_cmd_blackout',
            capabilities=CommandCapabilities(renderer='grid'),
        )
        registry.register('ПРИМЕНИТЬ', '_cmd_apply', capabilities=CommandCapabilities(renderer='grid'))
        return registry

        active_position_analysis = CommandCapabilities(
            requires_analysis=True,
            requires_position=True,
            requires_active_position=True,
            default_timeframe=DEFAULT_TF,
            renderer='position',
        )
        journal_only = CommandCapabilities(requires_journal=True, renderer='journal')
        active_journal_only = CommandCapabilities(requires_journal=True, requires_active_journal=True, renderer='journal')
        position_only = CommandCapabilities(requires_position=True, renderer='position')
        lifecycle = CommandCapabilities(
            requires_analysis=True,
            requires_journal=True,
            requires_position=True,
            default_timeframe=DEFAULT_TF,
            renderer='lifecycle',
        )

        registry.register('HELP', '_cmd_help', capabilities=CommandCapabilities(renderer='help'))
        registry.register('ПОМОЩЬ', '_cmd_help', capabilities=CommandCapabilities(renderer='help'))
        registry.register('SYSTEM STATUS', '_cmd_system_status', capabilities=CommandCapabilities(renderer='status'))
        registry.register('СТАТУС СИСТЕМЫ', '_cmd_system_status', capabilities=CommandCapabilities(renderer='status'))
        registry.register('⚡ ЧТО ДЕЛАТЬ СЕЙЧАС', '_cmd_action_now', capabilities=default_analysis)
        registry.register('⚡ ЧТО ДЕЛАТЬ', '_cmd_action_now', capabilities=default_analysis)
        registry.register('DEBUG EXPORT', '_cmd_debug_export', capabilities=CommandCapabilities(requires_analysis=True, requires_journal=True, requires_position=True, default_timeframe=DEFAULT_TF, renderer='debug'))
        registry.register('СОХРАНИТЬ КЕЙС', '_cmd_save_case', capabilities=CommandCapabilities(requires_analysis=True, requires_journal=True, requires_position=True, default_timeframe=DEFAULT_TF, renderer='debug'))
        registry.register_many(['BTC 5M', 'BTC 15M', 'BTC 1H', 'BTC 4H', 'BTC 1D'], '_cmd_analysis', capabilities=analysis_tf)
        registry.register('BTC SUMMARY', '_cmd_summary', capabilities=analysis_with_journal)
        registry.register('СВОДКА BTC', '_cmd_summary', capabilities=analysis_with_journal)
        registry.register('BTC FORECAST', '_cmd_forecast', capabilities=analysis_with_journal)
        registry.register('ПРОГНОЗ BTC', '_cmd_forecast', capabilities=analysis_with_journal)
        registry.register('BTC GINAREA', '_cmd_ginarea', capabilities=analysis_with_journal)
        registry.register('BTC DECISION', '_cmd_decision', capabilities=default_analysis)
        registry.register('FINAL DECISION', '_cmd_decision', capabilities=default_analysis)
        registry.register('ФИНАЛЬНОЕ РЕШЕНИЕ', '_cmd_decision', capabilities=default_analysis)
        registry.register('WHY NO TRADE', '_cmd_why_no_trade', capabilities=default_analysis)
        registry.register('ПОЧЕМУ НЕТ СДЕЛКИ', '_cmd_why_no_trade', capabilities=default_analysis)
        registry.register('BTC LONG PLAN', '_cmd_long_plan_default', capabilities=analysis_with_journal)
        registry.register('BTC SHORT PLAN', '_cmd_short_plan_default', capabilities=analysis_with_journal)
        registry.register('BTC EXECUTION PLAN', '_cmd_execution_plan', capabilities=analysis_with_journal)
        registry.register('EXEC PLAN', '_cmd_exec_plan_brief', capabilities=default_analysis)
        registry.register('BTC LIFECYCLE', '_cmd_lifecycle', capabilities=lifecycle)
        registry.register('BTC SMART EXIT', '_cmd_smart_exit', capabilities=analysis_with_journal)
        registry.register('BTC STRUCTURE', '_cmd_structure', capabilities=analysis_with_journal)
        registry.register('BTC SETUP QUALITY', '_cmd_setup_quality', capabilities=analysis_with_journal)
        registry.register('BTC CONFLUENCE', '_cmd_confluence', capabilities=analysis_with_journal)
        registry.register('BTC INVALIDATION', '_cmd_invalidation', capabilities=analysis_with_journal)
        registry.register_prefix(
            'LONG <TF>',
            lambda t: t.startswith('LONG ') and any(t.endswith(x) for x in ('5M', '15M', '1H', '4H', '1D')),
            '_cmd_long_plan_tf',
            capabilities=CommandCapabilities(requires_analysis=True, requires_journal=True, supports_timeframe=True, renderer='analysis'),
        )
        registry.register_prefix(
            'SHORT <TF>',
            lambda t: t.startswith('SHORT ') and any(t.endswith(x) for x in ('5M', '15M', '1H', '4H', '1D')),
            '_cmd_short_plan_tf',
            capabilities=CommandCapabilities(requires_analysis=True, requires_journal=True, supports_timeframe=True, renderer='analysis'),
        )
        registry.register('HOLD BTC', '_cmd_hold_auto', capabilities=analysis_with_journal)
        registry.register('ВЕСТИ BTC', '_cmd_hold_auto', capabilities=analysis_with_journal)
        registry.register('CLOSE BTC', '_cmd_close_btc', capabilities=analysis_with_journal)
        registry.register('ЗАКРЫТЬ BTC', '_cmd_close_btc', capabilities=analysis_with_journal)
        registry.register('WAIT BTC', '_cmd_wait_btc', capabilities=analysis_with_journal)
        registry.register('IN LONG', '_cmd_hold_long', capabilities=analysis_with_journal)
        registry.register('IN SHORT', '_cmd_hold_short', capabilities=analysis_with_journal)
        registry.register('BTC TRADE MANAGER', '_cmd_trade_manager_auto', capabilities=analysis_with_journal)
        registry.register('МЕНЕДЖЕР BTC', '_cmd_trade_manager_auto', capabilities=analysis_with_journal)
        registry.register('BEST TRADE', '_cmd_best_trade', capabilities=default_analysis)
        registry.register('ЛУЧШАЯ СДЕЛКА', '_cmd_best_trade', capabilities=default_analysis)
        registry.register('BTC TP PLAN', '_cmd_tp_plan', capabilities=default_analysis)
        registry.register('BTC BE PLAN', '_cmd_be_plan', capabilities=default_analysis)
        registry.register('BTC PARTIAL EXIT', '_cmd_partial_exit', capabilities=analysis_with_journal)
        registry.register('BTC PARTIAL SIZE', '_cmd_partial_size', capabilities=analysis_with_journal)
        registry.register('BTC TRAILING', '_cmd_trailing', capabilities=analysis_with_journal)
        registry.register('MANAGE LONG', '_cmd_manage_long', capabilities=analysis_with_journal)
        registry.register('ВЕСТИ ЛОНГ', '_cmd_manage_long', capabilities=analysis_with_journal)
        registry.register('MANAGE SHORT', '_cmd_manage_short', capabilities=analysis_with_journal)
        registry.register('ВЕСТИ ШОРТ', '_cmd_manage_short', capabilities=analysis_with_journal)
        registry.register('OPEN LONG', '_cmd_open_long', capabilities=default_analysis)
        registry.register('ОТКРЫТЬ ЛОНГ', '_cmd_open_long', capabilities=default_analysis)
        registry.register('OPEN SHORT', '_cmd_open_short', capabilities=default_analysis)
        registry.register('ОТКРЫТЬ ШОРТ', '_cmd_open_short', capabilities=default_analysis)
        registry.register('MY POSITION', '_cmd_my_position', capabilities=position_only)
        registry.register('МОЯ ПОЗИЦИЯ', '_cmd_my_position', capabilities=position_only)
        registry.register('CLOSE POSITION', '_cmd_close_position', capabilities=active_position_analysis)
        registry.register('JOURNAL STATUS', '_cmd_journal_status', capabilities=journal_only)
        registry.register('MARK TP1', '_cmd_mark_tp1', capabilities=active_journal_only)
        registry.register('MARK TP2', '_cmd_mark_tp2', capabilities=active_journal_only)
        registry.register('MOVE BE', '_cmd_move_be', capabilities=active_journal_only)
        registry.register('PARTIAL DONE', '_cmd_partial_done', capabilities=active_journal_only)
        registry.register(
            'FINAL CLOSE',
            '_cmd_final_close',
            capabilities=CommandCapabilities(requires_analysis=True, requires_journal=True, requires_active_journal=True, default_timeframe=DEFAULT_TF, renderer='journal'),
        )
        registry.register('JOURNAL MANAGER', '_cmd_journal_manager', capabilities=analysis_with_journal)
        registry.register('BOTS STATUS', '_cmd_bots_status', capabilities=CommandCapabilities(renderer='status'))
        registry.register('СТАТУС БОТОВ', '_cmd_bots_status', capabilities=CommandCapabilities(renderer='status'))
        registry.register('BOT HELP', '_cmd_bot_help', capabilities=CommandCapabilities(renderer='help'))
        registry.register('ПОМОЩЬ ПО БОТАМ', '_cmd_bot_help', capabilities=CommandCapabilities(renderer='help'))
        registry.register_prefix(
            'BOT <NAME> <ACTION>',
            lambda t: t.startswith('BOT ') and any(x in t for x in ('CT LONG','CT SHORT','RANGE LONG','RANGE SHORT')),
            '_cmd_bot_manual_action',
            capabilities=CommandCapabilities(renderer='status'),
        )
        return registry

    def _answer(self, chat_id: int, payload: BotResponsePayload | str) -> None:
        self.responder(chat_id, payload)

    def handle(self, chat_id: int, text: str) -> None:
        upper = (text or '').strip().upper()
        trace = RequestTrace(command=upper or 'UNKNOWN', chat_id=chat_id)
        ctx = AnalysisRequestContext(trace=trace)
        batch_state = self._touch_batch_state(chat_id)

        try:
            logger.info('request.start request_id=%s chat_id=%s command=%s', trace.request_id, chat_id, upper)
            resolution = self.registry.resolve(upper)
            trace.mark('resolve')
            if resolution is None:
                payload = BotResponsePayload(
                    text='Команда не найдена.\n\nНажми кнопку или напиши HELP.',
                    command=upper,
                    metadata=trace.as_metadata(),
                )
                logger.info('request.unknown request_id=%s command=%s', trace.request_id, upper)
                return self._answer(chat_id, payload)

            entry = resolution.entry
            effective_tf = resolution.resolved_timeframe or normalize_tf(text) or DEFAULT_TF
            capabilities = entry.capabilities
            trace.set(action=entry.handler_name, timeframe=effective_tf, renderer=capabilities.renderer)

            prefetched_snapshots: dict[str, object] = {}
            prefetched_journal = None
            prefetched_position = None
            bundle_cache = self._get_bundle_cache(chat_id)

            if capabilities.requires_analysis:
                analysis_tf = effective_tf or capabilities.default_timeframe or DEFAULT_TF
                cached_snapshots = (bundle_cache or {}).get('snapshots') if isinstance(bundle_cache, dict) else {}
                if isinstance(cached_snapshots, dict) and analysis_tf in cached_snapshots:
                    prefetched_snapshots[analysis_tf] = cached_snapshots[analysis_tf]
                    if trace is not None:
                        trace.mark(f'prefetch:{analysis_tf}:bundle_cache')
                else:
                    prefetched_snapshots[analysis_tf] = ctx.get_snapshot(analysis_tf)
            if capabilities.requires_journal:
                cached_journal = (bundle_cache or {}).get('journal') if isinstance(bundle_cache, dict) else None
                prefetched_journal = cached_journal or JournalSnapshot.from_dict(load_trade_journal())
            if capabilities.requires_position:
                cached_position = (bundle_cache or {}).get('position') if isinstance(bundle_cache, dict) else None
                prefetched_position = cached_position or PositionSnapshot.from_dict(load_position_state())
            trace.mark('prefetch')

            logger.info(
                'command.prefetch request_id=%s command=%s snapshots=%s journal=%s position=%s',
                trace.request_id,
                upper,
                ','.join(sorted(prefetched_snapshots.keys())) or '-',
                prefetched_journal is not None,
                prefetched_position is not None,
            )

            validation = validate_command_context(
                upper,
                capabilities,
                analysis_snapshot=next(iter(prefetched_snapshots.values()), None),
                journal_snapshot=prefetched_journal,
                position_snapshot=prefetched_position,
                timeframe=effective_tf,
            )
            trace.mark('validate')
            if not validation.ok:
                logger.info('command.validation_failed request_id=%s command=%s', trace.request_id, upper)
                payload = validation.payload or BotResponsePayload(text='Команда недоступна.', command=upper)
                payload.metadata.setdefault('request_id', trace.request_id)
                payload.metadata.setdefault('timings', dict(trace.marks))
                payload.metadata.setdefault('total_ms', trace.total_ms)
                return self._answer(chat_id, payload)

            action_ctx = CommandActionContext(
                command=upper,
                timeframe=effective_tf,
                snapshot_loader=ctx.get_snapshot,
                request_context=ctx,
                journal_loader=lambda: JournalSnapshot.from_dict(load_trade_journal()),
                position_loader=lambda: PositionSnapshot.from_dict(load_position_state()),
                prefetched_snapshots=prefetched_snapshots,
                prefetched_journal=prefetched_journal,
                prefetched_position=prefetched_position,
                trace=trace,
            )
            actions = build_action_map(action_ctx)
            action = actions[entry.handler_name]
            logger.info(
                'command.resolved request_id=%s command=%s action=%s tf=%s needs_analysis=%s needs_journal=%s needs_position=%s renderer=%s guards=journal:%s position:%s',
                trace.request_id,
                upper,
                entry.handler_name,
                effective_tf,
                capabilities.requires_analysis,
                capabilities.requires_journal,
                capabilities.requires_position,
                capabilities.renderer,
                capabilities.requires_active_journal,
                capabilities.requires_active_position,
            )

            payload = execute_action_safely(
                command=upper,
                action_name=entry.handler_name,
                action=action,
                timeframe=effective_tf,
                analysis_snapshot=next(iter(prefetched_snapshots.values()), None),
                journal_snapshot=prefetched_journal,
                position_snapshot=prefetched_position,
                trace=trace,
            )
            trace.mark('action')
            payload.metadata.setdefault('request_id', trace.request_id)
            payload.metadata.setdefault('timings', dict(trace.marks))
            payload.metadata.setdefault('total_ms', trace.total_ms)

            if self._is_mutating_handler(entry.handler_name):
                # During a burst, keep the current bundle alive so the rest of the queued
                # read-only commands reuse one coherent snapshot set. The bundle will expire
                # shortly after the batch window closes.
                if self._get_batch_state(chat_id) is None:
                    self._invalidate_bundle_cache(chat_id)
            self._save_bundle_cache(
                chat_id,
                snapshots=prefetched_snapshots,
                journal=prefetched_journal,
                position=prefetched_position,
            )
            return self._answer(chat_id, payload)
        except Exception:
            logger.exception('command.flow_failed request_id=%s command=%s', trace.request_id, upper)
            fallback = BotResponsePayload(
                text='Произошла системная ошибка при обработке команды. Детали записаны в logs/errors.log.',
                command=upper,
                timeframe=normalize_tf(text) or DEFAULT_TF,
                metadata=trace.as_metadata(),
            )
            return self._answer(chat_id, fallback)
        finally:
            logger.info('request.done request_id=%s command=%s total_ms=%s | %s', trace.request_id, upper, trace.total_ms, ' | '.join(ctx.summary_lines()))
