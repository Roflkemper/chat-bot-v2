# ВАРИАНТЫ ВЫХОДА — SHORT 79k / 82.3k / anchor 75.2k
# reconciled v3, 2026-05-06

## §1 Контекст позиции

| Поле | Значение |
|---|---:|
| Entry | 79,036 |
| Current | 82,300 |
| Position | 1.416 BTC |
| Unrealized PnL | -3,572 USD |
| Anchor роста | 75,200 |
| Funding | -0.0082% / 8h |
| Distance to liq | ~18% |

База аналогов одна и та же в обоих прогонах: **406**.  
Ищется тот же setup: рост **75,200 → 82,300** за **6 дней**.  
Разница между v1 и v2 была не в analog search, а в bucket logic и источнике current-factor inputs.

## §2 Reconciliation note

Версии v1 и v2 архивированы в [`_archive/SHORT_EXIT_OPTIONS_2026-05-06_v1.md`](_archive/SHORT_EXIT_OPTIONS_2026-05-06_v1.md) и [`_archive/SHORT_EXIT_OPTIONS_2026-05-06_v2.md`](_archive/SHORT_EXIT_OPTIONS_2026-05-06_v2.md).  
Главный конфликт был в classification текущего setup: v1 давал `vola_compressing + fund_neg`, v2 давал nearest-neighbor группу `stable/stable/funding_near_zero`.  
После reconciliation как source of truth выбрана classification **`vola_compressing + fund_neg`**, потому что funding текущего setup объективно экстремально отрицательный и не должен попадать в `near_zero` bucket.

## §3 Доступные данные

| Source | Что реально доступно | Покрытие | Cadence | Статус в v3 |
|---|---|---|---|---|
| `data/forecast_features/full_features_1y.parquet` | `close`, `volume`, `funding_rate`, `sum_open_interest` | 2025-05-01 → 2026-05-01 | 5m | используется |
| `state/pattern_memory_BTCUSDT_1h_2025.csv`, `...2026.csv` | `open/high/low/close/volume` | 2025-01-01 → 2026-04-30 | 1h | используется для ATR-like sanity |
| `market_live/market_1m.csv` | live `open/high/low/close/volume` | 2026-04-24 → 2026-05-06 | 1m | используется для current setup |
| `market_live/liquidations/*` | recent liquidation tail | 2026-04-28 → 2026-05-03 | event | только availability, не для 406 cases |
| `market_live/orderbook/*` | recent orderbook tail | 2026-04-28 → 2026-05-03 | high-freq | только availability, не для 406 cases |
| `data/regime/BTCUSDT_features_1h.parquet` | auxiliary 1h features | 2024-04-25 → 2026-04-29 | 1h | не нужен для final classification |

Недоступно:

| Gap | Статус |
|---|---|
| full-year trades parquet output | нет |
| full-year orderbook history | нет |
| full-year liquidations history | нет |
| `data/ohlcv/` | нет |
| `data/parquet/` | нет |

## §4 Multi-factor distributions

### Таблица, совпадающая по смыслу между v1 и v2: volatility

| Volatility bucket | Source | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---|---:|---:|---:|---:|---:|
| `compressing` / `сжимается` | v1 | 156 | 8.3% | 18.6% | 46.2% | 26.9% |
| `compressing` + `fund_neg` | v1 | 52 | 0.0% | 46.2% | 53.8% | 0.0% |
| `сжимается` | v2 | 159 | 8.8% | 17.6% | 46.5% | 27.0% |

### Таблица, совпадающая по смыслу между v1 и v2: funding

| Funding bucket | Source | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---|---:|---:|---:|---:|---:|
| `fund_now<0` | v1 | 81 | 0.0% | 53.1% | 46.9% | 0.0% |
| `funding_negative` | v2 | 42 | 0.0% | 59.5% | 40.5% | 0.0% |
| `funding_near_zero` | v2 | 135 | 6.7% | 25.2% | 59.3% | 8.9% |

### Таблица, добавленная v2: volume

| Volume условие | Source | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---|---:|---:|---:|---:|---:|
| `растёт` | v2 | 121 | 5.8% | 44.6% | 25.6% | 24.0% |
| `стабильный` | v2 | 217 | 23.0% | 17.5% | 39.2% | 20.3% |
| `падает` | v2 | 68 | 1.5% | 13.2% | 72.1% | 13.2% |

