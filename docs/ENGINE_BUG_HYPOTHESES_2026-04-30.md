# ENGINE_BUG_HYPOTHESES_2026-04-30

**TZ:** TZ-ENGINE-BUG-INVESTIGATION  
**Дата:** 2026-04-30  
**Движок:** `C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src\backtest_lab\engine_v2`  
**Инструмент:** `c:\bot7\tools\calibrate_ginarea.py`  
**Данные:** `c:\bot7\docs\calibration\CALIBRATION_VS_GINAREA_2026-04-30.md`  
**Правило:** только анализ. Продакшн-код не трогаем.

---

## Фактические данные из калибровки (2026-04-30 10:36 UTC)

| Dir | TD | sim_realized | ga_realized | K_realized | sim_volume | ga_volume | K_volume |
|---|---|---:|---:|---:|---:|---:|---:|
| SHORT | 0.19 | **-63.86** | 31,746.86 | **-497.11** | 2,976,253 | 52,666,201 | 17.70 |
| SHORT | 0.21 | +130.23 | 34,791.83 | +267.15 | 2,890,302 | 48,937,853 | 16.93 |
| SHORT | 0.25 | **-384.13** | 38,909.93 | **-101.29** | 3,850,847 | 42,780,857 | 11.11 |
| SHORT | 0.30 | +1,129.06 | 42,616.75 | +37.75 | 3,398,953 | 37,010,264 | 10.89 |
| SHORT | 0.35 | +1,339.32 | 46,166.43 | +34.47 | 3,184,523 | 33,000,181 | 10.36 |
| SHORT | 0.45 | +1,499.71 | 49,782.51 | +33.19 | 3,307,296 | 26,676,981 | 8.07 |
| LONG | 0.25 | **-0.1530** | +0.1249 | **-0.82** | 3,865,200 | 14,211,200 | 3.68 |
| LONG | 0.30 | **-0.1551** | +0.1336 | **-0.86** | 3,873,800 | 12,207,600 | 3.15 |
| LONG | 0.45 | **-0.1559** | +0.1542 | **-0.99** | 3,956,600 | 8,344,000 | 2.11 |

**Наблюдения:**
1. SHORT при td < 0.30: sim_realized меняет знак (отрицательный или едва положительный). При td ≥ 0.30: стабильный K_realized ≈ 33-38.
2. LONG во всех трёх TD: sim_realized отрицательный, ga_realized положительный. K_realized ≈ -0.82 до -0.99 (близко к -1 — почти зеркально).
3. K_volume для SHORT (8-18) в 4x больше, чем для LONG (2-4). Обе группы имеют схожий объём на ордер, поэтому 4x разрыв требует объяснения.

---

## Anomaly A — SHORT K_realized нестабилен и меняет знак при td < max_stop

### Hypothesis A1: Начальный combo_stop выше entry для SHORT с td < max_stop

**Why suspect:**  
Для SHORT `OutStopGroup.from_triggered` (`group.py:40-48`):  
```python
init_stop = extreme * (1.0 + max_stop_pct / 100.0)
```  
где `extreme ≈ trigger_price = entry × (1 − td%)`.

Итого: `combo_stop_init = entry × (1−td%) × (1+max_stop%) ≈ entry × (1 + max_stop − td)`

- Если `td < max_stop (0.30%)`: combo_stop_init > entry. Немедленный разворот после тригера → группа закрывается выше entry → **SHORT ЗАКРЫВАЕТСЯ В УБЫТОК** (для LINEAR: PnL = qty × (entry − close), close > entry → PnL < 0).
- Если `td > max_stop (0.30%)`: combo_stop_init < entry → немедленный разворот = прибыль.

Данные подтверждают:
| TD | td > max_stop? | sim_realized |
|---|---|---|
| 0.19 | НЕТ | -63.86 (убыток) |
| 0.21 | НЕТ | +130 (нестабильно) |
| 0.25 | НЕТ | -384.13 (убыток) |
| 0.30 | **ГРАНИЦА** | +1,129 (разворот в прибыль) |
| 0.35 | ДА | +1,339 (стабильно) |
| 0.45 | ДА | +1,499 (стабильно) |

