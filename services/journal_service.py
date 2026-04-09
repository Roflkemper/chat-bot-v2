from __future__ import annotations

from typing import Any, Dict, Union

from core.btc_plan import fmt_price
from models.snapshots import AnalysisSnapshot, PositionSnapshot
from storage.position_store import close_position, load_position_state, open_position
from storage.trade_journal import final_close_trade, open_trade_journal


def _coerce_analysis_snapshot(analysis_data: Union[AnalysisSnapshot, Dict[str, Any]], symbol: str = "BTCUSDT", timeframe: str = "1h") -> AnalysisSnapshot:
    if isinstance(analysis_data, AnalysisSnapshot):
        return analysis_data
    return AnalysisSnapshot.from_dict(analysis_data, symbol=symbol, timeframe=timeframe)


def open_position_with_journal(side: str, analysis_data: Union[AnalysisSnapshot, Dict[str, Any]], timeframe: str, symbol: str = "BTCUSDT") -> str:
    analysis_snapshot = _coerce_analysis_snapshot(analysis_data, symbol=symbol, timeframe=timeframe)
    pos = open_position(
        side=side,
        symbol=symbol,
        timeframe=timeframe,
        entry_price=analysis_snapshot.price,
        comment=f"Открыто через Telegram-кнопку {side}",
    )
    decision = analysis_snapshot.decision.to_dict()
    journal_notes = f"journal created from telegram button {side}"
    if decision.get("summary"):
        journal_notes = f"{journal_notes} | decision: {decision.get('summary')}"
    journal = open_trade_journal(
        side=side,
        symbol=symbol,
        timeframe=timeframe,
        entry_price=analysis_snapshot.price,
        notes=journal_notes,
        decision_snapshot=analysis_snapshot.decision.to_dict(),
        analysis_snapshot=analysis_snapshot.to_dict(),
    )
    lines = [
        "✅ POSITION SAVED",
        "",
        f"Сторона: {pos.get('side')}",
        f"Инструмент: {pos.get('symbol')}",
        f"Таймфрейм: {pos.get('timeframe')}",
        f"Цена входа: {fmt_price(pos.get('entry_price'))}",
        f"Открыта: {pos.get('opened_at')}",
        "",
        f"journal_id: {journal.get('trade_id')}",
        f"lifecycle_state: {journal.get('lifecycle_state') or 'ENTRY'}",
    ]
    if decision:
        lines.extend([
            "",
            "Decision snapshot:",
            f"• направление: {decision.get('direction_text') or 'нет данных'}",
            f"• действие: {decision.get('action_text') or 'нет данных'}",
            f"• режим: {decision.get('mode') or 'нет данных'}",
            f"• confidence: {round(decision.get('confidence_pct') or 0.0, 1)}%",
            f"• risk: {decision.get('risk_level') or 'нет данных'}",
        ])
    return "\n".join(lines)


def close_position_with_context(reason: str, analysis_data: Union[AnalysisSnapshot, Dict[str, Any], None] = None) -> str:
    old = PositionSnapshot.from_dict(load_position_state())
    if old.has_position and analysis_data is not None:
        position_snapshot = _coerce_analysis_snapshot(analysis_data, symbol=old.symbol or "BTCUSDT", timeframe=old.timeframe or "1h")
        final_close_trade(
            reason=reason,
            exit_price=position_snapshot.price,
            close_context_snapshot=position_snapshot.to_dict(),
        )
    else:
        final_close_trade(reason)
    close_position()
    return "Позиция закрыта." if old.has_position else "Позиции для закрытия не было."
