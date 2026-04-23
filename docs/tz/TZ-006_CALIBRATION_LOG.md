# TZ-006: CALIBRATION LOG + DAILY REPORT

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
- TZ-005: `killswitch.py` + защита маржи + команды `/killswitch`

**Baseline бэктеста (НЕЛЬЗЯ ЛОМАТЬ):**
- Trades: 20
- Winrate: 75.0%
- PnL: +10.5709%

**Текущий статус тестов:** 209 passed

---

## ЗАДАЧА TZ-006

Реализовать **calibration_log** — систему логирования и анализа решений оркестратора.

**Цели:**
1. **Логирование событий** — запись каждого изменения action категории, смены режима, срабатывания killswitch
2. **Daily Report** — ежедневная сводка активности оркестратора (команда `/daily_report`)
3. **Калибровка настроек** — данные для анализа эффективности action_matrix

**Формат хранения:** JSONL (JSON Lines) — одно событие = одна строка JSON в файле `state/calibration/{YYYY-MM-DD}.jsonl`

**Зачем JSONL:**
- Append-only логирование (не нужно перезаписывать файл)
- Парсинг по строкам (не нужно загружать весь файл в память)
- Устойчивость к сбоям (файл всегда валидный)

---

## DESIGN-ДОКУМЕНТ

**См. полный дизайн:** `docs/CALIBRATION_LOG_DESIGN_v0.1.md`

Ключевые моменты:
- Логи хранятся в `state/calibration/YYYY-MM-DD.jsonl`
- Класс `CalibrationLog` (singleton pattern)
- 4 типа событий: `ACTION_CHANGE`, `REGIME_SHIFT`, `KILLSWITCH_TRIGGER`, `MANUAL_COMMAND`
- Daily report через команду `/daily_report [yesterday|YYYY-MM-DD]`

---

## ЧТО НУЖНО РЕАЛИЗОВАТЬ

### 1. Core модули

#### 1.1 `core/orchestrator/calibration_log.py`

**Создать класс `CalibrationLog`:**

```python
from dataclasses import dataclass, asdict
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any
import json

from utils.safe_io import atomic_append_line


@dataclass
class CalibrationEvent:
    """Событие калибровки оркестратора."""
    ts: datetime
    event_type: str  # ACTION_CHANGE | REGIME_SHIFT | KILLSWITCH_TRIGGER | MANUAL_COMMAND
    regime: str
    modifiers: list[str]
    reason_ru: str
    triggered_by: str  # AUTO | MANUAL | KILLSWITCH
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

### 2. Утилита atomic_append_line()

**В `utils/safe_io.py` добавить:**

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

### 3. Интеграция с оркестратором

#### 3.1 Логирование в `core/orchestrator/command_dispatcher.py`

**Добавить вызовы CalibrationLog в `dispatch_orchestrator_decisions()`:**

```python
def dispatch_orchestrator_decisions(store: PortfolioStore, regime_snapshot: dict[str, Any]) -> DispatchResult:
    from core.orchestrator.killswitch import KillswitchStore
    from core.orchestrator.calibration_log import CalibrationLog

    portfolio = store.get_snapshot()
    killswitch = KillswitchStore.instance()
    if killswitch.is_active():
        return DispatchResult(
            changed=[],
            unchanged=list(portfolio.categories.keys()),
            alerts=[],
            ts=datetime.now(timezone.utc),
        )

    regime = str(regime_snapshot.get("primary") or "RANGE")
    modifiers = list(regime_snapshot.get("modifiers") or [])
    cal_log = CalibrationLog.instance()

    changes: list[CategoryChange] = []
    unchanged: list[str] = []

    for cat_key, cat in portfolio.categories.items():
        if not cat.enabled:
            unchanged.append(cat_key)
            continue

        decision = decide_category_action(regime, modifiers, cat)
        new_action = decision.action
        old_action = cat.orchestrator_action

        # Логируем изменение action
        if new_action != old_action:
            # Получаем список ботов в категории
            affected_bot_ids = [
                bot_key for bot_key, bot in portfolio.bots.items()
                if bot.category == cat_key
            ]

            cal_log.log_action_change(
                category_key=cat_key,
                from_action=old_action,
                to_action=new_action,
                regime=regime,
                modifiers=modifiers,
                reason_ru=decision.reason,
                reason_en=decision.reason_en,
                affected_bots=affected_bot_ids,
                triggered_by="AUTO",
            )

            # ... остальная логика изменения action ...
