# ORCHESTRATOR LOOP DESIGN v0.1

**Статус:** Draft  
**Дата:** 2026-04-18  
**Автор:** Claude (архитектор)  
**Цель:** Автоматический цикл оркестратора — таймеры + авто-алерты = MVP готов

---

## 1. КОНЦЕПЦИЯ

Orchestrator Loop — автоматический фоновый процесс, который:
1. **Периодически проверяет режим рынка** (regime_classifier)
2. **Применяет правила action_matrix** (dispatch_orchestrator_decisions)
3. **Проверяет триггеры killswitch** (check_all_killswitch_triggers)
4. **Отправляет алерты в Telegram** при изменениях
5. **Логирует события** (calibration_log)
6. **Отправляет daily report** по расписанию

**Это финальный модуль P1 (сетки) — после него MVP оркестратора готов.**

---

## 2. АРХИТЕКТУРА

### 2.1 Файловая структура

```
core/orchestrator/
  orchestrator_loop.py      # Основной цикл оркестратора

services/
  telegram_alert_service.py # Отправка алертов в Telegram

config.py                   # Параметры таймеров

tests/
  test_orchestrator_loop.py
  test_telegram_alert_service.py
```

---

### 2.2 Основной цикл

**Файл `core/orchestrator/orchestrator_loop.py`:**

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
        lines.append(f"Боты: {', '.join(change.affected_bots)}")

        return "\n".join(lines)

    async def _maybe_send_daily_report(self) -> None:
        """Проверяет нужно ли отправить daily report."""
        now = datetime.now(timezone.utc)
        target_time = time.fromisoformat(self.daily_report_time)

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

### 2.3 Telegram Alert Service

**Файл `services/telegram_alert_service.py`:**

```python
import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)


async def send_telegram_alert(text: str) -> None:
    """
    Отправляет алерт в Telegram.
    
    NOTE: В реальной реализации здесь будет вызов Telegram Bot API.
    Сейчас это заглушка для логирования.
    """
    logger.info(f"[TELEGRAM ALERT]\n{text}")
    # TODO: Реализовать отправку через aiogram или python-telegram-bot
    # await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)


async def send_daily_report(day: date) -> None:
    """
    Отправляет daily report в Telegram.
    """
    from core.orchestrator.calibration_log import CalibrationLog
    from renderers.calibration_renderer import render_daily_report

    summary = CalibrationLog.instance().summarize_day(day)
    report_text = render_daily_report(summary)

    logger.info(f"[DAILY REPORT]\n{report_text}")
    # TODO: Реализовать отправку через Telegram Bot API
    # await bot.send_message(chat_id=ADMIN_CHAT_ID, text=report_text)
```

**ВАЖНО:** Реальная интеграция с Telegram Bot API (aiogram/python-telegram-bot) выходит за рамки TZ-007. Сейчас это заглушка для логирования.

---

### 2.4 Запуск цикла

**Модификация `telegram_bot_runner.py` или создание отдельного `orchestrator_runner.py`:**

```python
import asyncio
import logging
from pathlib import Path

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

## 3. КОНФИГУРАЦИЯ

**В `config.py` добавить:**

```python
# ================== ORCHESTRATOR LOOP SETTINGS ==================

# Интервал проверки режима рынка и применения правил (секунды)
ORCHESTRATOR_LOOP_INTERVAL_SEC = int(os.getenv("ORCHESTRATOR_LOOP_INTERVAL_SEC", "300"))  # 5 минут

# Время отправки daily report (UTC, формат HH:MM)
ORCHESTRATOR_DAILY_REPORT_TIME = os.getenv("ORCHESTRATOR_DAILY_REPORT_TIME", "09:00")

# Включить автоматическую отправку алертов
ORCHESTRATOR_ENABLE_AUTO_ALERTS = os.getenv("ORCHESTRATOR_ENABLE_AUTO_ALERTS", "true").lower() == "true"
```

---

## 4. ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩИМИ МОДУЛЯМИ

### 4.1 Нет изменений в:
- `regime_classifier.py` — используется как есть
- `action_matrix.py` — используется как есть
- `command_dispatcher.py` — используется как есть
- `killswitch_triggers.py` — используется как есть
- `calibration_log.py` — используется как есть

### 4.2 Новые зависимости:
- `asyncio` — для асинхронного цикла
- `aiogram` или `python-telegram-bot` — для отправки в Telegram (опционально, можно отложить)

---

## 5. ТЕСТЫ

### 5.1 `tests/test_orchestrator_loop.py`

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, time, timezone

from core.orchestrator.orchestrator_loop import OrchestratorLoop


@pytest.mark.asyncio
async def test_orchestrator_loop_tick():
    """Проверка одной итерации цикла."""
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

        # Проверяем что вызвали нужные функции
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

        # Mock dispatch result с изменением
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

        # Проверяем что отправили алерт
        mock_send.assert_called_once()
        alert_text = mock_send.call_args[0][0]
        assert "ОРКЕСТРАТОР: ИЗМЕНЕНИЕ" in alert_text
        assert "btc_short" in alert_text.lower()
```

