# TAILS AUDIT — what's broken / abandoned / forgotten

**Date**: 2026-05-07
**Method**: disk-check (per К28) — mtime файлов, content state, code traces. Не доверяя inventory-документам.

**Update 2026-05-07 14:00**: P0 #1 + #5 closed (commit 51a484f). См. ниже.

---

## P0 — BROKEN, СЕЙЧАС МЕШАЕТ ТОРГОВАТЬ

### 1. `state/state_latest.json` (Snapshot не пишется) — ✅ CLOSED 2026-05-07

**Симптом**: `paper_journal: state_latest.json age=4900s > 600s` каждые 5 мин в логе.
**Причина**: писатель — `scripts/state_snapshot.py`, был привязан к scheduled task `bot7-state-snapshot`. Таска была отключена 2026-05-07 для cleanup orphans. Никто не включил обратно.
**Последствие**: `paper_journal`, `decision_log`, `decision_layer` — все ослеплены. /advise audit пишется, но без state-context'а neполный.
**Фикс**: ✅ DONE 2026-05-07 14:00 (commit 51a484f). Создан `scripts/state_snapshot_loop.py` (300s wrapper). Зарегистрирован в supervisor как 5-й managed process. Heartbeat `managed=4` подтверждён в 12:00:16Z. iter=2 в 14:00:47 — каждые 5 минут стабильный refresh state_latest.json. Больше не зависит от scheduled task admin permissions.

### 2. `state/regime_state.json` — все TF = None

**Симптом**: `python -m json.tool state/regime_state.json` показывает `regime: None` для 15m/1h/4h.
**Причина**: classifier v1 (`core/orchestrator/regime_classifier.py`) пишет туда — но он, видимо, не запущен. Все live tasks используют classifier v2 (`services/regime_classifier_v2/`) который НЕ персистит — каждый вызов `build_multi_timeframe_view()` пересчитывает с нуля.
**Последствие**: dashboard состояние `regime` пустое. Decision Layer R-rules **слепые** на live regime.
**Фикс**: добавить persist в `services/regime_classifier_v2/multi_timeframe.py` ИЛИ запустить classifier v1 параллельно. 1-2 часа.

### 3. Live OI / Funding — нет ingest pipeline

**Симптом**: `services/derivatives_ingest/` — это **historical batch** (1y backfill). Нет live poll.
**Последствие**: advisor v2 имеет код для `oi_price_div_1h_z` / `funding_rate_z`, но **читает свежие значения из 1y parquet** который не обновляется live. То есть momentum-флаг "OI/funding extreme" сегодня смотрит на цифры 04.05.
**Фикс**: live REST poll (Binance `/futures/data/openInterestHist` каждые 5 мин, `/fapi/v1/premiumIndex` для funding). 3-5 часов.

### 4. `data/exit_advisor/` — пустая папка

**Симптом**: exit_advisor запускается каждые 120 сек, но `data/exit_advisor/` пустая (нет outcome файлов).
**Причина**: либо exit_advisor работает но не пишет outcome'ы, либо логика срабатывания не выполняется ни разу за 5 дней.
**Последствие**: тестируется ли он вообще — не известно. У тебя SHORT -1.371 BTC, exit_advisor должен анализировать сценарии — но молчит.
**Фикс**: проверить триггер-логику. ~1 час диагностики.

### 5. `state/paper_trades.jsonl` — не существует

**Симптом**: paper_trader запускается, но за 8+ дней ни одной сделки.
**Причина**: paper_trader **читает setups.jsonl** и открывает виртуальные сделки на conf≥60%. Setup detector работал с 06.05 13:39 → 07.05 13:21 **сломан** (build_context_failed). После 13:21 — ICT reader загрузился. Возможно теперь начнёт писать.
**Последствие**: за 8 дней нулевая статистика по setup'ам — невозможно валидировать confidence_pct.
**Фикс**: setup_detector только что заработал (13:34). Через 24h посмотреть — пишет ли setups + paper trades.

---

## P1 — FUNCTIONAL BUT CHEATING / INCOMPLETE

### 6. setup_detector.build_context_failed pair=BTCUSDT (24+ часа сломан) — ✅ CLOSED 2026-05-07

