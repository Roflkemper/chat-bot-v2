from __future__ import annotations

from typing import Callable, Optional

from core_facade import (
    build_legacy_text,
    build_legacy_text_with_journal,
    build_legacy_text_with_position_and_journal,
)
from models.responses import BotResponsePayload
from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot


class ResponseService:
    @staticmethod
    def _fallback_text(command: str, analysis_snapshot: Optional[AnalysisSnapshot] = None) -> str:
        fallback = f"⚠️ {command} временно недоступен: основной блок не собрался. Показан безопасный fallback."
        if analysis_snapshot is not None:
            try:
                from renderers.telegram_renderers import build_decision_block_text
                decision_text = build_decision_block_text(analysis_snapshot)
                if decision_text:
                    return decision_text + "\n\n" + fallback
            except Exception:
                pass
            try:
                price = getattr(analysis_snapshot, "price", 0.0)
                tf = getattr(analysis_snapshot, "timeframe", "1h")
                return f"📘 SAFE FALLBACK [{tf}]\n\nЦена: {price:,.2f}".replace(",", " ") + "\n\n" + fallback
            except Exception:
                pass
        return fallback

    @staticmethod
    def render_text(
        command: str,
        *,
        text_builder: Callable[..., str],
        analysis_snapshot: Optional[AnalysisSnapshot] = None,
        journal_snapshot: Optional[JournalSnapshot] = None,
        position_snapshot: Optional[PositionSnapshot] = None,
        timeframe: Optional[str] = None,
        **kwargs,
    ) -> BotResponsePayload:
        try:
            if analysis_snapshot is not None and (position_snapshot is not None or journal_snapshot is not None):
                text = build_legacy_text_with_position_and_journal(
                    text_builder,
                    analysis_snapshot,
                    position_snapshot=position_snapshot,
                    journal_snapshot=journal_snapshot,
                    **kwargs,
                )
            elif analysis_snapshot is not None and journal_snapshot is not None:
                text = build_legacy_text_with_journal(
                    text_builder,
                    analysis_snapshot,
                    journal_snapshot=journal_snapshot,
                    **kwargs,
                )
            elif analysis_snapshot is not None:
                text = build_legacy_text(text_builder, analysis_snapshot, **kwargs)
            else:
                text = text_builder(**kwargs)
        except Exception:
            text = ResponseService._fallback_text(command, analysis_snapshot)
        return BotResponsePayload(
            text=text,
            command=command,
            timeframe=timeframe,
            analysis_snapshot=analysis_snapshot,
            journal_snapshot=journal_snapshot,
            position_snapshot=position_snapshot,
        )

    @staticmethod
    def plain_text(command: str, text: str, **kwargs) -> BotResponsePayload:
        return BotResponsePayload(text=text, command=command, metadata=dict(kwargs))

    @staticmethod
    def file_response(command: str, text: str, *, file_path: str, file_caption: str | None = None, **kwargs) -> BotResponsePayload:
        return BotResponsePayload(
            text=text,
            command=command,
            metadata=dict(kwargs),
            file_path=file_path,
            file_caption=file_caption,
        )
