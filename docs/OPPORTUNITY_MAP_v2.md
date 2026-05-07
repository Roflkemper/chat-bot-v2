# Карта возможностей v2

**Last update:** 2026-05-01
**Статус:** empirical playbook v2, NOT execution guarantee
**Источник:** `docs/OPPORTUNITY_MAP_v1.md`, `reports/opportunity_map_with_costs_2026-05-01.md`, `_recovery/restored/whatif_results/SUMMARY_2026-04-27.md`
**Основано на:** PLAYBOOK.md v1.1, MASTER.md, What-If engine TZ-022, TZ-COST-MODEL-INTEGRATION

---

## §1 Главный вывод

На экстремуме движения открывать **новую** позицию, а не закрывать существующую в минус. Этот вывод из v1 сохраняется после добавления explicit cost model.

HARD BAN на P-5 / P-8 / P-10 стал только сильнее. После учёта taker fee и taker slippage эти приёмы остаются отрицательными уже не только по gross PnL, но и по net PnL.

Maker rebate структура GinArea / BitMEX даёт **structural edge** для maker-heavy grid plays. По comparison report `P-2` улучшился на `+$1.81` к gross, `P-6` улучшился на `+$2.18`. Для `P-7` stronger evidence не подтвердился: play остаётся положительным в net (`+$7.59` в recovered report), но ниже gross (`+$16.07`), то есть costs здесь ухудшили результат.

---

## §2 Правила из данных

**Правило A** — каскад вверх (рост >3% за 1ч): запустить stack-short + поднять границу (P-6).
В v1 best-combo оценка была `gross_pnl=+$134.54`, `win=69.2%`, `n=39`. Cost-aware comparison report подтверждает направление edge и улучшение после costs для самого play: `net_pnl=-$177.22` против `gross_pnl=-$179.40`, delta `+$2.18`. Caveat из v1 не меняется: это всего **39 эпизодов** за год, нужна дальнейшая проверка на большем окне и/или real outcomes.

**Правило B** — рост 2-3% за 1ч: доп. short bot на остановке роста (P-2).
Это остаётся главным рабочим приёмом по частоте и устойчивости: в v1 `gross_pnl=+$38.54`, `win=59.2%`, `n=157`. Comparison report показывает улучшение net относительно gross для play-level cost accounting: `gross_pnl=-$228.90`, `net_pnl=-$227.09`, delta `+$1.81`. Maker rebate на множественных fills усиливает edge, а не съедает его.

**Правило C** — dump >=2% с разворотом: stack-long (P-7).
В v1 best-combo оценка была `gross_pnl=+$26.30`, `win=67.7%`, `n=282`. После costs play остаётся положительным в recovered comparison report, но weaker: `gross_pnl=+$16.07`, `net_pnl=+$7.59`, delta `-$8.48`. Значит long reversal setup продолжает работать, но без тезиса о rebate-driven improvement.

**Правило D** — длинный безоткатный рост (3+ часа): остановить short-боты, не открывать новые IN, держать позицию (P-4).
В v1 это было почти нейтральной защитой: `gross_pnl=-$1.42`, `win=23.1%`. Funding contribution действительно присутствует в cost model, но в recovered comparison report она не перевешивает taker costs: `gross_pnl=-$301.49`, `net_pnl=-$306.14`, funding `+$1.20`. Вывод v1 сохраняется: это defensive play, а не доходный приём.

**Правило E** — подъём за upper boundary short: поднять границу +0.3% (P-1).
В v1 это страховка, не источник дохода: `gross_pnl=-$0.14`, `win=13.3%`, снижение peak DD на `0.5%`. Comparison report даёт небольшое улучшение после costs за счёт rebate/funding mix: `gross_pnl=-$221.32`, `net_pnl=-$218.44`, delta `+$2.88`. Смысл не меняется: это защита, не alpha-generator.

**Анти-правило F (HARD BAN)** — `/advise` v2 никогда не предлагает P-5 partial unload, P-8 force-close + restart, P-10 rebalance.
После учёта costs запрет усилился:
- `P-5`: `gross_pnl=-$462.23`, `net_pnl=-$472.28`
- `P-8`: `gross_pnl=-$495.99`, `net_pnl=-$507.22`
- `P-10`: `gross_pnl=-$266.65`, `net_pnl=-$277.89`

---

## §3 Карта решений

