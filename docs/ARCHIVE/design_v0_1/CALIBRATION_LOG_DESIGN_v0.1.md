# CALIBRATION LOG DESIGN v0.1

**Статус:** Draft  
**Дата:** 2026-04-18  
**Автор:** Claude (архитектор)  
**Цель:** Логирование решений оркестратора для калибровки и анализа эффективности

---

## 1. КОНЦЕПЦИЯ

Calibration Log — система логирования и анализа решений оркестратора. Отвечает на вопросы:
- Как часто меняются действия по категориям?
- Какие решения были правильными / ошибочными?
- Насколько эффективна текущая настройка action_matrix?
- Какие режимы рынка вызывают больше всего изменений?

**Основные функции:**
1. **Логирование событий** — каждое изменение action категории записывается
2. **Daily Report** — ежедневная сводка по оркестратору (команда `/daily_report`)
3. **Calibration Metrics** — метрики для оценки эффективности настроек

**НЕ путать с trade_journal** — там логи сделок (вход/выход), здесь — логи решений оркестратора.

---

## 2. АРХИТЕКТУРА

### 2.1 Файловая структура

```
core/orchestrator/
  calibration_log.py        # Основной модуль логирования

renderers/
  calibration_renderer.py   # Рендер daily report

handlers/
  command_actions.py        # Команда /daily_report

state/
  calibration/              # Директория с логами
    2026-04-18.jsonl        # Лог за день (JSONL формат)
    2026-04-17.jsonl
    ...

tests/
  test_calibration_log.py
  test_calibration_renderer.py
```

---

### 2.2 Модель данных (calibration event)

Каждое событие калибровки — строка JSON в `.jsonl` файле:

```json
{
  "ts": "2026-04-18T12:34:56.123456Z",
  "event_type": "ACTION_CHANGE",
  "category_key": "btc_short",
  "from_action": "RUN",
  "to_action": "PAUSE",
  "regime": "CASCADE_UP",
  "modifiers": ["VOLATILITY_SPIKE"],
  "reason_ru": "Каскад вверх — шорт на паузу",
  "reason_en": "BASE_CASCADE_UP",
  "affected_bots": ["btc_short_l1"],
  "triggered_by": "AUTO"
}
```

**Поля:**
- `ts` (ISO datetime) — timestamp события с микросекундами
- `event_type` (str) — тип события:
  - `ACTION_CHANGE` — изменение action категории
  - `REGIME_SHIFT` — смена режима рынка
  - `KILLSWITCH_TRIGGER` — срабатывание killswitch
  - `MANUAL_COMMAND` — ручная команда оператора
- `category_key` (str | null) — категория (если применимо)
- `from_action` (str | null) — предыдущий action
- `to_action` (str | null) — новый action
- `regime` (str) — текущий режим рынка
- `modifiers` (list[str]) — активные модификаторы
- `reason_ru` (str) — причина на русском
- `reason_en` (str) — технический код причины
- `affected_bots` (list[str]) — список ID ботов
- `triggered_by` (str) — источник: `AUTO` (оркестратор), `MANUAL` (оператор), `KILLSWITCH`

---

### 2.3 JSONL формат

**Почему JSONL, а не JSON массив?**
- Append-only логирование (добавление строки без перезаписи файла)
- Парсинг по строкам (не нужно загружать весь файл)
- Устойчивость к сбоям (файл всегда валидный)

**Пример файла `2026-04-18.jsonl`:**
```jsonl
{"ts":"2026-04-18T08:00:00.000000Z","event_type":"REGIME_SHIFT","regime":"RANGE","modifiers":[],"reason_ru":"Переход в боковик","triggered_by":"AUTO"}
{"ts":"2026-04-18T08:15:30.123456Z","event_type":"ACTION_CHANGE","category_key":"btc_short","from_action":"RUN","to_action":"RUN","regime":"RANGE","modifiers":[],"reason_ru":"Боковик активирован","reason_en":"BASE_RANGE","affected_bots":["btc_short_l1"],"triggered_by":"AUTO"}
{"ts":"2026-04-18T12:45:12.654321Z","event_type":"ACTION_CHANGE","category_key":"btc_short","from_action":"RUN","to_action":"PAUSE","regime":"CASCADE_UP","modifiers":["VOLATILITY_SPIKE"],"reason_ru":"Каскад вверх — шорт на паузу","reason_en":"BASE_CASCADE_UP","affected_bots":["btc_short_l1"],"triggered_by":"AUTO"}
```