```

**ВАЖНО:** Логировать нужно **ДО** изменения action в portfolio_state, чтобы захватить `from_action`.

---

#### 3.2 Логирование в `core/orchestrator/killswitch.py`

**Добавить вызов CalibrationLog в `trigger_killswitch()`:**

```python
def trigger_killswitch(reason: str, reason_value: Any) -> str:
    from core.orchestrator.portfolio_state import PortfolioStore
    from core.orchestrator.calibration_log import CalibrationLog
    from core.pipeline import build_full_snapshot
    from renderers.killswitch_renderer import render_killswitch_alert

    store = KillswitchStore.instance()
    if store.is_active():
        logger.warning("[KILLSWITCH] Повторная активация проигнорирована: %s", reason)
        current = store.get_current_event() or {"reason": reason, "reason_value": reason_value}
        return render_killswitch_alert(str(current.get("reason")), current.get("reason_value"))

    store.trigger(reason, reason_value)

    # Логируем killswitch
    try:
        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime_data = snapshot.get("regime", {}) if isinstance(snapshot, dict) else {}
        regime = str(regime_data.get("primary") or "UNKNOWN")
        modifiers = list(regime_data.get("modifiers") or [])
    except Exception:
        regime = "UNKNOWN"
        modifiers = []

    cal_log = CalibrationLog.instance()
    cal_log.log_killswitch_trigger(reason, reason_value, regime, modifiers)

    # ... остальная логика killswitch ...
```

---

#### 3.3 Логирование ручных команд

**В `handlers/command_actions.py` добавить логирование для команд `/pause`, `/resume`, `/bot_add`, `/bot_remove`, `/blackout`:**

**Пример для `/pause`:**

```python
def pause(self) -> BotResponsePayload:
    from core.orchestrator.calibration_log import CalibrationLog
    from core.pipeline import build_full_snapshot

    # ... парсинг аргументов ...

    category_key = args[0] if args else None
    if not category_key:
        return self.ctx.plain("❌ Укажите категорию. Пример: /pause btc_short")

    # Логируем ручную команду
    try:
        snapshot = build_full_snapshot(symbol="BTCUSDT")
        regime_data = snapshot.get("regime", {}) if isinstance(snapshot, dict) else {}
        regime = str(regime_data.get("primary") or "UNKNOWN")
        modifiers = list(regime_data.get("modifiers") or [])
    except Exception:
        regime = "UNKNOWN"
        modifiers = []

    cal_log = CalibrationLog.instance()
    cal_log.log_manual_command(
        command=f"/pause {category_key}",
        category_key=category_key,
        action="PAUSE",
        regime=regime,
        modifiers=modifiers,
    )

    # ... остальная логика pause ...
```

**Аналогично добавить логирование для:**
- `/resume` — `log_manual_command(command="/resume ...", action="RUN", ...)`
- `/bot_add` — `log_manual_command(command="/bot_add ...", ...)`
- `/bot_remove` — `log_manual_command(command="/bot_remove ...", ...)`
- `/blackout` — `log_manual_command(command="/blackout", ...)`
- `/apply` — `log_manual_command(command="/apply", ...)`

---

### 4. Рендер Daily Report

**Создать файл `renderers/calibration_renderer.py`:**

```python
from datetime import date, timedelta
from typing import Any

