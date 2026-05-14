from __future__ import annotations

import logging
from typing import Callable

from models.responses import BotResponsePayload
from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot
from services.response_service import ResponseService
from utils.observability import RequestTrace

logger = logging.getLogger(__name__)


def execute_action_safely(
    *,
    command: str,
    action_name: str,
    action: Callable[[], BotResponsePayload | str | None],
    timeframe: str | None = None,
    analysis_snapshot: AnalysisSnapshot | None = None,
    journal_snapshot: JournalSnapshot | None = None,
    position_snapshot: PositionSnapshot | None = None,
    trace: RequestTrace | None = None,
) -> BotResponsePayload:
    try:
        result = action()
        if isinstance(result, BotResponsePayload):
            if trace is not None:
                result.metadata.setdefault("request_id", trace.request_id)
                result.metadata.setdefault("timings", dict(trace.marks))
                result.metadata.setdefault("total_ms", trace.total_ms)
            return result
        if result is None:
            logger.warning('command.action_empty command=%s action=%s tf=%s', command, action_name, timeframe)
            return ResponseService.plain_text(
                command,
                'Команда выполнилась без текста ответа. Попробуй ещё раз.',
                timeframe=timeframe,
                analysis_snapshot=analysis_snapshot,
                journal_snapshot=journal_snapshot,
                position_snapshot=position_snapshot,
            )
        return ResponseService.plain_text(
            command,
            str(result),
            timeframe=timeframe,
            analysis_snapshot=analysis_snapshot,
            journal_snapshot=journal_snapshot,
            position_snapshot=position_snapshot,
        )
    except Exception:
        logger.exception('command.action_failed command=%s action=%s tf=%s', command, action_name, timeframe)
        return ResponseService.plain_text(
            command,
            'Во время выполнения команды произошла ошибка. Я сохранил детали в логах. Попробуй команду ещё раз.',
            timeframe=timeframe,
            analysis_snapshot=analysis_snapshot,
            journal_snapshot=journal_snapshot,
            position_snapshot=position_snapshot,
            error_kind='action_execution_failed',
            failed_action=action_name,
        )
