# KILLSWITCH DESIGN v0.1

**Статус:** Draft  
**Дата:** 2026-04-18  
**Автор:** Claude (архитектор)  
**Цель:** Защита маржи через автоматическую остановку ботов при критических событиях

---

## 1. КОНЦЕПЦИЯ

Killswitch — модуль защиты от критических потерь. Отслеживает:
- Просадку маржи (общий баланс портфолио)
- Каскадные ликвидации на рынке
- Аномальные движения цены (flash crash / flash pump)
- Ручное отключение оператором

При срабатывании триггера:
1. **Останавливает все боты** (переводит в `KILLSWITCH` режим)
2. **Отправляет критический алерт** в Telegram
3. **Логирует событие** с timestamp + причиной
4. **Блокирует автоматическое возобновление** до ручного снятия режима

---

## 2. ТРИГГЕРЫ KILLSWITCH

### 2.1 Margin Drawdown Trigger
**Условие:** Общий баланс портфолио упал ниже критического порога.

```python
portfolio_balance_usd = sum(bot.balance_usd for bot in active_bots)
initial_balance_usd = 10_000  # из конфига
current_drawdown_pct = ((initial_balance_usd - portfolio_balance_usd) / initial_balance_usd) * 100

if current_drawdown_pct >= KILLSWITCH_DRAWDOWN_THRESHOLD_PCT:
    trigger_killswitch(reason="MARGIN_DRAWDOWN", value=current_drawdown_pct)
```

**Параметры конфига:**
- `KILLSWITCH_DRAWDOWN_THRESHOLD_PCT` = 15.0 (default)
- `KILLSWITCH_INITIAL_BALANCE_USD` = 10000 (default)

**Алерт:**
```
🚨 KILLSWITCH: ПРОСАДКА МАРЖИ
Текущий баланс: $8,200
Просадка: -18.0%
Порог: -15.0%
Все боты остановлены.
```

---

### 2.2 Cascade Liquidation Trigger
**Условие:** Режим `CASCADE_DOWN` или `CASCADE_UP` + модификатор `LIQUIDATION_CASCADE`.

```python
regime = regime_classifier.get_current_regime()
modifiers = regime.modifiers

if regime.primary in ["CASCADE_DOWN", "CASCADE_UP"] and "LIQUIDATION_CASCADE" in modifiers:
    trigger_killswitch(reason="LIQUIDATION_CASCADE", value=regime.primary)
```

**Алерт:**
```
🚨 KILLSWITCH: КАСКАД ЛИКВИДАЦИЙ
Режим: CASCADE_DOWN
Модификатор: LIQUIDATION_CASCADE
Все боты остановлены для защиты.
```

---

### 2.3 Flash Crash / Flash Pump Trigger
**Условие:** Аномальное движение цены за короткий период (например, ±5% за 1 минуту).

```python
price_change_1m_pct = abs((price_now - price_1m_ago) / price_1m_ago) * 100

if price_change_1m_pct >= KILLSWITCH_FLASH_THRESHOLD_PCT:
    trigger_killswitch(reason="FLASH_MOVE", value=price_change_1m_pct)
```

**Параметры конфига:**
- `KILLSWITCH_FLASH_THRESHOLD_PCT` = 5.0 (default)
- `KILLSWITCH_FLASH_WINDOW_SEC` = 60 (default)

**Алерт:**
```
🚨 KILLSWITCH: АНОМАЛЬНОЕ ДВИЖЕНИЕ
Цена: $95,200 → $90,000 (-5.46%) за 1 мин
Порог: ±5.0%
Все боты остановлены.
```

---

### 2.4 Manual Killswitch
**Условие:** Оператор вызывает команду `/killswitch on`.

```python
# Команда: /killswitch on [причина]
trigger_killswitch(reason="MANUAL", value=user_reason or "Оператор")
```

**Алерт:**
```
🚨 KILLSWITCH: РУЧНАЯ ОСТАНОВКА
Причина: Оператор — подозрение на манипуляцию рынка
Все боты остановлены.
```

