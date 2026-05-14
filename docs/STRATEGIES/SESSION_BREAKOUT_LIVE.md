# Session Breakout — детектор подробно

## Идея в одну фразу

При смене торговой сессии (Asia→London, London→NY и т.д.) в первые 15 минут
новой сессии — если цена пробивает high или low **предыдущей** сессии,
торгуем в направлении пробоя.

## Почему это работает (рыночная логика)

Каждая торговая сессия (Asia, London, NY) имеет свой профиль участников:
- Asia (00:00-08:00 UTC) — преимущественно retail, тонкий рынок
- London (08:00-13:00) — крупные европейские деньги, ликвидность пик
- NY AM (13:00-17:00) — американский институционал
- NY Lunch (17:00-19:00) — спад активности
- NY PM (19:00-23:00) — закрытие позиций перед Asia

**Что происходит на стыке:**
1. К концу сессии формируются high/low — это **ключевые уровни** где участники
   сессии оставили свои стопы (выше high = stop'ы шортов, ниже low = стопы лонгов).
2. Новая сессия с новыми участниками **пробивает** этот уровень → срабатывание
   stop'ов прошлой сессии → импульс в направлении пробоя.
3. Особенно сильно на London open (после Asia) и NY open (после London) —
   там приходят свежие деньги с агрессивным позиционированием.

## Backtest (что мы знаем точно)

**Период:** 2 года BTCUSDT 1m данных, 2024-02-12 → 2026-05-11.
**Sweep:** 700 параметрических комбинаций.

### Best combo overall

| параметр | значение |
|---|---|
| entry_window | **15 минут** после смены сессии |
| breakout buffer | **0%** (касание уровня = вход) |
| hold | **3 часа** |
| PF | **1.73** |
| WR | 55% |
| N trades | 1,833 |
| **walk-forward folds** | **4/4 positive** |
| Total PnL за 2y | **+$4,029** |

### Per-transition (отдельно по каждой смене сессии)

| transition | PF | WR | N | per-fold |
|---|---:|---:|---:|---|
| **ny_pm → asia** | **2.57** | 57% | 456 | $399 / $428 / $379 / $376 — стабильнейший |
| ny_am → ny_lunch | 1.86 | 54% | 415 | $186 / $168 / $18 / $434 |
| london → ny_am | 1.36 | 55% | 708 | $372 / $82 / $216 / $756 |
| asia → london | 1.19 | 53% | 279 | $117 / $145 / $82 / $218 |

**Самый сильный edge — `ny_pm → asia`** (PF 2.57, все 4 фолда +$370-430,
не зависит от рыночного режима). Это связано с тем что:
- NY PM закрывает позиции
- Asia начинается с **тонким** объёмом — пробой high/low NY PM ловит
  тонкую ликвидность, цена «летит» дальше до восстановления объёма

### Что не выбрано как best (но тоже работает)

| combo | PF | N | comment |
|---|---:|---:|---|
| ew=15 hold=2h | 1.85 | 1,833 | короткий hold, чуть выше PF, меньше PnL |
| ew=15 hold=1h | **2.05** | 1,833 | самый высокий PF среди all-transitions |
| ew=30 hold=4h | 1.52 | 2,048 | старая версия до tuning |

## Текущие параметры в live

После deep-dive 2026-05-11 [SESSION_BREAKOUT_BACKTEST.md](./SESSION_BREAKOUT_BACKTEST.md):

```python
# services/setup_detector/session_breakout.py:
ENTRY_WINDOW_MIN = 15
BUFFER_PCT = 0.0
HOLD_HOURS = 3
DEFAULT_SL_PCT = 0.6   # стоп = entry ± 0.6%
DEFAULT_TP_RATIO = 1.5  # TP = entry ± SL × 1.5 = 0.9%
```

RR = 1:1.5 (риск $1 → потенциал $1.5).

## Что вы увидите в Telegram

Когда детектор срабатывает, приходит карточка (пример):

```
🟠 LONG — long_session_breakout
BTCUSDT | 17:34 UTC

Цена $81,643
Сила: 8/10 | Уверенность: 75%

ВХОД: $81,643 (limit)
СТОП:  $81,153
ЦЕЛИ: TP1 $82,378 | TP2 $82,818
RR: 1:1.5

ОСНОВАНИЕ:
• Session london (in 5min)
• Prior asia_high=81,540
• Prior asia_low=81,180
• Recent high=81,652

ОТМЕНА:
• price drops below entry by 0.5% within first hour
• hold window 3h expired

Портфель: ...
Размер: 0.05 BTC | Окно: 180 мин
```

🟠 — important префикс из severity_prefix системы (не 🔴 critical и не 🟡 info).

## Когда детектор НЕ срабатывает

- `session_active == "dead"` — между сессиями (например выходные, мы скипаем)
- `time_in_session_min > 15` — уже опоздали (entry window закрыт)
- prior session high/low неизвестен (parquet ICT данных пустой для bar'а)
- strength < 6 (стандартный фильтр базовых детекторов)
- confidence < SETUP_PUSH_MIN_CONFIDENCE = 70% (в setup_detector loop)

## Какие сессии и когда (UTC)

```
00:00-08:00  Asia
08:00-13:00  London
13:00-17:00  NY AM
17:00-19:00  NY Lunch
19:00-23:00  NY PM
23:00-00:00  dead/transition
```

**Сильные часы для детектора (UTC):**
- 08:00-08:15 — London open после Asia
- 13:00-13:15 — NY AM open после London (самый ликвидный)
- 00:00-00:15 — Asia open после NY PM (наш топ PF 2.57)

В MSK (UTC+3):
- 11:00-11:15 — London open
- 16:00-16:15 — NY AM open
- 03:00-03:15 — Asia open (😴)

## Confluence

С 2026-05-12 детектор участвует в **confluence boost** наряду с остальными.
Если в окне ±6h до session_breakout уже сработали другие детекторы в ту же
сторону, confidence повышается:
- 2 других → ×1.25
- 3 других → ×1.5
- 4+ других → ×1.75 (cap 100%)

Это **двойной фильтр качества** — частые сетапы становятся ещё точнее.

## Чего ждать в ближайшую неделю paper

- 5-10 срабатываний в день (зависит от волатильности)
- Самые сильные — 03:00 MSK (ny_pm→asia) и 16:00 MSK (london→ny_am)
- Backtest expectation: **~$4-5/day** на $1000 размер
- Если за 7 дней нет ни одного profit'а — alert, может drift

## Полный список колонок ICT использованных детектором

```
session_active, time_in_session_min,
asia_high, asia_low,
london_high, london_low,
ny_am_high, ny_am_low,
ny_lunch_high, ny_lunch_low,
ny_pm_high, ny_pm_low,
```

Из parquet `data/ict_levels/BTCUSDT_ict_levels_1m.parquet` (1.18M строк, обновляется при перезапуске генератора).

## Связанные файлы

- `services/setup_detector/session_breakout.py` — детектор
- `services/setup_detector/ict_context.py` — ICT context reader
- `tools/_backtest_session_breakout.py` — sweep tool
- `tests/services/setup_detector/test_session_breakout.py` — 11 unit-tests
- `docs/STRATEGIES/SESSION_BREAKOUT_BACKTEST.md` — sweep results
