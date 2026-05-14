# TZ-009: ORCHESTRATOR TELEGRAM ALERTS — реальная отправка

**Версия:** 1.0  
**Дата:** 2026-04-18  
**Статус:** Ready for Implementation  
**Приоритет:** P1 (функциональное расширение MVP)

---

## КОНТЕКСТ

**Grid Orchestrator MVP готов** (TZ-002 → TZ-008), baseline стабилизирован.

**Что уже работает:**
- Аналитический бот `telegram_bot_runner.py` — шлёт Trader/Grid View через telebot
- `BOT_TOKEN` и `CHAT_ID` настроены в env
- `telebot` (pyTelegramBotAPI) уже установлен (см. `requirements.txt`)

**Что сейчас заглушка:**
- `services/telegram_alert_service.py`: `send_telegram_alert()` и `send_daily_report()` только логируют, НЕ отправляют в Telegram

**Актуальный baseline:** 22 / 72.73% / +10.9273%  
**Тесты:** 225 passed (RUN_TESTS.bat)

---

## ЗАДАЧА TZ-009

Подключить Orchestrator Loop к реальному Telegram Bot API через существующий `telebot`, используя существующие `BOT_TOKEN` и `CHAT_ID`.

**НЕ ломать** работающий аналитический бот.  
**НЕ создавать** отдельный токен/чат — всё в одном месте.  
**Если токен не задан** — fallback на логирование, без крашей.

---

## DESIGN-ДОКУМЕНТ

**См.:** `docs/ORCHESTRATOR_TELEGRAM_DESIGN_v0.1.md`

Ключевые решения:
- Используем `telebot` (не aiogram) — совместимость с существующим кодом
- Отдельный `TeleBot` инстанс для отправки (не shared с аналитическим ботом)
- Singleton pattern + lazy init
- `asyncio.to_thread()` для обёртки синхронного `send_message`
- Чанкование длинных сообщений (лимит 3800 символов)

---

## ЧТО НУЖНО РЕАЛИЗОВАТЬ

### 1. Новый файл: `services/telegram_alert_client.py`

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
    """Singleton клиент для отправки алертов Orchestrator Loop."""
    
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
    
    @classmethod
    def reset(cls) -> None:
        """Для тестов — сброс синглтона."""
        with cls._lock:
            cls._instance = None
    
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
        """Парсит список chat_id: '12345' или '12345,67890' или '12345; 67890'."""
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

### 2. MODIFIED: `services/telegram_alert_service.py`

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

# Лимит длины Telegram-сообщения (с запасом от 4096)
_MAX_MESSAGE_LEN = 3800


def _split_chunks(text: str, limit: int = _MAX_MESSAGE_LEN) -> list[str]:
    """Разбивает длинный текст на chunks по переносам строк."""
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
        cut = body.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(body[:cut].rstrip())
        body = body[cut:].lstrip()
    return chunks


async def send_telegram_alert(text: str) -> None:
    """
    Отправляет алерт в Telegram.
    Логирует текст ВСЕГДА (для audit trail). Дополнительно шлёт в Telegram если клиент включён.
    Устойчиво к ошибкам — не крашит orchestrator loop.
    """
    logger.info("[ORCHESTRATOR ALERT]\n%s", text)
    
    from services.telegram_alert_client import TelegramAlertClient
    client = TelegramAlertClient.instance()
    
    if not client.is_enabled():
        return
    
    try:
        for chunk in _split_chunks(text):
            await asyncio.to_thread(client.send, chunk)
    except Exception as exc:
        logger.error("[ORCHESTRATOR ALERT] Delivery failed: %s", exc)


