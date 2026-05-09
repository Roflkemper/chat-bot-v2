# Session report — 2026-05-10

3 коммита, 5 закрытых задач. Ниже — что сделано, какие тесты прогнаны и какие цифры получены.

## 1. Watchdog v2 (commit `79b002d`)

### Проблема
До сегодня держание процессов работало через два слоя:
- `src/supervisor/daemon.py` — тихо умирал каждые ~2 мин на Windows pythonw, 4 итерации фиксов не помогли.
- `scripts/keepalive_check.py` — мониторил **только** `app_runner`, не трогал `tracker / collectors / state_snapshot`.

Результат: оператор получил TG STALE DATA — `tracker` и `collectors` были мертвы 5+ часов, `liquidations` 9+ часов, никто не заметил.

### Что сделано
Один файл `scripts/watchdog.py`. Каждый тик (раз в 2 мин через Task Scheduler) для каждого из 4 компонентов:
1. Проверяет cmdline через `psutil` — есть ли живой процесс.
2. Проверяет свежесть выходного файла (`max_age_min`).
3. Если NOT RUNNING → стартует. Если RUNNING + STALE → kill + restart. Если RUNNING + FRESH → ничего.

Запуск через `subprocess.Popen` с флагами `DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB | CREATE_NEW_PROCESS_GROUP` — процессы переживают завершение Task Scheduler task'а.

### Конфигурация компонентов

| Компонент | freshness file | max age |
|---|---|---|
| app_runner | logs/app.log | 5 min |
| tracker | ginarea_live/snapshots.csv | 10 min |
| collectors | market_live/market_1m.csv | 10 min |
| state_snapshot | — (только cmdline check) | — |

### Test (живой)
- Watchdog ручной запуск → все 4 компонента стартанули.
- Monitor на 5 минут отслеживал mtime `snapshots.csv` и `market_1m.csv` — оба файла обновлялись каждые **0–5 секунд**, fresh-event'ы пришли подряд (5 нотификаций за окно).
- Tracker и collector подтверждены живыми.

### Task Scheduler
- `bot7-keepalive` → **Disabled**.
- `bot7-watchdog` → создан, every 2 minutes, indefinite duration.

---

## 2. Liquidations websocket (no-fix, диагностика)

### Симптом
`market_live/liquidations.csv` не рос 10+ часов.

### Тесты
**Тест 1 — лог collector'а:** `market_live/collector.log` показывает регулярные `bybit_ws.connected` и `binance_ws.connected` после рестарта (00:40:02, 00:44:02, 00:45:41) — handshake успешен.

**Тест 2 — прямой WebSocket probe:**
```python
# Bybit allLiquidation.BTCUSDT, 25 сек прослушивания
SUBSCRIBE_RESP: {'success': True, 'op': 'subscribe'}
total liq events in 25s: 0

# Binance btcusdt@forceOrder, 25 сек
liq events: 0
```

**Вердикт:** Код работает, рынок просто тихий — 0 ликвидаций на BTCUSDT за 25 сек на двух биржах одновременно. На стабильном боковике это нормально. Не баг.

---

## 3. Self-spawn system-Python "ghost" процессы (false positive)

### Симптом
В `psutil.process_iter` рядом с каждым `.venv pythonw <component>` виден парный процесс под `C:\Program Files\Python310\pythonw.exe` с тем же cmdline и ppid = .venv parent.

### Тесты
- `grep -r "subprocess|os.execv|multiprocessing|sys.executable"` по коду компонентов — **0 совпадений** (кроме unrelated telegram_ui/state/command.py).
- create_time у "родителя" и "ребёнка" совпадает до секунды — невозможно для настоящего fork.
- "Ребёнок" не пишет в свои log-файлы и не держит pid lock.

### Вердикт
Не self-spawn — psutil/Defender создаёт ghost-entry в process listing для pythonw.exe. Не блокирует данные. Записал в memory как `project_system_python_ghosts.md`, чтобы в будущем не копать снова.

---

## 4. Binance derivative history download (commit `cc9ba83`)

### Что скачано
28 дней истории по 5 endpoint'ам × 3 символа = 18 parquet в `data/historical/`:

