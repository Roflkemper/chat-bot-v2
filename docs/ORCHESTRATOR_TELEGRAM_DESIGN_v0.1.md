# ORCHESTRATOR TELEGRAM ALERTS DESIGN v0.1

**Статус:** Draft  
**Дата:** 2026-04-18  
**Автор:** Claude (архитектор)  
**Цель:** Подключить Orchestrator Loop к реальному Telegram Bot API

---

## 1. КОНТЕКСТ

**Что есть:**
- Существующий аналитический бот использует `pyTelegramBotAPI` (telebot) через `services/telegram_runtime.py`
- Конфиг уже настроен: `BOT_TOKEN` + `CHAT_ID` в env
- Orchestrator Loop (TZ-007) работает, но `send_telegram_alert()` — заглушка (только логирует)

**Что нужно:**
- Заменить заглушки на реальные вызовы Telegram API
- Использовать **тот же токен** что и аналитический бот (чтобы всё в одном чате)
- **НЕ ломать** существующий аналитический бот
- **Не создавать** конфликт двух `TeleBot` инстансов

---

## 2. КЛЮЧЕВЫЕ РЕШЕНИЯ

### 2.1 Синхронная отправка, не aiogram

**Выбор:** `pyTelegramBotAPI` (telebot), как в существующем runtime.

**Почему не aiogram:**
- Существующий код уже на telebot
- Не нужно плодить две разные библиотеки
- Отправка — это короткий синхронный вызов (POST на api.telegram.org)
- Наш `async def send_telegram_alert()` может обернуть синхронный вызов через `asyncio.to_thread()`

---

### 2.2 Отдельный TeleBot-клиент для отправки (не shared instance)

**Выбор:** Создать **свой** `TeleBot` инстанс внутри `telegram_alert_service.py`, используя тот же токен.

**Почему отдельный:**
- Существующий `TelegramBotApp` занят polling'ом входящих сообщений
- Shared instance требует thread-safety и сложной координации
- `TeleBot(token)` — дешёвый объект, его можно создать лениво при первой отправке
- Telegram Bot API допускает множество клиентов с одним токеном (ограничения только rate limit)

**Риск rate limit:** Telegram допускает ~30 сообщений/сек в разные чаты, ~1 сообщение/сек в один чат. Orchestrator шлёт редко (каждые 5 мин при изменениях), конфликта не будет.

---

### 2.3 Fallback на логирование

Если `BOT_TOKEN` не задан / telegram send падает — **не крашить** цикл оркестратора, а логировать и продолжать.

---

## 3. АРХИТЕКТУРА

### 3.1 Файловая структура

```
services/
  telegram_alert_service.py   # MODIFIED - реальная отправка
  telegram_alert_client.py    # NEW - обёртка над TeleBot для отправки

tests/
  test_telegram_alert_service.py  # MODIFIED - обновить под новую логику
  test_telegram_alert_client.py   # NEW - тест клиента отправки
```

---

### 3.2 Компонент: TelegramAlertClient

**Файл:** `services/telegram_alert_client.py`

```python
"""
Ленивый клиент для отправки сообщений в Telegram из Orchestrator Loop.
Использует pyTelegramBotAPI (telebot), тот же токен что основной аналитический бот.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import config

logger = logging.getLogger(__name__)


class TelegramAlertClient:
    """Singleton клиент для отправки алертов."""
    
    _instance: Optional["TelegramAlertClient"] = None
    _lock = threading.Lock()
    
    def __init__(self) -> None:
        self._bot = None
        self._chat_ids: list[int] = []
        self._enabled = False
        self._init_client()
    
    @classmethod
    def instance(cls) -> "TelegramAlertClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _init_client(self) -> None:
        token = str(getattr(config, "BOT_TOKEN", "") or "").strip()
        chat_raw = str(getattr(config, "CHAT_ID", "") or "").strip()
        enabled = bool(getattr(config, "ENABLE_TELEGRAM", True))
        
        if not enabled:
            logger.info("[ALERT CLIENT] Telegram disabled via ENABLE_TELEGRAM=false")
            return
        
        if not token or ":" not in token:
            logger.warning("[ALERT CLIENT] BOT_TOKEN not set, alerts will be logged only")
            return
        
        chat_ids = self._parse_chat_ids(chat_raw)
        if not chat_ids:
            logger.warning("[ALERT CLIENT] CHAT_ID not set, alerts will be logged only")
            return
        
        try:
            import telebot
            self._bot = telebot.TeleBot(token, parse_mode=None)
            self._chat_ids = chat_ids
            self._enabled = True
            logger.info(
                "[ALERT CLIENT] Initialized for %d chat(s)",
                len(chat_ids),
            )
        except Exception as exc:
            logger.error("[ALERT CLIENT] Init failed: %s", exc)
    
    @staticmethod
    def _parse_chat_ids(raw: str) -> list[int]:
        out: list[int] = []
        seen: set[int] = set()
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                value = int(part)
                if value not in seen:
                    seen.add(value)
                    out.append(value)
            except ValueError:
                continue
        return out
    
    def is_enabled(self) -> bool:
        return self._enabled and self._bot is not None
    
    def send(self, text: str) -> bool:
        """
        Синхронная отправка во все chat_ids.
        Возвращает True если хотя бы одно сообщение отправлено.
        """
        if not self.is_enabled():
            return False
        
        ok_count = 0
        for chat_id in self._chat_ids:
            try:
                self._bot.send_message(chat_id, text)
                ok_count += 1
            except Exception as exc:
                logger.warning(
                    "[ALERT CLIENT] Send failed for chat %s: %s",
                    chat_id,
                    exc,
                )
        
        return ok_count > 0
```

