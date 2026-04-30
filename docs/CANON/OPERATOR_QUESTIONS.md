# OPERATOR'S OPEN QUESTIONS

**Принцип:** это вопросы, которые ОПЕРАТОР сам хочет решить через
backtest framework, а не через advice'ы architect'а. Каждый Q
становится приоритетом для backtest sweep когда framework заработает.

Status enum:
- PENDING: ждёт framework (Stage 1.2)
- ACTIVE: framework прогоняет sweep
- ANSWERED: backtest дал результат, документирован
- DEFERRED: оператор отложил
- INVALIDATED: больше не актуально

---

## Q-1: Контртрендовая позиция при затяжном тренде

**Status:** PENDING
**Source:** session 2026-04-30

Действительно ли эффективнее остановить бота на тренде, потом
включить когда рост закончился — чтобы он возобновил работу
с более выгодных позиций? Подтягивая среднюю точку входа
но увеличивая риски. Нужен баланс.

**Backtest target:** P-15 hypothesis on framework.

---

## Q-2: Порог критичности для частичного сброса

**Status:** PENDING

При каких значениях нужно критично сбросить какую часть позиции
на откате?
- Какую долю позиции?
- На каком % отката?
- Со стопом или без (вдруг это не просто откат, а возможность
  закрыть всю позицию в 0 или в +)

**Backtest target:** P-15 hypothesis subset.

---

## Q-3: Стоп vs ожидание

**Status:** PENDING

Если откат не оправдал ожидания — ставим ли стоп или ждём дальше?
И в каких условиях каждый из вариантов работает.

**Backtest target:** framework needs to test both branches.

---

## Q-4: Booster bot triggers

**Status:** PENDING

Идеальные условия активации post-impulse booster (Bot 6399265299):
- Какой признак "impulse exhausted"
- Насколько близко к зоне ликвидаций нужно быть
- Какой border.top offset оптимален
- Какой size relative to base shorts

**Backtest target:** P-16 backtest configuration sweep.

---

## Q-5: Asymmetric param adjustment на trend

**Status:** PENDING

Когда тренд подтверждён — как именно подгонять параметры LONG vs
SHORT чтобы:
- LONG быстрее набирал и чаще TP'шил
- SHORT мог сократить позицию пропорционально на откате
- Если рост продолжается — SHORT мог продолжать с более выгодных цен

**Backtest target:** P-15 v2 sweep over qty/target/border ranges.

---

## Q-6: Detection ложного выноса vs реального тренда

**Status:** PENDING

Какая комбинация сигналов даёт best precision/recall:
- Δprice 1h/4h
- PDH break + hold time
- Volume confirmation
- Round number proximity
- Killzone context

**Backtest target:** structural confirmation gate research, основа
для Layer 3.

---

(Любые будущие вопросы оператора фиксируются как Q-7, Q-8, ...)