Граничный TD точно совпадает с max_stop_pct = 0.30% (`calibrate_ginarea.py:43`).

**Proposed fix (НЕ делаем в этом TZ):**  
`group.py:41` — для SHORT зафиксировать: `init_stop = min(extreme * (1 + max_stop%), entry_price)`. Либо поднять min_stop_pct до уровня, где combo_stop_init ≤ entry. Альтернатива: документировать что max_stop_pct должен быть ≤ td для корректной работы.

**Test to verify:**  
Синтетический тест: SHORT LINEAR, entry=80000, td=0.25, max_stop=0.30. Один ордер триггерится, цена немедленно возвращается к combo_stop_init = 79800 × 1.003 = 80039. Проверить: `realized_pnl < 0`. Затем тот же тест с td=0.35: combo_stop_init = 79720 × 1.003 = 79959 < 80000. Проверить: `realized_pnl > 0`.

---

### Hypothesis A2: verdict() некорректно классифицирует отрицательный CV как STABLE

**Why suspect:**  
`calibrate_ginarea.py:212-219`:
```python
def verdict(cv: Optional[float]) -> str:
    if cv is None:
        return "UNKNOWN"
    if cv < 15:
        return "STABLE"
    ...
```

Из калибровки: CV(K_realized для SHORT) = -676.2% (`group_stats` → std/mean × 100 = 254/(-37.6) × 100 = -676%).

Поскольку -676 < 15, функция возвращает "**STABLE**" — и рекомендует использовать K = -37.641 как множитель. Это **ложный вердикт**: стабильность определяется по |CV|, а не по CV. Отрицательный CV возникает когда mean < 0 (знаки разнятся между ботами), что само по себе признак FRACTURED.

Calibration report (строка 66): `"CV=-676.2% → STABLE → Use K = -37.641 as fixed calibration multiplier."` — полностью ошибочный вывод.

**Proposed fix:**  
`calibrate_ginarea.py:213`: проверять `abs(cv) < 15` вместо `cv < 15`. Дополнительно: если mean и min/max имеют разные знаки (знакоизменение) — принудительный вердикт "FRACTURED" с пояснением "sign flip detected".

**Test to verify:**  
`test_calibrate_ginarea.py` — добавить тест:  
```python
def test_verdict_negative_cv_is_not_stable():
    # CV = -676 (std=254, mean=-37.6) должен быть FRACTURED, не STABLE
    assert verdict(-676.2) != "STABLE"
```
Текущий тест `test_verdict_boundary_15` проверяет только +14.99/+15, не покрывает отрицательные значения.

---

### Hypothesis A3: normalized_sim_realized в CalibRow всегда 0.0

**Why suspect:**  
`calibrate_ginarea.py:364`:
```python
rows.append(CalibRow(
    ...
    normalized_sim_realized=0.0,  # filled below
))
```

Комментарий "filled below" вводит в заблуждение — заполнения нет. Цикл `for i, cfg in enumerate(GINAREA_GROUND_TRUTH):` заканчивается, поле остаётся 0.0. Нормализация (`r.sim_realized * k_mean`) вычисляется ТОЛЬКО INLINE в `write_report()` (строки 292-293), но не записывается обратно в CalibRow.

Следствие: любой потребитель `CalibRow.normalized_sim_realized` (включая тест `test_normalized_within_20pct_of_ga`) получает 0.0 из объектов, построенных через `main()`. Тест создаёт row вручную (`normalized_sim_realized=sim_realized * k_realized`), обходя баг, но проверяет ДРУГУЮ формулу (individual K vs group mean K).

**Proposed fix:**  
После построения групп (`groups[...]`), пройти по всем rows и заполнить поле:
```python
for gname, gdata in groups.items():
    k_mean = gdata["k_realized"]["mean"] or 0.0
    for r in gdata["rows"]:
        r.normalized_sim_realized = r.sim_realized * k_mean
```

**Test to verify:**  
Запустить `main()` на 2 синтетических записях (мок OHLCV, 1 bar). Проверить: для каждого CalibRow в результате `normalized_sim_realized != 0.0` и `normalized_sim_realized == r.sim_realized * group_mean_k`.

---

## Anomaly B — LONG sign error