from core.orchestrator.calibration_log import CalibrationLog
from core.orchestrator.visuals import separator


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

    # Категории: изменения action
    if action_changes:
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
                word = "раз" if count == 1 else ("раза" if count < 5 else "раз")
                lines.append(f"  • {transition} ({count} {word})")
            word = "изменение" if len(changes) == 1 else ("изменения" if len(changes) < 5 else "изменений")
            lines.append(f"  Итого: {len(changes)} {word}")
            lines.append("")

    # Самые частые причины
    if action_changes:
        lines.append("САМЫЕ ЧАСТЫЕ ПРИЧИНЫ")
        lines.append(separator(28))
        reason_counts = {}
        for e in action_changes:
            reason_en = e.get("reason_en") or "UNKNOWN"
            reason_counts[reason_en] = reason_counts.get(reason_en, 0) + 1
        top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:5]
        for idx, (reason, count) in enumerate(top_reasons, start=1):
            word = "раз" if count == 1 else ("раза" if count < 5 else "раз")
            lines.append(f"{idx}. {reason} ({count} {word})")
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

### 5. Команда Telegram

**В `handlers/command_actions.py` добавить:**

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

    parts = self.ctx.command.strip().split(maxsplit=1)
    
    if len(parts) < 2:
        day = date.today()
    elif parts[1].lower() == "yesterday":
        day = date.today() - timedelta(days=1)
    else:
        try:
            day = date.fromisoformat(parts[1])
        except ValueError:
            return self.ctx.plain("❌ Неверный формат даты. Используйте YYYY-MM-DD или 'yesterday'.")

    report_text = render_daily_report(day)
    return self.ctx.plain(report_text)
```

**Зарегистрировать команду в `handlers/command_handler.py`:**

```python
# В register_commands():
register_action("daily_report", lambda ctx: CommandActions(ctx).daily_report())
register_action("отчёт", lambda ctx: CommandActions(ctx).daily_report())  # Русский алиас
```

---

### 6. Тесты

#### 6.1 `tests/test_calibration_log.py`

```python
import pytest
from datetime import datetime, date, timezone, timedelta
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

    assert log_path.exists()

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        import json
        data = json.loads(lines[0])
        assert data["category_key"] == "btc_long"


def test_multiple_events_same_day(temp_calibration_log):
    """Проверка что несколько событий добавляются в один файл."""
    temp_calibration_log.log_action_change(
        category_key="btc_short",
        from_action="RUN",
        to_action="PAUSE",
        regime="CASCADE_UP",
        modifiers=[],
        reason_ru="Тест 1",
        reason_en="TEST1",
        affected_bots=[],
        triggered_by="AUTO",
    )

    temp_calibration_log.log_action_change(
        category_key="btc_long",
        from_action="PAUSE",
        to_action="RUN",
        regime="RANGE",
        modifiers=[],
        reason_ru="Тест 2",
        reason_en="TEST2",
        affected_bots=[],
        triggered_by="AUTO",
    )

    today = date.today()
    events = temp_calibration_log.read_events(today)

    assert len(events) == 2
    assert events[0]["reason_en"] == "TEST1"
    assert events[1]["reason_en"] == "TEST2"
```

---

#### 6.2 `tests/test_calibration_renderer.py`

```python
import pytest
from datetime import date, timedelta
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
    CalibrationLog._instance = log  # Override singleton for test

    yesterday = date.today() - timedelta(days=1)
    report = render_daily_report(yesterday)

    assert "Нет данных за этот день" in report

    CalibrationLog._instance = None  # Reset singleton
```

---

### 7. Документация

**Создать файл `docs/CALIBRATION_LOG_DESIGN_v0.1.md`** — уже создан выше.

**Обновить `PROJECT_MANIFEST.md`:**

```markdown
## TZ-006: Calibration Log + Daily Report
- Status: ✅ Delivered
- Files:
  - core/orchestrator/calibration_log.py
  - renderers/calibration_renderer.py
  - utils/safe_io.py (atomic_append_line)
  - handlers/command_actions.py (команда /daily_report + логирование ручных команд)
  - core/orchestrator/command_dispatcher.py (логирование изменений action)
  - core/orchestrator/killswitch.py (логирование killswitch)
  - tests/test_calibration_log.py
  - tests/test_calibration_renderer.py