---

## 3. КЛАСС CalibrationLog

```python
from dataclasses import dataclass, asdict
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any
import json

from utils.safe_io import atomic_append_line


@dataclass
class CalibrationEvent:
    ts: datetime
    event_type: str
    regime: str
    modifiers: list[str]
    reason_ru: str
    triggered_by: str
    category_key: str | None = None
    from_action: str | None = None
    to_action: str | None = None
    reason_en: str | None = None
    affected_bots: list[str] | None = None

    def to_json(self) -> str:
        """Сериализация в JSON строку для JSONL."""
        data = asdict(self)
        data["ts"] = self.ts.isoformat()
        data["modifiers"] = list(data["modifiers"] or [])
        data["affected_bots"] = list(data["affected_bots"] or [])
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


class CalibrationLog:
    """
    Singleton для логирования калибровочных событий.
    Логи хранятся в state/calibration/{YYYY-MM-DD}.jsonl
    """
    _instance = None

    def __init__(self, base_path: Path = Path("state/calibration")):
        self._base_path = base_path
        self._base_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def instance(cls, base_path: Path | None = None) -> "CalibrationLog":
        if cls._instance is None:
            cls._instance = cls(base_path or Path("state/calibration"))
        return cls._instance

    def _get_log_path(self, day: date) -> Path:
        """Путь к лог-файлу за конкретный день."""
        return self._base_path / f"{day.isoformat()}.jsonl"

    def log_event(self, event: CalibrationEvent) -> None:
        """Добавляет событие в лог."""
        log_path = self._get_log_path(event.ts.date())
        line = event.to_json()
        atomic_append_line(str(log_path), line)

    def log_action_change(
        self,
        category_key: str,
        from_action: str,
        to_action: str,
        regime: str,
        modifiers: list[str],
        reason_ru: str,
        reason_en: str,
        affected_bots: list[str],
        triggered_by: str = "AUTO",
    ) -> None:
        """Логирует изменение action категории."""
        event = CalibrationEvent(
            ts=datetime.now(timezone.utc),
            event_type="ACTION_CHANGE",
            category_key=category_key,
            from_action=from_action,
            to_action=to_action,
            regime=regime,
            modifiers=modifiers,
            reason_ru=reason_ru,
            reason_en=reason_en,
            affected_bots=affected_bots,
            triggered_by=triggered_by,
        )
        self.log_event(event)

    def log_regime_shift(
        self,
        from_regime: str,
        to_regime: str,
        modifiers: list[str],
        reason_ru: str,
    ) -> None:
        """Логирует смену режима рынка."""
        event = CalibrationEvent(
            ts=datetime.now(timezone.utc),
            event_type="REGIME_SHIFT",
            regime=to_regime,
            modifiers=modifiers,
            reason_ru=f"Переход: {from_regime} → {to_regime}. {reason_ru}",
            triggered_by="AUTO",
        )
        self.log_event(event)

    def log_killswitch_trigger(
        self,
        reason: str,
        reason_value: Any,
        regime: str,
        modifiers: list[str],
    ) -> None:
        """Логирует срабатывание killswitch."""
        event = CalibrationEvent(
            ts=datetime.now(timezone.utc),
            event_type="KILLSWITCH_TRIGGER",
            regime=regime,
            modifiers=modifiers,
            reason_ru=f"Killswitch: {reason} ({reason_value})",
            triggered_by="KILLSWITCH",
        )
        self.log_event(event)

    def log_manual_command(
        self,
        command: str,
        category_key: str | None,
        action: str | None,
        regime: str,
        modifiers: list[str],
    ) -> None:
        """Логирует ручную команду оператора."""
        event = CalibrationEvent(
            ts=datetime.now(timezone.utc),
            event_type="MANUAL_COMMAND",
            category_key=category_key,
            to_action=action,
            regime=regime,
            modifiers=modifiers,
            reason_ru=f"Оператор: {command}",
            triggered_by="MANUAL",
        )
        self.log_event(event)

    def read_events(self, day: date) -> list[dict[str, Any]]:
        """Читает все события за день."""
        log_path = self._get_log_path(day)
        if not log_path.exists():
            return []

        events = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events
```

