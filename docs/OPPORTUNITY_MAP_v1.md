# Карта возможностей v1

**Last update:** 2026-04-28
**Статус:** empirical playbook v1, NOT execution guarantee
**Источник:** SUMMARY 2026-04-27, 11 plays × 240-min горизонт, BTCUSDT год
**Основано на:** PLAYBOOK.md v1.1, MASTER.md, What-If engine TZ-022

---

## §1 Главный вывод

На экстремуме движения — открывать **новую** позицию, а не закрывать существующую в минус.

3 топ-приёма (P-6, P-2, P-7) — все про открытие. 3 худших (P-8, P-10, P-5) — все про эвакуацию из позиции. По данным этого теста forced close / restart / partial unload хуже удержания, **но удержание допустимо только пока нет liquidation risk, margin stress или invalidation сигнала**.

---

## §2 Правила из данных

**Правило A** — Каскад вверх (рост >3% за 1ч): запустить стак-шорт + поднять границу (P-6).
**Самый сильный кандидат**, в среднем +$134, win 69%. Но это всего **39 эпизодов** за год — требует подтверждения на 720/1440 горизонтах и на большем периоде. До подтверждения — высокая ставка делается с осторожностью.

**Правило B** — Рост 2-3% за 1ч: доп.шорт-бот на остановке роста (P-2). +$38, win 59% на 157 эпизодах. **Главный приём**, статистики достаточно.

**Правило C** — Дамп ≥2% с разворотом: стак-лонг (P-7). +$26, win 67% на 282 эпизодах. **Лонг-сетка лучше всего работает после дампа**, не на ралли.

**Правило D** — Длинный безоткатный рост (3+ часа): остановить шорт-боты, не открывать новые IN, держать позицию (P-4). Не зарабатывает (-$1.4) но и не теряет, защита от продолжения тренда.

**Правило E** — Подъём за upper boundary шорта: поднять границу +0.3% (P-1). Не зарабатывает (-$0.14), снижает peak DD на 0.5%. Страховка, не доход.

**Анти-правило F (HARD BAN)** — `/advise` v2 **никогда не предлагает**: P-5 partial unload, P-8 force-close + restart, P-10 rebalance. -$26..-$192 в среднем, эмпирически вредны.

---

## §3 Карта решений

| Что вижу на рынке | Приём | Combo | Ожид. pnl* | Win | DD |
|---|---|---|---|---|---|
| Δprice 1h > +3% (rally_critical) | **P-6** stack-shorts + raise | offset=1.0%, size зависит от режима | ~+$50..+$134 | 69% | 1.4% |
| Δprice 1h +2..3% (rally_strong) | **P-2** stack-short на остановке | size зависит от режима | ~+$11..+$38 | 59% | 1.5% |
| Δprice 1h ≤ -2% после ралли с разворотом | **P-7** stack-long | size зависит от режима | ~+$7..+$26 | 67% | 2.1% |
| 3+ часа подряд вверх без отката | **P-4** stop ботов | — | ~0 | 23% | защита |
| Цена ушла за upper boundary | **P-1** raise +0.3% | offset=0.3% | ~0 | 13% | защита |
| Бот в DD 4+ часа, unreal < -$200 | **P-12** adaptive tighten | gs×0.85, target×0.8 | ~0 | 9% | нейтрал |
| **HARD BAN** | P-5, P-8, P-10 | — | от -$26 до -$192 | <42% | -1.4..-5.9% |

*Диапазон pnl зависит от режима размера (см. §4).

---

## §4 Размеры позиции для `/advise` v2

**Три режима, дефолт = normal.** Депозит ~$15k, идёт реинвест, плановое пополнение +$10-20k через 2 недели.

| Режим | Size | Когда выбирать |
|---|---|---|
| **conservative** | 0.05 BTC | DD > 5% от депозита, free margin < 30%, или есть открытые позиции в просадке |
| **normal** (default) | 0.10 BTC | Стандартное состояние портфеля, free margin 30-60% |
| **aggressive** | 0.18 BTC | Только если free margin > 60%, нет позиций в DD, exposure низкая |

**Правило:** `/advise` v2 выбирает размер автоматически по состоянию портфеля в момент рекомендации. Оператор видит и режим, и обоснование.

| Приём | conservative (0.05) | normal (0.10) | aggressive (0.18) |
|---|---|---|---|
| P-6 ожид. pnl | +$28 | +$84 | +$134 |
| P-2 ожид. pnl | +$10 | +$26 | +$38 |
| P-7 ожид. pnl | +$7 | +$15 | +$26 |

