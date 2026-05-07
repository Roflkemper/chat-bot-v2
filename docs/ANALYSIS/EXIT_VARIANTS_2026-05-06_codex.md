# 3 ВАРИАНТА СНИЖЕНИЯ ПОТЕРЬ — SHORT BTC 79,036 / 82,300 / 75,200

Контекст:
позиция `1.416 BTC`, entry `79,036`, current `82,300`, unrealized `-$3,572`.
Reconciled foundation: группа `vola_compressing + fund_neg`, `n=52`, исходы `46.2% up_extension / 53.8% pullback_continuation / 0.0% down_to_anchor / 0.0% sideways`.

## Вариант 1 — Защитная лестница на adverse continuation

| Что вижу | Приём | Уровень/Параметр | Шаг 1 | Шаг 2 | Шаг 3 |
|---|---|---|---|---|---|
| Цена пробивает текущую зону | закрыть часть/всё по stop logic | 82,400 | PnL `-$4,763` | reached в общей базе `94.6%` | further growth после пробоя `78.9%` |
| Пробой продолжается | следующий защитный уровень | 84,000 | PnL `-$7,029` | reached `74.9%` | further growth `51.3%` |
| Пробой уходит выше | финальный cap-loss уровень | 85,000 | PnL `-$8,445` | reached `47.5%` | further growth `46.6%` |

**Условия применимости:** цена идёт по ветке `up_extension`, а не по ветке отката.  
**Ожидаемый PnL спектр:** best `-$4,763` / median `-$7,029` / worst `-$8,445`.  
**Probability success:** `46.2%` adverse branch по reconciled группе `n=52`; внутри общего stop-study пробой `82,400` встречался в `94.6%` всех 406 аналогов.  
**Foundation основа:** reconciled group `vola_compressing + fund_neg`, `n=52`; `vol_up + fund_neg`, `n=19`, дал `100.0% up_extension`; sample dates `2025-05-10`, `2026-04-10`.

## Вариант 2 — Opportunistic pullback ladder

| Что вижу | Приём | Уровень/Параметр | Шаг 1 | Шаг 2 | Шаг 3 |
|---|---|---|---|---|---|
| Частичный откат | частичный exit в первом tier | 80,000 | PnL `-$1,365` | reached `64.3%` | reverse-up после касания `93.5%` |
| Полный возврат к entry | flat / BE tier | 79,036 | PnL `$0` | reached `56.4%` | reverse-up `92.6%` |
| Глубокий pullback | финальный profit tier | 77,000 | PnL `+$2,883` | reached `35.2%` | reverse-up `90.9%` |

**Условия применимости:** price branch переходит в `pullback_continuation`, а OI не растёт.  
**Ожидаемый PnL спектр:** best `+$2,883` / median `$0` / worst `-$1,365`.  
**Probability success:** `53.8% pullback_continuation` по reconciled группе `n=52`; для OI divergence bucket `n=96` доля `pullback_continuation` = `84.4%`; для `OI падает >5%` `n=42` доля = `100.0%`.  
**Foundation основа:** overall pullback levels из 406 analogs; OI buckets `n=96` и `n=42`; sample dates `2025-05-23`, `2026-04-17`.

## Вариант 3 — Hybrid contingent: price + OI + funding

| Что вижу | Приём | Уровень/Параметр | Шаг 1 | Шаг 2 | Шаг 3 |
|---|---|---|---|---|---|
| Откат к 81k без OI роста | включить trailing scheme | `30% @81k / 30% @79,036 / 40% @77k` | expected PnL `-$12,828` в общей базе | full fill `35.2%` | partial fill `50.5%` |
| Funding flips к `≥ 0` | перевести сценарий в branch re-evaluation | funding flip | flip встречался в `100.0%` neg-funding setups | after flip `53.1% up_extension` | after flip `46.9% pullback_cont` |
| OI уходит в `down >5%` или остаётся divergence | удерживать pullback-ветку | OI bucket | `100.0% pullback_cont` на `n=12` при `OI down + fund_neg + compressing` | `100.0% pullback_cont` на `n=8` при `OI flat + fund_neg + compressing` | `75.0% up_extension` only if OI turns up |

**Условия применимости:** решение меняется не только по цене, но и по переходу OI между `up / flat / down` внутри `fund_neg + compressing`.  
**Ожидаемый PnL спектр:** best `+$2,883` при полном fill до `77k` / median `+$319` по trailing study / worst `-$8,445`, если гибридный сценарий заканчивается защитным выходом выше `85,000`.  
**Probability success:** `53.8%` на reconciled base для pullback-ветки; `100.0%` для cross-bucket `OI down + fund_neg + compressing` (`n=12`) и `OI flat + fund_neg + compressing` (`n=8`); `75.0% up_extension` для `OI up + fund_neg + compressing` (`n=32`).  
**Foundation основа:** OI cross-classification `n=32/12/8`; funding-flip study `n=81`; sample dates `2025-06-28`, `2025-11-28`.

## Сводка

| Вариант | Категория | Главный trigger | PnL диапазон | Основание вероятности |
|---|---|---|---|---|
| Вариант 1 | защитный | пробой 82,400 → 84,000 → 85,000 | `-$4,763` → `-$8,445` | `46.2% up_extension`, `n=52` |
| Вариант 2 | opportunistic | откат 80,000 → 79,036 → 77,000 | `-$1,365` → `+$2,883` | `53.8% pullback_cont`, `n=52`; OI divergence `84.4%`, `n=96` |
| Вариант 3 | hybrid / contingent | совместно price + OI + funding | `-$8,445` → `+$2,883` | reconciled `n=52` + OI cross-buckets `n=32/12/8` |

Ограничения:
документ не даёт рекомендации и не даёт прогноза.
Все числа выше — это пересчёт исторических частот и PnL для позиции `1.416 BTC`.
