from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Iterable, List

import config
from core.app_logging import setup_logging
from handlers.command_handler import CommandHandler
from models.responses import BotResponsePayload
from services.analysis_service import call_btc_analysis
from storage.transition_alerts import build_transition_alert

logger = logging.getLogger(__name__)
_MAX_MESSAGE_LEN = 3800


def _safe_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(str(value).strip())
    except Exception:
        return None


def normalize_chat_ids(*values: object) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in values:
        if raw is None:
            continue
        text = str(raw).replace(';', ',')
        for part in text.split(','):
            value = _safe_int(part)
            if value is None or value in seen:
                continue
            seen.add(value)
            out.append(value)
    return out


def split_text_chunks(text: str, limit: int = _MAX_MESSAGE_LEN) -> list[str]:
    body = (text or '').strip()
    if not body:
        return ['⚠️ Пустой ответ.']
    if len(body) <= limit:
        return [body]

    chunks: list[str] = []
    current = ''
    for block in body.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ''
        if len(block) <= limit:
            current = block
            continue

        lines = block.splitlines()
        line_buf = ''
        for line in lines:
            line = line.rstrip()
            candidate_line = f"{line_buf}\n{line}".strip() if line_buf else line
            if len(candidate_line) <= limit:
                line_buf = candidate_line
                continue
            if line_buf:
                chunks.append(line_buf)
            if len(line) <= limit:
                line_buf = line
                continue
            start = 0
            while start < len(line):
                end = start + limit
                chunks.append(line[start:end])
                start = end
            line_buf = ''
        if line_buf:
            current = line_buf
    if current:
        chunks.append(current)
    return chunks or ['⚠️ Пустой ответ.']


class TelegramResponder:
    def __init__(self, bot) -> None:
        self.bot = bot

    @staticmethod
    def _payload_state(payload: BotResponsePayload | str) -> dict:
        if isinstance(payload, BotResponsePayload):
            position = payload.position_snapshot.to_dict() if getattr(payload, 'position_snapshot', None) else {}
            analysis = payload.analysis_snapshot.to_dict() if getattr(payload, 'analysis_snapshot', None) else {}
            decision = analysis.get('decision') if isinstance(analysis.get('decision'), dict) else {}
            return {
                'has_position': bool(position.get('has_position')),
                'position_side': position.get('side'),
                'direction': decision.get('direction_text') or analysis.get('final_decision') or analysis.get('forecast_direction'),
                'action': decision.get('action_text') or decision.get('action'),
                'confidence': decision.get('confidence_pct') or decision.get('confidence') or analysis.get('forecast_confidence') or 0.0,
                'risk': decision.get('risk_level') or analysis.get('risk_level'),
            }
        return {}

    @staticmethod
    def _keyboard(text: str, payload: BotResponsePayload | str):
        from telegram_ui.keyboards import build_debug_keyboard, build_dynamic_keyboard, build_main_keyboard

        upper = (text or '').upper()
        if 'ОТЛАДКА' in upper or 'DEBUG' in upper:
            return build_debug_keyboard()
        state = TelegramResponder._payload_state(payload)
        return build_dynamic_keyboard(state) if state else build_main_keyboard()

    def send(self, chat_id: int, payload: BotResponsePayload | str) -> None:
        text = payload.text if isinstance(payload, BotResponsePayload) else str(payload)
        chunks = split_text_chunks(text)
        markup = self._keyboard(text, payload)
        for index, chunk in enumerate(chunks):
            reply_markup = markup if index == len(chunks) - 1 else None
            self.bot.send_message(chat_id, chunk, reply_markup=reply_markup)
        if isinstance(payload, BotResponsePayload) and payload.file_path:
            path = Path(payload.file_path)
            if path.exists() and path.is_file():
                with path.open('rb') as fh:
                    self.bot.send_document(chat_id, fh, caption=payload.file_caption or None)


