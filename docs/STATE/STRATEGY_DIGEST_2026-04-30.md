# STRATEGY_DIGEST_2026-04-30

**Источник:** TZ-STRATEGY-DOCS-INVENTORY
**Дата составления:** 2026-04-30
**Правило:** только выписки + ссылки на исходные файлы и строки. Без интерпретации, без выводов.

---

## §1 Размеры позиции для `/advise` v2

**Источник:** `docs/OPPORTUNITY_MAP_v1.md` строки 51–68

> **Три режима, дефолт = normal.** Депозит ~$15k, идёт реинвест, плановое пополнение +$10-20k через 2 недели.
>
> | Режим | Size | Когда выбирать |
> |---|---|---|
> | **conservative** | 0.05 BTC | DD > 5% от депозита, free margin < 30%, или есть открытые позиции в просадке |
> | **normal** (default) | 0.10 BTC | Стандартное состояние портфеля, free margin 30-60% |
> | **aggressive** | 0.18 BTC | Только если free margin > 60%, нет позиций в DD, exposure низкая |
>
> **Правило:** `/advise` v2 выбирает размер автоматически по состоянию портфеля в момент рекомендации. Оператор видит и режим, и обоснование.
>
> | Приём | conservative (0.05) | normal (0.10) | aggressive (0.18) |
> |---|---|---|---|
> | P-6 ожид. pnl | +$28 | +$84 | +$134 |
> | P-2 ожид. pnl | +$10 | +$26 | +$38 |
> | P-7 ожид. pnl | +$7 | +$15 | +$26 |
>
> При увеличении пополнения до $25-35k — пропорционально расширим лимиты режимов отдельным апдейтом карты.

---

## §2 Фазовая карта решений (action matrix)

**Источник:** `docs/OPPORTUNITY_MAP_v1.md` строки 36–47

> | Что вижу на рынке | Приём | Combo | Ожид. pnl* | Win | DD |
> |---|---|---|---|---|---|
> | Δprice 1h > +3% (rally_critical) | **P-6** stack-shorts + raise | offset=1.0%, size зависит от режима | ~+$50..+$134 | 69% | 1.4% |
> | Δprice 1h +2..3% (rally_strong) | **P-2** stack-short на остановке | size зависит от режима | ~+$11..+$38 | 59% | 1.5% |
> | Δprice 1h ≤ -2% после ралли с разворотом | **P-7** stack-long | size зависит от режима | ~+$7..+$26 | 67% | 2.1% |
> | 3+ часа подряд вверх без отката | **P-4** stop ботов | — | ~0 | 23% | защита |
> | Цена ушла за upper boundary | **P-1** raise +0.3% | offset=0.3% | ~0 | 13% | защита |
> | Бот в DD 4+ часа, unreal < -$200 | **P-12** adaptive tighten | gs×0.85, target×0.8 | ~0 | 9% | нейтрал |
> | **HARD BAN** | P-5, P-8, P-10 | — | от -$26 до -$192 | <42% | -1.4..-5.9% |

**Источник:** `docs/MASTER.md` строки 218–246 (§7 Принципы торговли)

> **P0:** Никогда не закрывать в минус (без крайней необходимости). Сетка должна вытащить через работу, не через ножницы. Исключения только при риске ликвидации или конце конкурсного периода.
>
> **P1:** Защита > возможность. При конфликте сигналов (рост >3% + каскад с разворотом): сначала остановить, потом наблюдать, потом действовать.
>
> **P2:** Boundaries = анти-сквиз, не рабочая зона. Бот должен работать **везде** на любой цене. Boundaries — только страховка от безумного движения. По мере подтверждённого тренда — контролируемо двигать границу.
>
> **P8:** Каскады, ралли, каждое движение — возможность. Зарабатываем на всём. Нет «ждём идеального момента». Если в ситуации X есть edge — действуем.

---

## §3 Сценарии ручного вмешательства

**Источник:** `docs/SESSION_LOG.md` + `docs/PLAYBOOK.md` §3

Зафиксированные эпизоды ручного вмешательства (из `docs/PLAYBOOK.md` строки 569–594):

