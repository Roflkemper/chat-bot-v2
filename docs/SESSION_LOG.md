# SESSION LOG

## TZ-048 — Collectors memory leak fix: ParquetWriter rotation (2026-04-29)

**Root cause:** `pq.ParquetWriter` открыт 24 ч (до midnight rotation), накапливает C++
метаданные row groups линейно. 8 активных буферов × 13-24 MB/час = утечка подтверждена.

**Фикс:** threshold-based rotation в `collectors/storage.py`: `WRITER_MAX_ROWS=100k`,
`WRITER_MAX_BYTES=50MB`, `WRITER_MAX_AGE_S=1800s` (30 мин). После достижения любого
порога — `writer.close()`, путь инкрементируется (`{date}_N.parquet`), новый writer
открывается при следующем flush. Midnight rotation остаётся как safety net.

**Dev smoke:** 21 ротированных файл за 90s с WRITER_MAX_AGE_S=10s — механизм подтверждён.
**5 новых тестов** (test_collectors_storage_rotation.py): все green.
**Production rollout:** не выполнен — решение оператора (SIGTERM PID=5136).

## TZ-049 — Recover collectors/ from dangling git trees (2026-04-29)

**Проблема:** `collectors/` пакет существовал только как untracked директория в `C:\bot7`.
Был удалён (предположительно cleanup). Источники пропали с диска, в git никогда не коммитились.
Живой процесс PID=5136 держал модули в RAM — единственная оперативная копия.

**Recovery:** `git fsck --full --no-reflogs --unreachable` нашёл 640 dangling trees.
6 из них содержали полный `collectors/` пакет (15 файлов). Выбрана tree `c8801caa`
(единственная с timestamp-коммитом stash, ~2026-04-26, наибольший storage.py 8306 bytes).
Извлечение через `GIT_INDEX_FILE` temp index + `checkout-index` (без BOM, без воздействия на основной index).

**Результат:** 20 файлов закоммичены в `feature/tz-049-collectors-recovery`:
`collectors/` (15 файлов), `scripts/{watchdog,run_collectors,smoke_collectors}`,
`tests/test_collectors_parsers.py`, `_recovery/README.md`.
Все 36 collector-тестов зелёные. PID=5136 не тронут.

**Инвариант зафиксирован:** bytecode-only deployment запрещён. TZ-DEBT-04 в backlog.

## TZ-047 results 2026-04-28

Multi-asset episodes builder (BTC/ETH/XRP):
- Загружено: ETHUSDT_1m.parquet (11MB), XRPUSDT_1m.parquet (8.6MB), 366 дней
- Новый episodes.parquet: 7401 эпизодов (было 184 BTC profit_lock_opportunity)
- Распределение: BTC=1531, ETH=2878, XRP=2992
- BTC regression check: rally_strong=157 [50-200] PASS, rally_critical=42 [5-80] PASS
- Новые файлы: src/whatif/episodes_builder.py, src/whatif/binance_klines_downloader.py
- Отчёт: whatif_results/EPISODES_MULTIASSET_2026-04-28.md
- Статус: CLOSED

## 2026-04-29 — Финал сессии

### TZ-044 (backtest state isolation)
- Backtest больше не трогает live `state/regime_state.json`: `core.pipeline.build_full_snapshot(..., state_dir=...)` + backtest передаёт temp state_dir. Добавлены тесты на неизменность hash/mtime live state и независимость двух прогонов.

Закрытые TZ за день (хронологически):
- TZ-029-A smoke нового collectors runtime — PASS
- TZ-029-B cutover collectors на новый runtime
- TZ-030 supervisor full restart test (tree-kill, direct logging, heartbeat fix)
- TZ-031 system bootstrap (single command + Shell:Startup .bat)
- TZ-Codex-03 правила 11-13 в MASTER §0
- TZ-Codex-04 откат ошибочного 42 refs open question
- TZ-Codex-05 правило файлов спек в MASTER §0/§14
- TZ-027 H-WAIT-VS-CHASE comparative study (Codex)
- TZ-Codex-06 фиксация TZ-027 verdict
- TZ-D-ADVISOR-V1 /advise v2 cascade
- TZ-D-ADVISOR-V1-FIX-1 delta_1h_pct inline в pipeline
- TZ-D-ADVISOR-V1-FIX-2 auto outcome reconciliation
- TZ-D-ADVISOR-V1-FIX-3 watchdog status row + size_mode
- TZ-D-ADVISOR-V1-FIX-3-FOLLOWUP load_dotenv в config
- TZ-D-ADVISOR-V1-FIX-3-PATCH порог has_open_dd $-10
- TZ-033 supervisor crash investigation
- TZ-034 features pipeline live writer
- TZ-034-FIX-1 features_out parquet schema (DatetimeIndex)
- TZ-028-Codex H-CASCADE-DIRECTION study
- TZ-028-Codex-ADDENDUM marginal EV per entry event
- TZ-028-Codex-ADDENDUM-2 confidence intervals (CI overlap)
- TZ-Codex-07 фиксация confidence findings + правило §0 п15
- TZ-032-Codex P-13 LIQUIDITY-HARVESTER → REJECTED
- TZ-Codex-09 фиксация P-13 verdict
- TZ-035 multi-asset features (ETH+XRP)
- TZ-035-FIX-1 multi-asset вывод /advise (3 секции)
- TZ-036 cascade reader switch на live parquet
- TZ-038 incident response 12:50
- TZ-038-FOLLOWUP автозапуск watchdog
- TZ-039 collectors crash loop (orphan + lockfile)
- TZ-042 app_runner crash loop (orphan + 409 + retry)
- TZ-044 status false DEAD (cmdline matching через WMIC)
- TZ-045 Python orphans + memory monitor (TZ-DEBT-07 закрыт фундаментально)
- TZ-046 memory leak в collectors/storage.py (streaming ParquetWriter, tiered thresholds 300/500/800 МБ)
- TZ-Codex-08 правила и техдолг в MASTER §0
- TZ-Codex-10 обновление очереди
- TZ-041-Codex P-14 PROFIT-LOCK-RESTART → REJECTED (best mean +$12.27 но win_rate 22.83%)

