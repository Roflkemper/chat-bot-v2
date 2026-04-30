from __future__ import annotations

import csv
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
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


def _load_anti_spam_cfg() -> dict:
    """Load anti_spam section from config/anti_spam.yaml. Returns defaults on error."""
    cfg_path = Path(__file__).resolve().parents[1] / "config" / "anti_spam.yaml"
    defaults = {
        "enabled": True,
        "cooldowns_sec": {"RSI_EXTREME": 3600, "LEVEL_BREAK": 1800},
        "log_deduped": True,
    }
    if not cfg_path.exists():
        return defaults
    try:
        import yaml
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return raw.get("anti_spam", defaults)
    except Exception:
        logger.exception("anti_spam.cfg_load_failed")
        return defaults


class SignalAlertWorker(threading.Thread):
    """Polls signals.csv and sends new signals to Telegram.

    Anti-spam deduplication: RSI_EXTREME and LEVEL_BREAK are deduplicated by
    (signal_type, key_fields) within a configurable cooldown window.
    LIQ_CASCADE is never deduplicated here (handled by counter_long_manager).
    """

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

        # Anti-spam state
        _cfg = _load_anti_spam_cfg()
        self._spam_enabled: bool = bool(_cfg.get("enabled", True))
        self._cooldowns: dict[str, int] = dict(_cfg.get("cooldowns_sec", {}))
        self._log_deduped: bool = bool(_cfg.get("log_deduped", True))
        self._last_sent: dict[str, float] = {}  # dedup_key → epoch

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------ dedup

    @staticmethod
    def _dedup_key(row: dict) -> str | None:
        """Compute dedup key for a signal row. Returns None to skip dedup."""
        sig = row.get("signal_type", "")
        if sig == "LIQ_CASCADE":
            return None  # handled by counter_long_manager
        try:
            details = json.loads(row.get("details_json", "{}") or "{}")
        except Exception:
            return None
        if sig == "RSI_EXTREME":
            tf = details.get("timeframe", "")
            cond = details.get("condition", "")
            rsi = details.get("rsi", 0)
            return f"RSI_EXTREME|{tf}|{cond}|{round(float(rsi))}"
        if sig == "LEVEL_BREAK":
            level = details.get("level", 0)
            direction = details.get("direction", "")
            return f"LEVEL_BREAK|{round(float(level))}|{direction}"
        return None

    def _should_send(self, row: dict) -> bool:
        """Return True if signal should be sent, False if deduplicated."""
        if not self._spam_enabled:
            return True
        key = self._dedup_key(row)
        if key is None:
            return True
        sig = row.get("signal_type", "")
        cooldown = self._cooldowns.get(sig, 0)
        if cooldown <= 0:
            return True
        now = time.time()
        last = self._last_sent.get(key, 0.0)
        if now - last < cooldown:
            if self._log_deduped:
                last_ts = time.strftime("%H:%M:%S", time.gmtime(last))
                logger.info(
                    "signal_alert.deduped key=%s last_sent=%s ago=%.0fmin",
                    key, last_ts, (now - last) / 60,
                )
            return False
        self._last_sent[key] = now
        return True

    # ------------------------------------------------------------------ helpers

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
                        if not self._should_send(row):
                            continue
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