> **2026-04-22 07:57 UTC** — +5.04% за 1ч. TEST_1 pos -0.169, uPnL -$250. P-9 fix (закрыл LONG-B при +5%).
> **2026-04-20 08:47 UTC** — критический +7.19% за 1ч. TEST_1 pos -0.076, uPnL +$37..+$86 (выжили). Применён P-1 raise.
> **2026-04-23 10:12 UTC** — закрытие LONG-B/C = P-10 rebalance.
> **2026-04-23 15:24 UTC** — закрытие LONG-B/C = P-10 rebalance.
> **2026-04-26 22:15 UTC** — рост в зону ликвидаций шортистов (78400+), лонг закрыт, ждём откат.
> **2026-04-27 intraday UTC** — dry-run P-12: adaptive grid tightened на 3 шорт-ботах в просадке.
> **2026-04-17 13:55 UTC** — АНТИ-ПРИМЕР P-9: закрытие на пике дало худший исход (бот зашёл через 3ч на $78,089 = выше цены закрытия).
> **2026-04-17 09:31 UTC** — закрытие лонга #1, бот перезашёл через 4 мин на -0.7%.

**Источник:** `docs/PLAYBOOK.md` строки 360–395 (P-9 trigger-ветки):

> **fix_branch:** rapid_rally (+X% за Y минут), approach_to_resistance (PDH, KZ-H, round), liquidation_zone_of_shorts.
> **reinforce_branch:** controlled_rally, support_holding.
> УТОЧНЕНИЕ: 26.04 22:15 закрыл лонг в зоне ликвидаций шортистов на пробое. Это подвид fix_branch с дополнительным контекстом liquidation zone.

---

## §4 Каталог приёмов P-1..P-12

**Источник:** `docs/PLAYBOOK.md` строки 50–514

Краткая таблица (полные YAML-блоки — в файле источнике):

| ID | Название | Статус | N эпизодов | Trigger (ключевое) | Action |
|---|---|---|---|---|---|
| P-1 | controlled_raise_boundary | confirmed | many | D-MOVE-STRONG/CRITICAL + price_above_upper_boundary ≥15мин | A-RAISE-BOUNDARY offset_pct=[0.3,0.5,0.7,1.0] |
| P-2 | stack_bot_on_pullback | confirmed | regularly 5+/нед | D-MOVE-STRONG/MEDIUM + momentum_loss | A-LAUNCH-STACK-SHORT |
| P-3 | counter_long_hedge_with_ttl | dry-run-only | 1 (24.04 18:17) | D-LIQ-CASCADE-LONG + D-LIQ-CASCADE-WITH-REVERSAL | A-LAUNCH-COUNTER-LONG size=small TTL=15-45мин |
| P-4 | paused_no_new_entries | confirmed | W1-W3 эпизоды | D-MOVE-STRONG/CRITICAL + D-NO-PULLBACK | A-STOP (keep positions open) |
| P-5 | partial_unload | used_but_not_measured | не зафиксированы | paused_state OR D-PORT-DEEP-DD | A-CLOSE-PARTIAL-X |
| P-6 | shorts_on_short_squeeze_cascade | subset_of_P-1 | часть P-1 | D-LIQ-CASCADE-SHORT + D-LIQ-CASCADE-WITH-REVERSAL | A-RAISE-BOUNDARY + A-LAUNCH-STACK-SHORT |
| P-7 | longs_after_confirmed_dump | confirmed | 16-17.04 | D-LIQ-CASCADE-LONG/D-MOVE-CRITICAL(down) + reversal_confirmation≥1.5%/30мин | A-RESUME(LONG) или A-LAUNCH-STACK-LONG |
| P-8 | force_close_re_entry | **rejected** | 0 | position_large + D-PORT-LIQ-DANGER | A-CLOSE-ALL + A-RESTART-WITH-NEW-PARAMS |
| P-9 | long_fix_or_reinforce_on_rally | confirmed | 22.04, 26.04 | existing_long + rally_in_progress | fix: A-CLOSE-PARTIAL-X/ALL; reinforce: A-CHANGE-SIZE |
| P-10 | rebalance_close_reenter | **confirmed (HARD BAN)** | 4 кейса | D-MOVE-CRITICAL + position_significantly_offside | A-RESTART-WITH-NEW-PARAMS |
| P-11 | weekend_gap_false_breakout | confirmed | 1 (2026-04-27) | D-MOVE-STRONG/CRITICAL + weekend_gap_unfilled_below | A-LAUNCH-STACK-SHORT / A-RAISE-BOUNDARY |
| P-12 | adaptive_grid_tighten_in_drawdown | dry-run-only | 1 (2026-04-27) | bot_unrealized < -$200 дольше 4ч | A-CHANGE-TARGET(×0.60) + A-CHANGE-GS(×0.67) |
| P-13 | liquidity_harvester | **rejected** | 0 | D-CONSOLIDATION-AFTER-MOVE | — |
| P-14 | profit_lock_and_restart | **rejected** | 0 | D-PROFIT-LOCK-OPPORTUNITY | A-CLOSE-ALL-AND-RESTART |