**Контекст:** Все 3 LONG INVERSE бота: sim_realized ≈ −0.153 BTC, ga_realized ≈ +0.125 BTC. Коэффициент K ≈ −1 (при td=0.45: K = −0.99 → |ga|/|sim| = 0.989 ≈ 1). Это не масштабная ошибка, а знаковая: движок вычисляет почти точно правильную ВЕЛИЧИНУ PnL, но с ОБРАТНЫМ ЗНАКОМ.

### Hypothesis B1: Начальный combo_stop НИЖЕ entry для LONG — убытки при немедленном развороте

**Why suspect:**  
`group.py:53-55` для LONG:
```python
init_stop = extreme * (1.0 - max_stop_pct / 100.0)
```
где `extreme ≈ trigger_price = entry × (1 + td%)`.

`combo_stop_init = entry × (1+td%) × (1−max_stop%) ≈ entry × (1 + td − max_stop)`

Для LONG td=0.25%, max_stop=0.30%:  
`combo_stop_init = entry × (1 + 0.0025 − 0.003) = entry × 0.9995 < entry`

При немедленном развороте после тригера → группа закрывается НИЖЕ entry → для INVERSE:  
`pnl = qty × (1/entry − 1/close_price)`. Если `close_price < entry`: `1/close > 1/entry` → pnl < 0 → **УБЫТОК**.

В отличие от SHORT (где проблема начинается при td < max_stop), для LONG:  
При td=0.45%, max_stop=0.30%: combo_stop_init = entry × (1+0.0045−0.003) = entry × 1.0015 > entry → немедленный разворот должен давать ПРИБЫЛЬ.

Но данные показывают K = -0.99 при td=0.45, т.е. sim_realized ОТРИЦАТЕЛЬНЫЙ. Значит, здесь действует дополнительный механизм, не только combo_stop_init. Гипотеза B1 объясняет часть убытков (при td=0.25, 0.30), но не всё.

**Proposed fix:**  
Для LONG: `init_stop = max(extreme × (1−max_stop%), entry_price)` — гарантировать, что stop не ниже entry при открытии группы.

**Test to verify:**  
INVERSE LONG, entry=80000, td=0.25%, max_stop=0.30%. Trigger fires at 80200. Цена сразу падает до 79960 (combo_stop_init). Проверить: `realized_pnl < 0` (баг воспроизведён). После фикса: проверить `realized_pnl >= 0` при той же траектории.

---

### Hypothesis B2: Индикатор LONG срабатывает на спаде — бот систематически открывается в начале нисходящих волн

**Why suspect:**  
`indicator.py:38-40`:
```python
if self.side == Side.SHORT:
    return v > self.threshold_pct
return v < -self.threshold_pct  # LONG: fires when price FELL by threshold over period
```

LONG бот активируется когда цена упала на >0.3% за 30 баров. В боковом/медвежьем рынке BTC (часть 2025-2026) это может означать: бот начинает аккумуляцию в середине нисходящего тренда → стопы срабатывают раньше, чем цена восстанавливается.

Для GinArea: возможно, LONG INVERSE бот у GinArea активируется по ДРУГОМУ условию (рост цены: v > threshold), т.е. стратегия "лонг на трендовом росте". В этом случае sim-движок активирует LONG не тогда, когда GinArea, и открывает позиции в противоположной фазе рынка.

Если GinArea-индикатор для LONG = `v > threshold` (симметрично SHORT):
- GinArea LONG: активируется на росте (SHORT momentum)
- Sim LONG: активируется на спаде  
- GinArea набирает позицию ВНИЗ по тренду роста (успешно)  
- Sim набирает позицию на продолжающемся спаде (убыточно)

**Proposed fix:**  
`indicator.py:40`: для LONG изменить на `return v > self.threshold_pct` (симметрично SHORT). Верифицировать с оператором, какую именно стратегию имитирует GinArea LONG бот.

**Test to verify:**  
Синтетический бар-массив: 30 баров роста (цена +0.3%), затем откаты. При текущей логике (v < -threshold): бот НЕ активируется (цена выросла, не упала). При изменённой логике (v > threshold): бот активируется после 30 баров роста. Сравнить trade_count за тест-период.

---

