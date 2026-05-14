# Ежедневная сводка bot7 — 2026-05-14

_Сгенерирован 15:16 UTC, окно 24ч_

## Коммиты (0)

- (нет)

## Pipeline — 9438 событий, 49 в TG (0.52%)

Воронка: env_disabled=7743 → combo_blocked=878 → mtf_conflict=20 → mtf_neutral=21 → type_pair_dedup_skip=406 → semantic_dedup_skip=280 → gc_shadow=41 → emitted=49

- env_disabled: 7743 — выключен в env (отключены: short_pdh_rejection, long_rsi_momentum_ga, short_mfi_multi_ga)
- combo_blocked: 878 — режим/комбо блокирует
- type_pair_dedup_skip: 406 — дедуп по типу+паре
- semantic_dedup_skip: 280 — семантический дедуп
- emitted: 49 — отправлен в TG
- gc_shadow: 41 — GC shadow-mode
- mtf_neutral: 21 — MTF neutral (нет согласия)
- mtf_conflict: 20 — конфликт таймфреймов

## Перезапуски app_runner: 37
  • Распределение нормальное

## P-15 lifecycle

- PnL за день: $-75.45
- Закрытых сделок: 12 | WR: 42% | avg win: $+1.04 | avg loss: $-11.52
- Лучшая: $+1.98 | худшая: $-60.90 | MaxDD по equity: $-78.85
- Стадии: OPEN=2, HARVEST=10, CLOSE=2
- HARVEST/OPEN ratio: 5.00 (>1 = частичные фиксации активны)

## Paper trader (одиночные сетапы)

- PnL за день: $+307.08
- Закрытых сделок: 7 | WR: 29% | avg win: $+258.27 | avg loss: $-41.89
- Лучшая: $+516.43 | худшая: $-80.01 | MaxDD: $-209.35 | Profit factor: 2.47
- По сторонам: LONG $+386 (4 сд, WR 50%) | SHORT $-78 (3 сд, WR 0%)

## Решения Grid Coordinator

- pass-through: 31
- boost +15.0%: 8
- penalty -30.0%: 2
- boost:penalty = 8:2 (4.0, перевес в сторону усиления)
