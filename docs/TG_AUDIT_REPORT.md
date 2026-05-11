# Telegram audit + keyboard redesign (2026-05-11)

## 1. Что бот слал в TG за 48 часов

**134 setup-карточек:**

| Тип | Сколько | Note |
|---|---|---|
| short_pdh_rejection | 22 | **16 из них на XRPUSDT 10 мая** — взрыв ложных сигналов. Зафиксено `DISABLED_DETECTORS=short_pdh_rejection` 10 мая ночью. Новых нет. |
| p15_long_harvest | 21 | P-15 lifecycle, нормально |
| p15_long_close | 19 | P-15 lifecycle |
| p15_long_reentry | 18 | P-15 lifecycle |
| p15_long_open | 14 | P-15 lifecycle |
| short_mfi_multi_ga | 9 | **DEGRADED candidate** (TODO-7). Каждый час 1 alert. На радар. |
| p15_short_open | 8 | P-15 lifecycle |
| p15_short_close | 6 | P-15 lifecycle |
| long_double_bottom | 4 | XRPUSDT х4 — слабый сигнал на этой паре |
| short_rally_fade | 3 | XRPUSDT х3 — не валидирован на XRP |
| остальное | 10 | редкие, ок |

**91 из 134 (68%) — это P-15 lifecycle карточки** (OPEN/HARVEST/REENTRY/CLOSE).
Реально торговых сигналов **43**.

## 2. Шумители (после fix dedup)

Топ-3 самых "близких" событий:
1. **short_pdh_rejection / XRPUSDT — 16 раз с gap 1 минута** (10 мая). Зафиксено через runtime kill switch. Больше не повторится.
2. **short_mfi_multi_ga / BTCUSDT — 9 раз gap 4 мин**. Не disable пока — N=9 in precision tracker, ждём N=30 для verdict.
3. **short_pdh_rejection / BTCUSDT — 3 раза gap 4 мин**.

## 3. Что в кнопках сейчас

13 кнопок 4 рядами:

| Row | Buttons | Польза для трейдера |
|---|---|---|
| 1 | `/morning_brief` `/advise` `FINAL DECISION` | Утренний бриф (ок) — Advisor (ок) — Финальное решение (ок) |
| 2 | `/momentum_check` `/setups_15m` `/regime_v2` | Momentum (рарo полезен) — 15m setups (часто пустой) — Regime v2 (debug) |
| 3 | `СТАТУС БОТОВ` `BTC GINAREA` `BTC SUMMARY` | Bot status, Ginarea overview, BTC summary |
| 4 | `/papertrader` `/watch` `/advisor` `HELP` | Paper PnL, Watchlist, Advisor (дубликат с row 1), Help |

**Проблемы:**
- `/advise` и `/advisor` — **дубликаты** (row 1 + row 4)
- `/regime_v2` — debug-команда, оператору не нужна
- `/papertrader` — низкая ценность (P-15 lifecycle уже показывает PnL)
- `/setups_15m` — редко даёт результат (15m TF мало fires)
- **19 новых slash-команд не доступны через кнопки** (/status, /p15, /pipeline, /precision, /histogram, /inspect, /cron, /disable, /enable, /changelog etc)

## 4. Предлагаемая раскладка кнопок

**Reorganization in 4 rows (12 buttons, no duplicates):**

```
Row 1 (Daily snapshot):
  /status          /p15             /ginarea

Row 2 (Trading insight):
  /morning_brief   FINAL DECISION   /advise

Row 3 (Health & history):
  /pipeline        /precision       /changelog

Row 4 (Help):
  /watch           HELP             (free slot)
```

**Что убрано:**
- `/regime_v2` (debug-only)
- `/papertrader` (P-15 lifecycle уже на /p15)
- `/setups_15m` (часто пустой; можно через `/setups` команду)
- `/advisor` (дубликат `/advise`)
- `СТАТУС БОТОВ` (заменён на `/ginarea` — то же самое + позиции и unrz PnL)
- `BTC GINAREA` (то же что `/ginarea`)
- `BTC SUMMARY` (низкая частота использования; есть через /advise)
- `/momentum_check` (редкий use)

**Что добавлено:**
- `/status` — heartbeat, последний setup, P-15 legs, restarts (общий health snapshot)
- `/p15` — детальный per-leg отчёт со всеми событиями
- `/ginarea` — снимок 52 ботов + позиции + PnL
- `/pipeline` — funnel: где сколько событий теряется
- `/precision` — какие детекторы работают / DEGRADED
- `/changelog` — что произошло за 24ч

## 5. Action items

| Приоритет | Действие |
|---|---|
| 1 | Обновить `telegram_ui/keyboards.py` под новую раскладку |
| 2 | Удалить `/regime_v2` handler если он там есть |
| 3 | Объединить `/advise` и `/advisor` → один handler |
| 4 | Тест: рестарт бота, проверить что новые кнопки появились |

После apply — миграция на Mac пройдёт уже с чистым меню.