### Hypothesis B3: unrealized_pnl для INVERSE LONG суммируется с wrong base при комбинированных ордерах

**Why suspect:**  
`bot.py:331-348` (`_open_in`): при `combined_count > 1` создаётся один InOrder с `qty = order_size × combined_count`. В `group.py:155-160` при закрытии:
```python
pnl = self.contract.unrealized_pnl(
    self.side, order.qty, order.entry_price, close_price
)
```

Для INVERSE: `pnl = qty × (1/entry − 1/close)`. При combined_count=3 и entry=80000:  
`pnl = (3 × 200) × (1/80000 − 1/close) = 600 × ...`

Но настоящий `entry_price` комбинированного ордера — это `last_in_price` в момент открытия, а не взвешенное среднее. Если за один такт были пропущены уровни 79900, 79800, 79700, а combined открылся на 79700 — весь совокупный объём (600 контрактов) оценивается по 79700, хотя "настоящие" 200 контрактов должны быть на 79900, 200 на 79800, 200 на 79700.

Для INVERSE это создаёт систематическую ошибку: если combined_count > 1, PnL считается по САМОЙ НИЗКОЙ цене входа (худшей для LONG), занижая прибыль и увеличивая убытки.

**Proposed fix:**  
При combined ордере в `_open_in`: создавать несколько отдельных InOrder по каждому уровню, а не один combined. Или хранить список `[(qty_i, entry_i)]` внутри InOrder и суммировать PnL по каждому уровню отдельно.

**Test to verify:**  
Два сценария с identical total qty: (a) один combined InOrder qty=600 entry=79700; (b) три раздельных InOrder qty=200 entry=79900/79800/79700. Оба закрываются на 80000. Ожидаемый PnL (b) > PnL (a) для LONG INVERSE. Если (a)=(b) — баг отсутствует. Если (a) < (b) — баг подтверждён.

---

## Anomaly C — K_volume gap: LINEAR (12.5x) vs INVERSE (3.0x)

**Контекст:** При схожем размере ордеров в USD (~225 USD для SHORT vs 200 USD для LONG), коэффициент K_volume (GA/sim) в 4x больше для SHORT LINEAR (12.5) чем для LONG INVERSE (3.0). sim_volume для обоих ≈ 3.8-3.9M в их единицах (USDT vs USD). ga_volume: SHORT 26-52M vs LONG 8-14M.

### Hypothesis C1: notional_usd для INVERSE не учитывает цену — sim_volume недооценён при высоких ценах

**Why suspect:**  
`contracts.py:93-94`:
```python
def notional_usd(self, qty: float, price: float) -> float:
    return qty  # 1 contract = $1
```

Для LINEAR (`contracts.py:57`): `return qty * price`. Это корректно: 0.003 BTC × 80000 = 240 USDT за ордер.

Для INVERSE: `notional_usd = qty = 200` USD. Это корректно (1 контракт XBTUSD = $1, всегда). **НО:** GinArea может считать объём ИНАЧЕ — как BTC-эквивалент: `notional_BTC = qty / price = 200/80000 = 0.0025 BTC`, затем умножить на цену: 0.0025 × 80000 = 200 — в итоге то же самое. Противоречия нет.

Альтернатива: GinArea считает INVERSE volume как `qty_USD_contracts × BTC_price_at_trade`. Т.е. для 200 контрактов при цене 80000: 200 × 80000 = 16,000,000 USD за ордер — это нереально много и противоречит ga_volume ≈ 14M за весь год.

**Вывод:** Hypothesis C1 вероятно НЕ подтверждается — единицы объёма совпадают. Требует проверки, какие именно единицы GinArea показывает для LONG volume.

**Test to verify:**  
Расчёт от обратного: `ga_volume/n_triggers_est` для LONG = 14,211,200 / (582_GA_triggers × 2_sides) ≈ 14M/1164 ≈ 12,210 USD per trigger. Для LONG order_size=200: 12,210/200 = 61 orders per close event — нереально много. Либо GinArea LONG triggers << 582, либо единицы объёма не USD-контракты.

---

### Hypothesis C2: GinArea считает LONG volume как BTC-нотионал (qty/price), sim считает USD (qty)

