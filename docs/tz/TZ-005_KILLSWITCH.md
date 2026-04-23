# TZ-005: KILLSWITCH — Защита маржи

**Версия:** 1.0  
**Дата:** 2026-04-18  
**Статус:** Ready for Implementation  
**Приоритет:** P1 (критическая функциональность)

---

## КОНТЕКСТ

Grid Orchestrator — Telegram-бот для управления сеточными ботами на GinArea+Bitmex.

**Что уже сделано:**
- TZ-001: Чистка legacy кода
- TZ-002: `regime_classifier.py` (метки режима рынка + модификаторы)
- TZ-002B: Русификация i18n + Unicode визуализация
- TZ-003: `portfolio_state.py` + команды `/portfolio /regime /category /bot`
- TZ-004: `action_matrix.py` + `command_dispatcher.py` + команды `/pause /resume /bot_add /bot_remove /blackout /apply`

**Baseline бэктеста (НЕЛЬЗЯ ЛОМАТЬ):**
- Trades: 20
- Winrate: 75.0%
- PnL: +10.5709%

**Текущий статус тестов:** 190 passed

---

## ЗАДАЧА TZ-005

Реализовать **killswitch** — модуль автоматической защиты портфолио от критических потерь.

Killswitch срабатывает при:
1. **Просадка маржи** (баланс портфолио упал ниже порога)
2. **Каскад ликвидаций** (режим CASCADE + модификатор LIQUIDATION_CASCADE)
3. **Аномальное движение** (flash crash/pump ±5% за минуту) — опционально
4. **Ручная активация** оператором (`/killswitch on`)

При срабатывании:
- Останавливает **все боты** (переводит категории в action `KILLSWITCH`)
- Логирует событие с timestamp + причиной + значением триггера
- Блокирует автоматическое возобновление (требуется `/killswitch off`)

---

## DESIGN-ДОКУМЕНТ

**См. полный дизайн:** `docs/KILLSWITCH_DESIGN_v0.1.md`

Ключевые моменты:
- State персистится в `state/killswitch_state.json`
- Класс `KillswitchStore` (singleton pattern как в `PortfolioStore`)
- Функция `trigger_killswitch(reason, reason_value)` — централизованная точка активации
- Триггеры в отдельном модуле `killswitch_triggers.py`
- Новый action `KILLSWITCH` добавляется в `portfolio_state.py`

---

## ЧТО НУЖНО РЕАЛИЗОВАТЬ

### 1. Core модули

#### 1.1 `core/orchestrator/killswitch.py`

**Создать класс `KillswitchStore`:**

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import threading

from utils.safe_io import atomic_write_json, safe_read_json


@dataclass
class KillswitchEvent:
    triggered_at: datetime
    reason: str
    reason_value: Any
    disabled_at: datetime | None = None
    disabled_by: str | None = None