Ключевые решения (продолжение нумерации D):
- D-064: правило операторской работы (MASTER §0 п15) — никаких строчных команд оператору, всё через ТЗ
- D-065/066: P-13 rejected (hi-variance не tradeable)
- D-067: TZ-DEBT-07 закрыт через TZ-045 (cmdline matching через WMIC для всех 5 процессов)
- D-068: 4 incident-а app_runner за день имели общий корень — lockfile валидировал только PID, не cmdline. Симптоматические фиксы накапливались, фундаментальный фикс TZ-045 закрыл проблему
- D-069: ADVISOR в проде на 3 активах (BTC/ETH/XRP) — live writer features + cascade reader на parquet, load_dotenv корректный, has_open_dd порог $-10
- D-070: H-CASCADE-DIRECTION CI overlap на всех 4 episode_type — каскад MAP §5 не опровергнут но статистически не подтверждён
- D-071: P-14 PROFIT-LOCK-RESTART rejected — гипотеза оператора 28.04 14:55 проверена. Best combo (pnl_threshold=1%, offset=1%, same side) win_rate 22.83% — психологически непригодно
- D-072: правило ТЗ-целостности (MASTER §0 п16) — каждое ТЗ самодостаточный блок, готовый к копированию, никогда не "см.выше". При правке — переписать весь ТЗ заново
- D-073: memory leak в collectors/storage.py read+concat+write паттерн → streaming ParquetWriter. Tiered alarm thresholds 300/500/800 МБ. Auto-restart app_runner при 800+ МБ

Открытые задачи на следующую сессию:
- PROD-CHECK ADVISOR через 24h (~29.04 после TZ-046 рестарта)
- TZ-029-C 24h validation коллекторов (~29.04 11:36 UTC)
- TZ-040 real bot snapshots в What-If (Codex next)

Технический долг для backlog:
- TZ-DEBT-08 ProcessPoolExecutor WinError 5 — повторяется на What-If прогонах (TZ-032, TZ-041), приходится использовать n_workers=1. Нужен fix для параллельных прогонов на Windows.
- 13 pre-existing test failures (test_grid_commands API, test_protection_alerts event loop pollution)
- TZ-DEBT-02 re-arm в bt-симуляторе — отложен до Шага 5

## 2026-04-29 — TZ-028-Codex-ADDENDUM-2 закрыт

Confidence-анализ 4 episode_type:
- rally_critical: P-6 130.69±82.73 vs P-7 62.18±42.89 — CI overlap
- rally_strong: P-6 54.73±27.76 vs P-7 50.01±14.96 — CI overlap
- dump_critical: P-6 79.12±43.91 vs P-7 46.83±27.58 — CI overlap
- dump_strong: P-6 45.89±17.64 vs P-7 67.49±14.21 — CI overlap

D-062: Все 4 episode_type показывают CI overlap для P-6 vs P-7.
       Caveat добавлен в OPPORTUNITY_MAP_v1.md §6 пункт 10.
       Каскад MAP §5 не опровергнут, но статистически не подтверждён.
D-063: Расширение выборки — следующий приоритет (multi-asset
       ETH/XRP либо real bot snapshots в What-If v2). Отдельный TZ
       после TZ-032.

## 2026-04-29 — TZ-027 H-WAIT-VS-CHASE закрыт

**Ключевой результат (196 BTC-эпизодов, 240-min горизонт):**
- REVERTED (n=64): P-2 +$189.88 vs P-1 -$0.36 → P-2 winner
- CONSOLIDATED (n=67): P-2 +$53.98 vs P-1 -$2.99 → P-2 winner
- CONTINUED (n=65): P-1 +$2.41 vs P-2 -$18.95 → P-1 winner ($21 edge)
- EV без знания будущего: P-2 +$73/эпизод, P-1 -$0.40/эпизод

D-060: каскад MAP §5 (P-2 раньше P-1) подтверждён эмпирически.
       Не править OPPORTUNITY_MAP_v1, не менять порядок каскада в ADVISOR.
D-061: P-1 эффективен только в CONTINUED-сценарии. Без надёжного
       предиктора continuation — P-2 dominant strategy на rally.

## 2026-04-28 (поздний вечер) — Handoff конца сессии

**Закрыто сегодня:**
- ✅ TZ-022 Шаг 7 (reports.py)
- ✅ TZ-024 (run_config + aggregator)
- ✅ Полный прогон What-If P-1..P-12 + SUMMARY
- ✅ TZ-028 supervisor (commit 7ba8ffd)
- ✅ TZ-Codex-01 collector audit
- ✅ TZ-Codex-02 OPPORTUNITY_MAP_v1.md

## 2026-04-28 — TZ-040 results 2026-04-28