**Симптом**: логи показывают `build_context_failed` каждые 60 сек 24+ часа подряд (06.05 23:13 → 07.05 13:21).
**Причина**: ICT levels parquet не загружался — путь сломан или файла не было. Заработал в 13:34 после рестарта.
**Последствие**: 24 часа НИ ОДНОГО setup'а не было обнаружено. `setups.jsonl` остановился на 06.05 13:39.
**Фикс**: ✅ DONE 2026-05-07 (commit 51a484f). stale_monitor расширен: `setups.jsonl` 1h threshold + `state_latest.json` 15min threshold. Если setup_detector замолчит снова на час — Telegram alert.

### 7. Live derivatives data — collected но не подаётся в advisor

**Симптом**: liquidation stream чинится сейчас (commit cb55907), `market_live/orderbook/` тоже мёртв с 03.05, `data/derivatives/` не обновляется live.
**Последствие**: advisor v2 строки про "OI/funding/taker imbalance" — выводят текст из устаревших parquet. Это **decoration**, не сигнал.
**Фикс**: связано с #3. Live ingest → live consumption.

### 8. Watchdog DEAD

**Симптом**: `python -m bot7 status` показывает `watchdog -- DEAD 13h ago`.
**Причина**: watchdog (отдельный supervisor) — отдельная сущность, не запускается app_runner'ом. Не запущен с прошлой ночи.
**Последствие**: если supervisor.py упадёт — некому его поднять. Сегодня я уже видел supervisor crash (PID change). Без watchdog'а это ручной recovery.
**Фикс**: включить watchdog scheduled task ИЛИ забить (если supervisor стабилен). Решение оператора.

---

## P2 — ЗАБЫТЫЕ TZ ИЗ PENDING

Эти не "сломаны", но **открыты и не активированы**:

### 9. TZ-DECISION-LAYER-CORE-WIRE — READY, не запущен

Самый важный из готовых. Decision Layer designed (`docs/DESIGN/DECISION_LAYER_v1.md` 376 строк), но **не зашит** в pipeline. R/M/P/D rules пишутся в pending_decisions, но никто их не читает на /advise.

**Эффект на трейдера**: /advise сейчас показывает verdict, но **не формализованный action card** ("M-1 forced unload, P-2 stack-bot allowed"). Decision Layer это даст.

**Эффорт**: 4-6 часов. У нас есть design doc, есть код-skeleton.

### 10. TZ-MARGIN-COEFFICIENT-INPUT-WIRE — OPEN

Margin coefficient не считается → **M-rules в Decision Layer dormant**. /margin команда есть, но margin не доходит до downstream.

**Эффорт**: 1-2 часа.

### 11. TZ-MTF-CLASSIFIER-PER-TF-WIRE — READY-AFTER

После Decision Layer — wire MTF disagreement signal в /advise.

### 12. TZ-MANUAL-LAUNCH-CHECKLIST — OPEN

Чек-лист первого бота. Завязан на твой SHORT cleanup.

### 13. TZ-POSITION-CLEANUP-SUPPORT — OPEN

Аналитика для твоего SHORT cleanup. Самая твоя живая боль.

---

## P3 — ЗАЛИПЛО В НИКУДА

### 14. `data/forecast_features/` — устаревшие данные

`full_features_1y.parquet` создавался когда forecast model был активен. Сейчас **decommissioned** (FORECAST_CALIBRATION_DIAGNOSTIC verdict). Но advisor v2 **всё ещё читает** этот parquet для momentum/flow/OI.

**Последствие**: советник получает features которые могут не обновляться (нужно проверить timestamp).

**Фикс**: либо обновлять parquet (cron), либо выкинуть зависимость.

### 15. `pattern_memory_BTCUSDT_1h_*.csv` (3 файла, ~3 MB)

Файлы pattern memory от 03.05. Последний апдейт. Использовались для какого-то ML в прошлом — сейчас не понятно.

**Решение**: проверить кем читаются. Если никем — в archive.

### 16. `decision_state.json` — устарел 5 дней

03.05 02:38. Никто не пишет.

### 17. `_archive` в state/ — что там

