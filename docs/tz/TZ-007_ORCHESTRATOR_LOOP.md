# TZ-007: ORCHESTRATOR LOOP — MVP ФИНАЛ

**Версия:** 1.0  
**Дата:** 2026-04-18  
**Статус:** Ready for Implementation  
**Приоритет:** P1 (критическая функциональность — завершение MVP)

---

## КОНТЕКСТ

Grid Orchestrator — Telegram-бот для управления сеточными ботами на GinArea+Bitmex.

**Что уже сделано:**
- TZ-001: Чистка legacy кода
- TZ-002: `regime_classifier.py` (метки режима рынка + модификаторы)
- TZ-002B: Русификация i18n + Unicode визуализация
- TZ-003: `portfolio_state.py` + команды `/portfolio /regime /category /bot`
- TZ-004: `action_matrix.py` + `command_dispatcher.py` + команды управления
- TZ-005: `killswitch.py` + защита маржи
- TZ-006: `calibration_log.py` + daily report

**Baseline бэктеста (НОВЫЙ, НЕЛЬЗЯ ЛОМАТЬ):**
- Trades: 23
- Winrate: 73.91%
- PnL: +11.7123%

**Текущий статус тестов:** 209+ passed

---

## ЗАДАЧА TZ-007

Реализовать **orchestrator_loop** — автоматический цикл оркестратора.

**Это финальный модуль P1 (сетки) — после него Grid Orchestrator MVP готов! 🎉**

**Цели:**
1. **Автоматическая проверка режима рынка** каждые N минут
2. **Применение правил action_matrix** автоматически
3. **Проверка killswitch триггеров** автоматически
4. **Отправка алертов в Telegram** при изменениях (заглушка — логирование)
5. **Отправка daily report** по расписанию (заглушка — логирование)
6. **Логирование событий** через calibration_log

---

## DESIGN-ДОКУМЕНТ

**См. полный дизайн:** `docs/ORCHESTRATOR_LOOP_DESIGN_v0.1.md`

Ключевые моменты:
- Асинхронный цикл на `asyncio`
- Интервал проверки: 5 минут (настраивается)
- Telegram алерты — заглушка (логирование), реальная интеграция — post-MVP
- Daily report в 09:00 UTC (настраивается)

---

## ЧТО НУЖНО РЕАЛИЗОВАТЬ

### 1. Core модуль

#### 1.1 `core/orchestrator/orchestrator_loop.py`

**Создать класс `OrchestratorLoop`:**

