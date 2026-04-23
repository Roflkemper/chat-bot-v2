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
    kb.row(_btn("/menu"), _btn("HELP"), _btn("BTC GINAREA"))
    kb.row(_btn("BTC 5M"), _btn("BTC 15M"), _btn("BTC 1H"))
    kb.row(_btn("BTC 4H"), _btn("BTC 1D"))
    return kb


def build_debug_keyboard() -> ReplyKeyboardMarkup:
    return build_main_keyboard()


def build_dynamic_keyboard(state: Dict[str, Any] | None = None) -> ReplyKeyboardMarkup:
    return build_main_keyboard()