**HARD BAN** (`docs/OPPORTUNITY_MAP_v1.md` строка 31):
> **Анти-правило F (HARD BAN)** — `/advise` v2 **никогда не предлагает**: P-5 partial unload, P-8 force-close + restart, P-10 rebalance. -$26..-$192 в среднем, эмпирически вредны.

---

## §5 Правила подъёма border.top

**Источник:** `docs/PLAYBOOK.md` строки 50–88 (P-1 полный YAML)

```yaml
id: P-1
name: controlled_raise_boundary
status: confirmed
trigger:
  required:
    - D-MOVE-STRONG OR D-MOVE-CRITICAL  # рост ≥2% за 1ч
    - price_above_current_upper_boundary
  any_of:
    - delta_1h > 3%
    - delta_4h > 4.5%
  context:
    - hold_above_boundary_min: 15  # минут удержания цены выше границы
action:
  type: A-RAISE-BOUNDARY
  params:
    new_top: current_high * (1 + offset_pct/100)
    offset_pct: [0.3, 0.5, 0.7, 1.0]  # grid
    discrete_step: true  # не плавно за хаем
cancel:
  - price_below_new_lower_bound
  - reversal_confirmed (откат >0.5% от нового хая)
notes: |
  Не "гонка за ценой", а умножение позиции на хороших ценах.
  Альтернатива dsblin=true ОТВЕРГНУТА (volume падает).
ict_context:
  - лучше работает при пробое PDH или KZ-high с подтверждением
  - хуже при ложном выносе у round number (78000, 80000)
```

**Источник:** `docs/MASTER.md` строки 176–180 (каталог действий)

> **A-RAISE-BOUNDARY:** поднять upper (для шорта) или lower (для лонга) на N% [N параметр]

**Источник:** `docs/PLAYBOOK.md` строки 636–637 (§4 Антипаттерны)

> ❌ **Boundaries как «рабочий диапазон»** — это анти-сквиз, не working zone.
> ❌ **Boundary плавно за хаем на каждом баре** — это chasing, нужны дискретные шаги с подтверждением.

---

## §6 Механизм Adaptive Grid Manager

**Источник:** `services/adaptive_grid_manager.py` строки 1–9 (docstring)

```
Adaptive grid manager — авто-затягивание параметров шорт-ботов в просадке.

Логика:
- Каждые 5 минут читает snapshots.csv (current_profit = unrealized USD) и params.csv.
- Тригерует «затянуть» (target×0.60, gs×0.67) когда бот в просадке ≥4ч с unreal < -$200.
- Отпускает к original_params когда unreal > -$50.
- State персистируется в state/adaptive_grid_state.json (переживает рестарт).
- dry_run: пишет в JSONL вместо PUT /params.
```

**Источник:** `services/adaptive_grid_manager.py` строки 34–52 (структуры данных)

```python
@dataclass
class BotSnapshot:
    bot_id: str
    alias: str
    unrealized_usd: float   # current_profit from snapshots.csv
    gap_tog: float          # gap.tog from params.csv
    gs: float               # gs from params.csv

@dataclass
class BotGridState:
    mode: str = "original"               # "original" | "tightened"
    original_gap_tog: float = 0.0
    original_gs: float = 0.0
    drawdown_start_epoch: float | None = None
    last_release_epoch: float | None = None
    tightenings_24h: list[float] = field(default_factory=list)
```

**Источник:** `services/adaptive_grid_manager.py` строки 58–68 (фильтр eligible ботов)

```python
def read_short_bots_snapshot(
    params_csv, snapshots_csv,
    *, target_min: float = 0.18, target_max: float = 0.30,
) -> list[BotSnapshot]:
    """Eligible: side==2 (SHORT), gap.tog in [target_min, target_max]."""
```

**Источник:** `docs/PLAYBOOK.md` строки 471–513 (P-12 полный YAML)