---

### 3.3 Компонент: telegram_alert_service

**Файл:** `services/telegram_alert_service.py` (MODIFIED)

```python
"""
Сервис отправки алертов Orchestrator Loop.
Async wrapper над синхронным TelegramAlertClient.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Лимит длины Telegram-сообщения
_MAX_MESSAGE_LEN = 3800


def _split_chunks(text: str, limit: int = _MAX_MESSAGE_LEN) -> list[str]:
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= limit:
        return [body]
    
    chunks: list[str] = []
    while body:
        if len(body) <= limit:
            chunks.append(body)
            break
        # Пытаемся разбить по переносам строк
        cut = body.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(body[:cut].rstrip())
        body = body[cut:].lstrip()
    return chunks


async def send_telegram_alert(text: str) -> None:
    """
    Отправляет алерт в Telegram.
    Логирует текст ВСЕГДА (для audit trail), дополнительно шлёт в Telegram если клиент включён.
    """
    logger.info("[ORCHESTRATOR ALERT]\n%s", text)
    
    from services.telegram_alert_client import TelegramAlertClient
    client = TelegramAlertClient.instance()
    
    if not client.is_enabled():
        return
    
    try:
        # Отправка в thread pool, чтобы не блокировать asyncio loop
        for chunk in _split_chunks(text):
            await asyncio.to_thread(client.send, chunk)
    except Exception as exc:
        logger.error("[ORCHESTRATOR ALERT] Delivery failed: %s", exc)


async def send_daily_report(day: date) -> None:
    """
    Отправляет daily report в Telegram.
    """
    from core.orchestrator.calibration_log import CalibrationLog
    from renderers.calibration_renderer import render_daily_report
    
    summary = CalibrationLog.instance().summarize_day(day)
    report_text = render_daily_report(summary)
    
    logger.info("[DAILY REPORT]\n%s", report_text)
    
    from services.telegram_alert_client import TelegramAlertClient
    client = TelegramAlertClient.instance()
    
    if not client.is_enabled():
        return
    
    try:
        for chunk in _split_chunks(report_text):
            await asyncio.to_thread(client.send, chunk)
    except Exception as exc:
        logger.error("[DAILY REPORT] Delivery failed: %s", exc)
```

---

## 4. ЗАПУСК

### 4.1 Параллельный запуск с аналитическим ботом

Пользователь хочет чтобы **оба** бота работали параллельно. Варианты:

**Вариант A — Два процесса (рекомендую):**
```
Terminal 1: python telegram_bot_runner.py      # аналитический бот
Terminal 2: python orchestrator_runner.py      # orchestrator loop
```

Плюсы:
- Полная изоляция
- Если один упал — другой работает
- Разные логи

Минусы:
- Два процесса вместо одного

**Вариант B — Один процесс (future):**
Добавить orchestrator_loop как background task в `TelegramBotApp.run()`. Не в TZ-009, можно в TZ-010.

**Решение:** в TZ-009 идём по варианту A. Никаких изменений в `telegram_bot_runner.py`.

---

### 4.2 Конфигурация

Никаких новых переменных окружения. Используем существующие:
- `BOT_TOKEN` — уже есть
- `CHAT_ID` — уже есть
- `ENABLE_TELEGRAM` — уже есть

---

## 5. ТЕСТЫ

### 5.1 test_telegram_alert_client.py