Сильнее всего разделяющие комбинации:

| Комбинация | Source | n | pullback или anchor | up_extension | sideways |
|---|---|---:|---:|---:|---:|
| `vola_compressing + fund_neg` | v1 | 52 | 53.8% | 46.2% | 0.0% |
| `падает / funding_near_zero / сжимается` | v2 | 47 | 87.2% | 0.0% | 12.8% |
| `растёт / funding_near_zero / расширяется` | v2 | 23 | 17.4% | 82.6% | 0.0% |

## §5 Текущий factor profile

| Factor | v1 | v2 | Reconciled v3 |
|---|---:|---:|---:|
| Volume ratio vs 30d | 0.658 | 4.315x | **4.315x** |
| Volume trend | `flat` | `растёт` | **растёт** |
| Volatility ratio vs 30d | 0.693 | 0.961x | **0.961x** |
| Volatility label | `compressing` | `сжимается` | **сжимается / compressing** |
| Funding point used | -2.9e-05 | operator snapshot -0.0082%/8h | **operator snapshot = negative** |
| Higher highs | 13 | 24 | **24** |
| Final impulse | 0.0% | +1.96% | **+1.96%** |
| Max internal pullback | n/a | 1.94% | **1.94%** |

Sanity checks:

| Check | Результат |
|---|---|
| `volume_ratio 4.315x` bug? | нет, `live 144h mean volume = 2804.97`, `30d baseline = 642.26`, ratio = `4.367x`; цифра реальна |
| `-0.0082%/8h` где в funding distribution? | это `-8.2e-05` decimal, ниже **98.4%** исторических hourly funding points, percentile rank ~**1.6%** |
| `0.961x` volatility ratio это stable или compressing? | по ratio это near-baseline, по внутриоконной динамике second-half std < first-half std, значит **compressing** |
| real OHLC ATR vs proxy | на sample analogs proxy ~`0.282%`, OHLC ATR-like ~`0.547%`, diff ~`0.264pp`; real OHLC materially better |

Итог v3:  
- volume и structure берутся из v2  
- ATR source берётся из v2  
- funding sign для classification берётся из operator snapshot, а не из stale last bar v1  
- bucket label для current setup остаётся **fund_neg**, не `near_zero`

## §6 Ближайшая историческая группа

Выбранная reconciled classification: **`vola_compressing + fund_neg`**.  
Источник: v1 bucket logic, но с v2 sanity checks на current inputs.  
Размер группы: **n=52**.

| Outcome | Reconciled v3 |
|---|---:|
| down_to_anchor | 0.0% |
| up_extension | 46.2% |
| pullback_continuation | 53.8% |
| sideways | 0.0% |

Это и есть финальная группа для probabilities в §7.  
v2 nearest-neighbor группа `stable/stable/funding_near_zero` (`n=38`) сохранена как альтернативный reference, но не выбрана как final.

## §7 Варианты выхода

| Вариант | Trigger | PnL для 1.416 BTC | CP1 | CP2 | Reconciled v3 |
|---|---|---:|---:|---:|---:|
| Stop 82,400 | пробой | -4,763 USD | 94.6% reached | 100.0% reached in v2 primary group | **94.6% reached / 99.2% false breakout of reached** |
| Stop 84,000 | пробой | -7,029 USD | 74.9% reached | 100.0% reached in v2 primary group | **74.9% reached / 51.3% further growth after reach** |
| BE 79,036 | откат | 0 USD | 56.4% reached | 78.9% reached in v2 primary group | **56.4% reached** |
| Exit 77,000 | глубокий откат | +2,883 USD | 35.2% reached | 55.3% reached in v2 primary group | **35.2% reached** |
| Trailing 81/79/77 | partial | median +319 USD | не считался | 55.3% full fill in v2 primary group | **reference only: v2 full fill 55.3%, not used as group probability** |
| Hold до 75,200 | full anchor | +5,432 USD | 14.3% full sample / 0.0% neg-funding subgroup | 0.0% in v2 primary group | **0.0% in reconciled group** |
| Pyramid +1 BTC @83k | breach + add | +3,964 / -20,567 USD median add-on | не считался | 78.9% success after trigger in v2 primary group | **reference only: 78.9% in v2 group, not mapped to v1 bucket** |
| Funding flip | rate→0/+ | depends | 100.0% of neg-funding setups flipped | 100.0% of neg-funding setups flipped | **100.0% flip incidence; after flip median move at flip +1.31%** |

