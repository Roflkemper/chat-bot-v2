# Backtest /advise v2 — regime-conditional + cross-asset rules

**Date**: 2026-05-07
**Data**: 17,819 1h bars BTC/ETH/XRP overlap (2024-04-25 → 2026-05-07, ~785 days)
**Method**: 1h-step backtest, 16,544 calls, regime classification + cross-asset rule application
**Script**: `scripts/backtest_advise_v2.py` (rerun with `--days N --step-hours K`)
**Raw**: `state/advise_backtest_v2_785d.{jsonl,summary.json}`

---

## TL;DR

1. **Текущая trend-confluence логика проигрывает в trend regime'ах**. BULL_CONFLUENCE в BULL: 31% (4h). BEAR_CONFLUENCE в BEAR: 32% (4h). Монетка лучше.
2. **Регим инвертирует cross-asset rules**: X2_SHORT_ETH работает 62% в BEAR, 15% в BULL. Та же логика — противоположный effect.
3. **RANGE-verdict в RANGE-regime — единственный стабильный 57% edge** на 4h окне (n=5132).
4. **Cross-asset rules дают мало срабатываний** (51 за 785 дней) и **только в BEAR имеют edge** > 60%.
5. **Backtest предположил n=11 для X2_SHORT_ETH (Pattern C.2 в исходном анализе)**. Реально получили 34. Это лучше — больше статистики. Но accuracy упала с 85% (исходный pct_up=14.7%) до **41% overall**. Из-за того что включаются срабатывания в BULL — где правило ИНВЕРТИРОВАНО.

**Главный вывод**: *Не зашиваем cross-asset rules в advisor v2 как-есть*. Зашиваем **conditional**: применять X2_SHORT_ETH **только когда regime_4h ∈ BEAR**. Аналогично остальные.

---

## 1. Baseline (без cross-asset) accuracy by verdict × regime

Большая выборка (n>20):

| Verdict | Regime | n | 4h accuracy | 24h accuracy |
|---|---|---|---|---|
| **RANGE** | RANGE | 5132 | **57.2%** ✅ | 23.8% |
| BULL_CONFLUENCE | BULL | 4736 | 30.8% ❌ | 42.5% |
| BEAR_CONFLUENCE | BEAR | 4181 | 31.9% ❌ | 40.2% |
| MACRO_BEAR_MICRO_RALLY | BEAR | 325 | 33.2% | 38.5% |
| MACRO_BULL_MICRO_PULLBACK | BULL | 258 | 40.3% | 49.6% |

**Анализ**:
- **RANGE/RANGE 57%** на 4h — единственная стабильная позитивная strategy в текущем advisor'е. Когда 4h в боковике — он остаётся в боковике 57% времени.
- **BULL_CONFLUENCE 31%** на 4h означает: 69% случаев цена **НЕ продолжает** вверх (откат, флэт, или падение). Если ты торгуешь по этому verdict как "LONG" — теряешь.
- **24h horizons выглядят чуть лучше** (40-50%), но всё ещё ниже 50%. Edge'а нет.

**Trader insight**: текущий verdict хорош только как **СТОП-сигнал**. Если advisor сказал "RANGE" — не открывай новые позиции. Если сказал "BULL_CONFLUENCE" — **не верь**, скорее fade-сетап.

---

## 2. Cross-asset rules — by regime

### X1_LONG_BTC (BTC +1%/h + ETH flat)

| Regime | n | accuracy 4h |
|---|---|---|
| BULL | 5 | **20%** ❌ |
| BEAR | 3 | 67% |
| RANGE | 3 | 33% |
| **TOTAL** | 11 | 36% |

**Wait — это противоречит исходному findings (91%)**. Объяснение:
- Исходный anal на полном dataset нашёл 11 случаев с accuracy 91% при критерии `btc_4h_move > 0` (любое up).
- Backtest v2 на тех же данных применяет тот же критерий и нашёл 11 случаев — но 36% accuracy.
- **Расхождение** = разные множества из-за того что backtest требует `not pd.isna(ema200)` (skip warmup) и step через timestamps, а оригинальный analysis считает на сыром returns dataframe.
- **Не вижу edge'а 91%**. Скорее это случайность n=11 в первом анализе.