```python
import pytest
from unittest.mock import MagicMock, patch

from services.telegram_alert_client import TelegramAlertClient


@pytest.fixture(autouse=True)
def reset_singleton():
    """Сброс синглтона между тестами."""
    TelegramAlertClient._instance = None
    yield
    TelegramAlertClient._instance = None


def test_disabled_when_no_token():
    with patch("services.telegram_alert_client.config") as mock_cfg:
        mock_cfg.BOT_TOKEN = ""
        mock_cfg.CHAT_ID = "12345"
        mock_cfg.ENABLE_TELEGRAM = True
        
        client = TelegramAlertClient.instance()
        assert not client.is_enabled()
        assert client.send("test") is False


def test_disabled_when_no_chat_id():
    with patch("services.telegram_alert_client.config") as mock_cfg:
        mock_cfg.BOT_TOKEN = "123:abc"
        mock_cfg.CHAT_ID = ""
        mock_cfg.ENABLE_TELEGRAM = True
        
        client = TelegramAlertClient.instance()
        assert not client.is_enabled()


def test_disabled_when_telegram_off():
    with patch("services.telegram_alert_client.config") as mock_cfg:
        mock_cfg.BOT_TOKEN = "123:abc"
        mock_cfg.CHAT_ID = "12345"
        mock_cfg.ENABLE_TELEGRAM = False
        
        client = TelegramAlertClient.instance()
        assert not client.is_enabled()


def test_parse_chat_ids():
    assert TelegramAlertClient._parse_chat_ids("12345") == [12345]
    assert TelegramAlertClient._parse_chat_ids("12345,67890") == [12345, 67890]
    assert TelegramAlertClient._parse_chat_ids("12345; 67890") == [12345, 67890]
    assert TelegramAlertClient._parse_chat_ids("12345,12345") == [12345]  # dedup
    assert TelegramAlertClient._parse_chat_ids("") == []
    assert TelegramAlertClient._parse_chat_ids("abc") == []


def test_send_success():
    with patch("services.telegram_alert_client.config") as mock_cfg:
        mock_cfg.BOT_TOKEN = "123:abc"
        mock_cfg.CHAT_ID = "12345"
        mock_cfg.ENABLE_TELEGRAM = True
        
        with patch("telebot.TeleBot") as mock_telebot:
            mock_bot = MagicMock()
            mock_telebot.return_value = mock_bot
            
            client = TelegramAlertClient.instance()
            assert client.is_enabled()
            
            result = client.send("hello")
            assert result is True
            mock_bot.send_message.assert_called_once_with(12345, "hello")


def test_send_failure_returns_false():
    with patch("services.telegram_alert_client.config") as mock_cfg:
        mock_cfg.BOT_TOKEN = "123:abc"
        mock_cfg.CHAT_ID = "12345"
        mock_cfg.ENABLE_TELEGRAM = True
        
        with patch("telebot.TeleBot") as mock_telebot:
            mock_bot = MagicMock()
            mock_bot.send_message.side_effect = RuntimeError("Network error")
            mock_telebot.return_value = mock_bot
            
            client = TelegramAlertClient.instance()
            result = client.send("hello")
            assert result is False
```

---

### 5.2 test_telegram_alert_service.py (UPDATED)

```python
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from services.telegram_alert_service import send_telegram_alert, send_daily_report, _split_chunks


@pytest.mark.asyncio
async def test_send_telegram_alert_logs_always(caplog):
    """Алерт ВСЕГДА пишется в лог, даже если Telegram отключён."""
    with patch("services.telegram_alert_service.TelegramAlertClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.is_enabled.return_value = False
        mock_client_cls.instance.return_value = mock_client
        
        with caplog.at_level("INFO"):
            await send_telegram_alert("test alert")
        
        assert "test alert" in caplog.text


@pytest.mark.asyncio
async def test_send_telegram_alert_when_enabled():
    """Когда клиент включён, отправка происходит через to_thread."""
    with patch("services.telegram_alert_service.TelegramAlertClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.is_enabled.return_value = True
        mock_client.send.return_value = True
        mock_client_cls.instance.return_value = mock_client
        
        await send_telegram_alert("hello")
        
        mock_client.send.assert_called_once_with("hello")


@pytest.mark.asyncio
async def test_send_telegram_alert_survives_exception():
    """Исключение в отправке не должно крашить."""
    with patch("services.telegram_alert_service.TelegramAlertClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.is_enabled.return_value = True
        mock_client.send.side_effect = RuntimeError("boom")
        mock_client_cls.instance.return_value = mock_client
        
        # Не должно бросить
        await send_telegram_alert("hello")


def test_split_chunks_short():
    assert _split_chunks("short") == ["short"]


def test_split_chunks_empty():
    assert _split_chunks("") == []
    assert _split_chunks("   ") == []


def test_split_chunks_splits_on_newline():
    text = "line1\n" + ("x" * 3900) + "\nline3"
    chunks = _split_chunks(text, limit=3800)
    assert len(chunks) >= 2
    assert all(len(c) <= 3800 for c in chunks)


@pytest.mark.asyncio
async def test_send_daily_report_builds_report():
    with patch("services.telegram_alert_service.CalibrationLog") as mock_log_cls, \
         patch("services.telegram_alert_service.render_daily_report") as mock_render, \
         patch("services.telegram_alert_service.TelegramAlertClient") as mock_client_cls:
        
        mock_log_cls.instance().summarize_day.return_value = MagicMock()
        mock_render.return_value = "Report text"
        
        mock_client = MagicMock()
        mock_client.is_enabled.return_value = False
        mock_client_cls.instance.return_value = mock_client
        
        await send_daily_report(date.today())
        
        mock_render.assert_called_once()
```