---

## 4. ИНТЕГРАЦИЯ С ОРКЕСТРАТОРОМ

### 4.1 Логирование в command_dispatcher.py

**Добавить вызовы CalibrationLog в `dispatch_orchestrator_decisions()`:**

```python
def dispatch_orchestrator_decisions(store: PortfolioStore, regime_snapshot: dict[str, Any]) -> DispatchResult:
    from core.orchestrator.killswitch import KillswitchStore
    from core.orchestrator.calibration_log import CalibrationLog

    # ... существующий код ...

    cal_log = CalibrationLog.instance()
    regime = str(regime_snapshot.get("primary") or "RANGE")
    modifiers = list(regime_snapshot.get("modifiers") or [])

    # ... цикл по категориям ...

    for cat_key, cat in portfolio.categories.items():
        # ... логика решения ...
        
        decision = decide_category_action(regime, modifiers, cat)
        new_action = decision.action
        old_action = cat.orchestrator_action

        if new_action != old_action:
            # Логируем изменение
            cal_log.log_action_change(
                category_key=cat_key,
                from_action=old_action,
                to_action=new_action,
                regime=regime,
                modifiers=modifiers,
                reason_ru=decision.reason,
                reason_en=decision.reason_en,
                affected_bots=[bot.id for bot in portfolio.bots.values() if bot.category == cat_key],
                triggered_by="AUTO",
            )

            # ... остальная логика ...
```

---

### 4.2 Логирование в killswitch.py

**Добавить вызов CalibrationLog в `trigger_killswitch()`:**

```python
def trigger_killswitch(reason: str, reason_value: Any) -> str:
    from core.orchestrator.portfolio_state import PortfolioStore
    from core.orchestrator.calibration_log import CalibrationLog
    from core.pipeline import build_full_snapshot
    from renderers.killswitch_renderer import render_killswitch_alert

    # ... существующий код ...

    # Логируем killswitch
    snapshot = build_full_snapshot(symbol="BTCUSDT")
    regime_data = snapshot.get("regime", {})
    regime = str(regime_data.get("primary") or "UNKNOWN")
    modifiers = list(regime_data.get("modifiers") or [])

    cal_log = CalibrationLog.instance()
    cal_log.log_killswitch_trigger(reason, reason_value, regime, modifiers)

    # ... остальная логика ...
```

---

### 4.3 Логирование ручных команд

**Добавить в handlers/command_actions.py для команд `/pause`, `/resume`, `/bot_add` и т.д.:**

```python
def pause(self) -> BotResponsePayload:
    from core.orchestrator.calibration_log import CalibrationLog
    from core.pipeline import build_full_snapshot

    # ... парсинг аргументов ...

    # Логируем ручную команду
    snapshot = build_full_snapshot(symbol="BTCUSDT")
    regime_data = snapshot.get("regime", {})
    regime = str(regime_data.get("primary") or "UNKNOWN")
    modifiers = list(regime_data.get("modifiers") or [])

    cal_log = CalibrationLog.instance()
    cal_log.log_manual_command(
        command=f"/pause {category_key}",
        category_key=category_key,
        action="PAUSE",
        regime=regime,
        modifiers=modifiers,
    )

    # ... остальная логика ...
```

---

## 5. DAILY REPORT

### 5.1 Команда `/daily_report`

**Синтаксис:**
```
/daily_report              # Отчёт за сегодня
/daily_report yesterday    # Отчёт за вчера
/daily_report 2026-04-15   # Отчёт за конкретный день
```

