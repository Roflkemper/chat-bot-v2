---
# ROADMAP — Grid Orchestrator → Auto Trader

## Текущий milestone
Фаза 0 — инфраструктура и гигиена (in progress)

## Фазы

### ФАЗА 0 — Infrastructure & гигиена
Status: in_progress

Active tasks:
- TZ-PROJECT-MEMORY-DEFENSE v2 [DONE 9d7e5c2]
- TZ-CONFLICTS-TRIAGE [DONE a91d317]
- TZ-CALENDAR-REACTIVATION [DONE pending commit]
- TZ-CASCADE-DECISION [pending after triage]
- TZ-CALENDAR-INTO-MARKETCONTEXT [pending]

Exit criteria:
- Все conflicts классифицированы
- calendar.py + weekend_gap.py в active path
- все 26 pre-existing test errors устранены или классифицированы
- cascade.py решение принято

### ФАЗА 0.5 — Engine validation
Status: in_progress

Active tasks:
- reconcile retry until GREEN/YELLOW
- TZ-ENGINE-FIX-* per discovered mismatches

Exit criteria:
- Reconcile verdict GREEN или YELLOW with documented tolerances
- Backtest движок trustworthy для optimize TZs

### ФАЗА 1 — Paper Journal Launch
Status: in_progress

Goal: оркестратор смотрит, пишет paper journal, не действует

Active tasks:
- TZ-PAPER-JOURNAL-LIVE [DONE]
- TZ-WEEKLY-COMPARISON-REPORT [planned]

Exit criteria:
- Paper journal пишется minimum 14 дней непрерывно
- Первый weekly report сгенерирован
- Operator confirms что comparison report даёт useful insight

### ФАЗА 2 — Operator Augmentation
Status: planned

Goal: оркестратор активный советник через /advise команду
      + push на high-confidence сетапы

Active tasks:
- /advise Telegram command
- push notifications (P-2/P-6/P-7 with confidence > 0.75)

Exit criteria:
- Operator подтверждает что /advise влияет на торговые решения
  positively
- Edge over no-action measured > 10% over 30 дней

### ФАЗА 3 — Tactical Bot Management
Status: planned

Goal: оркестратор сам ставит/паузит/останавливает ботов
      запускает усилители на сетапах
      управляет рисками (size снижение при DD)

Pre-requisites:
- Reconcile GREEN
- Optimize пресеты validated
- 30+ дней Phase 2 reports с positive edge
- GinArea API automation tested на dry-run

### ФАЗА 4 — Full Auto
Status: planned

Goal: оркестратор торгует сам, оператор в роли governance

Pre-requisites:
- 100+ paper signals с edge > 25%, Sharpe > 1.2
- 30+ дней Phase 3 без срывов

## Параллельные потоки (не блокеры)
- H10 overnight backtest [operator's запуск]
- TZ-H1-H2-VALIDATION (после reconcile)
- TZ-LIQ-COUNTERFACTUAL (после Phase 1 paper journal)
- TZ-OPTIMIZE-SHORT/LONG (после reconcile GREEN)

## Принципы
- Никаких параллельных вселенных
- Идеи вне фазы → в QUEUE как IDEA с пометкой "проверить
  вписывается ли"
- Каждый TZ ссылается на фазу
- Trader-first проверка через roadmap