**Why suspect:**  
Различие между LINEAR и INVERSE в том, как рассчитывается "объём" позиции:
- SHORT LINEAR: объём = qty_BTC × price_USD → растёт с ценой BTC
- LONG INVERSE: объём = qty_USD_contracts (фиксирован) → НЕ зависит от цены

Если GinArea для INVERSE отображает volume как `face_value_BTC × price = (qty/price) × price = qty` — то же самое. НО: если GinArea показывает volume в BTC-единицах (qty/price), а симуляция добавляет `sim_volume += qty`:
- При entry=80000: sim добавляет +200 USD, GinArea записывает 200/80000 = 0.0025 BTC.
- ga_volume_BTC = 0.0025 × N_trades, при N_trades = 5,684,480 трейдов/год → нереально.

**Вывод:** Гипотеза требует знания того, в каких единицах GinArea экспортирует volume для INVERSE.  
Конкретный проверяемый тест: сравнить `ga_volume / ga_realized` отношение для SHORT vs LONG:
- SHORT td=0.25: 42.8M / 38,909 ≈ 1,100 (USDT volume per USDT profit)
- LONG td=0.25: 14.2M USD / 0.1249 BTC ≈ 113,700,000 USD/BTC — абсурдно, если оба в одних единицах

Если га_volume для LONG в BTC: 14,211,200 BTC → ещё хуже. Вывод: скорее всего ga_volume для LONG — это USD, и 14.2M USD объём за год на INVERSE bot — реалистично.

**Test to verify:**  
Запустить симуляцию только на 100 барах (тестовый OHLCV, 1 LONG INVERSE ордер). Посчитать вручную sim_volume = qty_contracts для каждого fill. Сравнить с ожидаемым GinArea: тот же round-trip ≈ qty_contracts × 2 (in+out). Подтвердить, что единицы совпадают.

---

### Hypothesis C3: Tick-level inflation ratio фундаментально разный для LINEAR vs INVERSE

**Why suspect:**  
K_volume = ga_volume / sim_volume отражает, сколько ДОПОЛНИТЕЛЬНЫХ заполнений тик-уровень добавляет по сравнению с 1m барами. Для SHORT (grid step 0.03%, instop 0.03%): каждую минуту BTC может пройти несколько уровней сетки на тике — высокая частота. Для LONG (td=0.25%, grid step 0.03%, instop 0.018%): аналогичная структура.

Но `out_qty_notional` для LONG INVERSE использует `contract.notional_usd(o.qty, price) = o.qty` (`bot.py:238`). При КАЖДОМ close за day GinArea может иметь N tick-exits, а sim только M bar-exits, M << N. Если для INVERSE каждый "группа-close" в sim считается как один exit, а GinArea фиксирует несколько exit'ов внутри одной сессии, sim недооценивает число выходов.

НО для LINEAR та же проблема. Разница в K_volume (12x vs 3x) может быть обусловлена тем, что GinArea LONG INVERSE практически не срабатывает часто — большинство LONG позиций висят в просадке долго (unrealized < 0) и не генерируют объём. Это объяснило бы меньший ga_volume у LONG и меньший K_volume.

**Proposed fix:** Нет — это фундаментальное рыночное поведение, не баг движка.

**Test to verify:**  
Вычислить `out_count` для LONG и SHORT по реальному запуску:
- SHORT td=0.25: sim_trades=1,759 → out_count ≈ аналогично  
- LONG td=0.25: sim_trades=1,739 → схожий out_count  

Если out_count схожий, но K_volume разный (3.68 vs 11.11), проблема в ga_volume (GinArea считает по-разному для CONTRACT типов). Проверить напрямую в GinArea UI: что именно показывает "volume" для SHORT vs LONG бота.

---

## Рекомендованный порядок фиксов

1. **A2 (verdict bug) — наивысший приоритет, наименьший риск.** Однострочный фикс `abs(cv)`. Добавить тест на отрицательный CV. Баг активно вводит в заблуждение (выдаёт STABLE для бессмысленного K).

2. **A1 (SHORT combo_stop_init > entry) + B1 (LONG combo_stop_init < entry) — общий root cause.** Условие `td < max_stop_pct` создаёт систематическое смещение. Требует изменения инициализации combo_stop в `group.py:40-55`. Высокая уверенность — подтверждается данными.

