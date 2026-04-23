# BASELINE INVESTIGATION DESIGN v0.1

**Статус:** Draft  
**Дата:** 2026-04-18  
**Автор:** Claude (архитектор)  
**Цель:** Найти и устранить источник недетерминизма в бэктесте

---

## 1. ПРОБЛЕМА

Запуск бэктеста на **одном и том же frozen dataset** даёт разные результаты:

| Прогон | Trades | Winrate | PnL | Max DD |
|--------|--------|---------|-----|--------|
| TZ-005 | 20 | 75.00% | +10.5709% | -2.1542% |
| TZ-006 | 23 | 73.91% | +11.7123% | -2.1542% |
| TZ-007 | 22 | 72.73% | +10.9273% | -2.1542% |

**Ключевое наблюдение:** `Max DD` идентичен во всех прогонах → **данные свечей стабильны**, но **логика обработки недетерминированна**.

**Последствия:**
- Невозможно сравнивать версии кода между собой
- Невозможно проверить что изменения не сломали систему
- Live trading может быть так же нестабилен

---

## 2. ГЛАВНЫЕ ПОДОЗРЕВАЕМЫЕ

После анализа кодовой базы выявлены 3 потенциальных источника дрейфа:

### 🎯 Подозреваемый #1: `datetime.now()` в trading pipeline

**Файл:** `core/pipeline.py:843`
```python
regime = classify(
    symbol=symbol,
    ts=datetime.now(timezone.utc),  # ⚠️ ТЕКУЩЕЕ ВРЕМЯ, НЕ ВРЕМЯ СВЕЧИ
    ...
)
```

**Проблема:** Когда `classify()` вызывается в бэктесте, он получает **текущее время запуска бэктеста**, а не timestamp последней свечи. Это влияет на:
- Гистерезис (hysteresis) в regime_classifier
- Активацию/деактивацию модификаторов (например, WEEKEND_LOW_VOL зависит от дня недели!)
- Возраст режима (`regime_age_bars`)

**Пример влияния:** Если один прогон запущен в субботу, а другой — в воскресенье, модификатор `WEEKEND_LOW_VOL` будет активен в обоих, но с разным контекстом → разные решения.

**Ещё одна точка:** `core/pipeline.py:496` — `'timestamp': datetime.now().strftime('%H:%M')` (но это только для отображения).

---

### 🎯 Подозреваемый #2: Persistent `state/regime_state.json`

**Файл:** `state/regime_state.json`

```json
{
  "version": 1,
  "symbols": {
    "BTCUSDT": {
      "current_primary": "RANGE",
      "primary_since": "2026-04-18T13:07:40.883120Z",
      "regime_age_bars": 0,
      "pending_primary": null,
      "hysteresis_counter": 0,
      "active_modifiers": {
        "WEEKEND_LOW_VOL": {
          "activated_at": "2026-04-18T12:28:54.827348Z",
          ...
        }
      },
      "atr_history_1h": [...]
    }
  }
}
```

**Проблема:** Этот файл **сохраняется между прогонами** бэктеста. Следующий прогон начинается с состоянием последнего прогона:
- `hysteresis_counter` — может быть не 0
- `active_modifiers` — уже активны
- `atr_history_1h` — содержит историю предыдущих вычислений

**Доказательство:** `save_market_state(prep_state)` в `core/pipeline.py:860` сохраняет состояние.

---

### 🎯 Подозреваемый #3: Pattern Memory CSV

**Файлы:** `state/pattern_memory_BTCUSDT_1h_{2024,2025,2026}.csv` (19876 строк суммарно)

**Проблема:** Pattern learning engine **обновляет** эти CSV между прогонами. Новые данные → новые паттерны → новые решения.

---

## 3. СТРАТЕГИЯ РАССЛЕДОВАНИЯ

### Фаза 1: Диагностика (обязательно)

**Задача:** Доказать недетерминизм и найти **точный** источник.

#### 3.1 Тест детерминизма (A/B)

**Цель:** Запустить бэктест 3 раза подряд на одном frozen dataset. Зафиксировать результаты.

**Скрипт `tests/test_backtest_determinism.py`:**
```python
def test_backtest_is_deterministic():
    """3 последовательных прогона должны дать одинаковый результат."""
    results = []
    for i in range(3):
        _reset_state()  # Сбрасываем все persistent state
        result = run_backtest_from_frozen("backtests/frozen/BTCUSDT_1h_180d_frozen.json")
        results.append({
            "trades": result.trades,
            "winrate": result.winrate,
            "pnl": result.pnl,
            "max_dd": result.max_dd,
        })
    
    # Все 3 прогона должны быть идентичны
    assert results[0] == results[1] == results[2], f"Drift detected: {results}"
```

---

#### 3.2 Фиксация подозреваемых

**Скрипт `tools/baseline_diagnostics.py`:**
```python
"""
Запускает бэктест 3 раза, записывает что изменилось между прогонами.
"""

import hashlib
import json
from pathlib import Path
from datetime import datetime

def hash_file(path: Path) -> str:
    if not path.exists():
        return "NONE"
    return hashlib.md5(path.read_bytes()).hexdigest()

def snapshot_state() -> dict:
    return {
        "regime_state": hash_file(Path("state/regime_state.json")),
        "pattern_2024": hash_file(Path("state/pattern_memory_BTCUSDT_1h_2024.csv")),
        "pattern_2025": hash_file(Path("state/pattern_memory_BTCUSDT_1h_2025.csv")),
        "pattern_2026": hash_file(Path("state/pattern_memory_BTCUSDT_1h_2026.csv")),
        "system_time": datetime.now().isoformat(),
    }

def run_diagnostics():
    snapshots = []
    for i in range(3):
        before = snapshot_state()
        # ... run backtest ...
        after = snapshot_state()
        snapshots.append({
            "run": i,
            "before": before,
            "after": after,
            "result": backtest_result,
        })
    
    # Анализируем что менялось
    report_diffs(snapshots)
```