---

## 3. АРХИТЕКТУРА

### 3.1 Файловая структура

```
core/orchestrator/
  killswitch.py          # Основная логика killswitch
  killswitch_triggers.py # Проверка условий триггеров

handlers/
  command_actions.py     # Команды /killswitch /killswitch_status

state/
  killswitch_state.json  # Персистентное состояние

tests/
  test_killswitch.py
  test_killswitch_triggers.py
```

---

### 3.2 Модель данных (killswitch_state.json)

```json
{
  "version": 1,
  "active": false,
  "triggered_at": null,
  "reason": null,
  "reason_value": null,
  "manually_disabled_at": null,
  "history": [
    {
      "triggered_at": "2026-04-18T12:34:56Z",
      "reason": "MARGIN_DRAWDOWN",
      "reason_value": 18.5,
      "disabled_at": "2026-04-18T13:15:00Z",
      "disabled_by": "operator"
    }
  ]
}
```

**Поля:**
- `active` (bool) — killswitch сейчас активен?
- `triggered_at` (ISO datetime | null) — когда сработал
- `reason` (str | null) — причина: `MARGIN_DRAWDOWN`, `LIQUIDATION_CASCADE`, `FLASH_MOVE`, `MANUAL`
- `reason_value` (float | str | null) — значение триггера (процент просадки, режим и т.д.)
- `manually_disabled_at` (ISO datetime | null) — когда оператор снял режим
- `history` (list) — лог всех срабатываний

---

### 3.3 Класс KillswitchStore

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.safe_io import atomic_write_json, safe_read_json


@dataclass
class KillswitchEvent:
    triggered_at: datetime
    reason: str
    reason_value: Any
    disabled_at: datetime | None = None
    disabled_by: str | None = None


class KillswitchStore:
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
        return self._state.get("active", False)

    def trigger(self, reason: str, reason_value: Any) -> None:
        now = datetime.now(timezone.utc)
        self._state["active"] = True
        self._state["triggered_at"] = now.isoformat()
        self._state["reason"] = reason
        self._state["reason_value"] = reason_value
        self._save()

    def disable(self, operator: str = "operator") -> None:
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
        if not self.is_active():
            return None
        return {
            "triggered_at": self._state["triggered_at"],
            "reason": self._state["reason"],
            "reason_value": self._state["reason_value"],
        }

    def get_history(self) -> list[dict]:
        return self._state.get("history", [])

    def _save(self) -> None:
        atomic_write_json(self._state_path, self._state)
```

---

### 3.4 Функция trigger_killswitch()

```python
def trigger_killswitch(reason: str, reason_value: Any) -> None:
    """
    Активирует killswitch:
    1. Записывает событие в state
    2. Останавливает все боты (переводит в KILLSWITCH action)
    3. Отправляет критический алерт в Telegram
    """
    from core.orchestrator.killswitch import KillswitchStore
    from core.orchestrator.portfolio_state import PortfolioStore
    from renderers.grid_renderer import render_killswitch_alert

    store = KillswitchStore.instance()
    if store.is_active():
        # Уже активен, не дублируем
        return

    store.trigger(reason, reason_value)

    # Останавливаем все категории
    portfolio = PortfolioStore.instance()
    for cat_key in portfolio.get_snapshot().categories.keys():
        portfolio.set_action(cat_key, "KILLSWITCH", reason=f"Killswitch: {reason}")

    # Отправка алерта (заглушка — реальная отправка в TZ-007)
    alert_text = render_killswitch_alert(reason, reason_value)
    logger.critical(f"[KILLSWITCH TRIGGERED] {alert_text}")
```

---

### 3.5 Проверка триггеров (killswitch_triggers.py)

```python
from typing import Any

from core.orchestrator.killswitch import trigger_killswitch
from core.orchestrator.portfolio_state import PortfolioStore
from core.pipeline import build_full_snapshot