**Пример вывода:**
```
📊 DAILY REPORT: 2026-04-18

АКТИВНОСТЬ ОРКЕСТРАТОРА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Всего событий: 47
  • Изменений action: 12
  • Смен режима: 8
  • Ручных команд: 3
  • Срабатываний killswitch: 0

РЕЖИМЫ РЫНКА (часов)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RANGE          ████████████░░░ 12.5ч (52%)
TREND_UP       ███░░░░░░░░░░░░  3.2ч (13%)
COMPRESSION    ██████░░░░░░░░░  6.1ч (25%)
CASCADE_DOWN   ██░░░░░░░░░░░░░  2.2ч (9%)

КАТЕГОРИИ: ИЗМЕНЕНИЯ ACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
btc_short:
  • RUN → PAUSE (3 раза)
  • PAUSE → RUN (2 раза)
  • Итого: 5 изменений

btc_long:
  • RUN → PAUSE (2 раза)
  • PAUSE → RUN (3 раза)
  • Итого: 5 изменений

btc_long_l2:
  • ARM → PAUSE (1 раз)
  • PAUSE → ARM (1 раз)
  • Итого: 2 изменения

САМЫЕ ЧАСТЫЕ ПРИЧИНЫ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. BASE_RANGE (6 раз)
2. BASE_CASCADE_DOWN (3 раза)
3. BASE_TREND_UP (2 раза)

РУЧНЫЕ КОМАНДЫ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 08:15 - /pause btc_short
• 12:30 - /resume btc_short
• 18:45 - /apply

KILLSWITCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Не срабатывал

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Период: 2026-04-18 00:00 - 23:59 UTC
```

---

### 5.2 Рендер daily report

**Файл `renderers/calibration_renderer.py`:**

