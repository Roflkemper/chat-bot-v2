# P-15 Fix Proposal — что менять в живом боте

## Что узнали

1. **dd_cap НЕ виноват** (sweep 84 комбо, dd_cap 2-6% — все +$15-25k за 2y)
2. **Главная проблема — max_reentries**:
   - Live использует max_re=10 → к layer 6-7 avg_entry уходит +3-4% от стартовой цены
   - Бэктест 15m sweep: max_re=999 даёт нереалистичный +$420k (leverage без ограничения позиции)
   - max_re=3-5 даёт реалистичные +$30-60k на 2y (соответствует ожиданиям)
3. **K (reentry offset) тоже играет**: K=0.5% даёт avg +$35k, K=2.0% даёт +$288k — но это с unlimited reentries

## Предлагаемые изменения

### Безопасный fix (immediate)
**Снизить max_reentries 10 → 5**.

Эффект:
- `max_layer` capped at 6 (1 initial + 5 reentries)
- avg_entry дрейфует максимум +2.5% (при K=0.5%) до +5% (при K=1%)
- dd_cap 3% перестаёт срабатывать так часто (positions меньше)
- Backtest avg: $52k SHORT / $44k LONG (всё ещё положительно)

### Лучше: смешанный fix
**max_re=5, K=0.5%, harvest_pct=0.3, R=0.3%**

Это smooth profile:
- Reentries ограничены (5 максимум)
- Reentry близко к exit (0.5% offset) — мало дрифт avg
- Малый harvest size (30%) — позиция не "развинчивается" слишком быстро
- R 0.3% (как сейчас) — частота harvest как live

Бэктест-ожидание: ~$30-45k на 2y, более стабильное распределение.

### Не делать
- ❌ Не убирать reentry полностью — это убьёт edge
- ❌ Не ставить max_re=999 — backtest показывает leverage drift
- ❌ Не повышать dd_cap до 5% — fix не решает первопричину

## Где править код

`services/setup_detector/p15_rolling.py` или конфиг где задаются:
- `R` (retrace trigger)
- `K` (reentry offset)
- `dd_cap_pct`
- `max_reentries` (новая константа)
- `harvest_pct` (если не 0.5 fixed)

## План внедрения

1. ✅ Бэктест (этот документ)
2. Изменить конфиг: max_re=5, K=0.5%, harvest_pct=0.3
3. Restart бот, наблюдать paper-trade 3-5 дней
4. Сравнить с прежним PnL (был −$926/мес)
5. Если ≥0 → продолжать paper ещё 7 дней
6. Если ≥+$200/неделя устойчиво → можно рассмотреть микро-аллокацию реальных денег

## Параллельные предложения (для дальнейших сессий)

- **Cap по pos_size** — как в GinArea (cap_pos_btc) — жёстко лимитирует total_qty
- **Trailing stop вместо dd_cap** — exit at fixed % retrace from extreme
- **Confidence weighting** — увеличивать size в сильных trend gates, уменьшать в слабых

## Файлы
- Sweep dd_cap: [P15_DD_CAP_SWEEP.md](./P15_DD_CAP_SWEEP.md)
- Sweep reentry: [P15_REENTRY_SWEEP.md](./P15_REENTRY_SWEEP.md)
- Диагноз live: [P15_LIVE_VS_BACKTEST_DIAGNOSIS.md](./P15_LIVE_VS_BACKTEST_DIAGNOSIS.md)