```

---

## КРИТЕРИИ ПРИЁМКИ

### Обязательные (Must Have):
1. ✅ **Baseline бэктеста не изменён:** 20 / 75% / +10.5709%
2. ✅ **Все тесты проходят:** 209+ passed (включая новые для calibration_log)
3. ✅ **CalibrationLog работает:**
   - События пишутся в JSONL формат (`state/calibration/YYYY-MM-DD.jsonl`)
   - `read_events()` корректно парсит логи
   - Поддержка 4 типов событий: ACTION_CHANGE, REGIME_SHIFT, KILLSWITCH_TRIGGER, MANUAL_COMMAND
4. ✅ **Интеграция с оркестратором:**
   - `dispatch_orchestrator_decisions()` логирует изменения action
   - `trigger_killswitch()` логирует срабатывания
   - Ручные команды (`/pause`, `/resume`, `/bot_add`, `/bot_remove`, `/blackout`, `/apply`) логируются
5. ✅ **Команда `/daily_report`:**
   - Работает для сегодня / вчера / конкретной даты
   - Рендер содержит секции: активность, категории, причины, команды, killswitch
6. ✅ **Тесты:**
   - `test_calibration_log.py` — логирование событий + JSONL формат
   - `test_calibration_renderer.py` — рендер отчёта

### Опциональные (Nice to Have):
- Секция "РЕЖИМЫ РЫНКА (часов)" в daily report (можно упростить или пропустить)
- Rotation логов старше N дней (отложено на TZ-007)

---

## OUT OF SCOPE (TZ-007)

- Автоматическая отправка daily report в Telegram (будет в orchestrator_loop)
- Rotation старых логов (можно добавить позже)
- Визуализация графиков (пока только текст)

---

## ТЕХНИЧЕСКИЕ ЗАМЕТКИ

### Unix-style пути
Все пути в коде: `Path("state/calibration")`, а НЕ `Path("state\\calibration")`

### JSONL формат
- Одна строка = один JSON объект
- Append-only (не перезаписываем файл)
- Парсинг построчный (не нужно загружать весь файл)

### Thread-safety
`atomic_append_line()` использует `a` mode с flush для атомарности записи

### Логирование ПЕРЕД изменением
В `dispatch_orchestrator_decisions()` логировать нужно **ДО** вызова `portfolio.set_category_action()`, чтобы захватить `from_action`

---

## DELIVERY

**Формат поставки:** Единый ZIP-архив с полным кодом проекта.

**Структура:**
```
TZ-006_delivery.zip
├── core/orchestrator/
│   ├── calibration_log.py          (NEW)
│   ├── command_dispatcher.py       (MODIFIED - добавлено логирование)
│   └── killswitch.py               (MODIFIED - добавлено логирование)
├── renderers/
│   └── calibration_renderer.py     (NEW)
├── handlers/
│   └── command_actions.py          (MODIFIED - /daily_report + логирование команд)
├── utils/
│   └── safe_io.py                  (MODIFIED - atomic_append_line)
├── state/
│   └── calibration/                (NEW, пустая директория)
├── tests/
│   ├── test_calibration_log.py     (NEW)
│   └── test_calibration_renderer.py (NEW)
├── docs/
│   └── CALIBRATION_LOG_DESIGN_v0.1.md (NEW)
├── TZ-006_report.md                (отчёт о выполнении)
└── (все остальные файлы без изменений)
```

**Отчёт TZ-006_report.md должен содержать:**
- Что сделано
- Результаты тестов (сколько passed)
- Baseline бэктеста (20/75%/+10.57%)
- Список изменённых файлов
- Примеры использования `/daily_report`

---

## ВОПРОСЫ И УТОЧНЕНИЯ

Если что-то непонятно — спрашивай ПЕРЕД началом реализации, а не после.

Удачи! 🚀
