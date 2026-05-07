# CUSTOM BOTS REGISTRY

**Принцип:** этот файл фиксирует все live боты оператора с их
ролями, активационными условиями и связями с патернами.

---

## Production base grid bots

(Из docs/MASTER.md L211-213)

### TEST_1, TEST_2, TEST_3
- Side: SHORT
- Pair: BTCUSDT (USDT-M linear)
- Size: 0.001 BTC
- Orders: 200
- gs: 0.03%
- Target: 0.25%
- Instop: 0 / 0.018 / 0.03% соответственно
- Boundaries: 68000-78600

### BTC-LONG-C, BTC-LONG-D
- Side: LONG
- Pair: BTCUSD (COIN-M inverse)
- Size: $100
- Orders: 220
- Target: 0.20-0.21%

---

## Special-purpose bots

### Bot 6399265299 — Post-impulse SHORT booster

**Status:** Live, manual activation
**Связан с pattern:** P-16 (см. HYPOTHESES_BACKLOG.md)
**Source:** session 2026-04-30 operator description

**Назначение:** ограниченный SHORT-бот, активируется когда impulse
рост остановился и цена в зоне ликвидаций.

**Активация (manual):**
1. Detect impulse exhaustion (operator judgement)
2. Check цена в зоне liq / у resistance
3. Set hard border.top чуть выше recent high
4. Включить бот

**Поведение:**
- Если breakout продолжился → border.top срабатывает рано
- Если range/проторговка → молотит TPs, подтягивает avg общих
  shorts вверх

**Открытые вопросы:** см. Q-4 в OPERATOR_QUESTIONS.md

---

(Любые новые custom боты добавляются здесь)