```python
from datetime import date, timedelta
from typing import Any

from core.orchestrator.calibration_log import CalibrationLog
from core.orchestrator.visuals import separator, bar_chart


def render_daily_report(day: date) -> str:
    """Рендер ежедневного отчёта по калибровке оркестратора."""
    cal_log = CalibrationLog.instance()
    events = cal_log.read_events(day)

    if not events:
        return f"📊 DAILY REPORT: {day.isoformat()}\n\nНет данных за этот день."

    lines = [
        f"📊 DAILY REPORT: {day.isoformat()}",
        "",
        "АКТИВНОСТЬ ОРКЕСТРАТОРА",
        separator(28),
    ]

    # Подсчёт событий
    action_changes = [e for e in events if e.get("event_type") == "ACTION_CHANGE"]
    regime_shifts = [e for e in events if e.get("event_type") == "REGIME_SHIFT"]
    manual_commands = [e for e in events if e.get("event_type") == "MANUAL_COMMAND"]
    killswitch_triggers = [e for e in events if e.get("event_type") == "KILLSWITCH_TRIGGER"]

    lines.append(f"Всего событий: {len(events)}")
    lines.append(f"  • Изменений action: {len(action_changes)}")
    lines.append(f"  • Смен режима: {len(regime_shifts)}")
    lines.append(f"  • Ручных команд: {len(manual_commands)}")
    lines.append(f"  • Срабатываний killswitch: {len(killswitch_triggers)}")
    lines.append("")

    # Режимы рынка (время в каждом режиме)
    lines.append("РЕЖИМЫ РЫНКА (часов)")
    lines.append(separator(28))
    regime_hours = _calculate_regime_hours(events)
    total_hours = sum(regime_hours.values())
    for regime, hours in sorted(regime_hours.items(), key=lambda x: -x[1]):
        pct = (hours / total_hours) * 100 if total_hours > 0 else 0
        bar = bar_chart(pct, max_width=15)
        lines.append(f"{regime:<14} {bar} {hours:.1f}ч ({pct:.0f}%)")
    lines.append("")

    # Категории: изменения action
    lines.append("КАТЕГОРИИ: ИЗМЕНЕНИЯ ACTION")
    lines.append(separator(28))
    category_changes = _group_action_changes_by_category(action_changes)
    for cat_key, changes in category_changes.items():
        lines.append(f"{cat_key}:")
        transition_counts = {}
        for change in changes:
            transition = f"{change['from_action']} → {change['to_action']}"
            transition_counts[transition] = transition_counts.get(transition, 0) + 1
        for transition, count in sorted(transition_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  • {transition} ({count} {'раз' if count == 1 else 'раза' if count < 5 else 'раз'})")
        lines.append(f"  Итого: {len(changes)} {'изменение' if len(changes) == 1 else 'изменения' if len(changes) < 5 else 'изменений'}")
        lines.append("")

    # Самые частые причины
    lines.append("САМЫЕ ЧАСТЫЕ ПРИЧИНЫ")
    lines.append(separator(28))
    reason_counts = {}
    for e in action_changes:
        reason_en = e.get("reason_en") or "UNKNOWN"
        reason_counts[reason_en] = reason_counts.get(reason_en, 0) + 1
    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:5]
    for idx, (reason, count) in enumerate(top_reasons, start=1):
        lines.append(f"{idx}. {reason} ({count} {'раз' if count == 1 else 'раза' if count < 5 else 'раз'})")
    lines.append("")

    # Ручные команды
    lines.append("РУЧНЫЕ КОМАНДЫ")
    lines.append(separator(28))
    if manual_commands:
        for cmd in manual_commands:
            ts = cmd.get("ts", "")[:16]  # YYYY-MM-DDTHH:MM
            reason = cmd.get("reason_ru", "")
            lines.append(f"• {ts[11:]} - {reason}")
    else:
        lines.append("Нет ручных команд")
    lines.append("")

    # Killswitch
    lines.append("KILLSWITCH")
    lines.append(separator(28))
    if killswitch_triggers:
        for ks in killswitch_triggers:
            ts = ks.get("ts", "")[:16]
            reason = ks.get("reason_ru", "")
            lines.append(f"⚠️ {ts[11:]} - {reason}")
    else:
        lines.append("✅ Не срабатывал")
    lines.append("")

    lines.append(separator(28))
    lines.append(f"Период: {day.isoformat()} 00:00 - 23:59 UTC")

    return "\n".join(lines)


def _calculate_regime_hours(events: list[dict[str, Any]]) -> dict[str, float]:
    """
    Подсчёт времени в каждом режиме.
    Предполагаем, что режим активен до следующей смены режима.
    """
    from datetime import datetime

    regime_shifts = [e for e in events if e.get("event_type") == "REGIME_SHIFT"]
    if not regime_shifts:
        return {}

    # Сортируем по времени
    regime_shifts = sorted(regime_shifts, key=lambda e: e.get("ts", ""))

    regime_hours: dict[str, float] = {}
    for i, shift in enumerate(regime_shifts):
        regime = shift.get("regime", "UNKNOWN")
        start_ts = datetime.fromisoformat(shift["ts"].replace("Z", "+00:00"))

        # До следующей смены или до конца дня
        if i + 1 < len(regime_shifts):
            end_ts = datetime.fromisoformat(regime_shifts[i + 1]["ts"].replace("Z", "+00:00"))
        else:
            # Конец дня
            end_ts = start_ts.replace(hour=23, minute=59, second=59)

        duration_hours = (end_ts - start_ts).total_seconds() / 3600
        regime_hours[regime] = regime_hours.get(regime, 0.0) + duration_hours

    return regime_hours


def _group_action_changes_by_category(action_changes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Группирует изменения action по категориям."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in action_changes:
        cat_key = change.get("category_key")
        if cat_key:
            grouped.setdefault(cat_key, []).append(change)
    return grouped
```

---

## 6. УТИЛИТА: atomic_append_line()

**Добавить в `utils/safe_io.py`:**

```python
def atomic_append_line(file_path: str, line: str) -> None:
    """
    Атомарное добавление строки в конец файла.
    Используется для JSONL логов.
    """
    from pathlib import Path

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Append mode с flush
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
```

---

## 7. КОМАНДА TELEGRAM

