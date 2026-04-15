from __future__ import annotations

from typing import Any, Dict

from telebot.types import ReplyKeyboardMarkup, KeyboardButton


def _btn(text: str) -> KeyboardButton:
    return KeyboardButton(text)


def _norm_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y", "on", "да"}:
        return True
    if s in {"false", "0", "no", "n", "off", "нет"}:
        return False
    return bool(value)


def build_main_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.row(_btn("/market"), _btn("/entry"), _btn("/exit"))
    kb.row(_btn("BTC 15M"), _btn("BTC 1H"), _btn("ФИНАЛЬНОЕ РЕШЕНИЕ"))
    kb.row(_btn("/position"), _btn("/manage"), _btn("/status"))
    kb.row(_btn("СВОДКА BTC"), _btn("ПРОГНОЗ BTC"), _btn("СТАТУС БОТОВ"))
    kb.row(_btn("BTC GINAREA"), _btn("ОТЛАДКА"))
    return kb


def build_debug_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.row(_btn("/market"), _btn("/entry"), _btn("/exit"))
    kb.row(_btn("BTC INVALIDATION"), _btn("ПОЧЕМУ НЕТ СДЕЛКИ"), _btn("СТАТУС СИСТЕМЫ"))
    kb.row(_btn("/position"), _btn("/manage"), _btn("СТАТУС БОТОВ"))
    kb.row(_btn("DEBUG EXPORT"), _btn("СОХРАНИТЬ КЕЙС"), _btn("ПОМОЩЬ"))
    kb.row(_btn("ОБНОВИТЬ ИНТЕРФЕЙС"), _btn("ГЛАВНОЕ МЕНЮ"))
    return kb


def build_dynamic_keyboard(state: Dict[str, Any] | None = None) -> ReplyKeyboardMarkup:
    state = state or {}
    direction = _norm_upper(state.get("direction"))
    action = _norm_upper(state.get("action"))
    has_position = _safe_bool(state.get("has_position"))
    position_side = _norm_upper(state.get("position_side"))
    risk = _norm_upper(state.get("risk"))
    confidence = float(state.get("confidence") or 0.0)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.row(_btn("/market"), _btn("/entry"), _btn("/exit"))
    kb.row(_btn("BTC 15M"), _btn("BTC 1H"), _btn("ФИНАЛЬНОЕ РЕШЕНИЕ"))

    if has_position:
        kb.row(_btn("/position"), _btn("/manage"), _btn("BTC INVALIDATION"))
        if position_side == "LONG":
            kb.row(_btn("ВЕСТИ BTC"), _btn("ВЕСТИ ЛОНГ"), _btn("ЗАКРЫТЬ BTC"))
        elif position_side == "SHORT":
            kb.row(_btn("ВЕСТИ BTC"), _btn("ВЕСТИ ШОРТ"), _btn("ЗАКРЫТЬ BTC"))
        else:
            kb.row(_btn("ВЕСТИ BTC"), _btn("МЕНЕДЖЕР BTC"), _btn("ЗАКРЫТЬ BTC"))
    else:
        kb.row(_btn("/status"), _btn("СВОДКА BTC"), _btn("ПРОГНОЗ BTC"))
        if direction in {"LONG", "ЛОНГ"} and confidence >= 55.0:
            kb.row(_btn("ОТКРЫТЬ ЛОНГ"), _btn("МЕНЕДЖЕР BTC"), _btn("BTC INVALIDATION"))
        elif direction in {"SHORT", "ШОРТ"} and confidence >= 55.0:
            kb.row(_btn("ОТКРЫТЬ ШОРТ"), _btn("МЕНЕДЖЕР BTC"), _btn("BTC INVALIDATION"))
        else:
            kb.row(_btn("⚡ ЧТО ДЕЛАТЬ СЕЙЧАС"), _btn("ЛУЧШАЯ СДЕЛКА"), _btn("МЕНЕДЖЕР BTC"))
        if risk == "HIGH" or action in {"WAIT", "ЖДАТЬ", "NO_TRADE"}:
            kb.row(_btn("ПОЧЕМУ НЕТ СДЕЛКИ"), _btn("BTC INVALIDATION"), _btn("СТАТУС БОТОВ"))

    kb.row(_btn("BTC GINAREA"), _btn("ОТЛАДКА"))
    return kb