class DecisionLogAlertWorker(threading.Thread):
    def __init__(self, bot, chat_ids: Iterable[int], events_path: Path, *, poll_interval_sec: int = 15) -> None:
        super().__init__(daemon=True, name="decision-log-alert-worker")
        self.bot = bot
        self.chat_ids = list(chat_ids)
        self.events_path = events_path
        self.poll_interval_sec = max(int(poll_interval_sec), 5)
        self._stop_event = threading.Event()
        self._seen_event_ids: set[str] = self._load_seen_ids()

    def stop(self) -> None:
        self._stop_event.set()

    def _load_seen_ids(self) -> set[str]:
        """Pre-seed seen IDs from existing JSONL so restart doesn't re-send historical events."""
        from services.decision_log import iter_events

        seen: set[str] = set()
        try:
            for event in iter_events(self.events_path):
                seen.add(event.event_id)
        except Exception:
            logger.exception("decision_log_alert_worker.seed_seen_ids_failed")
        logger.info("decision_log_alert_worker.seed_seen_ids loaded=%d", len(seen))
        return seen

    def _read_new_events(self) -> list:
        from services.decision_log import EventSeverity, iter_events

        events = []
        for event in iter_events(self.events_path):
            if event.event_id in self._seen_event_ids:
                continue
            self._seen_event_ids.add(event.event_id)
            if event.severity in (EventSeverity.WARNING, EventSeverity.CRITICAL):
                events.append(event)
        return events

    def run(self) -> None:
        logger.info("decision_log_alert_worker.start path=%s", self.events_path)
        while not self._stop_event.is_set():
            try:
                from services.decision_log import build_event_keyboard, format_event_message

                for event in self._read_new_events():
                    text = format_event_message(event)
                    markup = build_event_keyboard(event.event_id)
                    for chat_id in self.chat_ids:
                        self.bot.send_message(chat_id, text, reply_markup=markup)
                        time.sleep(0.1)
            except Exception:
                logger.exception("decision_log_alert_worker.loop_failed")
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
        self._decision_log_pending_reason: dict[int, str] = {}
        self.decision_log_alert_worker = DecisionLogAlertWorker(
            self.bot,
            self.allowed_chat_ids,
            self._decision_log_events_path(),
            poll_interval_sec=15,
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

    def _decision_log_events_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "state" / "decision_log" / "events.jsonl"

    def _decision_log_annotations_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "state" / "decision_log" / "annotations.jsonl"

    def _decision_log_outcomes_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "state" / "decision_log" / "outcomes.jsonl"

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

        @self.bot.message_handler(commands=['protect_status'])
        def handle_protect_status(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.protection_alerts import ProtectionAlerts
            self.bot.send_message(chat_id, ProtectionAlerts.instance().status_text())

        @self.bot.message_handler(commands=['protect_off'])
        def handle_protect_off(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.protection_alerts import ProtectionAlerts
            ProtectionAlerts.instance().set_enabled(False)
            self.bot.send_message(chat_id, '⏸ Защита отключена.')

        @self.bot.message_handler(commands=['protect_on'])
        def handle_protect_on(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.protection_alerts import ProtectionAlerts
            ProtectionAlerts.instance().set_enabled(True)
            self.bot.send_message(chat_id, '✅ Защита включена.')

        @self.bot.message_handler(commands=['protect_threshold'])
        def handle_protect_threshold(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            # Usage: /protect_threshold position_stress critical -250
            parts = str(message.text or '').strip().split()
            if len(parts) != 4:
                self.bot.send_message(chat_id, 'Формат: /protect_threshold <alert> <level> <value>\nПример: /protect_threshold position_stress critical -250')
                return
            _, alert, level, raw_value = parts
            try:
                value = float(raw_value)
            except ValueError:
                self.bot.send_message(chat_id, f'Неверное значение: {raw_value}')
                return
            from services.protection_alerts import ProtectionAlerts
            ok = ProtectionAlerts.instance().set_threshold(alert, level, value)
            if ok:
                self.bot.send_message(chat_id, f'✅ {alert}.{level} = {value}')
            else:
                self.bot.send_message(chat_id, f'❌ Неизвестный алерт/уровень: {alert}/{level}')

        @self.bot.message_handler(commands=['boundary_status'])
        def handle_boundary_status(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.boundary_expand_manager import BoundaryExpandManager
            self.bot.send_message(chat_id, BoundaryExpandManager.instance().status_text())

        @self.bot.message_handler(commands=['boundary_off'])
        def handle_boundary_off(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.boundary_expand_manager import BoundaryExpandManager
            BoundaryExpandManager.instance().set_enabled(False)
            self.bot.send_message(chat_id, '⏸ Boundary expand отключён.')

        @self.bot.message_handler(commands=['boundary_on'])
        def handle_boundary_on(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.boundary_expand_manager import BoundaryExpandManager
            BoundaryExpandManager.instance().set_enabled(True)
            self.bot.send_message(chat_id, '✅ Boundary expand включён.')

        @self.bot.message_handler(commands=['grid_status'])
        def handle_grid_status(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.adaptive_grid_manager import AdaptiveGridManager
            self.bot.send_message(chat_id, AdaptiveGridManager.instance().status_text())

        @self.bot.message_handler(commands=['grid_off'])
        def handle_grid_off(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.adaptive_grid_manager import AdaptiveGridManager
            AdaptiveGridManager.instance().set_enabled(False)
            self.bot.send_message(chat_id, '⏸ Adaptive grid отключён.')

        @self.bot.message_handler(commands=['grid_on'])
        def handle_grid_on(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён для этого чата.')
                return
            from services.adaptive_grid_manager import AdaptiveGridManager
            AdaptiveGridManager.instance().set_enabled(True)
            self.bot.send_message(chat_id, '✅ Adaptive grid включён.')

        # ── TZ-028: /logs and /restart ────────────────────────────────────────

        @self.bot.message_handler(commands=['logs'])
        def handle_logs(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён.')
                return
            parts = str(message.text or '').strip().split()
            component = parts[1] if len(parts) > 1 else 'all'
            try:
                from src.supervisor.process_config import ALL_COMPONENTS, log_path
                from src.utils.logging_config import CURRENT_DIR
                names = ALL_COMPONENTS if component == 'all' else [component]
                out_parts = []
                for name in names:
                    lp = log_path(name) if name in ALL_COMPONENTS else CURRENT_DIR / f'{name}.log'
                    if not lp.exists():
                        out_parts.append(f'[{name}] нет лога')
                        continue
                    lines = lp.read_text(encoding='utf-8', errors='replace').splitlines()
                    warn_lines = [l for l in lines if ' WARNING ' in l or ' ERROR ' in l or ' CRITICAL ' in l]
                    tail = warn_lines[-20:] if warn_lines else lines[-5:]
                    out_parts.append(f'[{name}]\n' + '\n'.join(tail))
                self.bot.send_message(chat_id, '\n\n'.join(out_parts)[:3800])
            except Exception as exc:
                self.bot.send_message(chat_id, f'Ошибка: {exc}')

        @self.bot.message_handler(commands=['restart'])
        def handle_restart(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён.')
                return
            parts = str(message.text or '').strip().split()
            if len(parts) < 2:
                self.bot.send_message(chat_id, 'Формат: /restart <component>\nКомпоненты: app_runner, tracker, collectors')
                return
            component = parts[1]
            try:
                from src.supervisor.process_config import ALL_COMPONENTS, pid_path
                from src.supervisor.daemon import DAEMON_PID_PATH, _pid_alive, _read_pid
                import os, signal as _signal
                if component not in ALL_COMPONENTS:
                    self.bot.send_message(chat_id, f'Неизвестный компонент: {component}')
                    return
                pid = _read_pid(pid_path(component))
                if pid and _pid_alive(pid):
                    os.kill(pid, _signal.SIGTERM)
                    self.bot.send_message(chat_id, f'♻️ {component} (PID={pid}) — отправлен SIGTERM. Supervisor перезапустит через 30s.')
                else:
                    self.bot.send_message(chat_id, f'⚠️ {component} не запущен (PID файл пуст или процесс мёртв). Supervisor перезапустит.')
            except Exception as exc:
                self.bot.send_message(chat_id, f'Ошибка: {exc}')

        # ── TZ-D-ADVISOR-V1: /advise ──────────────────────────────────────────

        @self.bot.message_handler(commands=['advise'])
        def handle_advise(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён.')
                return
            parts = str(message.text or '').strip().split()
            subcmd = parts[1].lower() if len(parts) > 1 else ''

            try:
                from src.advisor.v2.portfolio import read_portfolio_state
                from src.advisor.v2.size_mode import pick_size_mode
                from src.advisor.v2.cascade import evaluate as advisor_evaluate
                from src.advisor.v2 import dedup as advisor_dedup
                from src.advisor.v2 import telemetry as advisor_telemetry
                from core.pipeline import build_full_snapshot
            except Exception as exc:
                self.bot.send_message(chat_id, f'❌ Advisor недоступен: {exc}')
                return

            if subcmd == 'stats':
                stats = advisor_telemetry.get_stats()
                by_count = stats.get('by_play_count', {})
                by_out = stats.get('by_play_outcomes', {})
                lines = [f'📊 Advisor stats ({stats.get("days", 7)}д, всего: {stats["total"]})', '']
                all_plays = sorted(set(list(by_count.keys()) + list(by_out.keys())))
                if not all_plays:
                    lines.append('Нет данных в advisor_log.jsonl')
                for pid in all_plays:
                    cnt = by_count.get(pid, 0)
                    out = by_out.get(pid)
                    if out:
                        lines.append(
                            f'  {pid}: {cnt}x рек | hit {out["hit_rate"]:.0f}% (n={out["n"]}) | '
                            f'actual≈${out["mean_actual_pnl"]:.0f} vs exp≈${out["mean_expected_pnl"]:.0f}'
                        )
                    else:
                        lines.append(f'  {pid}: {cnt}x рек | нет outcomes')
                self.bot.send_message(chat_id, '\n'.join(lines))
                return

            if subcmd == 'log':
                entries = advisor_telemetry.get_recent_log(n=5)
                if not entries:
                    self.bot.send_message(chat_id, 'advisor_log.jsonl пуст.')
                    return
                lines = ['📋 Последние рекомендации:', '']
                for e in reversed(entries):
                    lines.append(
                        f"{e.get('ts_utc','?')} | {e.get('play_id','?')} | "
                        f"{e.get('size_mode','?')} | pnl≈${e.get('expected_pnl',0):.0f} | "
                        f"{e.get('trigger','')}"
                    )
                self.bot.send_message(chat_id, '\n'.join(lines)[:3800])
                return

            # Default: run advisor on current snapshot — show all 3 symbols (TZ-035-FIX-1)
            _SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'XRPUSDT']
            try:
                from src.advisor.v2.feature_writer import read_latest_features as _read_pq
            except Exception:
                _read_pq = None

            try:
                snapshot = build_full_snapshot(symbol='BTCUSDT')
            except Exception as exc:
                self.bot.send_message(chat_id, f'❌ Ошибка получения snapshot: {exc}')
                return

            portfolio = read_portfolio_state()
            size_mode, size_reason = pick_size_mode(portfolio)

            lines = [
                '🧠 *ADVISOR v2 — multi-asset*',
                f'Режим размера: *{size_mode}* ({size_reason})',
                f'Портфель: ${portfolio.depo_total:,.0f} (доступно ${portfolio.depo_available:,.0f}) | '
                f'DD: {portfolio.dd_pct:.1f}% | Margin free: {portfolio.free_margin_pct:.0f}%',
                '',
            ]

            for sym in _SYMBOLS:
                # Resolve live features for price display and cold-start detection
                live = _read_pq(sym) if _read_pq else None
                btc_price = snapshot.get('price') if isinstance(snapshot, dict) else None
                sym_price = (live or {}).get('price') if sym != 'BTCUSDT' else btc_price
                price_str = f'${sym_price:,.2f}' if sym_price else 'н/д'

                features = snapshot if sym == 'BTCUSDT' else {}
                rec = advisor_evaluate(features, portfolio, size_mode, symbol=sym)

                if live is None and rec is None:
                    # No parquet yet — cold start
                    lines.append(f'▸ *{sym}* {price_str} | ⏳ cold start')
                elif rec is None:
                    lines.append(f'▸ *{sym}* {price_str} | ✅ нет сигналов')
                else:
                    already_seen = advisor_dedup.is_duplicate(rec)
                    tag = ' _(уже)_' if already_seen else ''
                    lines += [
                        f'▸ *{sym}* {price_str} | 📌 *{rec.play_id}* {rec.play_name}{tag}',
                        f'  Триггер: {rec.trigger}',
                        f'  Причина: {rec.reason}',
                        f'  Размер: {rec.size_btc:.2f} BTC | Ожид. pnl: ~${rec.expected_pnl:.0f}'
                        f' | Win: {rec.win_rate*100:.0f}% | DD: {rec.dd_pct:.1f}%',
                    ]
                    if rec.params:
                        lines.append(f'  Параметры: {rec.params}')
                    if not already_seen:
                        advisor_dedup.record(rec)
                        advisor_telemetry.log_recommendation(rec, portfolio.balance)
                        ref_price = float(sym_price or btc_price or 0)
                        advisor_telemetry.schedule_outcome_check(rec, ref_price)

            self.bot.send_message(chat_id, '\n'.join(lines), parse_mode='Markdown')

        @self.bot.message_handler(commands=['events'])
        def handle_events(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён.')
                return
            from services.decision_log import iter_annotations, iter_events

            parts = str(message.text or "").strip().split()
            subcmd = parts[1].lower() if len(parts) > 1 else "today"
            events = list(iter_events(self._decision_log_events_path()))
            if subcmd == "today":
                today = datetime.now(timezone.utc).date()
                events = [event for event in events if event.ts.astimezone(timezone.utc).date() == today]
            elif subcmd == "pending":
                annotated_ids = {item.event_id for item in iter_annotations(self._decision_log_annotations_path())}
                events = [event for event in events if event.event_id not in annotated_ids]
            if not events:
                self.bot.send_message(chat_id, "Событий не найдено.")
                return
            lines = ["📒 События decision log:", ""]
            for event in events[-10:]:
                lines.append(f"{event.event_id} | {event.event_type.value} | {event.severity.value} | {event.summary}")
            self.bot.send_message(chat_id, "\n".join(lines)[:3800])

        @self.bot.message_handler(commands=['event'])
        def handle_event_details(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён.')
                return
            from services.decision_log import format_event_message, iter_events, iter_outcomes

            parts = str(message.text or "").strip().split()
            if len(parts) != 2:
                self.bot.send_message(chat_id, "Формат: /event <event_id>")
                return
            event_id = parts[1]
            event = next((item for item in iter_events(self._decision_log_events_path()) if item.event_id == event_id), None)
            if event is None:
                self.bot.send_message(chat_id, "Событие не найдено.")
                return
            outcomes = [item for item in iter_outcomes(self._decision_log_outcomes_path()) if item.event_id == event_id]
            lines = [format_event_message(event), ""]
            if outcomes:
                lines.append("Outcomes:")
                for outcome in outcomes:
                    lines.append(
                        f"• {outcome.checkpoint_minutes}m | pnl {outcome.delta_pnl_since_event:+.0f} USD | {outcome.delta_pnl_classification}"
                    )
            self.bot.send_message(chat_id, "\n".join(lines)[:3800])

        @self.bot.message_handler(commands=['outcomes'])
        def handle_outcomes(message) -> None:
            chat_id = int(message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.send_message(chat_id, '⛔ Доступ запрещён.')
                return
            from services.decision_log import iter_outcomes

            parts = str(message.text or "").strip().split()
            subcmd = parts[1].lower() if len(parts) > 1 else "today"
            outcomes = list(iter_outcomes(self._decision_log_outcomes_path()))
            if subcmd == "today":
                today = datetime.now(timezone.utc).date()
                outcomes = [item for item in outcomes if item.checkpoint_ts.astimezone(timezone.utc).date() == today]
            if not outcomes:
                self.bot.send_message(chat_id, "Outcomes не найдены.")
                return
            lines = ["🧾 Outcomes decision log:", ""]
            for outcome in outcomes[-10:]:
                lines.append(
                    f"{outcome.event_id} | {outcome.checkpoint_minutes}m | {outcome.delta_pnl_since_event:+.0f} USD | {outcome.delta_pnl_classification}"
                )
            self.bot.send_message(chat_id, "\n".join(lines)[:3800])

        @self.bot.callback_query_handler(func=lambda call: str(getattr(call, "data", "")).startswith("decision_log:"))
        def handle_decision_log_callback(call) -> None:
            chat_id = int(call.message.chat.id)
            if not self._is_allowed(chat_id):
                self.bot.answer_callback_query(call.id, "Доступ запрещён.")
                return
            from services.decision_log import handle_callback

            result = handle_callback(
                str(call.data),
                pending_reasons=self._decision_log_pending_reason,
                chat_id=chat_id,
                annotations_path=self._decision_log_annotations_path(),
            )
            self.bot.answer_callback_query(call.id, result.get("message", "ok"))
            try:
                self.bot.send_message(chat_id, result.get("message", "ok"))
            except Exception:
                logger.exception("decision_log.callback_reply_failed")

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
            if chat_id in self._decision_log_pending_reason:
                from services.decision_log import handle_reason_message

                result = handle_reason_message(
                    chat_id,
                    text,
                    pending_reasons=self._decision_log_pending_reason,
                    annotations_path=self._decision_log_annotations_path(),
                )
                if result is not None:
                    self.bot.send_message(chat_id, result.get("message", "Причина сохранена."))
                    return
            self._dispatch(chat_id, text)

    def run(self) -> None:
        if getattr(config, 'AUTO_EDGE_ALERTS_ENABLED', True) and self.allowed_chat_ids:
            self.alert_worker.start()
        if self.allowed_chat_ids:
            self.signal_alert_worker.start()
        if self.allowed_chat_ids and not self.decision_log_alert_worker.is_alive():
            self.decision_log_alert_worker.start()
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
        decision_log_worker = getattr(self, 'decision_log_alert_worker', None)
        if decision_log_worker is not None and self.allowed_chat_ids and not decision_log_worker.is_alive():
            decision_log_worker.start()
        logger.info(
            'telegram_bot.start config_source=%s allowed_chat_ids=%s',
            getattr(config, 'CONFIG_SOURCE', ''),
            self.allowed_chat_ids,
        )
        import time as _time
        while True:
            try:
                self.bot.infinity_polling(skip_pending=True, timeout=25, long_polling_timeout=25)
            except KeyboardInterrupt:
                logger.info('telegram_bot.stopped_by_keyboard')
                raise
            except Exception:
                logger.exception('telegram_bot.polling_failed; restart in 10s')
                _time.sleep(10)
