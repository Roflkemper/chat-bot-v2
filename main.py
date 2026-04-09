from __future__ import annotations

import logging
import os
import traceback
import time
import re
from typing import Any, Dict

import telebot
from telebot import types

from core.app_logging import setup_logging
from handlers.command_handler import CommandHandler
from models.responses import BotResponsePayload
from storage.personal_bot_learning import build_closed_trade_learning_text, update_learning_from_closed_trade
from telegram_ui.keyboards import build_debug_keyboard, build_dynamic_keyboard, build_main_keyboard
from core.exchange_liquidity_engine import start_background_engine
from core.auto_edge_alerts import AutoEdgeAlertService

try:
    from config import BOT_TOKEN, CHAT_ID, CONFIG_SOURCE, AUTO_EDGE_ALERTS_ENABLED, AUTO_EDGE_ALERTS_INTERVAL_SEC, AUTO_EDGE_ALERTS_COOLDOWN_SEC, AUTO_EDGE_ALERTS_TIMEFRAMES
except Exception:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    CHAT_ID = os.getenv("CHAT_ID", "")
    CONFIG_SOURCE = "environment_or_empty"
    AUTO_EDGE_ALERTS_ENABLED = True
    AUTO_EDGE_ALERTS_INTERVAL_SEC = int(os.getenv("AUTO_EDGE_ALERTS_INTERVAL_SEC", "45"))
    AUTO_EDGE_ALERTS_COOLDOWN_SEC = int(os.getenv("AUTO_EDGE_ALERTS_COOLDOWN_SEC", "300"))
    AUTO_EDGE_ALERTS_TIMEFRAMES = os.getenv("AUTO_EDGE_ALERTS_TIMEFRAMES", "15m,1h")

setup_logging()
logger = logging.getLogger(__name__)

BOT_TOKEN = str(BOT_TOKEN or "").strip()

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден или имеет неверный формат. "
        "Положи .env или bot_local_config.json рядом с main.py, в папку проекта или в родительскую папку. "
        f"Источник конфига: {CONFIG_SOURCE or 'not_found'}"
    )

logger.info("Telegram config source: %s", CONFIG_SOURCE or "not_found")
print(f"[OK] Telegram config source: {CONFIG_SOURCE or 'not_found'}")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

LAST_UI_STATE: Dict[int, Dict[str, Any]] = {}
LAST_UI_MODE: Dict[int, str] = {}
LAST_LIFECYCLE_ALERTS: Dict[int, str] = {}
LAST_LEARNING_ALERTS: Dict[int, str] = {}
LAST_CHAT_ACTIVITY: Dict[int, float] = {}
LAST_SENT_TEXT_SIGNATURES: Dict[int, Dict[str, float]] = {}
LAST_COMMAND_TEXTS: Dict[int, Dict[str, tuple[str, float]]] = {}
LAST_FAMILY_TEXTS: Dict[int, Dict[str, tuple[str, float]]] = {}
BURST_WINDOW_SEC = 3.0
LIFECYCLE_FRESH_SEC = 120.0


def _touch_chat_activity(chat_id: int) -> float:
    now = time.time()
    LAST_CHAT_ACTIVITY[chat_id] = now
    return now


def _in_burst(chat_id: int) -> bool:
    last_at = float(LAST_CHAT_ACTIVITY.get(chat_id) or 0.0)
    return (time.time() - last_at) <= BURST_WINDOW_SEC


def _remember_text_signature(chat_id: int, text: str) -> bool:
    sigs = LAST_SENT_TEXT_SIGNATURES.setdefault(chat_id, {})
    now = time.time()
    text = str(text or '').strip()
    if not text:
        return False
    # prune old entries
    for key, ts in list(sigs.items()):
        if now - ts > 30.0:
            sigs.pop(key, None)
    if text in sigs and (now - sigs[text]) <= BURST_WINDOW_SEC:
        return True
    sigs[text] = now
    return False




def _compress_output_text(command: str, text: str) -> str:
    command_u = str(command or '').strip().upper()
    body = str(text or '').strip()
    if not body:
        return body
    if command_u in {'⚡ ЧТО ДЕЛАТЬ СЕЙЧАС', '⚡ ЧТО ДЕЛАТЬ', 'ЛУЧШАЯ СДЕЛКА', 'МЕНЕДЖЕР BTC', 'BTC TRADE MANAGER', 'BTC GINAREA', 'СТАТУС БОТОВ', 'BTC SUMMARY', 'СВОДКА BTC', 'BTC FORECAST', 'ПРОГНОЗ BTC', 'ФИНАЛЬНОЕ РЕШЕНИЕ', 'FINAL DECISION'}:
        while '\n\n\n' in body:
            body = body.replace('\n\n\n', '\n\n')
        lines = body.splitlines()
        compact: list[str] = []
        prev = None
        for line in lines:
            norm = line.strip()
            if norm and norm == prev:
                continue
            prev = norm or prev
            compact.append(line.rstrip())
        body = '\n'.join(compact).strip()
    return body