| Что вижу на рынке | Приём | Combo | gross_pnl | net_pnl | Win | DD |
|---|---|---|---:|---:|---:|---|
| Δprice 1h > +3% (`rally_critical`) | **P-6** stack-shorts + raise | `offset=1.0%`, `size` зависит от режима | `+$134.54` | `-$177.22*` | 69% | 1.4% |
| Δprice 1h +2..3% (`rally_strong`) | **P-2** stack-short на остановке | `size` зависит от режима | `+$38.54` | `-$227.09*` | 59% | 1.5% |
| Δprice 1h <= -2% после rally с разворотом | **P-7** stack-long | `size` зависит от режима | `+$26.30` | `+$7.59*` | 67% | 2.1% |
| 3+ часа подряд вверх без отката | **P-4** stop ботов | — | `-$1.42` | `-$306.14*` | 23% | защита |
| Цена ушла за upper boundary | **P-1** raise `+0.3%` | `offset=0.3%` | `-$0.14` | `-$218.44*` | 13% | защита |
| Бот в DD 4+ часа, `unreal < -$200` | **P-12** adaptive tighten | `gs×0.85`, `target×0.8` | `+$0.04` | `-$310.81*` | 9% | нейтрал |
| **HARD BAN** | P-5, P-8, P-10 | — | `-$26.87 .. -$192.69` | `-$277.89 .. -$507.22*` | <42% | -1.4..-5.9% |

`*` `net_pnl` здесь взят из recovered comparison report на уровне whole-play post-hoc cost accounting, а не из полного combo-level rerun v1. Это пригодно для direction-of-change и ranking review, но не является точной заменой best-combo gross цифры один-к-одному.

Смоук-чек покрытия plays из v1:
- В карту решений включены основные plays v1: `P-1`, `P-2`, `P-4`, `P-5`, `P-6`, `P-7`, `P-8`, `P-10`, `P-12`.
- В caveats ниже сохранены статусы `P-3`, `P-9`, `P-11`, `P-13`, `P-14`, чтобы покрытие `P-1` через `P-14` не потерялось.

---

## §4 Размеры позиции для `/advise` v2

**Три режима, дефолт = normal.** Депозит `~$15k`, идёт реинвест, плановое пополнение `+$10-20k` через 2 недели.

| Режим | Size | Когда выбирать |
|---|---|---|
| **conservative** | `0.05 BTC` | DD > 5% от депозита, free margin < 30%, или есть открытые позиции в просадке |
| **normal** (default) | `0.10 BTC` | Стандартное состояние портфеля, free margin 30-60% |
| **aggressive** | `0.18 BTC` | Только если free margin > 60%, нет позиций в DD, exposure низкая |

**Правило:** `/advise` v2 выбирает размер автоматически по состоянию портфеля в момент рекомендации. Режимы и пороги **не меняются** относительно v1.

Все ожидаемые PnL в этой секции должны дальше читаться как target for future net-aware recalibration. Для v2.0 default sizing логика сохранена, а численные net-оценки по режимам не подставляются искусственно без полного rerun.

| Приём | conservative gross_pnl | conservative net_pnl | normal gross_pnl | normal net_pnl | aggressive gross_pnl | aggressive net_pnl |
|---|---:|---|---:|---|---:|---|
| P-6 ожидаемый pnl | `+$28` | `n/a — нужен полный rerun v2` | `+$84` | `n/a — нужен полный rerun v2` | `+$134` | `n/a — нужен полный rerun v2` |
| P-2 ожидаемый pnl | `+$10` | `n/a — нужен полный rerun v2` | `+$26` | `n/a — нужен полный rerun v2` | `+$38` | `n/a — нужен полный rerun v2` |
| P-7 ожидаемый pnl | `+$7` | `n/a — нужен полный rerun v2` | `+$15` | `n/a — нужен полный rerun v2` | `+$26` | `n/a — нужен полный rerun v2` |

При увеличении депозита до `$25-35k` пропорционально расширить лимиты режимов отдельным апдейтом карты. Cost model сама по себе это правило не меняет.

---

## §5 Алгоритм `/advise` v2 (псевдокод)

```text
on_minute_tick:
    detectors = compute_all_detectors(current_features)
    portfolio_state = read_portfolio_snapshot()
    size_mode = pick_size_mode(portfolio_state)  # conservative/normal/aggressive
    size_btc = MODE_TO_SIZE[size_mode]

    # Liquidation risk check — override любых приёмов открытия
    if any_bot_distance_to_liq < 15%:
        propose ONLY defensive: P-4 stop, или close partial если совсем критично
        do NOT propose new positions
        return

    # Главный каскад решений
    if D-LIQ-CASCADE-LONG and D-LIQ-CASCADE-WITH-REVERSAL:
        propose P-3 with size=conservative, label="low_confidence (n=1)"
    elif D-MOVE-CRITICAL up:
        propose P-6 (raise+stack short, offset=1.0, size=size_btc)
    elif D-MOVE-STRONG up and momentum_loss_signs:
        propose P-2 (stack short, size=size_btc)
    elif (D-MOVE-CRITICAL down or D-MOVE-STRONG down) and reversal_confirmed:
        propose P-7 (stack long, size=size_btc)
    elif D-NO-PULLBACK-UP-3H and shorts_in_drawdown:
        propose P-4 (stop bots, keep position)
    elif price_above_short_boundary and held_15min:
        propose P-1 (raise boundary +0.3%)
    elif bot_in_drawdown_4h+ and unrealized < -$200:
        propose P-12 (adaptive tighten)

    # HARD BAN — никогда не предлагать
    NEVER propose: P-5, P-8, P-10

    # Логировать
    log_recommendation(advisor_log.jsonl, include_fields=['gross_pnl', 'net_pnl', 'fees', 'slippage', 'funding'])
    schedule_outcome_check(1h, 4h, 24h, advisor_outcomes.jsonl)
```