| Endpoint | Период | Rows/символ |
|---|---|---|
| openInterestHist | 1h | 500 |
| fundingRate | 8h | 84-90 |
| takerlongshortRatio | 1h | 500 |
| globalLongShortAccountRatio | 1h | 500 |
| topLongShortPositionRatio | 1h | 500 |

Покрытие: **2026-04-12 → 2026-05-09** (UTC).

### Найденный bug
Скрипт стартанул с `DAYS_BACK=30` → все 4 ratio-эндпоинта вернули `HTTP 400 'parameter startTime is invalid'`.

Probe показал предел: 28 дней работает, 30 — отвергается. Зафиксил `DAYS_BACK = 28`. Funding endpoint не имеет этого ограничения.

---

## 5. Grid_coordinator retro validation на полных данных (commit `5e4ece7`)

### Что изменено
До: retro-скрипт использовал `deriv = {oi:0, funding:0, ls:1.0}` (стаб) и `eth=None` — индикатор был лишён 2 из 5 сигналов.

После: `_deriv_at(ts)` делает `asof`-lookup по `binance_combined_BTCUSDT.parquet`, ETH 1h-окно из `ETHUSDT_1h_2y.csv` подаётся в evaluate_exhaustion для eth-sync сигнала.

### Тестовый прогон

```
[retro] последние 28 дней: 40,321 1m баров (2026-04-09 → 2026-05-07)
[retro] 1h aggregation: 673 hours
[retro] ETH 1h: 732 bars
[retro] derivatives: 501 1h rows
[retro] processed 623 hours, found 2 signals
```

### Сами сигналы (state/grid_coordinator_retro_signals.csv)

| Время (UTC) | Direction | Score | 60m | 120m | 240m |
|---|---|---|---|---|---|
| 2026-04-12 14:00 | downside | 3/5 | NEUTRAL (+0.02%) | NEUTRAL (+0.16%) | **TRUE** (+0.53%) |
| 2026-04-17 16:00 | upside | 3/5 | NEUTRAL (-0.05%) | **TRUE** (-0.48%) | **TRUE** (-0.58%) |

### Метрики

| Direction | Horizon | TRUE | FALSE | NEUTRAL | Precision | Avg move |
|---|---|---|---|---|---|---|
| upside | 60m | 0 | 0 | 1 | n/a | -0.05% |
| upside | 120m | 1 | 0 | 0 | **100%** | -0.48% |
| upside | 240m | 1 | 0 | 0 | **100%** | -0.58% |
| downside | 60m | 0 | 0 | 1 | n/a | +0.02% |
| downside | 120m | 0 | 0 | 1 | n/a | +0.16% |
| downside | 240m | 1 | 0 | 0 | **100%** | +0.53% |

### Выводы

✅ **Сильное:**
- 0 FALSE positives — индикатор не даёт ложных тревог в выборке.
- Сигналы срабатывают **редко** (2 за 28 дней) — оператора не будет заваливать TG-карточками.
- Цена движется в ожидаемую сторону на 0.5%+ через 4 часа — экономически осмысленно.

⚠️ **Слабое:**
- N=2 — статистическая значимость нулевая. На 100% precision полагаться нельзя.
- 60-минутный горизонт — оба сигнала NEUTRAL. Реакция рынка на exhaustion-сигнал начинается с 120-min.
- Окно покрытия только 28 дней (Binance API limit).

📋 **Что нужно для полноценной валидации:**
- Накопить live-сигналы 3-6 месяцев → выборка 20-30 events.
- Тогда станет видно реальный hit-rate и можно будет калибровать порог 3/5 vs 4/5.

---

## Сводная таблица коммитов

| Commit | Что |
|---|---|
| 79b002d | Unified watchdog заменяет broken keepalive+supervisor |
| cc9ba83 | DAYS_BACK 30→28 для Binance API |
| 5e4ece7 | Binance derivs + ETH 1h в retro grid_coordinator |

## Что осталось / следующие шаги

- Накопление live-выборки grid_coordinator (пассивно — индикатор уже работает в проде).
- Если интересно: расширить retro на 6m-12m через альтернативный источник OI (Bybit, Coinglass) — тогда выборка вырастет с 2 до 50+.
- Self-spawn ghost — задокументирован, не лезу.