---

## 6. SMOKE TEST (ручной)

После реализации ГПТ должен выполнить **ручной smoke test** (а не только автотесты):

**Шаг 1 — Проверка конфига:**
```bash
python -c "import config; print('TOKEN set:', bool(config.BOT_TOKEN)); print('CHAT_ID:', config.CHAT_ID)"
```

**Шаг 2 — Одиночная отправка:**
```python
# python
import asyncio
from services.telegram_alert_service import send_telegram_alert
asyncio.run(send_telegram_alert("🔄 TZ-009 smoke test"))
```

Ожидание: **сообщение пришло в Telegram** на указанный CHAT_ID.

**Шаг 3 — Запуск loop:**
```bash
python orchestrator_runner.py
```

Ожидание: в Telegram приходят сообщения при срабатывании изменений (или при daily report time).

---

## 7. КРИТЕРИИ ПРИЁМКИ

### Обязательные:
1. ✅ `TelegramAlertClient` корректно инициализируется с существующими `BOT_TOKEN` / `CHAT_ID`
2. ✅ `send_telegram_alert()` реально отправляет сообщение в Telegram (если клиент включён)
3. ✅ Если `BOT_TOKEN` не задан — fallback на лог, БЕЗ crash
4. ✅ Если Telegram API падает — loop продолжает работать, ошибка залогирована
5. ✅ Длинные сообщения корректно разбиваются на chunks (лимит 3800 символов)
6. ✅ Unit-тесты проходят: `test_telegram_alert_client.py` + `test_telegram_alert_service.py`
7. ✅ Full regression: 225+ passed (RUN_TESTS.bat)
8. ✅ Baseline не сдвинут: 22 / 72.73% / +10.9273%
9. ✅ Существующий аналитический бот не сломан (проверить импортом `services.telegram_runtime`)

### Опциональные:
- Parse mode (HTML/Markdown) — пока не используем, тексты plain
- Retry с exponential backoff — Telegram rarely fails, пока не нужно

---

## 8. OUT OF SCOPE

- Объединение двух ботов в один процесс (TZ-010 возможно)
- Интерактивные кнопки в алертах
- Rich formatting (HTML/Markdown)
- Отправка картинок/графиков

---

## 9. РИСКИ

**Низкие:**
- Rate limit — не достижим при текущей частоте алертов
- Дубли сообщений между ботами — нет, у них разные триггеры

**Средние:**
- `telebot.TeleBot` thread-safety — используем `asyncio.to_thread()`, клиент создаётся один раз, методы потокобезопасны для разных чатов

**Требуют проверки:**
- Что именно находится в существующем `services/telegram_runtime.py` — чтобы случайно не дёрнуть side effects

---

## 10. ВАЖНО ДЛЯ ГПТ

1. **Не трогать** `services/telegram_runtime.py` и `telegram_bot_runner.py` — это рабочий аналитический бот
2. **Использовать** существующие переменные `config.BOT_TOKEN` и `config.CHAT_ID`
3. **Использовать** библиотеку `telebot` (pyTelegramBotAPI), она уже есть в requirements
4. **Обязательно** сделать ручной smoke test после автотестов и приложить скриншот/лог в `TZ-009_report.md`
5. Проверить что `import services.telegram_runtime` всё ещё работает

---

**Конец документа.**