**В `handlers/command_actions.py`:**

```python
def daily_report(self) -> BotResponsePayload:
    """
    Ежедневный отчёт по калибровке оркестратора.
    /daily_report              - за сегодня
    /daily_report yesterday    - за вчера
    /daily_report 2026-04-15   - за конкретный день
    """
    from datetime import date, timedelta
    from renderers.calibration_renderer import render_daily_report

    args = self.ctx.args
    if not args:
        day = date.today()
    elif args[0].lower() == "yesterday":
        day = date.today() - timedelta(days=1)
    else:
        try:
            day = date.fromisoformat(args[0])
        except ValueError:
            return self.ctx.plain("❌ Неверный формат даты. Используйте YYYY-MM-DD или 'yesterday'.")

    report_text = render_daily_report(day)
    return self.ctx.plain(report_text)
```

**Зарегистрировать команду в `handlers/command_handler.py`:**

```python
register_action("daily_report", lambda ctx: CommandActions(ctx).daily_report())
register_action("отчёт", lambda ctx: CommandActions(ctx).daily_report())  # Русский алиас
```

---

## 8. ТЕСТЫ

### 8.1 `tests/test_calibration_log.py`

```python
import pytest
from datetime import datetime, date, timezone
from pathlib import Path

from core.orchestrator.calibration_log import CalibrationLog, CalibrationEvent


@pytest.fixture
def temp_calibration_log(tmp_path):
    """Временный CalibrationLog для тестов."""
    log_path = tmp_path / "calibration"
    log = CalibrationLog(log_path)
    yield log
    # Cleanup
    for file in log_path.glob("*.jsonl"):
        file.unlink()


def test_log_action_change(temp_calibration_log):
    """Проверка логирования изменения action."""
    temp_calibration_log.log_action_change(
        category_key="btc_short",
        from_action="RUN",
        to_action="PAUSE",
        regime="CASCADE_UP",
        modifiers=["VOLATILITY_SPIKE"],
        reason_ru="Каскад вверх — шорт на паузу",
        reason_en="BASE_CASCADE_UP",
        affected_bots=["btc_short_l1"],
        triggered_by="AUTO",
    )

    # Читаем события
    today = date.today()
    events = temp_calibration_log.read_events(today)

    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "ACTION_CHANGE"
    assert event["category_key"] == "btc_short"
    assert event["from_action"] == "RUN"
    assert event["to_action"] == "PAUSE"
    assert event["regime"] == "CASCADE_UP"


def test_log_regime_shift(temp_calibration_log):
    """Проверка логирования смены режима."""
    temp_calibration_log.log_regime_shift(
        from_regime="RANGE",
        to_regime="TREND_UP",
        modifiers=["STRONG_MOMENTUM"],
        reason_ru="Рост моментума",
    )

    today = date.today()
    events = temp_calibration_log.read_events(today)

    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "REGIME_SHIFT"
    assert event["regime"] == "TREND_UP"


def test_read_events_empty_day(temp_calibration_log):
    """Проверка чтения событий за день без логов."""
    yesterday = date.today() - timedelta(days=1)
    events = temp_calibration_log.read_events(yesterday)
    assert events == []


def test_jsonl_format(temp_calibration_log):
    """Проверка что логи пишутся в JSONL формате."""
    temp_calibration_log.log_action_change(
        category_key="btc_long",
        from_action="PAUSE",
        to_action="RUN",
        regime="RANGE",
        modifiers=[],
        reason_ru="Боковик активирован",
        reason_en="BASE_RANGE",
        affected_bots=["btc_long_mid"],
        triggered_by="AUTO",
    )

    today = date.today()
    log_path = temp_calibration_log._get_log_path(today)

    # Проверяем что файл существует
    assert log_path.exists()

    # Проверяем что каждая строка — валидный JSON
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        import json
        data = json.loads(lines[0])
        assert data["category_key"] == "btc_long"
```

---

### 8.2 `tests/test_calibration_renderer.py`