```python
import asyncio
import logging
from datetime import datetime, time, timezone
from typing import Any

from core.orchestrator.calibration_log import CalibrationLog
from core.orchestrator.command_dispatcher import dispatch_orchestrator_decisions
from core.orchestrator.killswitch_triggers import check_all_killswitch_triggers
from core.orchestrator.portfolio_state import PortfolioStore
from core.pipeline import build_full_snapshot
from services.telegram_alert_service import send_telegram_alert, send_daily_report

logger = logging.getLogger(__name__)


class OrchestratorLoop:
    """
    Автоматический цикл оркестратора.
    Работает в фоновом режиме, проверяет режим рынка и применяет правила.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.interval_sec = config.get("ORCHESTRATOR_LOOP_INTERVAL_SEC", 300)  # 5 минут
        self.daily_report_time = config.get("ORCHESTRATOR_DAILY_REPORT_TIME", "09:00")  # UTC
        self._running = False
        self._last_daily_report_date = None

    async def start(self) -> None:
        """Запускает цикл оркестратора."""
        logger.info("[ORCHESTRATOR LOOP] Starting...")
        self._running = True

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"[ORCHESTRATOR LOOP] Error in tick: {e}", exc_info=True)

            # Ждём следующей итерации
            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        """Останавливает цикл оркестратора."""
        logger.info("[ORCHESTRATOR LOOP] Stopping...")
        self._running = False

    async def _tick(self) -> None:
        """Одна итерация цикла."""
        logger.debug("[ORCHESTRATOR LOOP] Tick")

        # 1. Получаем snapshot рынка
        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime = snapshot.get("regime", {})

        # 2. Проверяем killswitch триггеры
        check_all_killswitch_triggers(self.config)

        # 3. Применяем правила оркестратора
        portfolio = PortfolioStore.instance()
        result = dispatch_orchestrator_decisions(portfolio, regime)

        # 4. Отправляем алерты при изменениях
        if result.changed:
            logger.info(f"[ORCHESTRATOR LOOP] Detected {len(result.changed)} changes")
            for change in result.changed:
                alert_text = self._format_change_alert(change, regime)
                await send_telegram_alert(alert_text)

        # 5. Отправляем дополнительные алерты
        for alert in result.alerts:
            await send_telegram_alert(alert.text)

        # 6. Проверяем нужно ли отправить daily report
        await self._maybe_send_daily_report()

    def _format_change_alert(self, change: Any, regime: dict[str, Any]) -> str:
        """Форматирует алерт об изменении action категории."""
        from core.orchestrator.i18n_ru import ACTION_RU, CATEGORY_RU, tr

        lines = [
            "🔄 ОРКЕСТРАТОР: ИЗМЕНЕНИЕ",
            "",
            f"Категория: {tr(change.category_key, CATEGORY_RU)}",
            f"Действие: {tr(change.from_action, ACTION_RU)} → {tr(change.to_action, ACTION_RU)}",
            f"Причина: {change.reason_ru}",
            "",
            f"Режим: {regime.get('primary', 'UNKNOWN')}",
        ]

        modifiers = regime.get("modifiers", [])
        if modifiers:
            lines.append(f"Модификаторы: {', '.join(modifiers)}")

        lines.append("")
        if hasattr(change, 'affected_bots') and change.affected_bots:
            lines.append(f"Боты: {', '.join(change.affected_bots)}")

        return "\n".join(lines)

    async def _maybe_send_daily_report(self) -> None:
        """Проверяет нужно ли отправить daily report."""
        now = datetime.now(timezone.utc)
        
        # Парсим целевое время
        try:
            target_time = time.fromisoformat(self.daily_report_time)
        except Exception:
            logger.error(f"Invalid daily report time format: {self.daily_report_time}")
            return

        # Проверяем что сейчас близко к целевому времени (в пределах интервала цикла)
        current_time = now.time()
        time_diff_sec = abs(
            (current_time.hour * 3600 + current_time.minute * 60)
            - (target_time.hour * 3600 + target_time.minute * 60)
        )

        if time_diff_sec < self.interval_sec:
            # Проверяем что сегодня ещё не отправляли
            today = now.date()
            if self._last_daily_report_date != today:
                logger.info("[ORCHESTRATOR LOOP] Sending daily report")
                await send_daily_report(today)
                self._last_daily_report_date = today
```

---

### 2. Telegram Alert Service

**Создать файл `services/telegram_alert_service.py`:**

```python
import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)


async def send_telegram_alert(text: str) -> None:
    """
    Отправляет алерт в Telegram.
    
    NOTE: В MVP это заглушка — только логирование.
    Реальная интеграция с Telegram Bot API (aiogram/python-telegram-bot)
    будет реализована в post-MVP фазе.
    """
    logger.info(f"[TELEGRAM ALERT]\n{text}")
    
    # TODO (post-MVP): Реализовать отправку через Telegram Bot API
    # Example:
    # from aiogram import Bot
    # bot = Bot(token=TELEGRAM_BOT_TOKEN)
    # await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)


async def send_daily_report(day: date) -> None:
    """
    Отправляет daily report в Telegram.
    
    NOTE: В MVP это заглушка — только логирование.
    """
    from core.orchestrator.calibration_log import CalibrationLog
    from renderers.calibration_renderer import render_daily_report

    summary = CalibrationLog.instance().summarize_day(day)
    report_text = render_daily_report(summary)

    logger.info(f"[DAILY REPORT]\n{report_text}")
    
    # TODO (post-MVP): Реализовать отправку через Telegram Bot API
    # await bot.send_message(chat_id=ADMIN_CHAT_ID, text=report_text)
```

---

### 3. Конфигурация

**В `config.py` добавить:**

```python
# ================== ORCHESTRATOR LOOP SETTINGS ==================

# Интервал проверки режима рынка и применения правил (секунды)
ORCHESTRATOR_LOOP_INTERVAL_SEC = int(os.getenv("ORCHESTRATOR_LOOP_INTERVAL_SEC", "300"))  # 5 минут

# Время отправки daily report (UTC, формат HH:MM)
ORCHESTRATOR_DAILY_REPORT_TIME = os.getenv("ORCHESTRATOR_DAILY_REPORT_TIME", "09:00")

# Включить автоматическую отправку алертов (для будущего использования)
ORCHESTRATOR_ENABLE_AUTO_ALERTS = os.getenv("ORCHESTRATOR_ENABLE_AUTO_ALERTS", "true").lower() == "true"
```