def _remember_command_text(chat_id: int, command: str, text: str) -> bool:
    cmd = str(command or '').strip().upper()
    if not cmd:
        return False
    bucket = LAST_COMMAND_TEXTS.setdefault(chat_id, {})
    now = time.time()
    for key, (_, ts) in list(bucket.items()):
        if now - ts > 20.0:
            bucket.pop(key, None)
    prev = bucket.get(cmd)
    bucket[cmd] = (text, now)
    return bool(prev and prev[0].strip() == text.strip() and (now - prev[1]) <= BURST_WINDOW_SEC)

def _command_family(command: str) -> str:
    cmd = str(command or '').strip().upper()
    if cmd in {'BTC 15M', 'BTC 1H', 'BTC SUMMARY', 'СВОДКА BTC', 'BTC FORECAST', 'ПРОГНОЗ BTC', 'ФИНАЛЬНОЕ РЕШЕНИЕ', 'FINAL DECISION'}:
        return 'ANALYSIS'
    if cmd in {'⚡ ЧТО ДЕЛАТЬ СЕЙЧАС', '⚡ ЧТО ДЕЛАТЬ', 'ЛУЧШАЯ СДЕЛКА', 'МЕНЕДЖЕР BTC', 'BTC TRADE MANAGER', 'BTC GINAREA'}:
        return 'ACTION'
    return cmd or 'OTHER'


def _normalize_family_text(command: str, text: str) -> str:
    body = str(text or '').upper()
    body = re.sub(r'Цена:\s*[0-9., ]+', 'Цена: X', body)
    body = re.sub(r'\[[^\]]+\]', '[TF]', body)
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('ACTION AUTHORITY V12.8'):
            continue
        if line.startswith('🧠 FINAL DECISION') or line.startswith('📘 BTC SUMMARY') or line.startswith('🔮 BTC FORECAST') or line.startswith('📊 BTC ANALYSIS'):
            continue
        lines.append(line)
    return "\n".join(lines[:20])


def _remember_family_text(chat_id: int, command: str, text: str) -> bool:
    family = _command_family(command)
    if family in {'', 'OTHER'}:
        return False
    bucket = LAST_FAMILY_TEXTS.setdefault(chat_id, {})
    now = time.time()
    for key, (_, ts) in list(bucket.items()):
        if now - ts > 8.0:
            bucket.pop(key, None)
    normalized = _normalize_family_text(command, text)
    prev = bucket.get(family)
    bucket[family] = (normalized, now)
    return bool(prev and prev[0] == normalized and (now - prev[1]) <= BURST_WINDOW_SEC)


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


def _norm_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _fmt_num(value: Any, digits: int = 2) -> str:
    try:
        if value is None or value == "":
            return "-"
        return f"{float(value):,.{digits}f}".replace(",", " ")
    except Exception:
        return str(value or "-")