**Темы:**
1. Реализация real snapshot replay слоя для What-If
2. Smoke/schema validation для tracker snapshots
3. Прогон CLI на P-1/P-2/P-6/P-7 × TEST_3/BTC-LONG-B/BTC-LONG-C
4. Проверка temporal overlap episodes vs tracker coverage

**Что сделано:**
- Добавлен пакет `whatif/` с `real_snapshot_replay.py` и CLI `real_replay.py`
- Loader поддерживает контракт ТЗ: parquet при наличии, CSV fallback по факту repo
- Реальный baseline считается по дельте tracker realized/unrealized
- Добавлены тесты `tests/whatif/test_real_replay.py` (smoke + schema + baseline delta)
- Сгенерирован `whatif_results/REAL_SUMMARY_2026-04-28.md`

**Факты по данным:**
- Tracker coverage для доступных live snapshots: с 2026-04-23/24 по 2026-04-28
- Для play P-1/P-2/P-6/P-7 доступные episode windows в текущем workspace заканчиваются
  раньше; overlap = 0 эпизодов
- Поэтому real replay завершился без падений, но без строк результата (`rows=0`)
- CI 95% для P-6 vs P-7 на real data не пересчитан: нет валидной выборки

**Проверки:**
- `pytest tests/whatif/test_real_replay.py -q` → 3 passed
- `python -m whatif.real_replay ...` → завершился, summary записан
- `RUN_TESTS.bat` по текущему workspace падает на collection:
  `ModuleNotFoundError: No module named 'tests.fixtures'`
  Полный regression count из этого запуска не подтверждён; роста относительно
  «13 pre-existing failures» по текущему состоянию repo оценить нельзя

## 2026-04-28 — TZ-042 fix tests.fixtures collection error

**Фикс:** добавлены `tests/__init__.py` и `tests/fixtures/__init__.py`, чтобы импорты вида
`from tests.fixtures...` работали в pytest.

**Результат:** `RUN_TESTS.bat` проходит collection и доходит до итогового отчёта.

**Regression shield status:** 12 failed / 488 passed / 1 skipped (без collection errors).
Baseline «13 pre-existing failures» обновлён до 12 (фактическое текущее состояние).

## 2026-04-28 — TZ-043 extend features_out coverage + opportunistic real validation

**Research:**
- Feature pipeline: `src/features/pipeline.py`, запуск: `scripts/run_features.py`
- Episodes extractor: `src/episodes/extractor.py` (`--start/--end`)