---

### 5.2 `tests/test_telegram_alert_service.py`

```python
import pytest
from datetime import date
from unittest.mock import patch

from services.telegram_alert_service import send_telegram_alert, send_daily_report


@pytest.mark.asyncio
async def test_send_telegram_alert():
    """Проверка отправки алерта (заглушка)."""
    alert_text = "🚨 Тестовый алерт"

    # Сейчас это просто логирование, проверяем что не падает
    await send_telegram_alert(alert_text)


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

## 6. КОМАНДЫ УПРАВЛЕНИЯ ЦИКЛОМ

**Опционально — можно добавить в `handlers/command_actions.py`:**

### 6.1 `/orchestrator_status`

```python
def orchestrator_status(self) -> BotResponsePayload:
    """
    Статус оркестратора.
    """
    # TODO: Получить статус из OrchestratorLoop
    # Сейчас это заглушка
    lines = [
        "🤖 СТАТУС ОРКЕСТРАТОРА",
        "",
        "Режим: Автоматический",
        "Интервал: 5 минут",
        "Последняя проверка: 12:34:56 UTC",
        "",
        "Killswitch: ✅ Не активен",
        "Изменений за сегодня: 12",
    ]
    return self.ctx.plain("\n".join(lines))
```

---

## 7. КРИТЕРИИ ПРИЁМКИ

### Обязательные (Must Have):
1. ✅ **Baseline бэктеста не изменён:** 23 / 73.91% / +11.7123%
2. ✅ **Все тесты проходят:** 209+ passed (включая новые для orchestrator_loop)
3. ✅ **OrchestratorLoop работает:**
   - Периодически проверяет режим рынка
   - Применяет правила action_matrix
   - Проверяет killswitch триггеры
   - Логирует события через calibration_log
4. ✅ **Telegram Alert Service:**
   - Функция `send_telegram_alert()` работает (заглушка — логирует)
   - Функция `send_daily_report()` работает (заглушка — логирует)
5. ✅ **Конфигурация:**
   - `ORCHESTRATOR_LOOP_INTERVAL_SEC` настраивается
   - `ORCHESTRATOR_DAILY_REPORT_TIME` настраивается
6. ✅ **Тесты:**
   - `test_orchestrator_loop.py` — проверка tick + отправка алертов
   - `test_telegram_alert_service.py` — проверка заглушек

### Опциональные (Nice to Have):
- Реальная интеграция с Telegram Bot API (можно отложить на post-MVP)
- Команда `/orchestrator_status` (можно отложить)
- Graceful shutdown при остановке (можно упростить)

---

## 8. OUT OF SCOPE (POST-MVP)

- **Реальная Telegram Bot API интеграция** — требует токен, chat_id, aiogram/python-telegram-bot
- **Web UI dashboard** — визуализация состояния оркестратора
- **Alerting rules** — кастомизация условий отправки алертов
- **Multiple symbols** — сейчас только BTCUSDT
- **Backpressure handling** — если Telegram API тормозит

---

## 9. РИСКИ

**Низкие:**
- Интервал 5 минут может быть слишком частым (решается конфигом)
- Daily report может отправиться дважды при перезапуске (решается персистентностью `_last_daily_report_date`)

**Средние:**
- Без реального Telegram API алерты только в логах (приемлемо для MVP)
- Нет graceful shutdown — может прерваться в середине tick (не критично)

---

## 10. ФИНАЛЬНАЯ ДИАГРАММА MVP

```
┌─────────────────────────────────────────────────────────┐
│                  ORCHESTRATOR LOOP                      │
│                    (TZ-007)                             │
└─────────────────────────────────────────────────────────┘
              │
              │ Каждые 5 минут
              ▼
┌─────────────────────────────────────────────────────────┐
│  1. build_full_snapshot() → regime_classifier           │
│     (TZ-002)                                            │
└─────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│  2. check_all_killswitch_triggers()                     │
│     (TZ-005)                                            │
└─────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│  3. dispatch_orchestrator_decisions()                   │
│     action_matrix + command_dispatcher                  │
│     (TZ-004)                                            │
└─────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│  4. calibration_log.log_action_change()                 │
│     (TZ-006)                                            │
└─────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│  5. send_telegram_alert() [если изменения]              │
│     (TZ-007)                                            │
└─────────────────────────────────────────────────────────┘
              │
              ▼ (раз в день)
┌─────────────────────────────────────────────────────────┐
│  6. send_daily_report()                                 │
│     (TZ-007)                                            │
└─────────────────────────────────────────────────────────┘
```

---

**Конец документа.**

**После TZ-007 Grid Orchestrator MVP готов! 🎉**