```yaml
id: P-12
action:
  type: A-CHANGE-TARGET + A-CHANGE-GS
  params:
    target_factor: 0.60
    gs_factor: 0.67
    cooldown_hours: 2
    max_cycles_per_24h: 3
cancel:
  - bot_unrealized_pnl_above    # > -$50 → release
  - cooldown_hours_active
notes: |
  В просадке временно затягивает short-grid, чтобы увеличить обороты и быстрее
  подтянуть avg_entry. После выхода из глубокой просадки возвращает исходные параметры.
```

---

## §7 Правила паузы и возобновления ботов

**Источник:** `docs/PLAYBOOK.md` строки 184–221 (P-4 полный YAML)

```yaml
id: P-4
name: paused_no_new_entries
status: confirmed
trigger:
  required:
    - D-MOVE-STRONG OR D-MOVE-CRITICAL
    - D-NO-PULLBACK
  context:
    - existing_position_in_drawdown
    - direction_against_position
action:
  type: A-STOP  # шорты при ралли, лонги при дампе
  params:
    affected: bots_with_side_against_trend
    keep_positions_open: true
    target_hits_continue: true  # OUT работают, новые IN — нет
cancel:
  - pullback_detected (откат >0.3-1% от пика)
  - regime_flip_to_range
  - timeout (для UNLOAD)
notes: |
  Альтернативы которые менее радикальны:
  - уменьшить order_size + увеличить grid_step
  - перейти на Far Short preset
ict_context:
  - применять с пониманием killzone — если PAUSED активирован в начале NY,
    скорее всего нужно держать до конца NY PM
```

**Источник:** `docs/OPPORTUNITY_MAP_v1.md` строки 74–112 (алгоритм `/advise` v2, секция PAUSED)

```python
elif D-NO-PULLBACK-UP-3H and shorts_in_drawdown:
    propose P-4 (stop bots, keep position)
```

**GAP:** Точные часовые пороги перехода в PAUSED (сколько часов D-NO-PULLBACK обязательно) и условие выхода (точный % откатка) явно не зафиксированы в docs. В P-4 cancel указано "откат >0.3-1% от пика" как grid, не как фиксированное значение.

---

## §8 Поведение при каскадах ликвидаций

**Источник:** `docs/PLAYBOOK.md` строки 263–290 (P-6) и строки 293–320 (P-7)

P-6 (short-liq каскад вверх):
```yaml
trigger:
  required:
    - D-LIQ-CASCADE-SHORT  # прокол вверх со short-liq
    - D-LIQ-CASCADE-WITH-REVERSAL
action:
  steps:
    - A-RAISE-BOUNDARY (P-1)
    - A-LAUNCH-STACK-SHORT (P-2)
cancel:
  - rally_continues (если рост продолжается после cascade — стоп ботов)
```

P-7 (long-liq каскад вниз):
```yaml
trigger:
  required:
    - D-LIQ-CASCADE-LONG OR D-MOVE-CRITICAL (down)
    - reversal_confirmation (отскок ≥1.5% за 30 мин)
action:
  type: A-RESUME (лонг ботов) или A-LAUNCH-STACK-LONG
cancel:
  - dump_resumes
  - target_hit
ict_context:
  - sweep PDL/PWL + reversal = сильный сетап
  - в Asia слабее, в NY сильнее
```

P-3 (hedge counter-LONG на каскаде):
```yaml
trigger:
  required:
    - D-LIQ-CASCADE-LONG  # каскад long-liq ≥15-20 BTC за 60s
    - D-LIQ-CASCADE-WITH-REVERSAL  # цена развернулась за 5min
  context:
    - NOT D-LIQ-CASCADE-NO-REVERSAL  # без подтверждения отката НЕ открывать
action:
  side: LONG inverse XBTUSD
  size: small  # ~10-20% депозита, не основная позиция
  target: 0.25-0.35%
  stop: -0.5 to -1%
  ttl_minutes: 15-45
```

**Источник:** `docs/PLAYBOOK.md` строки 569–576 (§3 Эталонные каскадные эпизоды)

> **2026-04-27 00:55 UTC** — LIQ_CASCADE 41.978 BTC short-liq на пике 79200. Начало P-11.
> **2026-04-27 05:15 UTC** — LIQ_CASCADE 12.25 BTC long-liq. Counter-LONG triggered, target +0.30% за 1мин.
> **2026-04-27 06:31 UTC** — LIQ_CASCADE 16.18 BTC long-liq. Counter-LONG triggered, target hit за 1мин.
> **2026-04-24 18:17 UTC** — каскад 62 BTC long-liq → -0.37% за 5мин → +0.37% за час. P-3 эталон.

