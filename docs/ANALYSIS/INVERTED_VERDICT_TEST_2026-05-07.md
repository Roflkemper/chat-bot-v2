# Inverted Verdict Test — гипотеза не подтверждается

**Дата**: 2026-05-07
**Метод**: 785-дневный backtest, шаг 1ч, 17,619 точек. Сравнение original verdict-логики и инвертированной (fade-trend).
**Скрипт**: `scripts/backtest_advise_inverted.py`
**Raw**: `state/advise_inverted_test_785d.json`

---

## Гипотеза

Утром мы выяснили что текущий /advise verdict проигрывает (BULL/BEAR_CONFLUENCE accuracy 31-32% на 4h). Гипотеза: если **инвертировать** verdict (BULL → SHORT, BEAR → LONG, как fade-trend), получим 68-69% mean-reversion edge.

## Результат

| Verdict | Regime | n | Original 4h | Inverted 4h | Original 24h | Inverted 24h |
|---|---|---|---|---|---|---|
| BULL_CONFLUENCE | BULL | 4736 | 30.8% | **29.9%** ❌ | 42.5% | 41.2% |
| BEAR_CONFLUENCE | BEAR | 4181 | 31.9% | **34.3%** ⚠️ | 40.2% | **46.4%** |
| MACRO_BULL_MICRO_PULLBACK | BULL | 258 | 40.3% | 26.4% | 49.6% | 33.3% |
| MACRO_BEAR_MICRO_RALLY | BEAR | 325 | 33.2% | 34.5% | 38.5% | **51.1%** ✅ |
| RANGE | RANGE | 5132 | **57.2%** ✅ | 57.2% | 23.8% | 23.8% |

## Анализ

**Гипотеза НЕ подтверждается**.

1. **BULL_CONFLUENCE inversion даёт 29.9%** vs original 30.8% — **хуже**. Если бы trend-following honestly давал 31% (ниже монетки), fade должен был давать ~69%. Получили 30%. Значит цена **не движется в каком-либо направлении предсказуемо** в этих условиях, она просто **размазана**.

2. **9% "мёртвая зона"** (|move| < 0.3%) объясняет что 31+30=61%, а не 100%. На остальных 91% случаев цена двигается **случайно** туда-сюда.

3. **MACRO_BEAR_MICRO_RALLY на 24h = 51.1% inverted** — единственный честный mean-reversion edge, но крошечный (51% vs монетка).

4. **RANGE/RANGE 57%** на 4h остаётся единственным реальным edge (non-directional — предсказывает что цена **не уйдёт** далеко).

## Что это значит

**На 4h-окне current regime classifier alone не имеет direction-edge ни в каком виде** — ни trend-following, ни mean-reversion. Это **brutal honest finding**.

Возможные причины:
- 4h слишком короткое окно для multi-TF regime signals
- Regime classifier помогает только определить "type of price action" (trend / range), но не direction
- Нужны **дополнительные сигналы** (OI flip, funding extreme, structural break, cross-asset divergence) чтобы получить edge — regime один себе недостаточен.

## Что делать

**Не зашиваем инвертирование**. Не зашиваем cross-asset правила в чистом виде (тоже потеряли edge на larger sample).

**Что имеет смысл**:

1. **RANGE-as-no-trade gate**: когда verdict=RANGE и regime_4h=RANGE — `/advise` показывает "сейчас 57% что цена останется в боковике 4h, не открывать новые позиции". Это слабый, но честный edge.

2. **Multi-signal confluence**: только когда regime + OI flip + structural break **совпадают**, считать direction-bias. Нужно сначала собрать **outcomes для каждой confluence** на back-data, прежде чем зашивать.

3. **Different time horizons**: возможно на **1h** или **24h** classifier работает лучше. Backtest на этих окнах — следующий вопрос.

4. **Использовать live OI/funding которые мы только что подключили** — теперь advisor v2 видит свежие данные. Возможно OI flip + regime confluence даст edge.

## Связанные документы

- [BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md](BACKTEST_V2_REGIME_CONDITIONAL_2026-05-07.md) — оригинал backtest 785d с cross-asset
- [CROSS_ASSET_FINDINGS_2026-05-07.md](CROSS_ASSET_FINDINGS_2026-05-07.md) — cross-asset patterns
- `state/advise_inverted_test_785d.json` — raw data
