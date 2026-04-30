# HYPOTHESES BACKLOG

**Принцип:** все новые идеи стратегии и улучшений фиксируются
здесь. Каждая получает уникальный ID (P-NN). Validation статус
явно указан.

Status enum:
- DRAFT: только сформулирована
- BACKTEST_PENDING: ждёт Stage 1.2 framework
- BACKTEST_RUNNING: в процессе sweep
- VALIDATED: backtest подтвердил, готова к live test
- LIVE_DRY_RUN: в dry-run на проде
- CONFIRMED: используется live с фиксированными параметрами
- REJECTED: не работает
- HARD_BAN: эмпирически вредна

---

## P-15: rolling-trend-rebalance v2

**Status:** DRAFT
**Source:** session 2026-04-30 (operator)

### Описание
На confirmed trend подстраиваем параметры long/short так, чтобы
short мог закрыть часть позиции на retracement в нуль/плюс. После
закрытия — reentry shorts с более высоких уровней. Цикл repeat
на каждом impulse-ретрейс шаге.

### Цикл (8 шагов)
1. Цена идёт вверх (для bull case)
2. Detection: "это похоже тренд" (multi-signal gate)
3. Динамически меняем параметры long-grid и short-grid
4. Дожидаемся retracement (откат после impulse)
5. На откате SHORT закрывает часть позиции (или всю) в плюс/нулём
6. Если тренд продолжается:
   - Перезаходим в SHORT с новых, более высоких цен
   - С чистого баланса, без накопленной просадки
7. Цикл повторяется на каждом следующем impulse-ретрейс шаге
8. Safety net: если cycle не работает несколько раз → переход
   в P-4 PAUSED, не force-close

### 3 варианта обработки SHORT на trending up

(добавлено operator 2026-04-30 во время уточнения)

| Вариант | Поведение | Логика |
|---|---|---|
| (A) Defensive | dsblin=true ИЛИ уменьшить q.minQ | Защита капитала |
| (B) Aggressive add + cap | НАОБОРОТ, увеличить + hard border.top | Подтянуть avg быстрее, выйти на retracement в 0/+ |
| (C) Status quo | Без изменений | Без вмешательства |

### Открытые параметры для backtest sweep
Q1: trend onset detection thresholds (price/hold/volume)
Q2: LONG params adjustment ranges
Q3: SHORT params adjustment ranges
Q4: retracement detection thresholds
Q5: partial unload size (% позиции)
Q6: reentry conditions
Q7: stop / safety net
Q8: trend confirmation для НЕ-cycle

### Risks (от architect)
P-15 как идея сильная, но есть скрытое предположение: retracement
приходит regularly within tolerable time window. Что если на
сильном тренде BTC просто не даёт retracement'ов глубже 0.3-0.5%?
В таких случаях P-15 cycle будет бесконечно ждать retracement
которого нет. **Backtest должен проверить на каких типах трендов
P-15 работает:**
- Volatile trending (есть глубокие retracement'ы) → может работать
- Smooth low-volatility trending (мелкие retracement'ы) → не выезжает
- Cascade-driven impulse → застрянет

### Acceptance в production
- Backtest sweep на 3+ типах рынка показывает positive expected
  value на minimum 1 типе
- Sharpe > 1.0 на 2-летнем horizon
- Max DD < 5% депо
- Минимум 2 недели dry-run в production
- Operator approve based on dry-run logs

---

## P-16: post-impulse-booster

**Status:** DRAFT
**Source:** session 2026-04-30 (operator clarification)

### Описание
Отдельный SHORT-бот, активируется ОПЕРАТОРОМ когда:
- (a) impulse рост остановился (signs of exhaustion)
- (b) цена находится в зоне ликвидаций / у сильного resistance уровня
- (c) перед активацией ставится hard border.top чуть выше recent high

### Цели
1. Если breakout продолжается — border.top срабатывает рано,
   мин. потери
2. Если range/проторговка — booster добавляет volume + ускоряет
   подтягивание avg entry основных шорт-ботов → быстрее выход в плюс

### Текущая live реализация
**Bot 6399265299** (см. docs/CANON/CUSTOM_BOTS_REGISTRY.md)
Активируется руками. Это работающий механизм оператора, требует
формализации триггеров и backtest validation параметров.

### Открытые параметры для backtest sweep
- Какой признак "impulse exhausted" даёт best timing
- border.top offset от high (0.3% / 0.5% / 0.8% / 1.0%)
- Size бустера relative to base shorts (0.5x / 1x / 1.5x / 2x)
- Max activation time (когда автоматически отключать)
- Distance к liq cluster для активации

### Связь с P-15
P-15 и P-16 complementary, не конкурирующие.
- P-15: что делать с УЖЕ накопленной шорт-позицией (закрыть/переоткрыть)
- P-16: добавить новый, ограниченный SHORT-бот когда impulse завершён

На одном тренде могут работать оба:
1. Impulse идёт → base shorts набирают позицию (боль #4)
2. Impulse останавливается у resistance → активируется P-16 booster
3. Pullback приходит → P-15 закрывает часть base + P-16 закрывается профитно
4. Reentry на новых уровнях для следующего цикла

---

(Любые будущие гипотезы добавляются как P-17, P-18, ... в
аналогичном формате)