3. **A3 (normalized_sim_realized = 0.0) — простой фикс в main().** Добавить цикл заполнения поля после построения групп. Влияет на API CalibRow.

4. **B2 (индикатор LONG direction) — требует подтверждения от оператора** что GinArea LONG срабатывает на росте, а не спаде. Нельзя фиксить без подтверждения семантики.

5. **B3 (combined ордер PnL base price) — средняя уверенность.** Нужно воспроизвести в изолированном unit-тесте.

6. **C1/C2/C3 (K_volume unit mismatch) — требует инспекции GinArea UI** для выяснения единиц volume. До того — не фиксить движок.

---

## Synthetic test cases (для TZ-ENGINE-BUG-FIX)

### TC-1: SHORT LinearContract, combo_stop sign test

```python
"""Проверяет: для SHORT с td < max_stop, немедленный разворот = убыток.
   Для td > max_stop, немедленный разворот = прибыль."""
from backtest_lab.engine_v2.contracts import LINEAR, Side
from backtest_lab.engine_v2.group import OutStopGroup
from backtest_lab.engine_v2.order import InOrder, OrderState

def make_short_order(entry, td_pct, min_stop_pct, max_stop_pct, qty=0.003):
    order = InOrder(
        order_id=1, side=Side.SHORT,
        grid_level_price=entry, qty=qty,
        target_profit_pct=td_pct,
        min_stop_pct=min_stop_pct,
        max_stop_pct=max_stop_pct,
        state=OrderState.PENDING_INSTOP,
    )
    order.activate(entry, bar_idx=0)
    order.set_triggered()
    return order

# td=0.25 < max_stop=0.30 → combo_stop_init > entry → close at combo_stop = LOSS
entry = 80000.0
order = make_short_order(entry, td_pct=0.25, min_stop_pct=0.01, max_stop_pct=0.30)
trigger_price = entry * (1 - 0.0025)   # 79800
combo_stop_init = trigger_price * (1 + 0.003)  # 80039 > entry
group = OutStopGroup.from_triggered([order], trigger_price, LINEAR)
# Immediate reversal: price goes to combo_stop_init
pnl = LINEAR.unrealized_pnl(Side.SHORT, order.qty, entry, combo_stop_init)
assert pnl < 0, f"Expected LOSS for SHORT td<max_stop, got {pnl}"  # FAILS currently

# td=0.45 > max_stop=0.30 → combo_stop_init < entry → close at combo_stop = PROFIT
order2 = make_short_order(entry, td_pct=0.45, min_stop_pct=0.01, max_stop_pct=0.30)
trigger2 = entry * (1 - 0.0045)  # 79640
combo_stop2 = trigger2 * (1 + 0.003)  # 79879 < entry
pnl2 = LINEAR.unrealized_pnl(Side.SHORT, order2.qty, entry, combo_stop2)
assert pnl2 > 0, f"Expected PROFIT for SHORT td>max_stop, got {pnl2}"
```

### TC-2: LONG InverseContract, sign on immediate reversal