class KillswitchStore:
    """
    Singleton для управления состоянием killswitch.
    Персистентность в state/killswitch_state.json
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, state_path: Path):
        self._state_path = state_path
        self._state = self._load()

    @classmethod
    def instance(cls, state_path: Path | None = None) -> "KillswitchStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    path = state_path or Path("state/killswitch_state.json")
                    cls._instance = cls(path)
        return cls._instance

    def _load(self) -> dict:
        """Загрузка state из JSON, или создание дефолтного."""
        data = safe_read_json(self._state_path)
        if not data:
            return {
                "version": 1,
                "active": False,
                "triggered_at": None,
                "reason": None,
                "reason_value": None,
                "manually_disabled_at": None,
                "history": [],
            }
        return data

    def is_active(self) -> bool:
        """Активен ли killswitch сейчас?"""
        return self._state.get("active", False)

    def trigger(self, reason: str, reason_value: Any) -> None:
        """
        Активирует killswitch.
        reason: "MARGIN_DRAWDOWN" | "LIQUIDATION_CASCADE" | "FLASH_MOVE" | "MANUAL"
        reason_value: числовое значение или текст (зависит от reason)
        """
        now = datetime.now(timezone.utc)
        self._state["active"] = True
        self._state["triggered_at"] = now.isoformat()
        self._state["reason"] = reason
        self._state["reason_value"] = reason_value
        self._save()

    def disable(self, operator: str = "operator") -> None:
        """
        Отключает killswitch.
        Добавляет текущее событие в историю.
        """
        if not self.is_active():
            return
        now = datetime.now(timezone.utc)
        event = {
            "triggered_at": self._state["triggered_at"],
            "reason": self._state["reason"],
            "reason_value": self._state["reason_value"],
            "disabled_at": now.isoformat(),
            "disabled_by": operator,
        }
        self._state["history"].append(event)
        self._state["active"] = False
        self._state["triggered_at"] = None
        self._state["reason"] = None
        self._state["reason_value"] = None
        self._state["manually_disabled_at"] = now.isoformat()
        self._save()

    def get_current_event(self) -> dict | None:
        """Возвращает текущее событие killswitch, если активен."""
        if not self.is_active():
            return None
        return {
            "triggered_at": self._state["triggered_at"],
            "reason": self._state["reason"],
            "reason_value": self._state["reason_value"],
        }

    def get_history(self, limit: int = 5) -> list[dict]:
        """Возвращает последние N событий из истории."""
        history = self._state.get("history", [])
        return history[-limit:]

    def _save(self) -> None:
        """Атомарное сохранение state в JSON."""
        atomic_write_json(self._state_path, self._state)
```

**Также добавить функцию `trigger_killswitch()`:**

```python
import logging

logger = logging.getLogger(__name__)


def trigger_killswitch(reason: str, reason_value: Any) -> None:
    """
    Централизованная активация killswitch:
    1. Записывает событие в KillswitchStore
    2. Останавливает все боты (переводит категории в KILLSWITCH)
    3. Логирует критический алерт
    """
    from core.orchestrator.portfolio_state import PortfolioStore
    from renderers.grid_renderer import render_killswitch_alert

    store = KillswitchStore.instance()
    if store.is_active():
        # Уже активен, не дублируем
        logger.warning(f"[KILLSWITCH] Попытка повторной активации: {reason}")
        return

    store.trigger(reason, reason_value)

    # Останавливаем все категории
    portfolio = PortfolioStore.instance()
    snapshot = portfolio.get_snapshot()
    for cat_key in snapshot.categories.keys():
        portfolio.set_action(cat_key, "KILLSWITCH", reason=f"Killswitch: {reason}")

    # Логируем алерт
    alert_text = render_killswitch_alert(reason, reason_value)
    logger.critical(f"[KILLSWITCH TRIGGERED]\n{alert_text}")
```

---

#### 1.2 `core/orchestrator/killswitch_triggers.py`

**Создать функции проверки триггеров:**

```python
from typing import Any
import logging

from core.orchestrator.killswitch import trigger_killswitch
from core.orchestrator.portfolio_state import PortfolioStore
from core.pipeline import build_full_snapshot

logger = logging.getLogger(__name__)


def check_margin_drawdown_trigger(
    initial_balance_usd: float,
    threshold_pct: float,
) -> None:
    """
    Проверяет просадку маржи.
    Если текущий баланс упал ниже порога — активирует killswitch.
    """
    portfolio = PortfolioStore.instance()
    snapshot = portfolio.get_snapshot()

    total_balance = sum(
        bot.get("balance_usd", 0.0) for bot in snapshot.bots.values()
    )

    if total_balance == 0:
        logger.warning("[KILLSWITCH] Баланс портфолио = 0, триггер пропущен.")
        return

    drawdown_pct = ((initial_balance_usd - total_balance) / initial_balance_usd) * 100

    if drawdown_pct >= threshold_pct:
        logger.warning(
            f"[KILLSWITCH] Просадка маржи: {drawdown_pct:.2f}% >= {threshold_pct}%"
        )
        trigger_killswitch(reason="MARGIN_DRAWDOWN", reason_value=round(drawdown_pct, 2))


def check_cascade_trigger() -> None:
    """
    Проверяет каскад ликвидаций.
    Если режим CASCADE_DOWN/CASCADE_UP + модификатор LIQUIDATION_CASCADE — активирует killswitch.
    """
    try:
        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime = snapshot.get("regime", {})
        primary = regime.get("primary", "RANGE")
        modifiers = regime.get("modifiers", [])

        if primary in ["CASCADE_DOWN", "CASCADE_UP"] and "LIQUIDATION_CASCADE" in modifiers:
            logger.warning(
                f"[KILLSWITCH] Каскад ликвидаций: {primary} + LIQUIDATION_CASCADE"
            )
            trigger_killswitch(reason="LIQUIDATION_CASCADE", reason_value=primary)
    except Exception as e:
        logger.error(f"[KILLSWITCH] Ошибка проверки каскада: {e}")


def check_flash_move_trigger(
    price_now: float,
    price_1m_ago: float,
    threshold_pct: float,
) -> None:
    """
    Проверяет аномальное движение цены (flash crash/pump).
    Если изменение >= threshold_pct за 1 минуту — активирует killswitch.
    
    NOTE: Требует хранения price_1m_ago в отдельном state (можно добавить в TZ-007).
    Пока это заглушка для будущего расширения.
    """
    if price_1m_ago == 0:
        return

    change_pct = abs((price_now - price_1m_ago) / price_1m_ago) * 100

    if change_pct >= threshold_pct:
        logger.warning(
            f"[KILLSWITCH] Аномальное движение: ±{change_pct:.2f}% >= {threshold_pct}%"
        )
        trigger_killswitch(reason="FLASH_MOVE", reason_value=round(change_pct, 2))


def check_all_killswitch_triggers(config: dict[str, Any]) -> None:
    """
    Проверяет все автоматические триггеры killswitch.
    Вызывается из orchestrator_loop (TZ-007).
    """
    # Триггер 1: Просадка маржи
    check_margin_drawdown_trigger(
        initial_balance_usd=config.get("KILLSWITCH_INITIAL_BALANCE_USD", 10_000),
        threshold_pct=config.get("KILLSWITCH_DRAWDOWN_THRESHOLD_PCT", 15.0),
    )

    # Триггер 2: Каскад ликвидаций
    check_cascade_trigger()

    # Триггер 3: Flash move (пока не реализован, нужен price cache)
    # Можно добавить в TZ-007
```

---

### 2. Интеграция с portfolio_state.py

**В `core/orchestrator/portfolio_state.py` добавить новый action `KILLSWITCH`:**

```python
# В начале файла, где определены константы:
VALID_ACTIONS = ["RUN", "PAUSE", "ARM", "STOP", "REDUCE", "KILLSWITCH"]
```

**В методе `set_action()` добавить проверку блокировки killswitch:**

```python
def set_action(self, category_key: str, action: str, reason: str = "") -> None:
    """
    Устанавливает action для категории.
    ВАЖНО: Если killswitch активен и action != "KILLSWITCH",
    операция блокируется (требуется сначала /killswitch off).
    """
    from core.orchestrator.killswitch import KillswitchStore

    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action}")

    # Проверка блокировки killswitch
    ks = KillswitchStore.instance()
    if ks.is_active() and action != "KILLSWITCH":
        logger.warning(
            f"[PORTFOLIO] Попытка изменить action на {action} заблокирована: killswitch активен."
        )
        return

    # Остальная логика без изменений...
    with self._lock:
        if category_key not in self._state["categories"]:
            logger.error(f"[PORTFOLIO] Категория {category_key} не найдена.")
            return

        self._state["categories"][category_key]["orchestrator_action"] = action
        self._state["categories"][category_key]["base_reason"] = reason
        self._state["categories"][category_key]["last_command_at"] = _dt_to_str(_utc_now())
        self._save()

        logger.info(f"[PORTFOLIO] {category_key} → {action} (причина: {reason})")
```

---

### 3. Telegram команды

**В `handlers/command_actions.py` добавить команды:**

#### 3.1 `/killswitch`

```python
def killswitch(self) -> BotResponsePayload:
    """
    Управление killswitch:
    /killswitch on [причина]  — активировать вручную
    /killswitch off           — деактивировать
    /killswitch status        — показать статус
    """
    from core.orchestrator.killswitch import KillswitchStore, trigger_killswitch

    args = self.ctx.args  # список слов после команды
    store = KillswitchStore.instance()

    if not args:
        # По умолчанию показываем статус
        return self.killswitch_status()

    cmd = args[0].lower()

    if cmd == "on":
        # Активация вручную
        reason_text = " ".join(args[1:]) if len(args) > 1 else "Оператор"
        trigger_killswitch(reason="MANUAL", reason_value=reason_text)

        lines = [
            "🚨 KILLSWITCH АКТИВИРОВАН",
            "",
            "Причина: MANUAL",
            f"Значение: {reason_text}",
            "",
            "Все боты остановлены.",
        ]
        return self.ctx.plain("\n".join(lines))

    elif cmd == "off":
        # Деактивация
        if not store.is_active():
            return self.ctx.plain("✅ KILLSWITCH уже отключён.")

        store.disable(operator="operator")

        lines = [
            "✅ KILLSWITCH ОТКЛЮЧЁН",
            "",
            "Режим снят оператором.",
            "Боты можно возобновить через /apply.",
        ]
        return self.ctx.plain("\n".join(lines))

    elif cmd == "status":
        return self.killswitch_status()

    else:
        return self.ctx.plain(
            "❌ Неизвестная команда.\n"
            "Использование:\n"
            "  /killswitch on [причина]\n"
            "  /killswitch off\n"
            "  /killswitch status"
        )


def killswitch_status(self) -> BotResponsePayload:
    """
    Показывает статус killswitch + последние события из истории.
    """
    from core.orchestrator.killswitch import KillswitchStore

    store = KillswitchStore.instance()
    lines = ["🔐 СТАТУС KILLSWITCH", ""]

    if store.is_active():
        event = store.get_current_event()
        lines.append("Текущее состояние: ⚠️ АКТИВЕН")
        lines.append("")
        lines.append(f"Сработал: {event['triggered_at']}")
        lines.append(f"Причина: {event['reason']}")
        lines.append(f"Значение: {event['reason_value']}")
        lines.append("")
        lines.append("Для отключения: /killswitch off")
    else:
        lines.append("Текущее состояние: ✅ Неактивен")

    history = store.get_history(limit=5)
    if history:
        lines.append("")
        lines.append("История срабатываний (последние 5):")
        for idx, ev in enumerate(history, start=1):
            lines.append(f"{idx}️⃣ {ev['triggered_at']}")
            lines.append(f"   Причина: {ev['reason']} ({ev['reason_value']})")
            if ev.get("disabled_at"):
                lines.append(f"   Снят: {ev['disabled_at']} ({ev['disabled_by']})")

    return self.ctx.plain("\n".join(lines))
```

**Зарегистрировать команды в `handlers/command_handler.py`:**

```python
# В register_commands():
register_action("killswitch", lambda ctx: CommandActions(ctx).killswitch())
register_action("killswitch_status", lambda ctx: CommandActions(ctx).killswitch_status())

# Русские алиасы (опционально):
register_action("киллсвитч", lambda ctx: CommandActions(ctx).killswitch())
```

---

### 4. Рендеры

**В `renderers/grid_renderer.py` добавить функцию:**

```python
def render_killswitch_alert(reason: str, reason_value: Any) -> str:
    """
    Рендер критического алерта для killswitch.
    Возвращает текст для Telegram (или лога).
    """
    REASON_LABELS = {
        "MARGIN_DRAWDOWN": "ПРОСАДКА МАРЖИ",
        "LIQUIDATION_CASCADE": "КАСКАД ЛИКВИДАЦИЙ",
        "FLASH_MOVE": "АНОМАЛЬНОЕ ДВИЖЕНИЕ",
        "MANUAL": "РУЧНАЯ ОСТАНОВКА",
    }

    label = REASON_LABELS.get(reason, reason)
    lines = [
        "🚨 KILLSWITCH АКТИВИРОВАН",
        "",
        f"Причина: {label}",
    ]

    if reason == "MARGIN_DRAWDOWN":
        lines.append(f"Просадка: -{reason_value:.2f}%")
    elif reason == "LIQUIDATION_CASCADE":
        lines.append(f"Режим: {reason_value}")
    elif reason == "FLASH_MOVE":
        lines.append(f"Движение: ±{reason_value:.2f}% за 1 мин")
    elif reason == "MANUAL":
        lines.append(f"Оператор: {reason_value}")

    lines.append("")
    lines.append("Все боты остановлены.")

    return "\n".join(lines)
```

---

### 5. Конфигурация

**В `config.py` добавить параметры:**

```python
# ================== KILLSWITCH SETTINGS ==================

# Начальный баланс портфолио (USD) для расчёта просадки
KILLSWITCH_INITIAL_BALANCE_USD = 10_000

# Порог просадки для активации killswitch (%)
KILLSWITCH_DRAWDOWN_THRESHOLD_PCT = 15.0

# Порог для flash move (аномальное движение цены за 1 минуту, %)
KILLSWITCH_FLASH_THRESHOLD_PCT = 5.0

# Окно времени для flash move (секунды)
KILLSWITCH_FLASH_WINDOW_SEC = 60
```

---

### 6. Тесты

#### 6.1 `tests/test_killswitch.py`

```python
import pytest
from pathlib import Path

from core.orchestrator.killswitch import KillswitchStore, trigger_killswitch


@pytest.fixture
def temp_killswitch(tmp_path):
    """Временный KillswitchStore для тестов."""
    store_path = tmp_path / "test_killswitch.json"
    store = KillswitchStore(store_path)
    yield store
    # Cleanup
    if store_path.exists():
        store_path.unlink()


def test_killswitch_default_state(temp_killswitch):
    """Проверка дефолтного состояния."""
    assert not temp_killswitch.is_active()
    assert temp_killswitch.get_current_event() is None
    assert temp_killswitch.get_history() == []


def test_killswitch_trigger_sets_active(temp_killswitch):
    """Проверка активации killswitch."""
    temp_killswitch.trigger("MARGIN_DRAWDOWN", 18.5)

    assert temp_killswitch.is_active()
    event = temp_killswitch.get_current_event()
    assert event is not None
    assert event["reason"] == "MARGIN_DRAWDOWN"
    assert event["reason_value"] == 18.5


def test_killswitch_disable_adds_to_history(temp_killswitch):
    """Проверка деактивации и добавления в историю."""
    temp_killswitch.trigger("MANUAL", "operator test")
    temp_killswitch.disable("operator")

    assert not temp_killswitch.is_active()
    history = temp_killswitch.get_history()
    assert len(history) == 1
    assert history[0]["reason"] == "MANUAL"
    assert history[0]["disabled_by"] == "operator"


def test_killswitch_persistence(tmp_path):
    """Проверка сохранения state между инстансами."""
    store_path = tmp_path / "test_killswitch_persist.json"

    store1 = KillswitchStore(store_path)
    store1.trigger("LIQUIDATION_CASCADE", "CASCADE_DOWN")
    assert store1.is_active()

    # Новый инстанс должен загрузить state из файла
    store2 = KillswitchStore(store_path)
    assert store2.is_active()
    event = store2.get_current_event()
    assert event["reason"] == "LIQUIDATION_CASCADE"


def test_trigger_killswitch_stops_portfolio_actions(temp_killswitch):
    """
    Проверка что trigger_killswitch() переводит все категории в KILLSWITCH.
    NOTE: Требует доступа к PortfolioStore — может быть integration test.
    """
    # TODO: Реализовать через моки или интеграционный тест
    pass
```

---

#### 6.2 `tests/test_killswitch_triggers.py`

```python
import pytest
from unittest.mock import patch, MagicMock

from core.orchestrator.killswitch_triggers import (
    check_margin_drawdown_trigger,
    check_cascade_trigger,
)


def test_margin_drawdown_trigger_activates():
    """Проверка срабатывания триггера просадки маржи."""
    with patch("core.orchestrator.killswitch_triggers.PortfolioStore") as mock_portfolio, \
         patch("core.orchestrator.killswitch_triggers.trigger_killswitch") as mock_trigger:

        # Mock портфолио с балансом 8500 (просадка 15% от 10000)
        mock_snapshot = MagicMock()
        mock_snapshot.bots = {
            "bot1": {"balance_usd": 4000},
            "bot2": {"balance_usd": 4500},
        }
        mock_portfolio.instance().get_snapshot.return_value = mock_snapshot

        check_margin_drawdown_trigger(initial_balance_usd=10_000, threshold_pct=15.0)

        # Должен сработать, т.к. 8500 / 10000 = -15%
        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["reason"] == "MARGIN_DRAWDOWN"
        assert call_args["reason_value"] == 15.0


def test_cascade_trigger_activates():
    """Проверка срабатывания триггера каскада."""
    with patch("core.orchestrator.killswitch_triggers.build_full_snapshot") as mock_snapshot, \
         patch("core.orchestrator.killswitch_triggers.trigger_killswitch") as mock_trigger:

        mock_snapshot.return_value = {
            "regime": {
                "primary": "CASCADE_DOWN",
                "modifiers": ["LIQUIDATION_CASCADE", "VOLATILITY_SPIKE"],
            }
        }

        check_cascade_trigger()

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[1]
        assert call_args["reason"] == "LIQUIDATION_CASCADE"
        assert call_args["reason_value"] == "CASCADE_DOWN"
```

---

### 7. Документация

**Создать файл `docs/KILLSWITCH_DESIGN_v0.1.md`** — уже создан выше.

**Обновить `PROJECT_MANIFEST.md`:**

```markdown
## TZ-005: Killswitch (Protection Layer)
- Status: ✅ Delivered
- Files:
  - core/orchestrator/killswitch.py
  - core/orchestrator/killswitch_triggers.py
  - handlers/command_actions.py (команды /killswitch, /killswitch_status)
  - renderers/grid_renderer.py (render_killswitch_alert)
  - config.py (KILLSWITCH_* параметры)
  - tests/test_killswitch.py
  - tests/test_killswitch_triggers.py
```

---

## КРИТЕРИИ ПРИЁМКИ

### Обязательные (Must Have):
1. ✅ **Baseline бэктеста не изменён:** 20 / 75% / +10.5709%
2. ✅ **Все тесты проходят:** 190+ passed (включая новые для killswitch)
3. ✅ **KillswitchStore работает:**
   - `trigger()` активирует режим
   - `disable()` отключает и сохраняет в историю
   - Персистентность в `state/killswitch_state.json`
4. ✅ **Команды Telegram:**
   - `/killswitch on [причина]` — активирует вручную
   - `/killswitch off` — отключает
   - `/killswitch status` — показывает статус + историю
5. ✅ **Интеграция с portfolio_state:**
   - Новый action `KILLSWITCH`
   - Блокировка изменения action пока killswitch активен
6. ✅ **Триггеры:**
   - `check_margin_drawdown_trigger()` — работает
   - `check_cascade_trigger()` — работает
7. ✅ **Рендер алертов:**
   - `render_killswitch_alert()` — корректный Unicode + русский

### Опциональные (Nice to Have):
- Flash move trigger (можно отложить на TZ-007)
- Реальная отправка Telegram алертов (будет в TZ-007)

---

## OUT OF SCOPE (TZ-007)

- Автоматическая проверка триггеров в loop (будет в `orchestrator_loop.py`)
- Реальная отправка алертов в Telegram (пока только `logger.critical`)
- Flash move trigger с price cache (требует хранения истории цен)

---

## ТЕХНИЧЕСКИЕ ЗАМЕТКИ

### Unix-style пути
Все пути в коде: `Path("state/killswitch_state.json")`, а НЕ `Path("state\\killswitch_state.json")`

### Singleton pattern
`KillswitchStore.instance()` по аналогии с `PortfolioStore.instance()`

### Thread-safety
Используется `threading.Lock()` для безопасной работы из разных потоков (как в `PortfolioStore`)

### Логирование
Все критические события: `logger.critical()`, предупреждения: `logger.warning()`

---

## DELIVERY

**Формат поставки:** Единый ZIP-архив с полным кодом проекта.

**Структура:**
```
TZ-005_delivery.zip
├── core/orchestrator/
│   ├── killswitch.py           (NEW)
│   ├── killswitch_triggers.py  (NEW)
│   └── portfolio_state.py      (MODIFIED)
├── handlers/
│   └── command_actions.py      (MODIFIED)
├── renderers/
│   └── grid_renderer.py        (MODIFIED)
├── config.py                   (MODIFIED)
├── state/
│   └── killswitch_state.json   (NEW, пустой default)
├── tests/
│   ├── test_killswitch.py      (NEW)
│   └── test_killswitch_triggers.py (NEW)
├── docs/
│   └── KILLSWITCH_DESIGN_v0.1.md (NEW)
├── TZ-005_report.md            (отчёт о выполнении)
└── (все остальные файлы без изменений)
```

**Отчёт TZ-005_report.md должен содержать:**
- Что сделано
- Результаты тестов (сколько passed)
- Baseline бэктеста (20/75%/+10.57%)
- Список изменённых файлов

---

## ВОПРОСЫ И УТОЧНЕНИЯ

Если что-то непонятно — спрашивай ПЕРЕД началом реализации, а не после.

Удачи! 🚀