Логика каскада не меняется. Cost model встроена в симулятор и outcome computation; `/advise` не должен знать про costs как про отдельное условие выбора приёма.

---

## §6 Что карта v2 НЕ покрывает

Карта = **empirical playbook**, не execution guarantee. Не моделируется:

1. ICT контекст (Asia / London / NY) — приёмы могут вести себя иначе по сессиям
2. Real-time liquidations — после TZ-029 fix + 30 дней накопления
3. Multi-horizon — defensive plays могут показать другое на 720/1440
4. Реальные bot snapshots — v2 не заменяет отдельный real-outcome слой; ranking здесь всё ещё опирается на historical What-If + recovered cost report
5. Macro context (SPX, DXY, gold) — нет коллектора
6. Margin / liquidation risk dynamics — синтетические presets не моделируют реальные DD траектории
7. P-3 (counter-LONG) — `n=1`, нет real-time liq для бэктеста
8. Размеры режимов привязаны к текущему депозиту `$15k` — пересчитать после пополнения
9. H-WAIT-VS-CHASE study: подтверждает правильность порядка `P-2 -> P-1` в каскаде; без predictor continuation `P-2` остаётся dominant
10. Confidence intervals на point estimates: из addendum известно, что 95% CI для ряда plays пересекаются; ranking в §5 основан на средних, а не на статистически значимом разрыве
11. P-13 LIQUIDITY-HARVESTER — rejected в PLAYBOOK, в карту не добавляется
12. ADVISOR v1 в проде на 3 активах; live validation процесса продолжается
13. P-14 PROFIT-LOCK-RESTART — rejected в PLAYBOOK, в карту не добавляется
14. Cost model v1 предполагает constant maker rebate `-0.025%` для BitMEX inverse. Реальный rebate может измениться при смене fee tier или schedule; в этом случае нужен recalibration.
15. Slippage estimate — линейная аппроксимация (`spread/2 + 0.05 × notional / 10000`). На быстрых каскадах, особенно в `P-6` trigger, реальный slippage для taker-heavy legs может быть выше. Это bias в сторону оптимизма для taker-heavy plays.
16. Funding contribution берётся из historical frozen data или fallback assumption. При смене рыночного режима знак и величина funding меняются; для long-hold / short-hold защитных plays это может materially изменить net PnL.

---

## §7 Что меняется в `/advise` после внедрения карты v2

**Сейчас:** `/advise` пассивно показывает фичи и режим.

**После v2:**
1. Активно рекомендует приём при срабатывании триггера
2. Показывает ожидаемый `gross_pnl` + `net_pnl` + `win rate` + `DD`
3. Показывает режим размера (`conservative` / `normal` / `aggressive`) + обоснование
4. Показывает рекомендованные параметры (`size_btc`, `offset_pct`, `gs_factor`)
5. Уважает HARD BAN list — никогда не предлагает `P-5` / `P-8` / `P-10`
6. Уважает liquidation risk override
7. Логирует в `advisor_log.jsonl`
8. Через `1ч/4ч/24ч` фиксирует факт в `advisor_outcomes.jsonl`
9. В каждом log entry добавляет `net_pnl_estimate`, `fees_estimate`, `slippage_estimate`, `funding_estimate` для post-hoc валидации cost model на real outcomes

---

## §15 Изменения файла

2026-05-01 v2.0 — Обновление по результатам TZ-COST-MODEL-INTEGRATION. Основные таблицы расширены до `gross_pnl` и `net_pnl`. Maker rebate `(-0.025%)` усилил evidence для `P-2` и `P-6`. HARD BAN на `P-5` / `P-8` / `P-10` усилен taker slippage и taker fees. Sizing режимы не изменены. Confidence interval caveats из v1 остаются актуальными. Для combo-level net sizing чисел, которых нет в source artifacts, проставлено `n/a` вместо выдуманных значений.

2026-04-28 v1.0 — Первая фиксация по итогам Шага 6 §12 MASTER. Источник данных: `whatif_results/SUMMARY_2026-04-27.md`. Согласовано с оператором с правками: HARD BAN list для `P-5` / `P-8` / `P-10`, размеры `conservative` / `normal` / `aggressive` вместо одного дефолта, liquidation risk override как первое правило.