def _build_lifecycle_alert_text(payload: BotResponsePayload) -> str:
    journal = payload.journal_snapshot
    if not journal:
        return ""

    history = list(journal.lifecycle_history or [])
    if not history:
        return ""

    event = history[-1]
    state = _norm_upper(event.get("state") or journal.lifecycle_state or "")
    side = _norm_upper(journal.side or "") or "NONE"
    tf = journal.timeframe or payload.timeframe or "1h"
    symbol = journal.symbol or "BTCUSDT"
    entry = _fmt_num(journal.entry_price, 2)
    exit_price = _fmt_num(journal.exit_price, 2)
    rr = _fmt_num(journal.result_rr, 2)
    pct = _fmt_num(journal.result_pct, 2)

    state_titles = {
        "ENTRY": "🚀 LIFECYCLE ALERT — ENTRY",
        "TP1": "🎯 LIFECYCLE ALERT — TP1",
        "PARTIAL_DONE": "✂️ LIFECYCLE ALERT — PARTIAL DONE",
        "BE_MOVED": "🛡 LIFECYCLE ALERT — MOVE TO BE",
        "HOLD_RUNNER": "🏃 LIFECYCLE ALERT — HOLD RUNNER",
        "EXIT": "✅ LIFECYCLE ALERT — EXIT",
    }
    header = state_titles.get(state)
    if not header:
        return ""

    lines = [header, "", f"Инструмент: {symbol}", f"Таймфрейм: {tf}", f"Сторона: {side}"]
    if side in {"LONG", "SHORT"}:
        lines.append(f"Entry: {entry}")

    if state == "ENTRY":
        lines.extend([
            "",
            "Переход: NO_TRADE → ENTRY",
            "Что это значит:",
            "• сделка открыта и lifecycle запущен",
            "• дальше бот ждёт TP1 / partial / BE / runner",
        ])
    elif state == "TP1":
        lines.extend([
            "",
            "Переход: ENTRY → TP1",
            "Что делать:",
            "• проверить частичную фиксацию",
            "• не отдавать уже взятый ход без плана",
        ])
    elif state == "PARTIAL_DONE":
        lines.extend([
            "",
            "Переход: TP1 → PARTIAL_DONE",
            "Что делать:",
            "• часть позиции уже зафиксирована",
            "• дальше логика ведёт к BE и runner",
        ])
    elif state == "BE_MOVED":
        lines.extend([
            "",
            "Переход: PARTIAL_DONE → BE_MOVED",
            "Что делать:",
            "• остаток защищён переводом в безубыток",
            "• теперь задача — не испортить runner",
        ])
    elif state == "HOLD_RUNNER":
        lines.extend([
            "",
            "Переход: BE_MOVED → HOLD_RUNNER",
            "Что делать:",
            "• держать остаток только пока структура жива",
            "• при ослаблении рынка бот должен перевести runner в trail или exit",
        ])
    elif state == "EXIT":
        lines.extend([
            "",
            "Переход: HOLD_RUNNER → EXIT",
            f"Exit: {exit_price}",
            f"Result: {pct}% | RR: {rr}",
            "Что это значит:",
            "• жизненный цикл сделки завершён",
            "• можно фиксировать результат в журнале и ждать новый сценарий",
        ])

    note = str(event.get("note") or "").strip()
    at = str(event.get("at") or "").strip()
    if note:
        lines.extend(["", f"Note: {note}"])
    if at:
        lines.append(f"At: {at}")
    return "\n".join(lines)


def _maybe_send_closed_trade_learning_alert(bot_obj: telebot.TeleBot, chat_id: int, payload: BotResponsePayload, reply_markup: types.ReplyKeyboardMarkup) -> None:
    journal = payload.journal_snapshot
    if not journal or not bool(journal.closed):
        return
    signature = "|".join([str(journal.trade_id or "-"), str(journal.closed_at or "-"), str(journal.exit_reason_classifier or "-")])
    if LAST_LEARNING_ALERTS.get(chat_id) == signature:
        return
    update = update_learning_from_closed_trade(journal.to_dict())
    if not update.get("updated"):
        return
    alert_text = build_closed_trade_learning_text(update)
    if not alert_text:
        return
    LAST_LEARNING_ALERTS[chat_id] = signature
    bot_obj.send_message(chat_id, alert_text, reply_markup=reply_markup)


def _maybe_send_lifecycle_alert(bot_obj: telebot.TeleBot, chat_id: int, payload: BotResponsePayload, reply_markup: types.ReplyKeyboardMarkup) -> None:
    journal = payload.journal_snapshot
    if not journal:
        return
    history = list(journal.lifecycle_history or [])
    if not history:
        return
    event = history[-1]
    state = _norm_upper(event.get("state") or journal.lifecycle_state or "")
    if state not in {"ENTRY", "TP1", "PARTIAL_DONE", "BE_MOVED", "HOLD_RUNNER", "EXIT"}:
        return
    event_at = str(event.get("at") or "").strip()
    signature = "|".join([str(journal.trade_id or "-"), state, event_at or "-"])
    if LAST_LIFECYCLE_ALERTS.get(chat_id) == signature:
        return
    # Do not rebroadcast stale lifecycle events during read-only bursts.
    if _in_burst(chat_id):
        return
    if event_at:
        try:
            import datetime as _dt
            parsed = _dt.datetime.fromisoformat(event_at.replace('Z', '+00:00'))
            age_sec = time.time() - parsed.timestamp()
            if age_sec > LIFECYCLE_FRESH_SEC:
                return
        except Exception:
            pass
    alert_text = _build_lifecycle_alert_text(payload)
    if not alert_text:
        return
    LAST_LIFECYCLE_ALERTS[chat_id] = signature
    bot_obj.send_message(chat_id, alert_text, reply_markup=reply_markup)


