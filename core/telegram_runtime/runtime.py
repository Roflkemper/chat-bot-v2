from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from config import AUTO_EDGE_ALERTS_INTERVAL_SEC, BOT_TOKEN, CHAT_ID, ENABLE_TELEGRAM
from core.app_logging import setup_logging
from handlers.command_handler import CommandHandler
from models.responses import BotResponsePayload
from services.analysis_service import DEFAULT_TF, call_btc_analysis
from storage.position_store import load_position_state
from storage.transition_alerts import build_transition_alert
from telegram_runtime.state import (
    alerts_enabled,
    ensure_chat_registered,
    iter_alert_chat_ids,
    last_alert_text,
    set_alerts_enabled,
    set_last_alert_text,
)
from telegram_ui.keyboards import build_dynamic_keyboard

logger = logging.getLogger(__name__)
MAX_MESSAGE_LEN = 3800
ALERT_LOOP_SEC = max(30, int(os.getenv('TELEGRAM_ALERT_LOOP_SEC', str(AUTO_EDGE_ALERTS_INTERVAL_SEC or 60))))


ALIASES = {
    'АНАЛИЗ РЫНКА': 'СВОДКА BTC',
    'РЫНОК': 'СВОДКА BTC',
    'СЛЕЖЕНИЕ ЗА ПОЗИЦИЕЙ': 'МОЯ ПОЗИЦИЯ',
    'ПОЗИЦИЯ': 'МОЯ ПОЗИЦИЯ',
    'ВКЛ АЛЕРТЫ': '__ALERTS_ON__',
    'ВЫКЛ АЛЕРТЫ': '__ALERTS_OFF__',
}