---

### 4. Runner (опционально)

**Создать файл `orchestrator_runner.py` (опционально — для ручного запуска):**

```python
import asyncio
import logging

from core.orchestrator.orchestrator_loop import OrchestratorLoop
from config import (
    ORCHESTRATOR_LOOP_INTERVAL_SEC,
    ORCHESTRATOR_DAILY_REPORT_TIME,
    KILLSWITCH_INITIAL_BALANCE_USD,
    KILLSWITCH_DRAWDOWN_THRESHOLD_PCT,
    KILLSWITCH_FLASH_THRESHOLD_PCT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main():
    """Запуск цикла оркестратора."""
    config = {
        "ORCHESTRATOR_LOOP_INTERVAL_SEC": ORCHESTRATOR_LOOP_INTERVAL_SEC,
        "ORCHESTRATOR_DAILY_REPORT_TIME": ORCHESTRATOR_DAILY_REPORT_TIME,
        "KILLSWITCH_INITIAL_BALANCE_USD": KILLSWITCH_INITIAL_BALANCE_USD,
        "KILLSWITCH_DRAWDOWN_THRESHOLD_PCT": KILLSWITCH_DRAWDOWN_THRESHOLD_PCT,
        "KILLSWITCH_FLASH_THRESHOLD_PCT": KILLSWITCH_FLASH_THRESHOLD_PCT,
    }

    loop = OrchestratorLoop(config)

    try:
        await loop.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt, stopping...")
        loop.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

---

### 5. Тесты

#### 5.1 `tests/test_orchestrator_loop.py`

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, time, timezone

from core.orchestrator.orchestrator_loop import OrchestratorLoop


@pytest.mark.asyncio
async def test_orchestrator_loop_tick_no_changes():
    """Проверка tick без изменений."""
    config = {
        "ORCHESTRATOR_LOOP_INTERVAL_SEC": 300,
        "ORCHESTRATOR_DAILY_REPORT_TIME": "09:00",
        "KILLSWITCH_INITIAL_BALANCE_USD": 10_000,
        "KILLSWITCH_DRAWDOWN_THRESHOLD_PCT": 15.0,
    }

    loop = OrchestratorLoop(config)

    with patch("core.orchestrator.orchestrator_loop.build_full_snapshot") as mock_snapshot, \
         patch("core.orchestrator.orchestrator_loop.check_all_killswitch_triggers") as mock_check_ks, \
         patch("core.orchestrator.orchestrator_loop.dispatch_orchestrator_decisions") as mock_dispatch, \
         patch("core.orchestrator.orchestrator_loop.send_telegram_alert", new_callable=AsyncMock) as mock_send:

        # Mock snapshot
        mock_snapshot.return_value = {
            "regime": {
                "primary": "RANGE",
                "modifiers": [],
            }
        }

        # Mock dispatch result (без изменений)
        mock_result = MagicMock()
        mock_result.changed = []
        mock_result.alerts = []
        mock_dispatch.return_value = mock_result

        # Выполняем один tick
        await loop._tick()

        # Проверяем вызовы
        mock_snapshot.assert_called_once()
        mock_check_ks.assert_called_once()
        mock_dispatch.assert_called_once()
        mock_send.assert_not_called()  # Нет изменений — нет алертов


@pytest.mark.asyncio
async def test_orchestrator_loop_sends_alert_on_change():
    """Проверка отправки алерта при изменении action."""
    config = {
        "ORCHESTRATOR_LOOP_INTERVAL_SEC": 300,
        "ORCHESTRATOR_DAILY_REPORT_TIME": "09:00",
        "KILLSWITCH_INITIAL_BALANCE_USD": 10_000,
        "KILLSWITCH_DRAWDOWN_THRESHOLD_PCT": 15.0,
    }

    loop = OrchestratorLoop(config)

    with patch("core.orchestrator.orchestrator_loop.build_full_snapshot") as mock_snapshot, \
         patch("core.orchestrator.orchestrator_loop.check_all_killswitch_triggers"), \
         patch("core.orchestrator.orchestrator_loop.dispatch_orchestrator_decisions") as mock_dispatch, \
         patch("core.orchestrator.orchestrator_loop.send_telegram_alert", new_callable=AsyncMock) as mock_send:

        mock_snapshot.return_value = {
            "regime": {
                "primary": "CASCADE_UP",
                "modifiers": ["VOLATILITY_SPIKE"],
            }
        }

        # Mock изменение
        mock_change = MagicMock()
        mock_change.category_key = "btc_short"
        mock_change.from_action = "RUN"
        mock_change.to_action = "PAUSE"
        mock_change.reason_ru = "Каскад вверх — шорт на паузу"
        mock_change.affected_bots = ["btc_short_l1"]

        mock_result = MagicMock()
        mock_result.changed = [mock_change]
        mock_result.alerts = []
        mock_dispatch.return_value = mock_result

        await loop._tick()

        # Проверяем алерт
        mock_send.assert_called_once()
        alert_text = mock_send.call_args[0][0]
        assert "ОРКЕСТРАТОР: ИЗМЕНЕНИЕ" in alert_text
        assert "btc_short" in alert_text.lower()


@pytest.mark.asyncio
async def test_orchestrator_loop_format_change_alert():
    """Проверка форматирования алерта."""
    config = {
        "ORCHESTRATOR_LOOP_INTERVAL_SEC": 300,
        "ORCHESTRATOR_DAILY_REPORT_TIME": "09:00",
    }

    loop = OrchestratorLoop(config)

    mock_change = MagicMock()
    mock_change.category_key = "btc_long"
    mock_change.from_action = "PAUSE"
    mock_change.to_action = "RUN"
    mock_change.reason_ru = "Тренд вверх — лонг активен"
    mock_change.affected_bots = ["btc_long_mid", "btc_long_safe"]

    regime = {
        "primary": "TREND_UP",
        "modifiers": ["STRONG_MOMENTUM"],
    }

    alert = loop._format_change_alert(mock_change, regime)

    assert "ОРКЕСТРАТОР: ИЗМЕНЕНИЕ" in alert
    assert "btc_long" in alert.lower()
    assert "PAUSE → RUN" in alert or "pause → run" in alert.lower()
    assert "TREND_UP" in alert
```