def set_ui_mode(chat_id: int, mode: str) -> None:
    LAST_UI_MODE[chat_id] = mode


def get_ui_mode(chat_id: int) -> str:
    return LAST_UI_MODE.get(chat_id, "dynamic")


def save_ui_state(chat_id: int, state: Dict[str, Any]) -> None:
    LAST_UI_STATE[chat_id] = dict(state or {})


def get_ui_state(chat_id: int) -> Dict[str, Any]:
    return dict(LAST_UI_STATE.get(chat_id, {}))


def _extract_setup_valid(payload: BotResponsePayload) -> bool:
    snap = payload.analysis_snapshot
    if not snap:
        return False
    analysis = snap.analysis or {}
    setup = analysis.get("setup_quality") if isinstance(analysis.get("setup_quality"), dict) else {}
    if setup:
        if "setup_valid" in setup:
            return _safe_bool(setup.get("setup_valid"))
        entry_filter = _norm_upper(setup.get("entry_filter_status"))
        if entry_filter in {"BLOCK", "BLOCKED"}:
            return False
        if entry_filter in {"ALLOW", "PASS", "OK"}:
            return True
    decision = snap.decision
    if decision.action_text in {"ВХОДИТЬ", "СМОТРЕТЬ СЕТАП"} and (decision.confidence or decision.confidence_pct) >= 50:
        return True
    if "НЕ ЛЕЗТЬ" in _norm_upper(decision.setup_status_text) or "ПРОПУСТИТЬ" in _norm_upper(decision.setup_status_text):
        return False
    return False


def _extract_structure_status(payload: BotResponsePayload) -> str:
    snap = payload.analysis_snapshot
    if not snap:
        return ""
    analysis = snap.analysis or {}
    structure = analysis.get("structure") if isinstance(analysis.get("structure"), dict) else {}
    if structure:
        if structure.get("structure_status"):
            return str(structure.get("structure_status"))
        if _safe_bool(structure.get("choch_risk")):
            return "CHOCH_RISK"
    return ""


def build_ui_state_from_payload(payload: BotResponsePayload | str) -> Dict[str, Any]:
    if isinstance(payload, str):
        return {}
    snap = payload.analysis_snapshot
    pos = payload.position_snapshot
    journal = payload.journal_snapshot
    if not snap:
        return {}
    d = snap.decision
    return {
        "direction": d.direction_text or snap.final_decision or "НЕЙТРАЛЬНО",
        "action": d.action_text or "ЖДАТЬ",
        "confidence": float(d.confidence or d.confidence_pct or 0.0),
        "risk": d.risk or d.risk_level or "HIGH",
        "mode": d.mode or d.regime or "MIXED",
        "has_position": bool((pos.has_position if pos else False) or (journal.has_active_trade if journal else False) or (journal.active if journal else False)),
        "position_side": (pos.side if pos else "") or (journal.side if journal else "") or "NONE",
        "range_position": snap.range_position or d.range_position_zone or "UNKNOWN",
        "setup_valid": _extract_setup_valid(payload),
        "structure_status": _extract_structure_status(payload),
        "command": payload.command or "",
        "timeframe": payload.timeframe or snap.timeframe or "",
    }


def choose_keyboard(chat_id: int, state: Dict[str, Any] | None = None) -> types.ReplyKeyboardMarkup:
    mode = get_ui_mode(chat_id)
    if mode == "main":
        return build_main_keyboard()
    if mode == "debug":
        return build_debug_keyboard()
    return build_dynamic_keyboard(state or get_ui_state(chat_id))