def check_margin_drawdown_trigger(
    initial_balance_usd: float,
    threshold_pct: float,
) -> None:
    portfolio = PortfolioStore.instance()
    snapshot = portfolio.get_snapshot()

    total_balance = sum(
        bot.get("balance_usd", 0.0) for bot in snapshot.bots.values()
    )

    if total_balance == 0:
        return

    drawdown_pct = ((initial_balance_usd - total_balance) / initial_balance_usd) * 100

    if drawdown_pct >= threshold_pct:
        trigger_killswitch(reason="MARGIN_DRAWDOWN", reason_value=drawdown_pct)


def check_cascade_trigger() -> None:
    snapshot = build_full_snapshot(symbol="BTCUSDT")
    regime = snapshot.get("regime", {})
    primary = regime.get("primary", "RANGE")
    modifiers = regime.get("modifiers", [])

    if primary in ["CASCADE_DOWN", "CASCADE_UP"] and "LIQUIDATION_CASCADE" in modifiers:
        trigger_killswitch(reason="LIQUIDATION_CASCADE", reason_value=primary)


def check_flash_move_trigger(
    price_now: float,
    price_1m_ago: float,
    threshold_pct: float,
) -> None:
    if price_1m_ago == 0:
        return

    change_pct = abs((price_now - price_1m_ago) / price_1m_ago) * 100

    if change_pct >= threshold_pct:
        trigger_killswitch(reason="FLASH_MOVE", reason_value=change_pct)


def check_all_killswitch_triggers(config: dict[str, Any]) -> None:
    """
    Проверяет все автоматические триггеры killswitch.
    Вызывается из orchestrator_loop (TZ-007).
    """
    check_margin_drawdown_trigger(
        initial_balance_usd=config.get("KILLSWITCH_INITIAL_BALANCE_USD", 10_000),
        threshold_pct=config.get("KILLSWITCH_DRAWDOWN_THRESHOLD_PCT", 15.0),
    )

    check_cascade_trigger()

    # Flash move требует хранения price_1m_ago — можно добавить в TZ-007
    # Пока заглушка
```

---

## 4. КОМАНДЫ TELEGRAM

### 4.1 `/killswitch` — Управление режимом

**Синтаксис:**
```
/killswitch on [причина]       # Включить вручную
/killswitch off                # Выключить вручную
/killswitch status             # Показать статус
```

**Примеры:**
```
> /killswitch on подозрение на манипуляцию
🚨 KILLSWITCH АКТИВИРОВАН
Причина: MANUAL
Значение: подозрение на манипуляцию
Все боты остановлены.

> /killswitch off
✅ KILLSWITCH ОТКЛЮЧЁН
Режим снят оператором.
Боты можно возобновить через /apply.

> /killswitch status
⚠️ KILLSWITCH АКТИВЕН
Сработал: 2026-04-18 12:34:56 UTC
Причина: MARGIN_DRAWDOWN
Значение: -18.5%
Для отключения: /killswitch off
```

---

### 4.2 `/killswitch_status` — Статус и история

**Синтаксис:**
```
/killswitch_status
```

**Вывод:**
```
🔐 СТАТУС KILLSWITCH

Текущее состояние: ❌ Неактивен

История срабатываний (последние 5):
1️⃣ 2026-04-18 12:34:56 UTC
   Причина: MARGIN_DRAWDOWN (-18.5%)
   Снят: 2026-04-18 13:15:00 UTC (operator)

2️⃣ 2026-04-15 08:22:10 UTC
   Причина: LIQUIDATION_CASCADE (CASCADE_DOWN)
   Снят: 2026-04-15 08:45:30 UTC (operator)
```

---

## 5. РЕНДЕРЫ (grid_renderer.py)

### 5.1 render_killswitch_alert()

```python
def render_killswitch_alert(reason: str, reason_value: Any) -> str:
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

## 6. КОНФИГУРАЦИЯ (config.py)

```python
# Killswitch thresholds
KILLSWITCH_INITIAL_BALANCE_USD = 10_000  # Начальный баланс портфолио
KILLSWITCH_DRAWDOWN_THRESHOLD_PCT = 15.0  # Порог просадки (%)
KILLSWITCH_FLASH_THRESHOLD_PCT = 5.0      # Порог flash move (%)
KILLSWITCH_FLASH_WINDOW_SEC = 60          # Окно для flash move (сек)
```