**Coverage факты:**
- tracker_max_ts: 2026-04-28 08:08:43 UTC
- raw OHLCV (scripts/frozen/*/klines_1m) покрывает только до 2026-04-24 23:59 UTC
- поэтому расширение `features_out` клипается до raw_klines_max_ts, реальный period 25-28.04 недоступен без новой загрузки OHLCV
  (зафиксировано в `whatif/features_coverage.json`)

**Episodes и inventory:**
- `whatif/episodes_inventory.py` сгенерил episodes на доступном окне tracker×features
- `whatif/episodes_inventory.json` содержит 12 plays × 3 bots = 36 ячеек
- n>=5 получился только для P-4 и P-12 (тип `no_pullback_up_3h`) — остальные plays требуют rally/dump, которых в этом периоде нет

**Real validation:**
- `whatif/opportunistic_validate.py` посчитал bootstrap CI95 для доступных plays (см. `docs/REAL_SUMMARY_2026-04-28.md`)
- BTC-LONG-B/BTC-LONG-C исключены из real validation: inverse боты, позиция не в BTC (юнит-несовместимость с replay v1)

**Решение:**
- OPPORTUNITY_MAP_v1 не пересматривать по ranking: данных для real CI пока нет
- Следующий шаг для TZ-040: либо накопить tracker coverage на даты новых episodes,
  либо пересобрать episodes на окне 2026-04-23+ и повторить real replay

## 2026-04-28 — TZ-041 regenerate episodes on tracker window (blocked)

**Цель:** перегенерить episodes на окне tracker coverage и пересчитать real CI95 для P-6 vs P-7.

**Факт:** `features_out/BTCUSDT` в этом workspace покрывает максимум 2026-04-24, поэтому окно
tracker клипается до 2026-04-24 23:00 UTC. На этом окне генератор episodes (`src/episodes/extractor.py`)
не нашёл ни одного эпизода типов rally/dump (`0 rows`), поэтому real-replay и CI95 на real data
не пересчитаны.

**Артефакты:**
- `whatif/episodes_window.json`
- `whatif/episodes_archive/pre_tz041/episodes_*.parquet` (архив старого episodes)
- `docs/REAL_SUMMARY_2026-04-28.md`

**Следующий шаг:** расширить coverage `features_out` на 2026-04-25..2026-04-28 (или позже),
после чего повторить TZ-041 и получить n>=5 эпизодов на cell.
- ✅ §12 Шаг 6

**Сводка SUMMARY 2026-04-27:**
- 3 profitable: P-6 (+$134), P-2 (+$38), P-7 (+$26)
- 3 harmful: P-8 (-$192), P-10 (-$46), P-5 (-$27)
- Остальные defensive/neutral
- Все harmful — про закрытие в минус (эмпирическое подтверждение P0)
- Все profitable — про открытие новой позиции на экстремуме

**Прогноз оператора vs факт:** 4 совпадения из 11 (P-2, P-6, P-7, P-8). Совпали края (топ + худший).

**Ключевые правки в /advise v2 от оператора:**
- HARD BAN list: P-5/P-8/P-10
- Размеры conservative(0.05)/normal(0.10)/aggressive(0.18)
- Liquidation risk override как первое правило
- Карта = empirical playbook v1, NOT execution guarantee

**Депозит:** $15k currently, реинвест, +$10-20k через 2 недели.

**В работе у Code:** TZ-029-A → TZ-D-ADVISOR-V1.
**В работе у Codex:** TZ-027 (опционально, параллельно).

**Косяки сессии (LESSONS):**
- К25: "X тестов зелёных" в отчёте ≠ работает в проде. Пример: TZ-016 заявлял 36/36, реально это parser-only тесты, не WS runtime. Обязательная проверка через продовый лог через 24h после деплоя.
- К26: Расхождение между двумя collector runtime в репо обнаружено только при audit на 33-й день. Раз в неделю sanity check продовых процессов через `bot7 status`.

**Открытые вопросы (не блокируют):**
- Размеры режимов под депозит $25-35k — пересчитать после пополнения
- Multi-horizon прогон для defensive plays (720/1440) — для v2 карты
- Real bot snapshots в What-If v2 (88k snapshots уже накоплено)

**Следующая сессия должна начаться с:**
1. Чтения MASTER + PLAYBOOK + OPPORTUNITY_MAP_v1 + последних 3 записей SESSION_LOG
2. Проверки статуса TZ-029-A и TZ-D-ADVISOR-V1 от Code
3. Проверки статуса TZ-027 от Codex
4. Если Code закрыл TZ-029-A — нарезать TZ-029-B..G по результатам smoke

## 2026-04-28 (вечер) — Шаг 6 закрыт: Карта возможностей v1

**Темы:**
1. Анализ SUMMARY_2026-04-27 (11 plays)
2. Согласование Карты возможностей с оператором
3. Фиксация OPPORTUNITY_MAP_v1.md
4. TZ-028 supervisor закрыт (commit 7ba8ffd)

**Ключевые решения:**
- D-054: Топ-3 приёма (P-6/P-2/P-7) — все про открытие новой позиции на экстремуме
- D-055: HARD BAN list для /advise v2: P-5/P-8/P-10. Все три про закрытие в минус, эмпирически вредны (-$26 до -$192).
- D-056: Размеры позиций — три режима conservative(0.05)/normal(0.10)/aggressive(0.18). 0.18 ТОЛЬКО при free margin >60% и отсутствии DD.
- D-057: Liquidation risk override как первое правило советника. distance to liq < 15% → ТОЛЬКО defensive plays.
- D-058: Карта v1 = empirical playbook, НЕ execution guarantee. Ограничения 6-10 (multi-horizon, ICT, real snapshots, macro, P-3 missing data) — для v2.
- D-059: P-6 не маркетировать как "уверенно зарабатывать" — n=39 эпизодов, требует подтверждения на 720/1440.

**Что сделано в файлах:**
- docs/OPPORTUNITY_MAP_v1.md — новый файл, карта решений + псевдокод /advise v2
- docs/MASTER.md §11/§12 — Шаг 6 закрыт
- src/supervisor/* — TZ-028 commit 7ba8ffd

**Депозит / экспозиция:**
- $15k currently, реинвест активен
- Запланировано пополнение +$10-20k через 2 недели
- После пополнения карта будет переоткалибрована (новые лимиты режимов)

**Открытые задачи:**
1. /advise v2 — реализация по OPPORTUNITY_MAP_v1.md (Code, следующий)
2. TZ-029-A..G — пакет фиксов коллекторов (после TZ-028 готов)
3. TZ-027 H-WAIT-VS-CHASE comparative study (Codex)
4. TZ-026 grid simulation для stack-приёмов (Code)
5. TZ-025 alert noise fix (Code, deferred)

## 2026-04-28 — Audit коллекторов: расхождение с заявленным

**Темы:**
1. Полный прогон What-If P-1..P-12 завершён — SUMMARY получен
2. Прогноз оператора vs факт: 4 совпадения из 11
3. Audit коллекторов: реально работают только Binance+Bybit liquidations,
   HL/OKX/BitMEX/orderbook/trades НЕ запущены
4. Логирование разбросано по 3 терминалам — TZ-028 в работе

**Ключевые решения:**
- D-052: Топ-3 приёма (P-6/P-2/P-7) подтверждены данными.
  Худшие три (P-8/P-10/P-5) — все про закрытие в минус.
  Эмпирическое подтверждение P0 принципа.
- D-053: Запись 27.04 в SESSION_LOG про "5 бирж + L2 + trades, 36/36
  тестов" фактически некорректна. Реально работают 2 биржи только
  liquidations. См. TZ-029_COLLECTOR_AUDIT.md.
- К25 (lesson): Отчёты Code/Codex про "X тестов зелёных" не
  гарантируют работу в проде (повтор К14). Нужна обязательная
  проверка через продовый лог через 24h после деплоя.

**Что сделано в файлах:**
- whatif_results/SUMMARY_2026-04-27.md — полный прогон 11 plays
- whatif_results/P-{1..12}_2026-04-27.md — индивидуальные отчёты
- whatif_results/{*}_raw.parquet — детальные данные для top/worst-5
- docs/specs/TZ-029_COLLECTOR_AUDIT.md — audit документ (см. отдельно)

**Открытые задачи:**
1. Шаг 6 §12 — Карта возможностей (Claude в чате)
2. TZ-028 — unified logging + supervisor (Code)
3. TZ-029 — collector fix по приоритетам из audit (Code, после Codex audit)
4. TZ-027 — H-WAIT-VS-CHASE comparative study (Codex)
5. TZ-026 — grid simulation для stack-приёмов (Code)
6. TZ-025 — alert noise fix (Code, deferred)

## 2026-04-27 (вечер 4) — TZ-025 алерт-шум зафиксирован

**Тема:** оператор отметил спам в Telegram-алертах. За 5 часов ~25 LEVEL_BREAK, многие на одних уровнях туда-обратно (77634/77668/77690 по 3-4 раза). RSI_EXTREME — 3 алерта на одном oversold-состоянии за 2ч.

**Решение:**
- D-051: TZ-025 (фикс алерт-шума) откладывается до завершения Шага 6 §12. Не блокирует прогон Шага 5.
- К24 (lesson): алерты в проде должны иметь дедупликацию by default. Не делать NEW алерты без этого.

**Что делать в TZ-025 (детали для будущей сессии Code):**
1. LEVEL_BREAK: дедуп по (уровень, направление) на окно N минут (N=30 параметр); фильтр пробоя через закрытие 5m свечи за уровнем, не tick
2. RSI_EXTREME: дедуп — один extreme state = 1 алерт пока RSI не вышел из зоны и не зашёл обратно
3. Прорежение уровней: группировка близких ($20 расстояние) ИЛИ whitelist значимых (round numbers, PDH/PDL, KZ-H/L) с дропом промежуточных
4. Adaptive Grid отчёт: проверить периодичность, перевести на on-change или увеличить интервал

**Не делать в TZ-025:**
- Менять логику самих детекторов LEVEL_BREAK/RSI_EXTREME — только дедуп и фильтрацию
- Трогать другие алерт-каналы (KILLSWITCH, COUNTER-LONG-AUTO) — они сейчас не шумят

## 2026-04-27 (вечер 3) — Шаг 5 What-If MVP работает

**Темы:**
1. TZ-022 Шаги 1-7 завершены или в финале (acceptance gate пройден на P-1)
2. TZ-023 weekend gap features закрыт (4 колонки, schema 179→183)
3. Acceptance test P-1 на 196 эпизодах BTC: данные осмысленные
4. Diagnosis: P-1 raise_boundary даёт небольшой негатив на 240-min горизонте, снижает peak DD
5. Реализован baseline в grid_search.py + pnl_vs_baseline колонки

**Ключевые решения:**
- D-045: pnl_vs_baseline_usd добавлен в Outcome metrics, аналогично dd_vs_baseline_pct
- D-046: target_hit_pct добавлен в aggregation grid_search
- D-047: P-1 на 240-min горизонте показывает -$2 alpha, win_rate 7-11%. Реалистично — это защитный приём, не зарабатывающий
- D-048: smysl P-1 — защита от маржин-колла на длинных горизонтах. 240-min не захватывает. v2: longer horizon для defensive plays
- D-049: last_in_price добавлен в Snapshot для корректной симуляции grid IN levels
- D-050: PlayConfig имеет symbols filter (P-1/P-2/P-6/P-12 → BTCUSDT only)

**What-If P-1 results (196 BTC episodes, 240-min horizon):**
- 4 combo offset_pct ∈ [0.3, 0.5, 0.7, 1.0]
- mean_pnl_vs_baseline_usd: -1.97 to -2.00 (small negative)
- win_rate: 0.066-0.112 (7-11%)
- mean_dd_vs_baseline_pct: -0.04 to -0.09 (action reduces peak DD)
- mean_target_hit_pct: 0.077 константа (target не зависит от boundary)
- Время прогона: 33s

**Что сделано в файлах:**
- src/episodes/extractor.py + tests (TZ-021, 16 tests, 197659 episodes)
- src/features/weekend_gap.py + tests (TZ-023, 47 tests, 4 new cols)
- src/whatif/ Шаги 1-6 (TZ-022, 202 tests)
- frozen/labels/episodes.parquet (197659 эпизодов)
- features_out/ регенерирован с 183 колонками
- whatif_results/P-1_2026-04-27.parquet (16 combo × 196 episodes)

**Открытые задачи (для нового чата):**
1. Шаг 7 reports.py — markdown отчёты по результатам What-If
2. Полный прогон What-If по всем 12 приёмам P-1..P-12
3. TZ-DEBT-05: обновить frozen/ (download_historical.py — последний день 24.04)
4. TZ-DEBT-06: рассинхрон consec_bull/_1h_up в schema (не блокирует)
5. v2 functionality: longer horizons для defensive plays, integration с реальными bot snapshots

## 2026-04-27 (вечер 2) — TZ-021 episodes extractor + Шаг 5 в работе

**Темы:**
1. TZ-021 episodes extractor реализован (16 тестов)
2. 197659 эпизодов извлечены за 1095 partition × 3 символа
3. Output: frozen/labels/episodes.parquet (18 episode types)
4. TZ-022 What-If engine — Шаги 1-6 закрыты Code (Snapshot, ActionSimulator, HorizonRunner, Outcome, GridSearch, Runner+CLI)
5. Acceptance test P-1 выявил 3 проблемы — фиксятся

**Ключевые решения:**
- D-040: episodes.parquet используется как ground truth input для What-If
- D-041: TZ-DEBT-06 открыт — рассинхрон TZ-017 spec (consec_1h_up) vs реальная schema (consec_bull). Не блокирует, документировать.
- D-042: rally/dump counts выше bounds ТЗ-021 — реалистично для волатильного года 2025-2026
- D-043: P-1/P-2/P-6/P-12 в What-If ограничиваются symbols=BTCUSDT (приёмы для BTC шорт-бота)
- D-044: Snapshot расширяется полем last_in_price для корректной симуляции grid IN levels

**Что сделано в файлах:**
- src/episodes/extractor.py + tests (TZ-021)
- frozen/labels/episodes.parquet (197659 эпизодов × 10 колонок)
- src/whatif/snapshot.py + action_simulator.py + horizon_runner.py + outcome.py + grid_search.py + runner.py + CLI (TZ-022 Шаги 1-6, 202 теста)

**Sanity counts (BTCUSDT):**
- rally_strong: 157, rally_critical: 39
- dump_strong: 232, dump_critical: 50
- pdh_swept: 132, pdl_swept: 142
- no_pullback_*: выбивается из bounds (TZ-DEBT-06)

**Открытые на v2:**
- TZ-DEBT-06: унификация consec_bull/_1h_up в schema
- Acceptance gate Шага 5 на P-1 после фиксов last_in_price
- Шаг 7 reports.py

**Следующие шаги:**
1. Code: фиксы по acceptance P-1 (last_in_price в Snapshot, symbols в PlayConfig)
2. Code: повторный прогон P-1 на BTC-only
3. Code: Шаг 7 reports.py
4. После acceptance — полный прогон P-1..P-12

## 2026-04-27 — Шаг 4 закрыт: Feature Engine + pipeline на реальных данных

**Итог:**
- TZ-017 полностью закрыт: 7 модулей, 277 тестов зелёных
- 1095 партиций (3 × 365 дней), 179 колонок, 49 сек полный прогон
- Pipeline: `scripts/run_features.py`, output: `features_out/`

**Открытые debt:**
- TZ-DEBT-03: `test_protection_alerts.py` — 12 тестов падают в suite из-за `asyncio.get_event_loop()` в Python 3.10. Активный модуль, фикс тривиальный (asyncio.run), отложено.
- TZ-DEBT-05: `funding_8h.parquet` обрывается 2026-03-31, ~27 дней без funding-фич. Решение: запускать `download_historical.py` раз в неделю. Не блокирует bt.

**Следующий шаг:** Шаг 5 — What-If бэктест на `features_out/`.

---

## 2026-04-27 (вечер) — TZ-019 PLAYBOOK composition layer закрыт

**Темы:**
1. Реализован composition layer над TZ-018 detectors
2. PlaybookRegistry загружает 10 приёмов из PLAYBOOK.md
3. Validator с категоризацией unresolved refs
4. CLI tool python -m src.playbook.cli validate [--strict] [--verbose]

**Ключевые решения:**
- D-035: Unresolved refs категоризированы: future-feature / window-context / grid-placeholder / unknown
- D-036: X, Y в comparisons trated as grid-placeholder (warning, runtime False)
- D-037: Window context (latest_bar_close, previous_bar_high) — отложено до v2

**Что сделано:**
- src/playbook/ полная реализация (60+ unit + 20 acceptance тестов, всего ≥80)
- 10 приёмов P-1..P-10 готовы к What-If бэктесту
- Validator готов как pre-commit hook

**Открытые на v2:**
- Window context predicates
- Bot/portfolio signals (после интеграции portfolio module)
- Composite detectors для частых паттернов (momentum_loss_detected, reversal_confirmation)

**Следующие шаги:**
1. Module 6+7 от Code (cross_asset + pipeline)
2. После Module 7 — добавить P-11 weekend_gap, P-12 adaptive_grid в PLAYBOOK
3. Обновить MASTER §4 имена сессий (NYAM/NYLU/NYPM → NY_AM/NY_LUNCH/NY_PM)

Append-only журнал сессий. Каждая запись = блок с датой, темами, решениями, открытыми вопросами. Только дельта, не дублировать MASTER/PLAYBOOK.

---
## 2026-04-27 — TZ-016/TZ-017/TZ-018 параллельная работа
2026-04-27 — TZ-016/017/018/019 + Adaptive Grid в контексте
Темы:

TZ-016 коллекторы: расширены до 5 бирж (Binance/Bybit/HL + BitMEX + OKX), 36/36 unit-тестов, прогон 24h на машине оператора стартовал
TZ-017 feature engine: Modules 1-4 закрыты (calendar/killzones/dwm/technical), 173 теста кумулятивно. Module 5 derivatives.py — в работе
TZ-018 detector predicates: 86 канонических детекторов в registry + LEGACY_ALIASES, 411 тестов зелёные, принят
TZ-019 PLAYBOOK composition layer: ТЗ передан Codex параллельно с feature engine
ICT_KILLZONES_SPEC обновлён до v1.2 (фиксы по результатам Module 2 + добавление current day H/L)
Adaptive Grid Manager: восстановлен в контексте — функционал реализован 26.04 утром, не попал в финальную консолидацию вечером. В новой парадигме = один из приёмов PLAYBOOK
TZ-DEBT-02 (re-arm в bt-симуляторе): принято решение не чинить сейчас — архитектура What-If снимает 80% потребности
Эпизод P-11 weekend_gap_false_breakout записан как новый приём из реального события 27.04 (top 79200 → 77600)

Ключевые решения:

D-029: Canonical имена детекторов сессий — D-SESSION-NY_AM/NY_LUNCH/NY_PM (с подчёркиваниями). MASTER §4 нужно обновить (там старые NYAM/NYLU/NYPM)
D-030: Detectors — pure functions без I/O, registry + get_detector() для legacy resolve
D-031: Параллельная работа Code (features) + Codex (detectors+composition) — schema коммуникация через ТЗ-документы, без code-coupling
D-032: TZ-DEBT-02 не чинить до Шага 5. К Шагу 5 — оценить нужна ли re-arm логика. Если да, чинить через 15min микро-сегменты, не большие окна
D-033: Adaptive Grid — это уже реализованный пример приёма PLAYBOOK (action A-CHANGE-TARGET × 0.6 + A-CHANGE-GS × 0.67). Не отдельный модуль. Калибровка через bt после фикса TZ-DEBT-02 либо через What-If архитектуру
D-034: P-11 weekend_gap_false_breakout — добавить в PLAYBOOK после завершения TZ-019 (чтобы не сломать acceptance tests Codex)

Косяки этой сессии (LESSONS):

К21: При ревью TZ-018 Codex прислал "409 collected lines" вместо "X passed tests" — надо требовать конкретные числа в формате pytest, не collect-only output
К22: Не заметил пробел в документации Adaptive Grid — финальные 3 файла консолидации 26.04 не содержали этого функционала, узнал только после прямого вопроса оператора
К23: Использовал технический жаргон в объяснении adaptive grid ("target × 0.6, gs × 0.67") — оператор справедливо попросил объяснять по-русски и понятнее

Открытые вопросы (не блокируют):

TZ-DEBT-02: будет нужна re-arm логика в Шаге 5 или нет
Macro данные (SPX/gold/DXY/oil) — нужны для P-11 контекста, реализация через yfinance в отдельном TZ позже
Bot snapshot features (позиция, unrealized, dwell) — отсутствуют в TZ-017, нужны для adaptive grid bt-калибровки. Отдельный модуль когда дойдём до интеграции

Что сделано в файлах:

src/collectors/ — TZ-016 полная реализация, в проде, прогон 24h
src/features/calendar.py — Module 1 (43 теста)
src/features/killzones.py — Module 2 + sweep wick fix (45 тестов)
src/features/dwm.py — Module 3 (40 тестов)
src/features/technical.py — Module 4 (45 тестов)
src/detectors/ — TZ-018 полная реализация (411 тестов), 86 detectors + LEGACY_ALIASES
specs обновлены: ICT_KILLZONES_SPEC v1.2, TZ-017_FEATURE_ENGINE v1
Создан P-11_WEEKEND_GAP_FALSE_BREAKOUT.md (черновик, добавить в PLAYBOOK после TZ-019)

Текущее состояние портфеля (на момент сессии):

ROFLKemPer: SHORT -0.576 BTC entry $78248, liq $102434 (запас 27.7%)
LONG 7500 USD entry $77779, current loss -$11
Балланс $126,946 (+3.8% за 24ч)
Volume 24ч: $130,111
4 бота tightened через Adaptive Grid в дрy-run (TEST_1/2/3 + один main)
TEST_3 и TEST_1 released после восстановления unrealized > -$50
Сегодня сработал реальный P-11: top 79200 (00:55 UTC) → 77600 (08:30 UTC)

Следующие шаги:

Дождаться 24h отчёта коллекторов
Module 5 derivatives.py от Code (в работе)
Шаг 1 expected_columns.py от Codex (TZ-019)
После Module 7 + TZ-019 — добавить P-11 в PLAYBOOK, обновить MASTER §4 имена сессий
**Темы:**
1. TZ-016 коллекторы (Claude Code) — 5 бирж, 36/36 unit, прогон 24h
2. TZ-017 feature engine (Claude Code) — Modules 1-3 готовы (calendar/killzones/dwm), 128 tests green
3. TZ-018 detector predicates (Codex) — 86 detectors + LEGACY_ALIASES, 411 tests green

**Ключевые решения:**
- D-029: NY_AM/NY_LUNCH/NY_PM (с подчёркиваниями) — canonical names. NYAM/NYLU/NYPM в MASTER §4 устарели, обновить.
- D-030: Detectors — pure functions без I/O, registry + get_detector() для legacy resolve.
- D-031: Параллельная работа Code (features) + Codex (detectors) — schema коммуникация через ТЗ-документы, без code-coupling.

**Что сделано в файлах:**
- src/collectors/ (TZ-016 — в работе, прогон 24h)
- src/features/ (TZ-017 — Modules 1-3)
- src/detectors/ (TZ-018 — готов)

**Статус коллекторов:** 24h прогон стартовал [время], отчёт ожидается [время].

**Следующие шаги:**
1. Получить отчёт 24h по коллекторам
2. Module 4 technical.py (Claude Code)
3. Modules 5-7 (derivatives/cross_asset/pipeline)
4. После Module 7 — integration test detectors × features на реальном feature DataFrame
## 2026-04-26 (ночь) — Шаг 2 выполнен ✅

**Темы:**
1. Запуск `download_historical.py` оператором
2. Валидация скачанных данных (klines, metrics, funding)

**Результат:**
- 2229 / 2229 файлов скачаны успешно за 8.6 минут (0 ошибок, 0 missing, 0 fail)
- BTC klines 1m: 525,600 строк = 1 год минут БЕЗ ПРОПУСКОВ
- BTC metrics 5m: 105,117 строк (OI + L/S ratio top+retail + taker volume)
- BTC fundingRate: 1188 строк (13 месяцев с 01.03.2025)
- ETH/XRP: аналогично
- Размер на диске: ~270 MB

**Что это даёт:**
- Полный годовой датасет для What-If бэктеста готов
- Все ключевые деривативные фичи доступны (OI, funding, L/S ratio retail+top, taker imbalance)
- 0 пропусков в klines = можно строить minute-by-minute simulation без compensation

**Следующие шаги:**
1. Шаг 3 — real-time коллекторы (новый чат с Claude Code)
2. Параллельно — после Шага 3 готов → Шаг 4 (feature engine)

---

## 2026-04-26 (поздний вечер) — Скрипт скачивания + проверка протокола

**Темы:**
1. Решение по реализации Шага 2: локально на машине оператора (не Claude Code, не Codex) — скачивание это HTTP+распаковка, никакой логики
2. Написан `download_historical.py` (~17 KB) с защитой от падений (resume, retry, checksum, parallel)
3. Команды запуска для PowerShell даны
4. Проверка протокола начала сессии в новом чате — успех

**Ключевые решения:**
- D-026: Скачивание данных и любые batch-задачи — локально оператором, не через Claude/Code (экономия поинтов)
- D-027: Шаг 2 не требует ТЗ для Claude Code, скрипт уже готов
- D-028: Протокол начала сессии (MASTER §14) работает — новый Claude корректно подтвердил статус и задал точный уточняющий вопрос вместо догадок

**Что сделано:**
- `download_historical.py` написан и протестирован
- MASTER §12 шаг 2 переформулирован (скрипт готов, не требует Claude Code)
- MASTER §11 обновлён (статус скрипта)

**Что от оператора:**
- Запустить скрипт `cd C:\bot7\scripts && C:\bot7\.venv\Scripts\python.exe download_historical.py`
- ~30-60 минут ждать
- Если FAIL > 0 — прислать последние 30 строк лога

**Следующие шаги:**
1. Оператор запускает скачивание
2. Параллельно — новый чат с Claude Code пишет ТЗ для Шага 3 (real-time коллекторы)
3. После завершения скачивания — Шаг 4 (feature engine, включая ICT killzones)

---

## 2026-04-26 (вечер) — Консолидация и переориентация

**Темы:**
1. Прочитаны 150 фрагментов переписки klod.txt полностью (после второго подхода)
2. Критика ГПТ по архитектуре
3. Переосмысление цели: «зарабатывать всеми способами», не «защита от просадки»
4. Решение по бесплатным источникам данных (data.binance.vision хватает)
5. Загружен индикатор ICT Killzones & Pivots [TFO]
6. Консолидация 21 файла → 3 файла (MASTER + PLAYBOOK + SESSION_LOG)

**Ключевые решения:**
- D-018: Главная задача — зарабатывать всеми возможными способами на данных, не «защита боли»
- D-019: Backtest = What-If симулятор приёмов, не grid search параметров ботов
- D-020: PLAYBOOK = источник для кода (machine-readable), не документация
- D-021: Активы — BTC + ETH + XRP (не только BTC). ETH как follower, XRP как реактивный
- D-022: Данные — только бесплатные источники. Никаких CoinGlass/Tardis/Amberdata
- D-023: ICT killzones — реализовать на Python из переданного Pine кода, не использовать TradingView
- D-024: Структура документации — 3 файла (MASTER + PLAYBOOK + SESSION_LOG), всё остальное архивируется
- D-025: Протокол начала сессии — копи-паст команда (см. MASTER §14)

**Косяки этой сессии (для LESSONS):**
- К18: Перестал читать переписку на половине, сделал v0.1 на 50 фрагментах. Оператор справедливо заметил.
- К19: Собирал «главные эпизоды» вместо систематической разметки всей истории. Оператор: «главных нет, всё имеет значение».
- К20: Снова съехал в каталог-программирование вместо TRADER CONTROL LAYER. Поправил после ГПТ-критики.

**Открытые вопросы (не блокируют, но ждут ответа):**
- Параметры P-2 размера доп.шорта (зависит ли от ситуации?)
- Точные пороги P-9 «быстрый рост» vs «контролируемый»
- Принципы работы с большой шорт-позицией ($45k+) при росте выше 80k
→ **Все эти вопросы переходят в grid search в What-If backtest**, не требуют ответа от оператора

**Что сделано в файлах:**
- Создан MASTER.md v1.0 — единый источник правды (15 разделов)
- Создан PLAYBOOK.md v1.0 — 10 приёмов в machine-readable yaml блоках
- Создан SESSION_LOG.md (этот файл)
- Готов гайд по очистке старых 21 файлов

**Следующие шаги:**
1. Оператор переносит 3 файла в репо C:\bot7\docs\
2. Оператор архивирует старые 21 файл по гайду
3. В новом чате оператор использует протокол начала сессии (MASTER §14)
4. Следующая работа — Шаг 2 плана: скачивание исторических данных (см. MASTER §12)

**Текущее состояние портфеля (на момент сессии):**
- ROFLKemPer: SHORT -0.622 BTC entry 77844 liq 99869 (запас ~21.7%)
- LONG 1000 USD entry 77689 (закрыт в зоне liq шортистов 78400+)
- Ждёт отката для re-entry лонга
- Цена BTC ~78400 на 22:15

---