Иллюстративные даты:

| Scenario | Dates |
|---|---|
| `up_extension` | 2025-05-11, 2025-05-12 |
| `down_to_anchor` | 2025-08-11 |
| `pullback_continuation` | 2025-05-10 |

## §8 Что выбор reconciled classification меняет

В v1 текущий setup попадал в `vola_compressing + fund_neg`, `n=52`, с outcome `46.2% up_ext / 53.8% pullback`.  
В v2 nearest-neighbor логика помещала его в `stable/stable/funding_near_zero`, `n=38`, с outcome `21.1% up_ext / 78.9% pullback`.

Главная причина расхождения:  
- v1 использовал **stale current factor point** из последнего бара historical parquet  
- v2 использовал **live current price/volume**, но nearest-neighbor не жёстко уважал текущий negative funding sign

После reconciliation выбран v3:  
- funding bucket обязан быть **negative**, потому что `-0.0082%/8h` находится около **1.6 percentile** годового распределения  
- volatility label `compressing` и `сжимается` по сути совпадают  
- volume anomaly `4.315x` признана реальной, но она не должна автоматически перетаскивать setup в `near_zero funding` группу

## §9 Дополнительные signals для мониторинга

| Signal | Source | n | Outcome |
|---|---|---:|---|
| `oi_fell_>5%` | v1 | 42 | 100.0% pullback_cont, 0.0% up_ext |
| `volume_trend = падает` | v2 | 68 | 72.1% pullback_cont |
| `funding_negative` | v2 | 42 | 59.5% up_ext, 40.5% pullback_cont, 0.0% down |
| `funding flip` after neg-funding setup | v1 | 81 | 100.0% flip incidence, median move at flip +1.31% |
| `volume_ratio > 1.2x` | v2 | 72 | 62.5% down_to_anchor, 8.3% up_ext |
| `vol_up + fund_neg` | v1 | 19 | 100.0% up_ext |

`volume_ratio 4.315x` в текущем setup означает реальную активность сильно выше 30d baseline.  
Это не bug, но это отдельный signal и он не отменяет факт, что current funding sign экстремально negative.

## §10 Что foundation НЕ говорит

- Нет full-year liquidations для всех 406 analog cases  
- Нет full-year orderbook / trades history  
- OHLC для ATR-like есть только на 1h cadence  
- Нет timing predictions  
- Нет trading advice  
- Нет утверждения, что одна exit-схема лучше другой

## §11 Reconciliation findings

| Что | v1 | v2 | Reconciled v3 | Обоснование |
|---|---|---|---|---|
| Funding bucket boundary | `fund_now<0` vs `>=0` | `funding_negative < -5e-5`, `near_zero`, `positive` | **current setup = fund_neg** | `-8.2e-05` находится около 1.6 percentile, operationally это negative, не near_zero |
| Funding input for current setup | last historical bar from 1y parquet (`-2.9e-05`) | operator snapshot `-0.0082%/8h` | **operator snapshot** | он новее и относится именно к текущей позиции |
| Volatility classification | `compressing` | `сжимается` | **одно и то же** | разница в ярлыке, не в сути |
| Volume ratio | не использовался, stale profile дал `0.658` | live profile дал `4.315x` | **используется** | проверено отдельно: `2804.97 / 642.26 = 4.367x`, bug нет |
| ATR source | close-to-close proxy | real OHLC from `pattern_memory_*.csv` | **real OHLC** | sample diff ~`0.264pp`, proxy заметно занижает |
| Higher highs | 13 | 24 | **24** | v2 использует live setup window, v1 считал stale historical endpoint |
| Closest group n | 52 | 38 | **52** | v2 nearest-neighbor нарушал intuitive funding sign consistency |
| Current outcome split | `46.2/53.8/0/0` | `21.1/78.9/0/0` | **46.2/53.8/0/0** | chosen because funding bucket is reconciled as negative |