---

#### 5.2 `tests/test_telegram_alert_service.py`

```python
import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from services.telegram_alert_service import send_telegram_alert, send_daily_report


@pytest.mark.asyncio
async def test_send_telegram_alert():
    """Проверка отправки алерта (заглушка)."""
    alert_text = "🚨 Тестовый алерт"

    # Сейчас это просто логирование, проверяем что не падает
    await send_telegram_alert(alert_text)
    # Должно отработать без ошибок


@pytest.mark.asyncio
async def test_send_daily_report():
    """Проверка отправки daily report (заглушка)."""
    with patch("services.telegram_alert_service.CalibrationLog") as mock_log, \
         patch("services.telegram_alert_service.render_daily_report") as mock_render:

        mock_summary = MagicMock()
        mock_log.instance().summarize_day.return_value = mock_summary
        mock_render.return_value = "📊 DAILY REPORT\n..."

        await send_daily_report(date.today())

        mock_log.instance().summarize_day.assert_called_once()
        mock_render.assert_called_once()
```

---

### 6. Документация

**Создать файл `docs/ORCHESTRATOR_LOOP_DESIGN_v0.1.md`** — уже создан выше.

**Обновить `PROJECT_MANIFEST.md`:**

```markdown
## TZ-007: Orchestrator Loop (MVP Complete!)
- Status: ✅ Delivered
- Files:
  - core/orchestrator/orchestrator_loop.py
  - services/telegram_alert_service.py
  - config.py (ORCHESTRATOR_* параметры)
  - orchestrator_runner.py (опционально)
  - tests/test_orchestrator_loop.py
  - tests/test_telegram_alert_service.py

**Grid Orchestrator MVP READY! 🎉**
```

---

## КРИТЕРИИ ПРИЁМКИ

