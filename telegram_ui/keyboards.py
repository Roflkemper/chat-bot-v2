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
    """Redesigned 2026-05-11 — see docs/TG_AUDIT_REPORT.md for rationale.

    Layout principles:
      - Row 1: daily snapshot (state of bot + open legs + grid bots)
      - Row 2: trading insight (brief → final decision → advise)
      - Row 3: health & history (pipeline funnel, precision, changelog)
      - Row 4: utility (watch, help)
    Removed duplicates (/advise + /advisor), debug commands (/regime_v2),
    redundant buttons (BTC SUMMARY, СТАТУС БОТОВ → /ginarea).
    """
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    # Row 1 — daily snapshot
    kb.row(_btn("/status"), _btn("/p15"), _btn("/ginarea"))
    # Row 2 — trading insight
    kb.row(_btn("/morning_brief"), _btn("FINAL DECISION"), _btn("/advise"))
    # Row 3 — health & history
    kb.row(_btn("/pipeline"), _btn("/precision"), _btn("/changelog"))
    # Row 4 — utility
    kb.row(_btn("/watch"), _btn("HELP"))
    return kb


def build_debug_keyboard() -> ReplyKeyboardMarkup:
    return build_main_keyboard()


def build_dynamic_keyboard(state: Dict[str, Any] | None = None) -> ReplyKeyboardMarkup:
    return build_main_keyboard()
