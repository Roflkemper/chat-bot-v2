# ADVISE V2 — SPEC 2026-04-30

**TZ:** TZ-DECISION-LOG-SILENT-MODE + TZ-OPERATOR-TRADING-PROFILE-AND-CLEANUP  
**Generated:** 2026-04-30  
**Scope:** Спецификация /advise v2 — форматы, триггеры, feedback loop, open questions

---

## §1 Утренний брифинг (Morning Briefing)

**Триггер:** `/advise` в 09:00 KZ (или по запросу)  
**Канал:** ADVISOR channel (основной)

### Формат

```
📊 БРИФИНГ [дата]

РЕЖИМ: [label] [+модификаторы]
BTC: $XX XXX | RSI1h: XX | ATR: X.XX%

ЛОНГ USDT-M:
  [bot_alias]: [статус] | PnL: [unrealized USD] | [grid_info]

ШОРТ COIN-M:
  [bot_alias]: [статус] | PnL: [unrealized BTC] | [grid_info]

ДЕПО: $XX XXX (free margin: XX%)
Net unrealized: [+/-]$XXX

⚠️ ВНИМАНИЕ: [если есть issues]
```

**Поля:**
- `режим` = из `regime_adapter` (consolidation / trend_up / trend_down + модификаторы)
- `grid_info` = уровень сетки, расстояние до границы, тейк активен?
- `issues` = drawdown > 5%, граница пробита, позиция аномально большая

---

## §2 Реактивные алерты (Reactive Alerts)

**Источник:** `services/decision_log/` — event detector  
**Текущий режим:** `silent_mode=True` — JSONL пишется, Telegram отключён

### События и форматы

#### PNL_EVENT (delta > порог)
```
🟡 PnL событие — [bot_alias]
Изменение: [+/-]$XXX за [период]
Позиция: [X.XX BTC / $XXX]
Режим: [label]

[Рекомендация по ситуации — см. §3]
```

#### PNL_EXTREME (drawdown > 10%)
```
🔴 КРИТИЧНО — [bot_alias]
Просадка: [XX]% ([$XXX])
Рекомендация: пауза / ручное закрытие

[Кнопки: ✅ Принято | ❌ Игнорировать]
```

#### BOUNDARY_BREACH (пробой границы)
```
🟡 Граница пробита — [bot_alias]
Направление: [ВЫШЕ/НИЖЕ]
Цена: $XX XXX | Граница: $XX XXX
Действие: [из play matrix — see §3]
```

#### POSITION_CHANGE (delta ratio > порог)
```
ℹ️ Изменение позиции — [bot_alias]
Было: [X.XX BTC] → Стало: [X.XX BTC]
Delta: [+/-XX%]
```

---

## §3 Per-Pattern Breakdown — рекомендации

На каждый тип события / режим — таблица рекомендаций (из PLAYBOOK + OPPORTUNITY_MAP):

| Событие | Режим | Рекомендация |
|---|---|---|
| BOUNDARY_BREACH выше | consolidation | P-1: COUNTER_LONG активировать |
| BOUNDARY_BREACH ниже | consolidation | P-2: Расширение границ (boundary_expand) |
| PNL_EXTREME шорт | trend_down | Проверить буст, возможно взять профит |
| PNL_EXTREME лонг | trend_up | Проверить покупной буст |
| BOUNDARY_BREACH выше | trend_up | P-4: Adaptive grid up — не паниковать |
| BOUNDARY_BREACH ниже | trend_down | P-5: Anti-pattern — риск ручного close |

**Примечание:** Рекомендации на английском дублируются из `PLAYBOOK.md §P-*`.  
Operator принимает решение — `/advise` только информирует.

---

## §4 Cross-Asset Signals

**Scope:** BTC / ETH / XRP — три актива в `/advise` v2  
**Текущее состояние:** multi-asset архитектура реализована (`services/advise_v2/`)

### Сигналы корреляции

| Условие | Сигнал | Рекомендация |
|---|---|---|
| BTC -2% за 1h, ETH -3%, XRP -4% | Системный dump | Шорты в прибыли, лонги под давлением |
| BTC flat, ETH/XRP разнонаправлены | Rotation | Наблюдать, без action |
| BTC +1%, ETH/XRP не движутся | BTC outperform | Проверить шорт COIN-M (profit) |

**Формат алерта:**
```
📊 Кросс-актив: [тип сигнала]
BTC: [+/-]X.X% | ETH: [+/-]X.X% | XRP: [+/-]X.X%
Интерпретация: [строка]
```

---

## §5 Operator Feedback Loop — фазы

### Phase A (сейчас, 28.04–14.05): Observation
- `paper_journal` пишет в `advise_signals.jsonl`
- `decision_log` детектирует события, `silent_mode=True`
- Оператор получает только утренний брифинг по запросу
- Цель: накопить 14+ дней данных без шума

### Phase B (после 14.05): Signal Review
- Ручной разбор `advise_signals.jsonl` + `decision_log/events.jsonl`
- Оценка качества рекомендаций (было ли правильно?)
- Обновление threshold'ов для reactive alerts

### Phase C (Phase 1+): Selective Activation
- Включить reactive alerts для 1-2 событий (BOUNDARY_BREACH + PNL_EXTREME)
- `silent_mode=False` только для критических событий
- Остальные события — silent

### Phase D (Phase 2): Full Automation
- Все алерты включены, dedup настроен по данным Phase B
- play managers (adaptive_grid, boundary_expand, counter_long) на auto
- Feedback loop: оператор ← `/advise approve` → action tracker

---

## §6 Open Questions

**Q1: Threshold для PNL_EVENT?**  
Текущий threshold: `delta_pnl_usd` не задан явно в event_detector.  
Нужно: задать порог (например, >$500 изменение за 15 минут → WARNING).  
Статус: **OPEN** — требует анализа распределения PnL из paper_journal.

**Q2: Indicator direction для LONG COIN-M?**  
GinArea LONG индикатор — momentum (цена растёт) или contrarian (цена падает)?  
Sim: `v < -threshold` → fires on price DROP.  
Если GA fires on RISE → sign flip (B2 hypothesis, Phase 2C).  
Статус: **OPEN** — оператор должен проверить GinArea UI.

**Q3: Boundary decision tree — когда расширять vs пауза vs ручное?**  
P-2 (boundary_expand) неоднозначен: иногда правильно, иногда trap.  
Нужен: explicit decision tree с условиями.  
Статус: **OPEN** — Gap 3 из §16.6 MASTER.md.

**Q4: Cross-asset correlation weights?**  
Как взвешивать ETH/XRP сигналы vs BTC?  
Текущий `/advise` — равный вес.  
Gap 4 из §16.6 MASTER.md.  
Статус: **OPEN** — после Phase A данных.

---

## §7 Acceptance Criteria

| Часть | Критерий | Статус |
|---|---|---|
| silent_mode flag | `DecisionLogAlertWorker.__init__` принимает `silent_mode: bool` | ✅ |
| silent_mode wired | `silent_mode=True` в `telegram_runtime.py` instantiation | ✅ |
| silent_mode test | 3 теста pass: suppress send, _seen updated, normal mode works | ✅ |
| JSONL продолжает писаться | `_read_new_events()` работает в silent mode | ✅ |
| spec doc | Этот файл создан | ✅ |
| /advise behavior | НЕ изменён в этом TZ | ✅ |
| paper_journal | НЕ изменён | ✅ |
