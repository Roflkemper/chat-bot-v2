from __future__ import annotations

import csv
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Iterable

import config
from core.app_logging import setup_logging
from handlers.command_handler import CommandHandler
from models.responses import BotResponsePayload
from services.analysis_service import call_btc_analysis
from storage.position_store import load_position_state
from storage.transition_alerts import build_transition_alert

logger = logging.getLogger(__name__)
_MAX_MESSAGE_LEN = 3800


SLASH_COMMAND_ALIASES: dict[str, str] = {
    '/help': 'HELP',
    '/menu': 'HELP',
    '/market': 'BTC 1H',
    '/analysis': 'BTC 1H',
}


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


def resolve_telegram_text(text: str) -> str:
    raw = str(text or '').strip()
    if not raw:
        return ''
    parts = raw.split(maxsplit=1)
    slash = parts[0].lower()
    if slash in SLASH_COMMAND_ALIASES:
        return SLASH_COMMAND_ALIASES[slash]
    upper = raw.upper()
    aliases = {
        'ГЛАВНОЕ МЕНЮ': 'HELP',
        'ОБНОВИТЬ ИНТЕРФЕЙС': 'HELP',
    }
    return aliases.get(upper, raw)


def _fmt_price(value: object, digits: int = 2) -> str:
    try:
        if value is None:
            return '—'
        return f"{float(value):,.{digits}f}".replace(',', ' ')
    except Exception:
        return str(value or '—')


def _compact_reason(value: object) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    text = text.replace('_', ' ')
    return text[:220]


def _snapshot_manage_hint(snapshot_dict: dict) -> str:
    decision = snapshot_dict.get('decision') if isinstance(snapshot_dict.get('decision'), dict) else {}
    direction = str(decision.get('direction_text') or snapshot_dict.get('forecast_direction') or snapshot_dict.get('signal') or '').strip()
    action = str(decision.get('action_text') or decision.get('action') or snapshot_dict.get('final_decision') or '').strip()
    manager_action = str(decision.get('manager_action_text') or decision.get('manager_action') or '').strip()
    risk = str(decision.get('risk_level') or decision.get('risk') or snapshot_dict.get('risk_level') or '').strip().upper()
    invalidation = _compact_reason(decision.get('invalidation') or snapshot_dict.get('invalidation'))
    entry_reason = _compact_reason(decision.get('entry_reason') or snapshot_dict.get('entry_reason'))
    pressure_reason = _compact_reason(decision.get('pressure_reason') or snapshot_dict.get('pressure_reason'))
    confidence = decision.get('confidence_pct') or decision.get('confidence') or snapshot_dict.get('forecast_confidence') or 0.0
    try:
        confidence = round(float(confidence), 1)
    except Exception:
        confidence = 0.0

    bullets: list[str] = []
    if action:
        bullets.append(f'• вход сейчас: {action}')
    if direction:
        bullets.append(f'• сторона сценария: {direction}')
    if manager_action:
        bullets.append(f'• сопровождение: {manager_action}')
    bullets.append(f'• confidence: {confidence}%')
    if risk:
        bullets.append(f'• риск: {risk}')
    if entry_reason:
        bullets.append(f'• почему: {entry_reason}')
    if pressure_reason and pressure_reason != entry_reason:
        bullets.append(f'• давление/контекст: {pressure_reason}')
    if invalidation:
        bullets.append(f'• отмена сценария: {invalidation}')

    unload = 'держать и ждать подтверждения'
    side_upper = direction.upper()
    manager_upper = manager_action.upper()
    if 'PARTIAL' in manager_upper or 'TP1' in manager_upper or 'REDUCE' in manager_upper:
        unload = 'фиксировать часть / разгружать ступенчато'
    elif 'BE' in manager_upper:
        unload = 'переносить в безубыток и держать остаток'
    elif 'EXIT' in manager_upper or 'CLOSE' in manager_upper or risk == 'HIGH':
        unload = 'разгружать позицию агрессивнее / не добирать'
    elif 'LONG' in side_upper or 'SHORT' in side_upper:
        unload = 'держать только по сценарию, без погони за ценой'
    bullets.append(f'• что делать с позицией: {unload}')
    return '\n'.join(bullets)


def build_market_alert_message(snapshot, timeframe: str, transition_text: str) -> str:
    payload = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else {}
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    price = _fmt_price(payload.get('price'))
    direction = str(decision.get('direction_text') or payload.get('forecast_direction') or payload.get('signal') or '—')
    header = [
        f'🚨 BTCUSDT [{str(timeframe).upper()}]',
        f'Цена: {price}',
        f'Сценарий: {direction}',
    ]
    body = transition_text.strip()
    hint = _snapshot_manage_hint(payload)
    return '\n'.join(header) + '\n\n' + body + '\n\n🧭 ТРЕЙДЕРСКОЕ ДЕЙСТВИЕ\n' + hint


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
                    message = build_market_alert_message(snapshot, timeframe, alert_text)
                    for chat_id in self.chat_ids:
                        for chunk in split_text_chunks(message):
                            self.bot.send_message(chat_id, chunk)
                            time.sleep(0.15)
            except Exception:
                logger.exception('alert_worker.loop_failed')
            elapsed = time.time() - started
            sleep_for = max(5.0, self.interval_sec - elapsed)
            self._stop_event.wait(sleep_for)


