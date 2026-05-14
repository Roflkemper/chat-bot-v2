from __future__ import annotations

from dataclasses import dataclass

from handlers.command_registry import CommandCapabilities
from models.responses import BotResponsePayload
from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot
from services.response_service import ResponseService


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    payload: BotResponsePayload | None = None


def validate_command_context(
    command: str,
    capabilities: CommandCapabilities,
    *,
    analysis_snapshot: AnalysisSnapshot | None = None,
    journal_snapshot: JournalSnapshot | None = None,
    position_snapshot: PositionSnapshot | None = None,
    timeframe: str | None = None,
) -> ValidationResult:
    if capabilities.requires_analysis and analysis_snapshot is None:
        return ValidationResult(
            False,
            ResponseService.plain_text(
                command,
                'Не удалось подготовить analysis snapshot для этой команды. Попробуй ещё раз.',
                timeframe=timeframe,
            ),
        )

    if capabilities.requires_active_journal:
        if journal_snapshot is None or not journal_snapshot.trade_id or not journal_snapshot.has_active_trade:
            return ValidationResult(
                False,
                ResponseService.plain_text(
                    command,
                    'Сейчас нет активной сделки в journal.\n\nСначала открой позицию через ОТКРЫТЬ ЛОНГ или ОТКРЫТЬ ШОРТ.',
                    journal_snapshot=journal_snapshot,
                    timeframe=timeframe,
                ),
            )

    if capabilities.requires_active_position:
        if position_snapshot is None or not position_snapshot.has_position:
            return ValidationResult(
                False,
                ResponseService.plain_text(
                    command,
                    'Сейчас нет активной позиции.\n\nСначала открой позицию через ОТКРЫТЬ ЛОНГ или ОТКРЫТЬ ШОРТ.',
                    position_snapshot=position_snapshot,
                    timeframe=timeframe,
                ),
            )

    return ValidationResult(True, None)