```python
import pytest
from datetime import date
from pathlib import Path

from core.orchestrator.calibration_log import CalibrationLog
from renderers.calibration_renderer import render_daily_report


@pytest.fixture
def temp_calibration_log_with_data(tmp_path):
    """Создаёт CalibrationLog с тестовыми данными."""
    log_path = tmp_path / "calibration"
    log = CalibrationLog(log_path)

    # Добавляем тестовые события
    log.log_action_change(
        category_key="btc_short",
        from_action="RUN",
        to_action="PAUSE",
        regime="CASCADE_UP",
        modifiers=["VOLATILITY_SPIKE"],
        reason_ru="Каскад вверх",
        reason_en="BASE_CASCADE_UP",
        affected_bots=["btc_short_l1"],
        triggered_by="AUTO",
    )

    log.log_regime_shift(
        from_regime="RANGE",
        to_regime="CASCADE_UP",
        modifiers=["VOLATILITY_SPIKE"],
        reason_ru="Резкий рост волатильности",
    )

    log.log_manual_command(
        command="/pause btc_short",
        category_key="btc_short",
        action="PAUSE",
        regime="CASCADE_UP",
        modifiers=["VOLATILITY_SPIKE"],
    )

    yield log


def test_render_daily_report(temp_calibration_log_with_data):
    """Проверка рендера daily report."""
    today = date.today()
    report = render_daily_report(today)

    assert "DAILY REPORT" in report
    assert "АКТИВНОСТЬ ОРКЕСТРАТОРА" in report
    assert "Всего событий: 3" in report
    assert "btc_short" in report
    assert "CASCADE_UP" in report


def test_render_daily_report_empty(tmp_path):
    """Проверка рендера для дня без данных."""
    log_path = tmp_path / "calibration"
    log = CalibrationLog(log_path)
    
    yesterday = date.today() - timedelta(days=1)
    report = render_daily_report(yesterday)

    assert "Нет данных за этот день" in report
```

---

## 9. КОНФИГУРАЦИЯ

**В `config.py` добавить (опционально):**

```python
# ================== CALIBRATION LOG SETTINGS ==================

# Максимальный возраст логов (дни)
CALIBRATION_LOG_RETENTION_DAYS = 90

# Путь к логам калибровки
CALIBRATION_LOG_PATH = Path("state/calibration")
```

---

## 10. КРИТЕРИИ ПРИЁМКИ

### Обязательные:
1. ✅ **Baseline бэктеста не изменён:** 20 / 75% / +10.5709%
2. ✅ **Все тесты проходят:** 209+ passed (включая новые для calibration_log)
3. ✅ **CalibrationLog работает:**
   - События пишутся в JSONL формат
   - Файлы создаются по дням (`YYYY-MM-DD.jsonl`)
   - `read_events()` корректно парсит логи
4. ✅ **Интеграция с оркестратором:**
   - `dispatch_orchestrator_decisions()` логирует изменения action
   - `trigger_killswitch()` логирует срабатывания
   - Ручные команды логируются
5. ✅ **Команда `/daily_report`:**
   - Работает для сегодня / вчера / конкретной даты
   - Рендер содержит все секции (активность, режимы, категории, причины, команды, killswitch)
6. ✅ **Тесты:**
   - `test_calibration_log.py` — логирование событий
   - `test_calibration_renderer.py` — рендер отчёта

### Опциональные:
- Rotation логов старше N дней (можно отложить на TZ-007)
- Экспорт логов в CSV/JSON (можно отложить)

---

## 11. OUT OF SCOPE (TZ-007)

- Автоматическая отправка daily report в Telegram (будет в orchestrator_loop)
- Rotation старых логов (можно добавить позже)
- Визуализация графиков (пока только текст)

---

## 12. РИСКИ

**Низкие:**
- JSONL формат может вырасти в размере (решается rotation)
- Парсинг логов за день может быть медленным при большом количестве событий (решается индексированием)

**Средние:**
- Нет защиты от конкурентной записи в JSONL (в текущей архитектуре не критично, т.к. оркестратор работает в одном потоке)

---

**Конец документа.**
