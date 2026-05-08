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
    # Row 1 — flagship: morning brief (one-glance summary), then deep-dive
    kb.row(_btn("/morning_brief"), _btn("/advise"), _btn("FINAL DECISION"))
    # Row 2 — momentum / regime / setups
    kb.row(_btn("/momentum_check"), _btn("/regime_v2"), _btn("BTC 1H"))
    # Row 3 — bots / portfolio summaries
    kb.row(_btn("СТАТУС БОТОВ"), _btn("BTC GINAREA"), _btn("BTC SUMMARY"))
    # Row 4 — paper trader / watchlist / advisor / help
    kb.row(_btn("/papertrader"), _btn("/watch"), _btn("/advisor"), _btn("HELP"))
    return kb


def build_debug_keyboard() -> ReplyKeyboardMarkup:
    return build_main_keyboard()


def build_dynamic_keyboard(state: Dict[str, Any] | None = None) -> ReplyKeyboardMarkup:
    return build_main_keyboard()