class MarketAlertWorker(threading.Thread):
    def __init__(self, bot, chat_ids: Iterable[int], *, interval_sec: int, timeframes: Iterable[str]) -> None:
        super().__init__(daemon=True, name='market-alert-worker')
        self.bot = bot
        self.chat_ids = list(chat_ids)
        self.interval_sec = max(int(interval_sec), 20)
        self.timeframes = [str(tf).strip() for tf in timeframes if str(tf).strip()] or ['15m', '1h']
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info('alert_worker.start chat_ids=%s timeframes=%s interval=%s', self.chat_ids, self.timeframes, self.interval_sec)
        while not self._stop_event.is_set():
            started = time.time()
            try:
                for timeframe in self.timeframes:
                    snapshot = call_btc_analysis(timeframe)
                    alert_text = build_transition_alert(snapshot)
                    if not alert_text:
                        continue
                    header = f'⏱️ LIVE {timeframe.upper()}\n\n'
                    for chat_id in self.chat_ids:
                        for chunk in split_text_chunks(header + alert_text):
                            self.bot.send_message(chat_id, chunk)
                            time.sleep(0.15)
            except Exception:
                logger.exception('alert_worker.loop_failed')
            elapsed = time.time() - started
            sleep_for = max(5.0, self.interval_sec - elapsed)
            self._stop_event.wait(sleep_for)


class TelegramBotApp:
    def __init__(self) -> None:
        setup_logging()
        token = str(config.BOT_TOKEN or '').strip()
        if not token or ':' not in token:
            raise RuntimeError('BOT_TOKEN не найден. Проверь .env или bot_local_config.json')

        try:
            import telebot
        except Exception as exc:  # pragma: no cover
            raise RuntimeError('Не установлен pyTelegramBotAPI. Выполни pip install -r requirements.txt') from exc

        self.allowed_chat_ids = normalize_chat_ids(
            os.getenv('ALLOWED_CHAT_IDS', ''),
            getattr(config, 'CHAT_ID', ''),
        )
        self.bot = telebot.TeleBot(token, parse_mode=None)
        self.responder = TelegramResponder(self.bot)
        self.command_handler = CommandHandler(self.responder.send)
        self.alert_worker = MarketAlertWorker(
            self.bot,
            self.allowed_chat_ids,
            interval_sec=getattr(config, 'AUTO_EDGE_ALERTS_INTERVAL_SEC', 60),
            timeframes=str(getattr(config, 'AUTO_EDGE_ALERTS_TIMEFRAMES', '15m,1h')).split(','),
        )
        self._register_handlers()

    def _is_allowed(self, chat_id: int) -> bool:
        return not self.allowed_chat_ids or chat_id in self.allowed_chat_ids

    def _register_handlers(self) -> None:
        from telegram_ui.keyboards import build_main_keyboard

        @self.bot.message_handler(commands=['start', 'menu'])
        def handle_start(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            self.bot.send_message(
                chat_id,
                '✅ Чат-бот версия 2 запущен.\n\nКнопки внизу активны.\nАвто-алерты по рынку тоже включены.',
                reply_markup=build_main_keyboard(),
            )

        @self.bot.message_handler(commands=['help'])
        def handle_help(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            self.command_handler.handle(chat_id, 'HELP')

        @self.bot.message_handler(func=lambda m: True, content_types=['text'])
        def handle_text(message) -> None:
            chat_id = int(message.chat.id)
            text = str(message.text or '').strip()
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            if not text:
                self.bot.send_message(chat_id, 'Напиши команду или нажми кнопку.', reply_markup=build_main_keyboard())
                return
            upper = text.upper()
            aliases = {
                'ГЛАВНОЕ МЕНЮ': 'HELP',
                'ОБНОВИТЬ ИНТЕРФЕЙС': 'HELP',
                'ОТЛАДКА': 'DEBUG EXPORT',
            }
            self.command_handler.handle(chat_id, aliases.get(upper, text))

    def run(self) -> None:
        if getattr(config, 'AUTO_EDGE_ALERTS_ENABLED', True) and self.allowed_chat_ids:
            self.alert_worker.start()
        logger.info('telegram_bot.start config_source=%s allowed_chat_ids=%s', getattr(config, 'CONFIG_SOURCE', ''), self.allowed_chat_ids)
        while True:
            try:
                self.bot.infinity_polling(skip_pending=True, timeout=25, long_polling_timeout=25)
            except KeyboardInterrupt:
                logger.info('telegram_bot.stopped_by_keyboard')
                raise
            except Exception:
                logger.exception('telegram_bot.polling_failed; restart in 5s')
                time.sleep(5)