```python
"""Проверяет: для LONG INVERSE, режим когда большинство группа-closes происходит
   ниже entry → net realized_pnl отрицательный."""
import sys
sys.path.insert(0, r"C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src")
from backtest_lab.engine_v2.bot import GinareaBot, BotConfig, OHLCBar
from backtest_lab.engine_v2.contracts import INVERSE, Side

# Синтетический рынок: цена растёт на td%, немедленно разворачивается на max_stop%
# Repeats 100 times. Ожидаем: net realized_pnl < 0 (баг) или > 0 (ок после фикса)
cfg = BotConfig(
    bot_id="test", alias="test",
    side=Side.LONG, contract=INVERSE,
    order_size=200.0, order_count=10,
    grid_step_pct=0.03, target_profit_pct=0.25,
    min_stop_pct=0.01, max_stop_pct=0.30, instop_pct=0.0,
    boundaries_lower=10_000.0, boundaries_upper=999_999.0,
    indicator_period=1, indicator_threshold_pct=0.001,
    dsblin=False, leverage=100,
)
bot = GinareaBot(cfg)

entry_price = 80000.0
# Simulate indicator trigger, then 100 up-then-immediately-down cycles
bars = []
# First bar: indicator trigger (price fell 0.001%)
bars.append(OHLCBar("2025-01-01T00:00:00+00:00", entry_price, entry_price,
                    entry_price * (1 - 0.00001), entry_price * (1 - 0.00001)))

# For instop=0, open immediately. First grid level below entry.
grid_level = entry_price * (1 - 0.0003)  # 79976
trigger_price = grid_level * (1 + 0.0025)  # 80176

for i in range(100):
    # Bearish bar: price falls to grid level, then rises to trigger
    bars.append(OHLCBar(
        f"2025-01-01T{i:02d}:01:00+00:00",
        entry_price,       # open
        trigger_price * 1.001,  # high (triggers LONG exit)
        grid_level * 0.999,     # low (LONG entry)
        entry_price,            # close
        volume=1.0,
    ))
    # Price falls back to combo_stop territory
    bars.append(OHLCBar(
        f"2025-01-01T{i:02d}:02:00+00:00",
        entry_price,
        entry_price * 1.0001,
        entry_price * 0.9995,   # below entry = forces close via combo_stop
        entry_price * 0.9996,
        volume=1.0,
    ))

for idx, bar in enumerate(bars):
    bot.step(bar, idx)

print(f"LONG realized_pnl: {bot.realized_pnl:.6f} BTC")
# Expected after fix: > 0. Currently produces < 0.
assert bot.realized_pnl < 0, "Bug TC-2 confirmed: LONG net realized < 0 on immediate reversals"
```

### TC-3: verdict() с отрицательным CV

```python
"""Проверяет: verdict() не должна возвращать STABLE для отрицательного CV.
   Отрицательный CV означает отрицательное среднее — sign flip в группе."""
from tools.calibrate_ginarea import verdict, group_stats

# K_realized с разными знаками — признак sign flip
ks_sign_flip = [-497.11, 267.15, -101.29, 37.75, 34.47, 33.19]
st = group_stats(ks_sign_flip)
print(f"mean={st['mean']:.2f}, cv={st['cv']:.1f}%")
# Текущее поведение (баг): cv < 15 → "STABLE"
assert st["cv"] < 0              # negative CV (negative mean)
assert verdict(st["cv"]) != "STABLE", \
    "BUG: negative CV (sign flip group) should NOT be STABLE"  # FAILS currently

# Корректный вердикт должен быть FRACTURED (|CV| >> 35)
assert verdict(st["cv"]) == "FRACTURED"

# Дополнительно: знакоизменяющаяся группа = принудительный FRACTURED
min_k, max_k = min(ks_sign_flip), max(ks_sign_flip)
assert min_k < 0 < max_k, "Sign flip confirmed"
# → в write_report должны показать FRACTURED SIGN FLIP, не STABLE
```

---

## Статус тестов после анализа

```
pytest tests/ -q  (c:\bot7)
# baseline: 585 passed, 11 failed
# после написания этого документа: 0 изменений в prod-коде
# новых тестовых файлов не создано
# → no new failures vs baseline 585/11
```

Synthetic test cases описаны выше как PYTHON SNIPPETS — они НЕ добавлены в `tests/` пока, ждут TZ-ENGINE-BUG-FIX.

---

## Инвентарь файлов (для TZ-ENGINE-BUG-FIX)

| Файл | Строки | Проблема |
|---|---|---|
| `engine_v2/group.py` | 40-55 | `init_stop` SHORT/LONG: combo_stop_init по неправильной стороне от entry |
| `engine_v2/contracts.py` | 98-101 | INVERSE unrealized_pnl LONG: проверить знак на рыночных данных |
| `tools/calibrate_ginarea.py` | 212-219 | `verdict()`: отрицательный CV → ложный STABLE |
| `tools/calibrate_ginarea.py` | 364 | `normalized_sim_realized=0.0` — никогда не заполняется |
| `engine_v2/indicator.py` | 40 | LONG `v < -threshold`: верифицировать с оператором |
| `engine_v2/bot.py` | 334 | `_open_in` combined_count: один InOrder для N уровней = усреднение по низшей цене |