**Источник:** `docs/MASTER.md` строки 146–150 (детекторы ликвидаций)

> **D-LIQ-CASCADE-LONG:** sum(liq.long) > N BTC за 60s
> **D-LIQ-CASCADE-SHORT:** sum(liq.short) > N BTC за 60s
> **D-LIQ-CASCADE-WITH-REVERSAL:** cascade + цена развернулась в противоположную сторону за 5min
> **D-LIQ-CASCADE-NO-REVERSAL:** cascade + продолжение движения

**GAP:** Конкретное значение N (порог BTC) для D-LIQ-CASCADE-LONG/SHORT не зафиксировано в docs как единое число. В P-3 упомянуто "≥15-20 BTC за 60s" как диапазон.

---

## §9 Volume targeting (конкурсный режим)

**Источник:** `docs/MASTER.md` строки 43–51 (§1 Главная цель)

> **НЕ цель:** конкурс GinArea (1 место не догонять, отрыв 2.2x). **Бонус-цель:** $8-10M оборот.

**Источник:** `docs/MASTER.md` строки 211–213 (§6 Текущая live конфигурация)

> TEST_1/2/3: SHORT, 0.001 BTC, 200 ордеров, gs 0.03%, target 0.25%, instop 0/0.018/0.03%, boundaries 68000-78600
> BTC-LONG-C/D: LONG inverse, $100, 220 ордеров, target 0.20-0.21%

**GAP:** Формальных правил конкурсного режима (когда переключаться на высокий оборот, как балансировать PnL vs объём, параметры пресетов для volume mode) в docs нет. Оператор упоминал "$8-10M оборот" как бонус-цель, но алгоритма выбора параметров под объём нет.

---

## §10 GAPS — что не задокументировано

Список того, что существует как практика или намерение, но отсутствует в формальных docs:

| # | Gap | Источник упоминания |
|---|---|---|
| G-1 | **Volume targeting (конкурсный режим):** нет правил когда и как переключаться на агрессивный объём, какие параметры ботов для $8-10M/мес. | MASTER §1 (строка 51) — только цифра цели |
| G-2 | **Точные пороги PAUSED:** сколько часов D-NO-PULLBACK обязательно; точный % откатка для выхода из PAUSED. P-4 cancel — "откат >0.3-1%" = grid, не фиксированное значение. | PLAYBOOK P-4 строки 204-207 |
| G-3 | **Liquidation cluster reentry:** нет правил возврата в позицию после P-7 stack-long. Когда закрывать counter-LONG после достижения target? P-3 cancel — target_hit / stop_hit / ttl_expired — есть, но нет правила "что делать дальше" (держать/выходить/переворачиваться). | PLAYBOOK P-3 строки 163-167 |
| G-4 | **Порог D-LIQ-CASCADE-LONG/SHORT (значение N):** в детекторах указано "> N BTC за 60s" но N не задан. P-3 дает диапазон "≥15-20 BTC", не единое число для кода. | MASTER §4 строки 146-147, PLAYBOOK P-3 строка 148 |
| G-5 | **Калибровка размеров после пополнения:** прямо указано "При увеличении пополнения до $25-35k — пропорционально расширим лимиты режимов" но формула пересчёта не задана. | OPPORTUNITY_MAP_v1 строка 69 |
| G-6 | **Multi-horizon правила для defensive plays:** P-1/P-4 "смысл виден на длинных горизонтах". 720/1440-минутные горизонты не прогнаны. | OPPORTUNITY_MAP_v1 §6 пункт 3 (строки 123-124) |
| G-7 | **P-9 точные параметры:** "rapid_rally: +X% за Y минут [grid: X=2-3%, Y=15-60min]" — диапазоны, не финальные значения. | PLAYBOOK P-9 строки 362-363 |
| G-8 | **ICT killzone context для P-4:** "применять с пониманием killzone" — правило есть, но операционализация (конкретные часы Warsaw когда держать PAUSED без выхода) не задана. | PLAYBOOK P-4 строки 217-219 |
| G-9 | **P-2 размер stack-бота:** в YAML `size: same_as_main_or_aggressive  # ← OPEN: уточнить у оператора`. Метка OPEN с 2026-04-27. | PLAYBOOK P-2 строка 112 |
| G-10 | **Статус P-5 (partial unload):** status=used_but_not_measured, эпизоды не зафиксированы. Используется практически, данных нет. Не в HARD BAN, но и не в action matrix карты. | PLAYBOOK P-5 строки 227-229 |