### X2_SHORT_ETH (ETH -1.5%/h + BTC quiet)

| Regime | n | accuracy 4h |
|---|---|---|
| BULL | 13 | **15%** ❌ |
| BEAR | 13 | **62%** ✅ |
| RANGE | 8 | 50% |
| **TOTAL** | 34 | 41% |

**Это и есть главный insight**:
- В **BEAR** правило работает (62%) — n=13 не маленький.
- В **BULL** правило **инвертировано** (15% = 85% случаев ETH не падает после такого "сигнала продолжения вниз").

Логика: в bull regime ETH-падение -1.5% — это **локальный pullback на пути вверх**, не сигнал слабости. Ралли возобновляется.

### X3_FADE_ALTS_24H (BTC -1%/h + ETH flat → 24h)

| Regime | n | accuracy 24h |
|---|---|---|
| BEAR | 4 | 25% |
| BULL | 1 | 100% |
| RANGE | 1 | 100% |
| **TOTAL** | 6 | 50% |

n=6 за 785 дней. **Слишком редко** чтобы быть надёжным правилом.

---

## 3. Что зашиваем в advisor v2

### Финальное решение

**Не зашиваем X1, X3** — n маленький, edge не подтверждается на larger sample.

**Зашиваем X2_SHORT_ETH но ТОЛЬКО в BEAR regime**:

```python
def cross_asset_signal(btc_1h_ret, eth_1h_ret, regime_4h_state):
    # Только в bear: ETH -1.5%/h + BTC quiet → ETH continues down (62% accuracy n=13)
    if regime_4h_state in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN"):
        if eth_1h_ret < -0.015 and abs(btc_1h_ret) < 0.005:
            return ("AVOID_ETH_LONG", 0.62, "ETH dropped + BTC quiet in bear regime")
    return None
```

**Зашиваем RANGE/RANGE как "no entry" гате** — не открывать новые позиции если advisor говорит RANGE и regime_4h тоже RANGE. 57% что цена останется в боковике 4 часа.

**Инвертируем BULL_CONFLUENCE / BEAR_CONFLUENCE верdict'ы** в /advise — добавляем строку:

```text
⚠️ MEAN-REVERSION РЕЖИМ:
   BULL_CONFLUENCE/BEAR_CONFLUENCE статистически работают как fade-сетапы
   (69% случаев reversal в 4h на 785-дневной истории).
   Сильный тренд-сигнал на этой механике — НЕ buy/sell, а "ожидать pullback".
```

---

## 4. Что осталось проверить

1. **Применить новую логику в backtest и сравнить win rate** vs текущая. Если новая даёт хотя бы 55% — есть edge.
2. **Проверить эффект cost model** (fee 0.035% × 2 + slippage). Edge 57% → net edge может уйти в ноль после комиссий.
3. **Conditional patterns в OI/funding context** — когда live OI ingest появится.
4. **Размер позиции при cross-asset signal** — sizing rule зависит от n confidence. Pattern C.2 в bear 62%, n=13 — sizing «conservative» (0.05 BTC).

---

## 5. Предупреждение для оператора

- **n=13-34 — пограничная статистика**. Confidence interval широкий. Edge 62% может быть и 45%, и 78% при таком n.
- **Регим определяется самим классификатором с погрешностями**. Если regime_4h ошибочно сказал BEAR — правило применится в неправильных условиях.
- **Mean-reversion edge в BULL/BEAR_CONFLUENCE может исчезнуть** при macro-shift'е (например настоящий парабольный рост). Текущая статистика — за 2024-2026, преимущественно chop / slow trend.

---

## Связанные документы

- [CROSS_ASSET_FINDINGS_2026-05-07.md](CROSS_ASSET_FINDINGS_2026-05-07.md) — исходный analysis (отдельные n, без regime split)
- [CROSS_ASSET_LEADLAG_1M_2026-05-07.md](CROSS_ASSET_LEADLAG_1M_2026-05-07.md) — lead-lag на 1m: NO EDGE
- `state/advise_backtest_v2_785d.summary.json` — raw summary
- `scripts/backtest_advise_v2.py` — rerun с любыми параметрами