При увеличении пополнения до $25-35k — пропорционально расширим лимиты режимов отдельным апдейтом карты.

---

## §5 Алгоритм `/advise` v2 (псевдокод)
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
log_recommendation(advisor_log.jsonl)
schedule_outcome_check(1h, 4h, 24h, advisor_outcomes.jsonl)

---

## §6 Что карта v1 НЕ покрывает

Карта = **empirical playbook**, не execution guarantee. Не моделируется:

1. ICT контекст (Asia / London / NY) — приёмы могут вести себя иначе по сессиям
2. Real-time liquidations — после TZ-029 fix + 30 дней накопления
3. Multi-horizon — defensive plays могут показать другое на 720/1440
4. Реальные bot snapshots — с 28.04 у нас 88k snapshots от tracker, подключать в v2 движка.
   Статус TZ-040 на 2026-04-28: replay-слой реализован, но для P-1/P-2/P-6/P-7
   в текущем workspace overlap с episode windows отсутствует, поэтому пункт не
   снят и ranking не обновлялся.
5. Macro context (SPX, DXY, gold) — нет коллектора
6. Margin / liquidation risk dynamics — синтетические presets не моделируют реальные DD траектории
7. P-3 (counter-LONG) — n=1, нет real-time liq для бэктеста
8. Размеры режимов привязаны к текущему депозиту $15k — пересчитать после пополнения
9. H-WAIT-VS-CHASE study (whatif_results/H-WAIT-VS-CHASE_2026-04-28.md):
   подтверждает правильность порядка P-2→P-1 в каскаде §5. P-1 имеет
   edge только в CONTINUED-сценарии (~33% эпизодов, edge $21).
   Без предиктора continuation — P-2 dominant.
10. Confidence intervals на point estimates приёмов:
    Из TZ-028-Codex-ADDENDUM-2 (29.04) известно что 95% CI для
    P-6 vs P-7 пересекаются на всех 4 episode_type. Это значит
    цифры $134/$38/$26 в §1-§3 — point estimates, реальный edge
    может быть существенно меньше. Каскад P-6→P-2→P-7 в §5
    основан на средних, не на статистически значимом ranking.
    Пересмотр после расширения выборки (multi-asset либо
    real bot snapshots в v2 движка).
11. P-13 LIQUIDITY-HARVESTER (TZ-032-Codex 28.04):
    Гипотеза опровергнута на бэктесте — edge формально +$15
    но win_rate 2.91% (hi-variance), не tradeable. P-13 status
    = rejected в PLAYBOOK. Не добавляем в карту.
12. ADVISOR v1 в проде с 28.04 на 3 активах (BTC/ETH/XRP),
    live features writer + cascade reader на parquet.
    PROD-CHECK 24h в процессе. /advise stats и /advise log
    команды доступны в Telegram. Auto outcome reconciliation
    работает.
13. P-14 PROFIT-LOCK-RESTART (TZ-041-Codex 28.04):
    Гипотеза опровергнута на бэктесте — best combo
    (pnl_threshold=1%, offset=1%, same side) даёт mean +$12
    но win_rate 22.83% (77% эпизодов в минус). P-14 status =
    rejected в PLAYBOOK. Не добавляем в карту.

---

## §7 Что меняется в `/advise` после внедрения карты v1

**Сейчас:** `/advise` пассивно показывает фичи и режим.

**После v2:**
1. Активно **рекомендует** приём при срабатывании триггера
2. Показывает **ожидаемый pnl + win rate + DD** (из карты)
3. Показывает **режим размера** (conservative/normal/aggressive) + обоснование
4. Показывает **рекомендованные параметры** (size_btc, offset_pct, gs_factor)
5. Уважает HARD BAN list — никогда не предлагает P-5/P-8/P-10
6. Уважает liquidation risk override
7. Логирует в `advisor_log.jsonl`
8. Через 1ч/4ч/24ч — фиксирует факт в `advisor_outcomes.jsonl`

---

## §15 Изменения файла
2026-04-28 v1.0 — Первая фиксация по итогам Шага 6 §12 MASTER.
Источник данных: whatif_results/SUMMARY_2026-04-27.md.
Согласовано с оператором с правками:
- HARD BAN list для P-5/P-8/P-10
- Размеры conservative/normal/aggressive вместо одного дефолта
- Liquidation risk override как первое правило
- Без формулировок "уверенно зарабатывать" / "терпеть всегда лучше"