```
state/_archive/
```
— проверить, что внутри. Может что-то ценное.

---

## P4 — INFRASTRUCTURE DEBT

### 18. К14: рестарт обязателен

В MASTER §0 К14 говорит "после fix'а нужен реальный рестарт". Сегодня я несколько раз убедился: код в файлах ≠ код в памяти. Нужен **скрипт** `scripts/full_restart.sh` или /reload в Telegram, чтобы оператор мог легко применить fix.

### 19. Pre-commit hook защищает мёртвые файлы

`docs/STATE/QUEUE.md` — pre-commit hook не даёт удалить, хотя это устаревший документ. Сегодня я обошёл pointer'ом. Нужно почистить hook list.

### 20. bot7-keepalive / bot7-supervisor / bot7-state-snapshot — все scheduled tasks выключены

После сегодняшнего cleanup'а от orphan-процессов. **state-snapshot отключение и было причиной хвоста #1**. Нужно решить какие включить обратно.

### 21. 200+ CURRENT_STATE_*.md в `docs/STATE/`

Auto-rotation snapshots не ротируются. 211 файлов раздувают папку. План был в `CLEANUP_PROPOSAL.md` группа B — не сделан.

### 22. ETH полностью отсутствует в backtests/frozen/

Для cross-asset анализа BTC/ETH/XRP — ETH нужен. Закачать с 13.03.2024 (команды отправил оператору).

---

## P5 — DOCUMENTATION DEBT

### 23. `MASTER.md` §11 устарел (2026-04-29)

Статусы TZ-014..TZ-066 в MASTER не синхронизированы с PENDING_TZ.md. На MASTER §11 кто-то полагается, видит старое состояние.

### 24. `docs/CONTEXT/STATE_CURRENT.md` vs `docs/STATE/STATE_CURRENT_2026-05-05_EOS.md`

Сегодня я переименовал EOS файл в SESSION_CLOSE. Но `STATE_CURRENT.md` (без даты) — **не обновлялся с 05.05** (mtime 04.05 в README). Кто его должен обновлять?

### 25. `INVENTORY` файлы в `docs/STATE/` — старые

`INVENTORY_PAPER_JOURNAL_2026-04-29T232731Z.md`, `INVENTORY_SIGNAL_LOGGER_2026-04-30T004144Z.md` — snapshot от 29-30 апреля. Регенерировать или отнести в ARCHIVE.

### 26. `docs/specs/ADVISE_V2_SPEC_2026-04-30.md` — это spec advisor v0.1?

Один файл в `docs/specs/`. Если это spec для legacy advisor v0.1 (который мы сегодня выкинули) — в ARCHIVE.

### 27. Папка `docs/STRATEGIES/` с 1 файлом H10.md

H10 hypothesis — closed (decommissioned per SESSION_LOG D-100). Файл живой документ или archive?

---

## Сводка приоритетов

| Уровень | Что делать | Эффорт |
|---|---|---|
| **P0** (#1-#5) | Сегодня-завтра. Без них torговый pipeline дырявый. | 6-10 часов |
| **P1** (#6-#8) | Эта неделя. Functional integrity. | 3-5 часов |
| **P2** (#9-#13) | Следующая неделя. Decision Layer + execution. | 8-15 часов |
| **P3** (#14-#17) | Когда руки дойдут. Cleanup живых файлов. | 2-4 часа |
| **P4** (#18-#22) | Infrastructure. По одному в день. | 6-10 часов |
| **P5** (#23-#27) | Documentation. Раз в неделю. | 2-3 часа |

**Итого**: 27-47 часов чистой работы чтобы проект был "честно готов".

**Важная приоритизация**: пункты #1-#5 (P0) — это **prerequisites** для того чтобы /advise audit (commit cb55907) дал осмысленные данные за неделю. Без них audit будет писать verdict без полного context'а.

---

## Что НЕ требует моей работы (только твои решения)

1. Скачать historical data BTC+ETH+XRP с 13.03.2024 (команды отправлены)
2. Сбросить часть SHORT для unblock TZ-MANUAL-LAUNCH-CHECKLIST
3. Решить: /margin coefficient — какой источник биржи использовать
4. Решить: bot7-watchdog включать или нет