---

## 7. ИНТЕГРАЦИЯ С PORTFOLIO_STATE

При активации killswitch все категории переводятся в action `KILLSWITCH`:

```python
# В portfolio_state.py добавить новый action
VALID_ACTIONS = ["RUN", "PAUSE", "ARM", "STOP", "REDUCE", "KILLSWITCH"]

# При killswitch.trigger():
for cat_key in portfolio.get_snapshot().categories.keys():
    portfolio.set_action(cat_key, "KILLSWITCH", reason=f"Killswitch: {reason}")
```

**Правило:** Пока `killswitch.is_active() == True`, команда `/apply` не может изменить action с `KILLSWITCH` на другой. Требуется сначала `/killswitch off`.

---

## 8. ТЕСТЫ

### 8.1 test_killswitch.py

```python
def test_killswitch_trigger_sets_active():
    store = KillswitchStore(Path("test_killswitch.json"))
    assert not store.is_active()
    
    store.trigger("MARGIN_DRAWDOWN", 18.5)
    assert store.is_active()
    assert store.get_current_event()["reason"] == "MARGIN_DRAWDOWN"

def test_killswitch_disable_adds_to_history():
    store = KillswitchStore(Path("test_killswitch.json"))
    store.trigger("MANUAL", "operator")
    store.disable("operator")
    
    assert not store.is_active()
    assert len(store.get_history()) == 1
    assert store.get_history()[0]["reason"] == "MANUAL"

def test_killswitch_blocks_portfolio_actions():
    # Проверка что при active=True нельзя изменить action с KILLSWITCH
    pass
```

### 8.2 test_killswitch_triggers.py

```python
def test_margin_drawdown_trigger():
    # Эмуляция падения баланса ниже порога
    pass

def test_cascade_trigger():
    # Эмуляция режима CASCADE_DOWN + LIQUIDATION_CASCADE
    pass

def test_flash_move_trigger():
    # Эмуляция резкого движения цены
    pass
```

---

## 9. ПЛАН РЕАЛИЗАЦИИ (TZ-005)

### Scope:
1. ✅ Создать `core/orchestrator/killswitch.py` (KillswitchStore)
2. ✅ Создать `core/orchestrator/killswitch_triggers.py` (проверка триггеров)
3. ✅ Добавить команды `/killswitch`, `/killswitch_status` в `handlers/command_actions.py`
4. ✅ Добавить `render_killswitch_alert()` в `renderers/grid_renderer.py`
5. ✅ Добавить конфиг в `config.py`
6. ✅ Интегрировать с `portfolio_state.py` (новый action `KILLSWITCH`)
7. ✅ Добавить тесты: `test_killswitch.py`, `test_killswitch_triggers.py`
8. ✅ Проверить baseline бэктеста (не должен измениться)

### Out of scope (TZ-007):
- Автоматическая проверка триггеров в loop (будет в `orchestrator_loop.py`)
- Реальная отправка Telegram алертов (будет в TZ-007)
- Flash move trigger с хранением price_1m_ago (можно добавить позже)

---

## 10. КРИТЕРИИ ПРИЁМКИ

- ✅ 190+ тестов проходят (включая новые для killswitch)
- ✅ Baseline бэктеста 20/75%/+10.57% не изменён
- ✅ Команды `/killswitch on/off/status` работают
- ✅ При `killswitch.is_active() == True` все категории в action `KILLSWITCH`
- ✅ История срабатываний логируется в `killswitch_state.json`
- ✅ Рендер алертов корректный (unicode, русский язык)

---

## 11. РИСКИ

**Низкие:**
- Ложные срабатывания (порог 15% достаточно консервативен)
- Конфликт с ручными командами (решается через приоритет killswitch)

**Средние:**
- Flash move trigger может потребовать price cache (отложено на TZ-007)

---

**Конец документа.**