---

### Фаза 2: Устранение (после диагностики)

**Решения зависят от того, что покажет диагностика:**

#### Решение А: Изоляция state в бэктесте

Если проблема в `state/regime_state.json` и `pattern_memory_*.csv`:

```python
# В run_backtest.py добавить контекст
class BacktestStateIsolation:
    """
    Изолирует все persistent state файлы на время бэктеста.
    После прогона восстанавливает оригинальное состояние.
    """
    def __enter__(self):
        # Backup state files
        self._backup_paths = {}
        for state_file in ["state/regime_state.json", "state/pattern_memory_*.csv"]:
            # ... backup logic
        
        # Reset to clean state
        self._reset_state()
    
    def __exit__(self, *args):
        # Restore original state
        for path, backup in self._backup_paths.items():
            Path(path).write_bytes(backup)

# Использование:
with BacktestStateIsolation():
    result = run_backtest(...)
```

---

#### Решение B: Инжекция времени свечи

Если проблема в `datetime.now()` внутри бэктеста:

```python
# В core/pipeline.py добавить параметр
def build_full_snapshot(symbol: str, *, reference_time: datetime | None = None) -> dict:
    """
    reference_time: если задан, используется вместо datetime.now().
                    В бэктесте должно передаваться timestamp последней свечи.
    """
    now_ts = reference_time or datetime.now(timezone.utc)
    
    regime = classify(
        symbol=symbol,
        ts=now_ts,  # ✅ Детерминированное время
        ...
    )
```

---

#### Решение C: Freeze snapshot state для baseline тестов

Если нужно сохранить "эталонное состояние" для сравнения версий:

```
state/baseline_frozen/
├── regime_state.json
├── pattern_memory_BTCUSDT_1h_2024.csv
├── pattern_memory_BTCUSDT_1h_2025.csv
└── pattern_memory_BTCUSDT_1h_2026.csv
```

Команда `RUN_BACKTEST_DETERMINISTIC.bat` перед прогоном копирует эти файлы в `state/`.

---

### Фаза 3: Восстановление baseline

После устранения дрейфа:

1. Запустить бэктест на актуальной кодовой базе
2. Зафиксировать **новый эталон** (назовём его "TZ-008 baseline")
3. Добавить автотест детерминизма в CI (чтобы дрейф не появился снова)
4. Решить что делать со старыми baseline числами (20/75/+10.57 vs актуальный)

---

## 4. ПЛАН РЕАЛИЗАЦИИ

### Шаг 1: Диагностический скрипт
- Создать `tools/baseline_diagnostics.py`
- Запустить 3 прогона, зафиксировать diff state файлов
- Создать отчёт `reports/baseline_diagnostics_report.md`

### Шаг 2: Исправление корневой причины
- По результатам диагностики применить одно или несколько решений (A/B/C)
- Обновить `run_backtest.py` / `core/pipeline.py`

### Шаг 3: Детерминизм-тест
- Добавить `tests/test_backtest_determinism.py`
- Запускается локально и в CI (после миграции в git)

### Шаг 4: Фиксация нового baseline
- Запустить бэктест 3 раза, убедиться что результат одинаковый
- Зафиксировать как официальный baseline
- Обновить документацию

---

## 5. КРИТЕРИИ ПРИЁМКИ

### Обязательные:
1. ✅ **Детерминизм восстановлен:** 3 последовательных прогона на одном frozen dataset дают **идентичные** результаты (Trades, Winrate, PnL, Max DD совпадают до десятичного знака)
2. ✅ **Тест `test_backtest_determinism.py` проходит**
3. ✅ **Все существующие тесты проходят:** 209+ passed
4. ✅ **Отчёт `reports/baseline_diagnostics_report.md` создан:**
   - Что было причиной дрейфа
   - Как исправлено
   - Новый baseline (число)
5. ✅ **Orchestrator функционал не сломан** (проверка: `/portfolio`, `/apply`, `/daily_report` работают)

### Опциональные:
- Добавить `RUN_BACKTEST_DETERMINISTIC.bat` для честного сравнения версий
- Ввести концепцию "baseline frozen state" для долгосрочных сравнений

---

## 6. РИСКИ

**Высокие:**
- Устранение дрейфа может изменить baseline числа → **все предыдущие baseline'ы устаревают**
- Возможно придётся пересчитать pattern memory с нуля

**Средние:**
- Изменения в `core/pipeline.py` могут повлиять на live trading (не только на бэктест)
- Нужно осторожно тестировать инжекцию времени свечи

**Низкие:**
- Диагностический скрипт сам по себе безопасен (только читает state)

---

## 7. OUT OF SCOPE

- Переписывание regime_classifier (трогаем только интерфейс)
- Изменение логики hysteresis
- Миграция на git (отдельная задача)

---

**Конец документа.**