### Обязательные (Must Have):
1. ✅ **Baseline бэктеста не изменён:** 23 / 73.91% / +11.7123%
2. ✅ **Все тесты проходят:** 209+ passed (включая новые для orchestrator_loop)
3. ✅ **OrchestratorLoop работает:**
   - `start()` запускает асинхронный цикл
   - `_tick()` выполняет полный цикл проверки
   - `stop()` останавливает цикл
4. ✅ **Интеграция:**
   - Вызывает `build_full_snapshot()` для получения режима
   - Вызывает `check_all_killswitch_triggers()`
   - Вызывает `dispatch_orchestrator_decisions()`
   - Отправляет алерты через `send_telegram_alert()` при изменениях
   - Отправляет daily report через `send_daily_report()` по расписанию
5. ✅ **Telegram Alert Service:**
   - `send_telegram_alert()` — заглушка (логирует)
   - `send_daily_report()` — заглушка (логирует)
6. ✅ **Конфигурация:**
   - `ORCHESTRATOR_LOOP_INTERVAL_SEC` работает
   - `ORCHESTRATOR_DAILY_REPORT_TIME` работает
7. ✅ **Тесты:**
   - `test_orchestrator_loop.py` — tick без изменений + tick с изменениями + форматирование алерта
   - `test_telegram_alert_service.py` — заглушки работают

### Опциональные (Nice to Have):
- `orchestrator_runner.py` для ручного запуска (можно пропустить)
- Команда `/orchestrator_status` (можно отложить на post-MVP)

---

## OUT OF SCOPE (POST-MVP)

- **Реальная Telegram Bot API интеграция** — требует:
  - Токен бота
  - Chat ID администратора
  - Библиотека aiogram или python-telegram-bot
  - Обработка rate limits
- **Web UI dashboard** — визуализация состояния
- **Multiple symbols** — сейчас только BTCUSDT
- **Advanced alerting** — кастомизация правил алертов

---

## ТЕХНИЧЕСКИЕ ЗАМЕТКИ

### Asyncio
- Используем `asyncio.run()` для запуска
- `asyncio.sleep()` для интервалов
- Все alert функции — `async def`

### Graceful Shutdown
- `loop.stop()` устанавливает флаг `_running = False`
- Цикл завершится после текущего tick
- Можно улучшить через `signal.SIGINT` handler (опционально)

### Daily Report Timing
- Проверяем каждый tick: `|current_time - target_time| < interval_sec`
- `_last_daily_report_date` предотвращает дубликаты
- НЕ персистится — при перезапуске может отправить дважды (приемлемо для MVP)

### Telegram Заглушки
- Вся логика отправки — через `logger.info()`
- В будущем заменить на реальный Telegram Bot API
- Интерфейс уже готов — просто раскомментировать TODO

---

## DELIVERY

**Формат поставки:** Единый ZIP-архив с полным кодом проекта.

**Структура:**
```
TZ-007_delivery.zip
├── core/orchestrator/
│   └── orchestrator_loop.py            (NEW)
├── services/
│   └── telegram_alert_service.py       (NEW)
├── config.py                           (MODIFIED - добавлено ORCHESTRATOR_*)
├── orchestrator_runner.py              (NEW - опционально)
├── tests/
│   ├── test_orchestrator_loop.py       (NEW)
│   └── test_telegram_alert_service.py  (NEW)
├── docs/
│   └── ORCHESTRATOR_LOOP_DESIGN_v0.1.md (NEW)
├── TZ-007_report.md                    (отчёт о выполнении)
└── (все остальные файлы без изменений)
```

**Отчёт TZ-007_report.md должен содержать:**
- Что сделано
- Результаты тестов (сколько passed)
- Baseline бэктеста (23/73.91%/+11.7123%)
- Список изменённых файлов
- Подтверждение что **Grid Orchestrator MVP READY! 🎉**

---

## ПОЗДРАВЛЕНИЕ

**После TZ-007 Grid Orchestrator MVP готов!**

Реализованы все ключевые модули P1 (сетки):
- ✅ TZ-002: Режимы рынка + модификаторы
- ✅ TZ-003: Portfolio state
- ✅ TZ-004: Action matrix + команды управления
- ✅ TZ-005: Killswitch + защита маржи
- ✅ TZ-006: Calibration log + daily report
- ✅ TZ-007: Orchestrator loop + авто-алерты

**Следующая фаза — P2 (ручная торговля) и P3 (аналитика) — на будущее.**

Удачи! 🚀