async def send_daily_report(day: date) -> None:
    """
    Строит daily report и отправляет в Telegram.
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

### 3. Тесты

#### 3.1 `tests/test_telegram_alert_client.py` (NEW)

Полный текст — см. раздел 5.1 design-документа.

Ключевые сценарии:
- `test_disabled_when_no_token` — без токена клиент выключен
- `test_disabled_when_no_chat_id` — без chat_id выключен
- `test_disabled_when_telegram_off` — при `ENABLE_TELEGRAM=false` выключен
- `test_parse_chat_ids` — парсинг одного/нескольких/дедупликация
- `test_send_success` — отправка вызывает `telebot.send_message`
- `test_send_failure_returns_false` — исключение не пробрасывается

**ВАЖНО:** все тесты должны использовать fixture `reset_singleton` для сброса `TelegramAlertClient._instance` между тестами.

---

#### 3.2 `tests/test_telegram_alert_service.py` (UPDATED)

Полный текст — см. раздел 5.2 design-документа.

Ключевые сценарии:
- `test_send_telegram_alert_logs_always` — алерт пишется в лог даже если Telegram выключен
- `test_send_telegram_alert_when_enabled` — когда включён, вызывается `client.send()`
- `test_send_telegram_alert_survives_exception` — исключения не крашат
- `test_split_chunks_*` — чанкование корректное
- `test_send_daily_report_builds_report` — daily report строится и логируется

---

### 4. SMOKE TEST (обязательно, ручной)

ГПТ должен запустить **ручной smoke test** и задокументировать результат в отчёте.

#### Шаг 1: Проверка конфига
```bash
python -c "import config; print('TOKEN set:', bool(config.BOT_TOKEN), '| CHAT_ID:', config.CHAT_ID)"
```

Ожидание: `TOKEN set: True | CHAT_ID: <число>`

#### Шаг 2: Одиночная отправка
```python
import asyncio
from services.telegram_alert_service import send_telegram_alert
asyncio.run(send_telegram_alert("🔄 TZ-009 smoke test — orchestrator alerts live"))
```

Ожидание: сообщение приходит в Telegram. В отчёт добавить:
- Лог с [ORCHESTRATOR ALERT]
- Подтверждение получения в Telegram (если возможно — скриншот или текст: "Received in Telegram: YES/NO")

**Если ГПТ не может запустить Telegram** (нет реальных токенов в workspace) — он должен это честно указать в отчёте и указать что логи показывают правильное поведение (алерт логируется и попытка отправки делается).

#### Шаг 3: Проверка импортов
```bash
python -c "import services.telegram_runtime; print('Analytical bot import OK')"
python -c "import services.telegram_alert_service; print('Alert service import OK')"
```

Оба должны пройти без ошибок.

---

## КРИТЕРИИ ПРИЁМКИ

### Обязательные (Must Have):
1. ✅ Создан `services/telegram_alert_client.py` с `TelegramAlertClient` (singleton)
2. ✅ `services/telegram_alert_service.py` обновлён — реальная отправка через клиент
3. ✅ Без `BOT_TOKEN` — fallback на лог, БЕЗ crash
4. ✅ При исключении в отправке — loop не падает, ошибка залогирована
5. ✅ Длинные сообщения чанкуются (лимит 3800)
6. ✅ Все новые unit-тесты проходят
7. ✅ Full regression: **225 passed** (через `RUN_TESTS.bat`)
8. ✅ Baseline не сдвинут: **22 / 72.73% / +10.9273%**
9. ✅ `import services.telegram_runtime` работает (аналитический бот не сломан)
10. ✅ Smoke test выполнен и задокументирован в `TZ-009_report.md`

### Опциональные:
- Retry с backoff при 429 Too Many Requests
- Parse mode (HTML/Markdown) — пока plain text

---

## OUT OF SCOPE

- Объединение двух ботов в один процесс (возможно TZ-010)
- Inline кнопки в алертах
- Rich formatting
- Графики/картинки

---

## ТЕХНИЧЕСКИЕ ЗАМЕТКИ

### Unix-style paths
`Path("services/telegram_alert_service.py")` — всегда forward slashes

### НЕ ТРОГАТЬ:
- `services/telegram_runtime.py` — рабочий аналитический бот
- `telegram_bot_runner.py` — entry point аналитического бота
- `core/orchestrator/orchestrator_loop.py` — он уже вызывает `send_telegram_alert()`, менять не надо

### ИСПОЛЬЗОВАТЬ:
- `config.BOT_TOKEN`, `config.CHAT_ID`, `config.ENABLE_TELEGRAM` — существующие переменные
- `telebot` (`pyTelegramBotAPI`) — уже в requirements.txt

### asyncio.to_thread
`asyncio.to_thread(func, *args)` — стандартный способ запустить sync функцию без блокировки async loop. Доступен с Python 3.9+.

---

## DELIVERY

**Формат:** Единый ZIP `TZ-009_delivery.zip`

**Структура:**
```
TZ-009_delivery.zip
├── services/
│   ├── telegram_alert_client.py       (NEW)
│   └── telegram_alert_service.py      (MODIFIED)
├── tests/
│   ├── test_telegram_alert_client.py  (NEW)
│   └── test_telegram_alert_service.py (UPDATED)
├── docs/
│   └── ORCHESTRATOR_TELEGRAM_DESIGN_v0.1.md (NEW)
├── TZ-009_report.md                   (отчёт)
└── (все остальные файлы без изменений)
```

**В `TZ-009_report.md` обязательно:**
- Что сделано
- Результаты автотестов
- Результаты regression (`RUN_TESTS.bat` → 225 passed)
- Baseline проверка
- **Результат ручного smoke test** (даже если "не запустил из-за отсутствия токена" — явно об этом написать)
- Список изменённых файлов

---

Удачи! 🚀