def _build_keyboard_state(payload: BotResponsePayload | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {}
    if payload and payload.analysis_snapshot is not None:
        try:
            bag = payload.analysis_snapshot.to_dict()
        except Exception:
            bag = {}
        decision = bag.get('decision') if isinstance(bag.get('decision'), dict) else {}
        state.update({
            'direction': decision.get('direction_text') or bag.get('final_decision') or bag.get('signal'),
            'action': decision.get('action') or decision.get('action_text'),
            'risk': decision.get('risk_level') or decision.get('risk'),
        })
        try:
            conf = decision.get('confidence_pct')
            if conf is None:
                conf = float(decision.get('confidence') or 0.0) * 100.0 if float(decision.get('confidence') or 0.0) <= 1.0 else float(decision.get('confidence') or 0.0)
            state['confidence'] = float(conf or 0.0)
        except Exception:
            state['confidence'] = 0.0
    pos = load_position_state()
    state['has_position'] = bool(pos.get('has_position'))
    state['position_side'] = pos.get('side')
    return state


class TelegramRuntime:
    def __init__(self) -> None:
        setup_logging()
        self.bot = None
        self.command_handler: CommandHandler | None = None
        self._alert_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _lazy_bot(self):
        if self.bot is not None:
            return self.bot
        try:
            import telebot  # type: ignore
        except Exception as exc:
            raise RuntimeError('pyTelegramBotAPI is not installed. Install dependencies from requirements.txt.') from exc
        self.bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
        self.command_handler = CommandHandler(self._send_payload)
        self._register_handlers()
        return self.bot

    def _register_handlers(self) -> None:
        bot = self.bot
        if bot is None:
            return

        @bot.message_handler(commands=['start', 'menu'])
        def _start(message):
            ensure_chat_registered(message.chat.id, default_alerts_enabled=True)
            text = (
                '✅ Бот запущен.\n\n'
                'Кнопки:\n'
                '• АНАЛИЗ РЫНКА — текущая рыночная сводка\n'
                '• СЛЕЖЕНИЕ ЗА ПОЗИЦИЕЙ — текущее состояние позиции\n'
                '• ВКЛ/ВЫКЛ АЛЕРТЫ — уведомления только при изменении ситуации'
            )
            self._send_text(message.chat.id, text)

        @bot.message_handler(commands=['alerts_on'])
        def _alerts_on(message):
            ensure_chat_registered(message.chat.id, default_alerts_enabled=True)
            set_alerts_enabled(message.chat.id, True)
            self._send_text(message.chat.id, '🔔 Алерты включены. Буду писать только при существенном изменении ситуации.')

        @bot.message_handler(commands=['alerts_off'])
        def _alerts_off(message):
            ensure_chat_registered(message.chat.id, default_alerts_enabled=True)
            set_alerts_enabled(message.chat.id, False)
            self._send_text(message.chat.id, '🔕 Алерты отключены для этого чата.')

        @bot.message_handler(func=lambda message: True, content_types=['text'])
        def _text(message):
            ensure_chat_registered(message.chat.id, default_alerts_enabled=True)
            text = str(message.text or '').strip()
            command = ALIASES.get(text.upper(), text)
            if command == '__ALERTS_ON__':
                set_alerts_enabled(message.chat.id, True)
                return self._send_text(message.chat.id, '🔔 Алерты включены.')
            if command == '__ALERTS_OFF__':
                set_alerts_enabled(message.chat.id, False)
                return self._send_text(message.chat.id, '🔕 Алерты отключены.')
            if self.command_handler is None:
                return self._send_text(message.chat.id, 'Командный обработчик не инициализирован.')
            self.command_handler.handle(message.chat.id, command)

    def _send_payload(self, chat_id: int, payload: BotResponsePayload | str) -> None:
        if isinstance(payload, str):
            return self._send_text(chat_id, payload)
        if payload.file_path:
            self._send_document(chat_id, payload.file_path, caption=payload.file_caption or payload.text)
            if payload.text:
                self._send_text(chat_id, payload.text, payload=payload)
            return
        self._send_text(chat_id, payload.text, payload=payload)

    def _send_document(self, chat_id: int, file_path: str, caption: str | None = None) -> None:
        bot = self._lazy_bot()
        p = Path(file_path)
        if not p.exists():
            self._send_text(chat_id, f'Файл не найден: {file_path}')
            return
        with p.open('rb') as fh:
            bot.send_document(chat_id, fh, caption=caption or None)

    def _send_text(self, chat_id: int, text: str, payload: BotResponsePayload | None = None) -> None:
        bot = self._lazy_bot()
        markup = build_dynamic_keyboard(_build_keyboard_state(payload))
        chunks = []
        body = str(text or '').strip() or 'Пустой ответ.'
        while len(body) > MAX_MESSAGE_LEN:
            cut = body.rfind('\n', 0, MAX_MESSAGE_LEN)
            if cut <= 0:
                cut = MAX_MESSAGE_LEN
            chunks.append(body[:cut])
            body = body[cut:].lstrip()
        if body:
            chunks.append(body)
        for i, chunk in enumerate(chunks):
            bot.send_message(chat_id, chunk, reply_markup=markup if i == len(chunks)-1 else None)

    def _default_chat_bootstrap(self) -> None:
        if CHAT_ID:
            try:
                ensure_chat_registered(int(CHAT_ID), default_alerts_enabled=True)
            except Exception:
                logger.warning('telegram.bootstrap_chat_id_invalid chat_id=%s', CHAT_ID)

    def _alert_loop(self) -> None:
        logger.info('telegram.alert_loop_started interval=%s', ALERT_LOOP_SEC)
        while not self._stop_event.is_set():
            try:
                snapshot = call_btc_analysis(DEFAULT_TF)
                alert_text = build_transition_alert(snapshot)
                if alert_text:
                    for chat_id in iter_alert_chat_ids():
                        if not alerts_enabled(chat_id):
                            continue
                        if last_alert_text(chat_id) == alert_text:
                            continue
                        self._send_text(chat_id, alert_text)
                        set_last_alert_text(chat_id, alert_text)
            except Exception:
                logger.exception('telegram.alert_loop_failed')
            self._stop_event.wait(ALERT_LOOP_SEC)

    def run(self) -> None:
        if not ENABLE_TELEGRAM:
            raise RuntimeError('ENABLE_TELEGRAM=0, Telegram runtime disabled.')
        if not BOT_TOKEN:
            raise RuntimeError('BOT_TOKEN not configured. Add it to .env or bot_local_config.json.')
        self._default_chat_bootstrap()
        bot = self._lazy_bot()
        self._alert_thread = threading.Thread(target=self._alert_loop, name='telegram-alert-loop', daemon=True)
        self._alert_thread.start()
        logger.info('telegram.runtime_started')
        bot.infinity_polling(timeout=30, long_polling_timeout=30)


def run_telegram_runtime() -> None:
    TelegramRuntime().run()