class SignalAlertWorker(threading.Thread):
    """Polls signals.csv and sends new signals to Telegram."""

    _PREFIXES = {
        "LIQ_CASCADE": "⚠️ LIQ_CASCADE",
        "RSI_EXTREME": "📊 RSI_EXTREME",
        "LEVEL_BREAK": "🎯 LEVEL_BREAK",
    }

    def __init__(
        self,
        bot,
        chat_ids: Iterable[int],
        signals_csv: Path,
        *,
        poll_interval_sec: int = 30,
    ) -> None:
        super().__init__(daemon=True, name="signal-alert-worker")
        self.bot = bot
        self.chat_ids = list(chat_ids)
        self.signals_csv = signals_csv
        self.poll_interval_sec = poll_interval_sec
        self._stop_event = threading.Event()
        self._last_ts: str = ""

    def stop(self) -> None:
        self._stop_event.set()

    def _read_new_signals(self) -> list[dict]:
        if not self.signals_csv.exists():
            return []
        new: list[dict] = []
        try:
            with self.signals_csv.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    ts = row.get("ts_utc", "")
                    if ts > self._last_ts:
                        new.append(dict(row))
        except Exception:
            logger.exception("signal_alert_worker.read_failed")
        return new

    def _format_signal(self, row: dict) -> str:
        signal_type = row.get("signal_type", "")
        prefix = self._PREFIXES.get(signal_type, f"📡 {signal_type}")
        try:
            details = json.loads(row.get("details_json", "{}") or "{}")
        except Exception:
            details = {}
        ts_s = row.get("ts_utc", "")
        ts_short = ts_s[11:19] if len(ts_s) >= 19 else ts_s
        detail_s = "  ".join(f"{k}={v}" for k, v in details.items())
        return f"{prefix}  [{ts_short}]  {detail_s}"

    def run(self) -> None:
        # Initialize last_ts so we don't replay already-existing signals on startup
        existing = self._read_new_signals()
        if existing:
            self._last_ts = max(s.get("ts_utc", "") for s in existing)
        logger.info("signal_alert_worker.start last_ts=%s", self._last_ts)
        while not self._stop_event.is_set():
            try:
                new_signals = self._read_new_signals()
                if new_signals:
                    self._last_ts = max(s.get("ts_utc", "") for s in new_signals)
                    for row in new_signals:
                        text = self._format_signal(row)
                        for chat_id in self.chat_ids:
                            try:
                                self.bot.send_message(chat_id, text)
                                time.sleep(0.1)
                            except Exception:
                                logger.exception("signal_alert_worker.send_failed chat_id=%s", chat_id)
            except Exception:
                logger.exception("signal_alert_worker.loop_failed")
            self._stop_event.wait(self.poll_interval_sec)


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
        _signals_csv = Path(__file__).resolve().parents[1] / "market_live" / "signals.csv"
        self.signal_alert_worker = SignalAlertWorker(
            self.bot,
            self.allowed_chat_ids,
            _signals_csv,
            poll_interval_sec=30,
        )
        self._register_handlers()

    def _is_allowed(self, chat_id: int) -> bool:
        return not self.allowed_chat_ids or chat_id in self.allowed_chat_ids

    def _dispatch(self, chat_id: int, text: str) -> None:
        resolved = resolve_telegram_text(text)
        if not resolved:
            self.bot.send_message(chat_id, 'Напиши команду или нажми кнопку.')
            return
        if resolved == 'МОЯ ПОЗИЦИЯ':
            state = load_position_state()
            if not bool((state or {}).get('has_position')):
                self.bot.send_message(
                    chat_id,
                    '📭 Сейчас открытая позиция не зафиксирована.\n\nДля рынка используй /market или /entry. Для сопровождения после входа — /exit или /manage.',
                )
                return
        self.command_handler.handle(chat_id, resolved)

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
                'Бот запущен.\n\nДоступно:\n/help\n/market\nBTC 5M / BTC 15M / BTC 1H / BTC 4H / BTC 1D\nBTC GINAREA',
                reply_markup=build_main_keyboard(),
            )

        @self.bot.message_handler(commands=['help', 'market', 'analysis'])
        def handle_commands(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            self._dispatch(chat_id, str(message.text or '').strip())

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
            self._dispatch(chat_id, text)

    def run(self) -> None:
        if getattr(config, 'AUTO_EDGE_ALERTS_ENABLED', True) and self.allowed_chat_ids:
            self.alert_worker.start()
        if self.allowed_chat_ids:
            self.signal_alert_worker.start()
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

    def run_polling_blocking(self) -> None:
        if (
            getattr(config, 'AUTO_EDGE_ALERTS_ENABLED', True)
            and self.allowed_chat_ids
            and not self.alert_worker.is_alive()
        ):
            self.alert_worker.start()
        signal_worker = getattr(self, 'signal_alert_worker', None)
        if signal_worker is not None and self.allowed_chat_ids and not signal_worker.is_alive():
            signal_worker.start()
        logger.info(
            'telegram_bot.start config_source=%s allowed_chat_ids=%s',
            getattr(config, 'CONFIG_SOURCE', ''),
            self.allowed_chat_ids,
        )
        self.bot.infinity_polling(skip_pending=True, timeout=25, long_polling_timeout=25)