class TelegramResponder:
    def __init__(self, telebot_instance: telebot.TeleBot) -> None:
        self.bot = telebot_instance

    def send_payload(self, chat_id: int, payload: BotResponsePayload | str) -> None:
        _touch_chat_activity(chat_id)
        if isinstance(payload, str):
            payload = BotResponsePayload(text=payload)

        text = _compress_output_text(payload.command or '', payload.text or '')
        state = build_ui_state_from_payload(payload)
        if state:
            save_ui_state(chat_id, state)
        reply_markup = choose_keyboard(chat_id, state)

        if payload.file_path:
            with open(payload.file_path, "rb") as fh:
                self.bot.send_document(
                    chat_id,
                    fh,
                    caption=payload.file_caption or None,
                    reply_markup=reply_markup,
                )

        _maybe_send_lifecycle_alert(self.bot, chat_id, payload, reply_markup)
        if not _in_burst(chat_id):
            _maybe_send_closed_trade_learning_alert(self.bot, chat_id, payload, reply_markup)

        if text:
            if _remember_text_signature(chat_id, text):
                return
            if _remember_command_text(chat_id, payload.command or '', text):
                return
            if _remember_family_text(chat_id, payload.command or '', text):
                return
            chunks = []
            current = ""
            for line in text.splitlines(True):
                if len(current) + len(line) > 3900:
                    if current:
                        chunks.append(current.rstrip())
                        current = ""
                    if len(line) > 3900:
                        for i in range(0, len(line), 3900):
                            chunks.append(line[i:i + 3900].rstrip())
                    else:
                        current = line
                else:
                    current += line
            if current.strip():
                chunks.append(current.rstrip())
            for idx, chunk in enumerate(chunks):
                markup = reply_markup if idx == len(chunks) - 1 else None
                self.bot.send_message(chat_id, chunk, reply_markup=markup)

    def send_long_message(self, chat_id: int, text: str) -> None:
        self.send_payload(chat_id, text)


responder = TelegramResponder(bot)
command_handler = CommandHandler(responder.send_payload)


@bot.message_handler(commands=["start"])
def handle_start(message: types.Message) -> None:
    set_ui_mode(message.chat.id, "main")
    bot.send_message(
        message.chat.id,
        "✅ Бот запущен.\n\nВыбирай кнопку ниже.",
        reply_markup=choose_keyboard(message.chat.id),
    )


@bot.message_handler(commands=["help"])
def handle_help(message: types.Message) -> None:
    from renderers.telegram_renderers import build_help_text

    bot.send_message(
        message.chat.id,
        build_help_text(),
        reply_markup=choose_keyboard(message.chat.id),
    )


@bot.message_handler(func=lambda m: (m.text or "").strip().upper() in {"MAIN MENU", "ГЛАВНОЕ МЕНЮ"})
def handle_main_menu(message: types.Message) -> None:
    set_ui_mode(message.chat.id, "main")
    bot.send_message(message.chat.id, "📊 ГЛАВНОЕ МЕНЮ", reply_markup=build_main_keyboard())


@bot.message_handler(func=lambda m: (m.text or "").strip().upper() in {"DEBUG MENU", "ОТЛАДКА"})
def handle_debug_menu(message: types.Message) -> None:
    set_ui_mode(message.chat.id, "debug")
    bot.send_message(message.chat.id, "🔧 ОТЛАДКА", reply_markup=build_debug_keyboard())


@bot.message_handler(func=lambda m: (m.text or "").strip().upper() in {"FORCE REFRESH UI", "ОБНОВИТЬ ИНТЕРФЕЙС", "ОБНОВИТЬ UI"})
def handle_force_refresh_ui(message: types.Message) -> None:
    set_ui_mode(message.chat.id, "dynamic")
    bot.send_message(
        message.chat.id,
        "♻️ Интерфейс обновлён по текущему состоянию.",
        reply_markup=build_dynamic_keyboard(get_ui_state(message.chat.id)),
    )


@bot.message_handler(func=lambda msg: True)
def handle_all_messages(message: types.Message) -> None:
    try:
        command_handler.handle(message.chat.id, (message.text or "").strip())
    except Exception:
        logger.exception("telegram.message.error")
        responder.send_long_message(message.chat.id, "❌ Ошибка.\n\n" + traceback.format_exc()[:3000])


def main() -> None:
    print("==========================================")
    print("  CHAT BOT VERSION 2 - FINAL INTEGRATION")
    print("==========================================")
    print("Бот запущен.")
    start_background_engine()
    if AUTO_EDGE_ALERTS_ENABLED:
        tfs = [x.strip() for x in str(AUTO_EDGE_ALERTS_TIMEFRAMES or "15m,1h").split(",") if x.strip()]
        auto_edge_service = AutoEdgeAlertService(
            bot,
            CHAT_ID,
            timeframes=tfs,
            poll_interval_sec=AUTO_EDGE_ALERTS_INTERVAL_SEC,
            cooldown_sec=AUTO_EDGE_ALERTS_COOLDOWN_SEC,
        )
        auto_edge_service.start()
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            raise
        except Exception:
            logger.exception("Infinity polling crashed; restarting in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()
