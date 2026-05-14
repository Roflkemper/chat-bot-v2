# Group I Audit — карточки 39 файлов

> **Создан**: 2026-05-07
> **Назначение**: систематизированный аудит файлов в корне `docs/`, `docs/CONTEXT/`, `docs/STATE/`, `docs/CANON/`. Каждая карточка фиксирует суть файла и значимые решения, чтобы при чистке ничего не потерялось.
> **Статус**: справочник для принятия решений. Действий по файлам ещё не предпринято.
> **Парный документ**: [INDEX.md](INDEX.md) — общая карта; [CLEANUP_PROPOSAL.md](CLEANUP_PROPOSAL.md) — план перемещений.

---

## Карточки

### 1. MASTER.md
- **Размер**: 729 строк
- **Последнее обновление**: 2026-04-30 (в тексте), mtime 2026-05-03
- **Суть**: Главный единый источник правды по проекту Grid Orchestrator. Содержит правила общения (§0), цель проекта (§1), фазы (§2), архитектуру слоёв L1–L7 (§3), каталог детекторов 86 шт. (§4), каталог действий (§5), пресеты ботов (§6), принципы P0–P8 (§7), источники данных (§8), ICT killzones (§9), краткий список приёмов P-1..P-12 (§10), статус задач TZ-014..TZ-066 (§11), 9-шаговый план (§12), §16 OPERATOR TRADING PROFILE.
- **Ключевые решения/выводы**:
  - Анти-косяки К14–К26 (рестарт обязателен; «тесты зелёные» ≠ работает; не делать алертов без дедупа)
  - Правила ТЗ-целостности (один цельный блок, никаких «см.выше»)
  - Текущая фаза = 5 (аналитик-помощник, dry-run)
  - Полный список 33 закрытых TZ за 29.04 + бэклог
  - §16: SHORT linear, LONG inverse; HARD BAN P-5/P-8/P-10; sizing conservative/normal/aggressive
- **Дубликаты/пересечения**: §11 пересекается с STATE/QUEUE.md, STATE_CURRENT.md; §3–§4 — с PROJECT_CONTEXT.md; §10 — с PLAYBOOK.md (краткая ссылка)
- **Статус**: AUTHORITATIVE (но устарел в части §11 — статусы до 30.04)
- **Рекомендация**: KEEP (но §11 нуждается в синхронизации с STATE_CURRENT/PENDING_TZ)
- **Аргумент**: Это единственный документ с полной картой стратегии P0–P8 + детекторами + действиями.

### 2. SESSION_LOG.md
- **Размер**: 885 строк
- **Последнее обновление**: 2026-04-30 evening (последняя запись); mtime 2026-05-03
- **Суть**: Append-only журнал сессий с 26.04 по 30.04. Каждая запись = блок с датой/темами/решениями/открытыми вопросами/файлами. Содержит хронологию TZ-016 → TZ-066 + lessons К18–К26 + decisions D-018..D-073.
- **Ключевые решения/выводы**:
  - 30.04 evening: 4-layer combo filter, MIN_ALLOWED_STRENGTH=9, +$17,404/yr
  - 30.04: INC-014 architectural amnesia (CANON/* duplicates MASTER) — основа для §16
  - D-100..D-104: engine fixes A2+A3, decision_log KEEP, managed_grid_sim KEEP
  - 27–28.04: Шаг 5 What-If MVP, P-1 acceptance (-$2 alpha), HARD BAN P-5/P-8/P-10
  - 26.04: D-018..D-025 (3-file consolidation, BTC+ETH+XRP, ICT killzones реализуем сами)
- **Дубликаты/пересечения**: пересекается с MASTER §11, INCIDENTS.md (К-инциденты), STATE/QUEUE.md (TZ статусы)
- **Статус**: AUTHORITATIVE (исторический журнал; обрывается 30.04)
- **Рекомендация**: KEEP
- **Аргумент**: Единственный связный нарратив «что делалось когда» — критичен чтобы вспомнить решения D-018..D-073.

### 3. PROJECT_MANIFEST.md
- **Размер**: 20 строк
- **Последнее обновление**: 2026-05-02 (mtime)
- **Суть**: Очень короткий список правил разработки: «только готовые файлы», «без воды», «GRID/TRADER VIEW раздельно», «structure flags отдельным модулем».
- **Ключевые решения**: GRID VIEW и TRADER VIEW держать раздельно; structure flags через snapshot в engine.
- **Дубликаты/пересечения**: правила формирования ТЗ — фрагментарно повторены в MASTER §0; структурное правило про GRID/TRADER VIEW нигде больше не зафиксировано.
- **Статус**: REFERENCE (фрагмент)
- **Рекомендация**: ARCHIVE (но GRID/TRADER VIEW правило перенести в MASTER §0 или PLAYBOOK)
- **Аргумент**: CLEANUP_GUIDE сам помечает PROJECT_MANIFEST.md как АРХИВ — всё что важно, дублируется в MASTER §0/§1, кроме правила про GRID/TRADER VIEW.

### 4. NEXT_CHAT_PROMPT.md
- **Размер**: 60 строк
- **Последнее обновление**: 2026-04-29 (mtime)
- **Суть**: Шаблон first-message для нового чата от 27.04 — поручает прочитать MASTER+PLAYBOOK+SESSION_LOG, описывает где остановились (Шаг 5 What-If acceptance P-1).
- **Ключевые решения**: формализован 5-строчный handshake; Code/Codex/Claude разделение ролей.
- **Дубликаты/пересечения**: дублирует MASTER §14 (протокол начала сессии); CONTEXT/MAIN_CHAT_OPENING_PROMPT_2026-05-04.md (более новая версия для MAIN coordinator).
- **Статус**: SUPERSEDED (контекст 27.04, упомянуты задачи которые давно закрыты — Шаг 7 reports.py = DONE)
- **Рекомендация**: ARCHIVE
- **Аргумент**: Заменён MAIN_CHAT_OPENING_PROMPT_2026-05-04.md и MASTER §14.

### 5. BASELINE_INVESTIGATION_DESIGN_v0.1.md
- **Размер**: 323 строки
- **Последнее обновление**: 2026-04-18 (в тексте); mtime 2026-05-02
- **Суть**: Дизайн расследования недетерминизма бэктеста (3 прогона = разные результаты). Перечисляет 3 подозреваемых: `datetime.now()` в pipeline, persistent regime_state.json, pattern memory CSV.
- **Ключевые решения**: 3 решения А (изоляция state) / B (инжекция времени свечи) / C (frozen baseline state). План в 4 шага.
- **Дубликаты/пересечения**: проблема решена в TZ-044 (backtest hermetic state isolation, 29.04, MASTER §11) — `core.pipeline.build_full_snapshot(..., state_dir=...)`.
- **Статус**: SUPERSEDED (проблема закрыта TZ-044)
- **Рекомендация**: ARCHIVE
- **Аргумент**: Реализация done.

### 6. CALIBRATION_LOG_DESIGN_v0.1.md
- **Размер**: 903 строки
- **Последнее обновление**: 2026-04-18 (в тексте); mtime 2026-05-02
- **Суть**: Дизайн системы логирования решений оркестратора (calibration_log) + daily report.
- **Ключевые решения**: разделение trade_journal vs calibration_log; ежедневный `/daily_report`.
- **Дубликаты/пересечения**: реализовано в `services/decision_log/` (TZ-DECISION-LOG-V2 30.04) + `services/advise_v2/paper_journal.py`.
- **Статус**: SUPERSEDED
- **Рекомендация**: ARCHIVE
- **Аргумент**: Концепции живут в коде.

### 7. KILLSWITCH_DESIGN_v0.1.md
- **Размер**: 586 строк
- **Последнее обновление**: 2026-04-18 (в тексте); mtime 2026-05-02
- **Суть**: Дизайн модуля защиты от критических потерь (margin DD, каскады liq, flash moves).
- **Ключевые решения**: 4 типа триггера; алерт + лог + блокировка авто-возобновления.
- **Дубликаты/пересечения**: концепция размазана по `services/protection_alerts/` + `auto_edge_alerts.py` + supervisor.
- **Статус**: SUPERSEDED (отдельного killswitch модуля нет — функция в protection_alerts)
- **Рекомендация**: ARCHIVE
- **Аргумент**: Реализация под другим именем.

### 8. ORCHESTRATOR_LOOP_DESIGN_v0.1.md
- **Размер**: 564 строк
- **Последнее обновление**: 2026-04-18 (в тексте); mtime 2026-05-02
- **Суть**: Дизайн авто-цикла оркестратора (regime → action_matrix → killswitch → telegram → log → daily report). MVP P1.
- **Дубликаты/пересечения**: реализовано как `core/orchestrator/orchestrator_loop.py` + `app_runner.py`.
- **Статус**: SUPERSEDED
- **Рекомендация**: ARCHIVE
- **Аргумент**: Код в проде.

### 9. ORCHESTRATOR_TELEGRAM_DESIGN_v0.1.md
- **Размер**: 580 строк
- **Последнее обновление**: 2026-04-18 (в тексте); mtime 2026-05-02
- **Суть**: Дизайн интеграции Orchestrator Loop с Telegram через pyTelegramBotAPI (синхронный, не aiogram).
- **Дубликаты/пересечения**: реализовано в `services/telegram_runtime.py` + 11 asyncio tasks.
- **Статус**: SUPERSEDED
- **Рекомендация**: ARCHIVE
- **Аргумент**: Реализация в проде.

### 10. REAL_SUMMARY_2026-04-28.md
- **Размер**: 30 строк
- **Последнее обновление**: 2026-04-28
- **Суть**: Отчёт TZ-041 — попытка пересчитать CI 95% для P-6 vs P-7 на real tracker snapshots. Результат: 0 эпизодов в окне 2026-04-24..23:00 UTC, real CI не пересчитан.
- **Ключевые выводы**: окно tracker × features = пустое для rally/dump; нужен extend coverage features_out на 25.04..28.04.
- **Дубликаты/пересечения**: упомянут в OPPORTUNITY_MAP_v1 §6 п.4 и SESSION_LOG 28.04 (TZ-041).
- **Статус**: REFERENCE (исторический отчёт)
- **Рекомендация**: KEEP (или ARCHIVE в reports/)
- **Аргумент**: Маленький, технический. Содержит причину блока TZ-040/TZ-041.

### 11. ENGINE_BUG_HYPOTHESES_2026-04-30.md
- **Размер**: 458 строк
- **Последнее обновление**: 2026-04-30 (в тексте)
- **Суть**: 9 гипотез по 3 аномалиям SHORT/LONG K-факторов в калибровке engine_v2 vs GinArea ground truth. Anomaly A: SHORT K_realized нестабилен при td<max_stop. Anomaly B: LONG K~-1 (зеркало). Anomaly C: K_volume SHORT vs LONG 4× разрыв.
- **Ключевые решения**: A1 — combo_stop init выше entry для SHORT с td<max_stop (combo_stop_init = entry × (1+max_stop−td)); фикс через entry_floor применён в `engine_v2/group.py:58` 30.04.
- **Дубликаты/пересечения**: STATE_CURRENT §5 «Combo-stop geometry fix (B1+A1, 2026-04-30)»; SESSION_LOG D-100 (Engine fix Phase 1 partial).
- **Статус**: REFERENCE (часть закрыта; часть — открытые гипотезы B2 LONG indicator direction)
- **Рекомендация**: KEEP
- **Аргумент**: B2 LONG sign error всё ещё открытый вопрос (TZ-ENGINE-FIX-INSTOP-SEMANTICS-B). Уникальные данные для отладки.

### 12. README.md
- **Размер**: 9 строк
- **Последнее обновление**: 2026-05-02 (mtime)
- **Суть**: Минимальный README — описывает структуру docs/history/.
- **Дубликаты/пересечения**: финальная версия про MASTER+PLAYBOOK+SESSION_LOG из CLEANUP_GUIDE не применена.
- **Статус**: UNCLEAR (текущий README ссылается на history/release_notes/, может не существовать в актуальном виде)
- **Рекомендация**: NEEDS_OPERATOR_DECISION
- **Аргумент**: Переписать на канонический или оставить.

### 13. PROJECT_KNOWLEDGE_SYNC_2026-05-05.md
- **Размер**: 57 строк
- **Последнее обновление**: 2026-05-06 (mtime)
- **Суть**: Инструкция оператору по синхронизации Project Knowledge (Claude.ai Projects): UPDATE/CREATE/DELETE/KEEP списки документов после сессии 05.05. REGULATION_v0_1 → удалить, REGULATION_v0_1_1 → активная; перечисляет новые DESIGN/RESEARCH файлы.
- **Ключевые решения**: STATE_CURRENT_2026-05-05_EOS канонический в STATE/, не CONTEXT/; PROJECT_MAP.md в STATE/.
- **Дубликаты/пересечения**: с CONTEXT/MAIN_PROJECT_SETUP_GUIDE_2026-05-04.md (Step 1.2 список upload).
- **Статус**: REFERENCE (одноразовый sync-отчёт)
- **Рекомендация**: ARCHIVE (после применения)
- **Аргумент**: Checklist на дату; полезность кончилась.

### 14. CLEANUP_GUIDE.md
- **Размер**: 171 строка
- **Последнее обновление**: 2026-04-29 (mtime)
- **Суть**: PowerShell-инструкция (от 26.04) по архивации 21 старого файла после консолидации в MASTER+PLAYBOOK+SESSION_LOG. Включает явные списки.
- **Ключевые решения**: после cleanup в docs/ должно остаться 4–5 файлов (MASTER, PLAYBOOK, SESSION_LOG, GINAREA_MECHANICS, README); `archive/2026-04-26_pre_consolidation/` + `archive/tz_2026-04-26/`. Помечает design v0.1 файлы как АРХИВ.
- **Дубликаты/пересечения**: устарело — после 26.04 в docs/ накопилось ещё 30+ новых файлов.
- **Статус**: SUPERSEDED
- **Рекомендация**: ARCHIVE
- **Аргумент**: Документ из эпохи «3 файла»; рекомендации больше не отражают реальность.

### 15. PLAYBOOK.md
- **Размер**: 661 строка
- **Последнее обновление**: 2026-04-27 v1.1 (в тексте); mtime 2026-05-03
- **Суть**: Machine-readable каталог 12 приёмов P-1..P-12 в YAML-блоках с trigger/action/cancel/expected_outcome/notes/ict_context/episodes. §0.1 Real Validation Status.
- **Ключевые решения**: P-1 controlled_raise_boundary, P-2 stack_bot_on_pullback (главный), P-4..P-12 confirmed; HARD BAN P-5/P-8/P-10; P-13/P-14 rejected.
- **Дубликаты/пересечения**: краткий список в MASTER §10; правила использования в OPPORTUNITY_MAP_v1/v2.
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Источник для `/advise` и What-If; код подхватывает изменения.

### 16. PLAYBOOK_MANUAL_LAUNCH_v1.md
- **Размер**: 264 строки
- **Последнее обновление**: 2026-05-05 (в тексте); mtime 2026-05-05
- **Суть**: Operational pre-launch checklist для первой активации бота согласно REGULATION_v0_1_1.md. §1 Pre-launch gates G1–G5, §2 First bot recommendation = CFG-L-RANGE @ target=0.50, §3 pre-flight checks, exact prod params (220 orders, $100, instop=0.018).
- **Ключевые решения**: первый бот = CFG-L-RANGE LONG INDICATOR Pack E с production cap 220 orders ($22,000 max gross); Pack E backtest 5000 не transferable; не запускать пока G1–G5 не GREEN.
- **Дубликаты/пересечения**: REGULATION_v0_1_1.md §2/§3/§5/§7; STATE_CURRENT_2026-05-05_EOS.md (regulation activation blocked).
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Active checklist для предстоящего запуска.

### 17. REGULATION_v0_1.md
- **Размер**: 396 строк
- **Последнее обновление**: 2026-05-05 (в тексте)
- **Суть**: Первая версия regulation foundation: data coverage limitations (17 runs, packs A/C/D/E/BT), regime distribution RANGE 72%/MARKUP 13%/MARKDOWN 15%, что allowed/not-allowed claims.
- **Дубликаты/пересечения**: явно superseded by REGULATION_v0_1_1.md. PROJECT_KNOWLEDGE_SYNC: DELETE.
- **Статус**: SUPERSEDED
- **Рекомендация**: ARCHIVE
- **Аргумент**: REGULATION_v0_1_1.md перезаписала с FIX 1–4.

### 18. REGULATION_v0_1_1.md
- **Размер**: 358 строк
- **Последнее обновление**: 2026-05-05
- **Суть**: Active regulation v0.1.1 — fresh rewrite с 4 фиксами. 21 GinArea run; LONG taxonomy split (range vs far); SHORT default activation logic; F-G instop asymmetry; FIX 3 order_count=5000 для Pack E; FIX 4 instop direction asymmetry.
- **Ключевые решения**: 5 admissible config roles + 2 suspended; HYS H=1; TRANSITION 7.35%; не утверждать within-pack regime sensitivity (M1-infeasible).
- **Дубликаты/пересечения**: PLAYBOOK_MANUAL_LAUNCH_v1.md ссылается; STATE_CURRENT_EOS подтверждает active.
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Активный operational regulation.

### 19. INCIDENTS.md
- **Размер**: 139 строк
- **Последнее обновление**: 2026-05-05 (mtime)
- **Суть**: Накопительный журнал инцидентов с root cause + prevention rules. INC-008 no main branch; INC-009 encoding mojibake done.py; INC-010 acceptance leniency; INC-011 architect issued git/script commands; INC-012 architectural amnesia parallel implementation; INC-013 architect inventory pattern recurrence; INC-014 architectural amnesia (CANON/* duplicates MASTER).
- **Ключевые решения**: skill `architect_inventory_first` (INC-013); skill `operator_role_boundary` (INC-011); binary acceptance rule (INC-010); pre-commit hook for HANDOFF*.md (INC-008).
- **Дубликаты/пересечения**: с MASTER §0 К-косяки (К24–К26); SESSION_LOG (TZ-055, TZ-066).
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Уникальный журнал инцидентов с prevention rules.

### 20. OPERATOR_DEDUP_MONITORING.md
- **Размер**: 88 строк
- **Последнее обновление**: 2026-05-04 (mtime)
- **Суть**: Operator runbook для 24h-мониторинга dedup wrappers (POSITION_CHANGE, BOUNDARY_BREACH) в DecisionLogAlertWorker. Feature flags, frozen configs, counters, 24h checklist, rollback procedure.
- **Ключевые решения**: POSITION_CHANGE cooldown 300s/delta 0.05 BTC; BOUNDARY_BREACH cooldown 600s/per-bot isolation; PNL_EVENT и PNL_EXTREME — not wired yet.
- **Дубликаты/пересечения**: STATE_CURRENT §5 OPERATOR PENDING ACTIONS ссылается; CP-G/G2 в STATE_CURRENT §2.
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Активный 24h checklist пока monitoring не закрыт.

### 21. OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV.md
- **Размер**: 151 строка
- **Последнее обновление**: 2026-05-04 (mtime)
- **Суть**: Operator runbook для night download 1s BTCUSDT OHLCV: backup → fresh download 2025-05-01..2026-04-30 → verify → run reconcile_v3.
- **Ключевые решения**: 4 workers, ~3–6h, ~1.6 GB; команда `python scripts/ohlcv_ingest.py --symbol BTCUSDT --interval 1s ...`.
- **Дубликаты/пересечения**: STATE_CURRENT §3: «1s OHLCV coverage 31.5M bars (2025-05-01 → 2026-04-30) ✅ 100% GA window» → DONE.
- **Статус**: SUPERSEDED (download выполнен 04.05)
- **Рекомендация**: ARCHIVE
- **Аргумент**: Задача fulfilled; XRP версия — отдельный backlog item.

### 22. OPPORTUNITY_MAP_v1.md
- **Размер**: 185 строк
- **Последнее обновление**: 2026-04-28 v1.0
- **Суть**: Empirical playbook v1: 3 топ-приёма (P-6/P-2/P-7), HARD BAN (P-5/P-8/P-10), 6 правил A–F, карта решений, sizing 0.05/0.10/0.18 BTC, псевдокод /advise v2 cascade, 13 пунктов «что не покрывает».
- **Ключевые решения**: правило A каскад вверх → P-6 (+$134, win 69%, n=39); правило B рост 2–3% → P-2 main (+$38); правило C дамп → P-7 (+$26); HARD BAN; liquidation risk override как первое правило.
- **Дубликаты/пересечения**: superseded by v2 (которая ссылается на v1 как источник).
- **Статус**: SUPERSEDED
- **Рекомендация**: KEEP (как baseline; v2 опирается на цифры v1)
- **Аргумент**: v2 не дублирует данные v1, а добавляет cost layer. Базовые 196-эпизодные цифры — только в v1.

### 23. OPPORTUNITY_MAP_v2.md
- **Размер**: 176 строк
- **Последнее обновление**: 2026-05-01 v2.0
- **Суть**: Карта v2 после интеграции cost model (TZ-COST-MODEL-INTEGRATION). §1–§7 + §16 cost caveats. Maker rebate (-0.025%) усилил P-2/P-6; HARD BAN усилен taker fees+slippage.
- **Ключевые решения**: gross_pnl + net_pnl колонки; combo-level net sizing → n/a (нужен полный rerun v2); 3 новых caveat (14–16) про cost model assumptions.
- **Дубликаты/пересечения**: расширяет v1; псевдокод алгоритма §5 практически идентичен.
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Newer version с cost model.

### 24. GINAREA_MECHANICS.md
- **Размер**: 382 строки
- **Последнее обновление**: 24.04.2026 v1.3 (в тексте)
- **Суть**: Детальный reference на API/механику GinArea: режимы значений, типы контрактов (linear SHORT vs inverse LONG), параметры сетки, жизненный цикл IN-ордера, Out Stop, Instop Семантики A vs B, Indicator gate с «Разовой проверкой», Boundaries, PnL/liq формулы.
- **Ключевые решения**: SHORT linear BTCUSDT, LONG inverse XBTUSD; «Разовая проверка» сбрасывается только при full-close; Семантика A — задержка открытия IN; Семантика B — закрыта 2026-05-02 (CLOSE-GAP-05); liq_price из API + калибровка.
- **Дубликаты/пересечения**: PROJECT_CONTEXT §2 содержит сжатую версию.
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Единственный детальный технический reference платформы.

### 25. CONTEXT/PROJECT_CONTEXT.md
- **Размер**: 329 строк
- **Последнее обновление**: 2026-05-02 v1.0
- **Суть**: Static reference для нового Claude в начале сессии. §1 суть проекта, §2 механика GinArea (сжатая), §3 стратегия оператора, §4 иерархия инструментов + phase roadmap, §5 engine v2 calibration, §6 H10 detector, §7 11 asyncio tasks, §8 данные, §9 project rules, §10 communication rules, §11 ключевые файлы.
- **Ключевые решения**: Three-file rule (MASTER+PLAYBOOK+SESSION_LOG = SoT); Trader-first filter; Inventory first; Long ops rule; K_SHORT 9.637 stable / K_LONG 4.275 TD-dependent.
- **Дубликаты/пересечения**: §2 = сжатая GINAREA_MECHANICS; §3 = MASTER §16; §6 = STATE_CURRENT §6; §11 = CANON/INDEX (но иначе).
- **Статус**: REFERENCE (агрегированный обзор для входа в сессию)
- **Рекомендация**: KEEP
- **Аргумент**: «Одна страница входа», нечто среднее между MASTER и STATE_CURRENT.

### 26. CONTEXT/STATE_CURRENT.md
- **Размер**: 225 строк
- **Последнее обновление**: 2026-05-05 EOD; mtime 2026-05-04
- **Суть**: Living state document. §1 phase status (Phase 0 in_progress, 0.5 UNBLOCKED, 1 Day 5/14, 2 partial, 3 partial, 4 planned). §2 last results (week 2 — 16 CPs). §3 calibration numbers. §4 open TZs & blockers. §5 operator pending actions. §6 changelog.
- **Ключевые решения**: K_SHORT 8.87 median (DIRECT-1S, CV 31.8%); K_LONG 4.13 (CV 43.1%, DP-001 confirmed); coordinated grid $37,769/year (1y, multi-year needed); regulation activation blocked by SHORT cleanup; Week 3 top-3 = TRANSITION-MODE-COMPARE / PURE-INDICATOR-AB / K-RECALIBRATE-PRODUCTION.
- **Дубликаты/пересечения**: STATE_CURRENT_2026-05-05_EOS.md (узкий snapshot); MULTI_TRACK_ROADMAP §2026-05-06 update.
- **Статус**: AUTHORITATIVE (living)
- **Рекомендация**: KEEP
- **Аргумент**: Главный «текущий статус» документ; обновляется EOD.

### 27. CONTEXT/STATE_CURRENT_2026-05-05_EOS.md
- **Размер**: 41 строка
- **Последнее обновление**: 2026-05-05 EOS
- **Суть**: Узкий session-close snapshot 05.05: Foundation scope complete; 21 closed runs; F-G locked; H=1 calibration; TRANSITION 7.35%; REGULATION_v0_1_1 active; SHORT -1.416 BTC; margin 95%; regulation activation blocked by cleanup.
- **Ключевые решения**: foundation phase complete; execution = manual launch path 1; regulation activation blocked.
- **Дубликаты/пересечения**: PROJECT_KNOWLEDGE_SYNC: «keep в STATE/, не CONTEXT/». На диске обе копии.
- **Статус**: UNCLEAR
- **Рекомендация**: NEEDS_OPERATOR_DECISION (либо переместить в STATE/, либо удалить если есть копия в STATE/)
- **Аргумент**: На диске уже есть `docs/STATE/STATE_CURRENT_2026-05-05_EOS.md` — копия в CONTEXT/ дубль.

**Diff STATE_CURRENT.md vs STATE_CURRENT_2026-05-05_EOS.md**:
- STATE_CURRENT.md: полный (225 строк), 6 секций, Day 5/14 paper journal, week 3 queue с 10 TZ, актуальные K-числа.
- EOS: 41 строка, foundation-only, fix-list F-G/H=1/TRANSITION 7.35%, регуляторная активация блокирована, manual launch path 1.
- EOS — подмножество STATE_CURRENT.md, но с эксклюзивной формулировкой «21 closed runs / 5 admissible config roles / 2 suspended» и «live aggregate position SHORT -1.416 BTC, margin ~95%». Обе копии нужны — STATE_CURRENT.md канонический операционный, EOS — point-in-time fix scope.

### 28. CONTEXT/MAIN_PROJECT_SETUP_GUIDE_2026-05-04.md
- **Размер**: 216 строк
- **Последнее обновление**: 2026-05-04
- **Суть**: Operator instructions для setup Claude.ai Project «bot7 Coordinator» (MAIN). Part 1 one-time setup; Part 2 morning routine; Part 3 checkpoint; Part 4 evening; Part 5 weekly refresh; Part 6 troubleshooting; daily time budget ~10–15 min/day.
- **Ключевые решения**: разделение MAIN coordinator (claude.ai web Project) vs Code Worker (Claude Code в c:\bot7); MORNING/CP/EOD/WEEKLY protocols; 8 файлов в Project Knowledge.
- **Дубликаты/пересечения**: MAIN_CHAT_OPENING_PROMPT_2026-05-04.md = Custom Instructions.
- **Статус**: AUTHORITATIVE (operator workflow)
- **Рекомендация**: KEEP
- **Аргумент**: Active operational guide.

### 29. CONTEXT/MAIN_CHAT_OPENING_PROMPT_2026-05-04.md
- **Размер**: 330 строк
- **Последнее обновление**: 2026-05-03
- **Суть**: Custom Instructions для Claude.ai Project «bot7 Coordinator» — определение роли MAIN coordinator (strategic brain, not executor). Project snapshot, calibration facts, anti-drift rules, daily protocol, decision rules (Brier gates, scope additions, time drift), file list.
- **Ключевые решения**: MAIN не работает с диском, не пишет код; week schedule Mon–Sun (regime models target Brier ≤0.22); Failure rule: regime failing 0.28 → ship qualitative only.
- **Дубликаты/пересечения**: предполагает наличие WEEK_2026-05-04..., DEPRECATED_PATHS, DRIFT_HISTORY, SPRINT_TEMPLATE, MAIN_COORDINATOR_USAGE_GUIDE.
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Custom Instructions для отдельного Claude Project; нельзя удалить пока MAIN coordinator используется.

### 30. STATE/ROADMAP.md
- **Размер**: 98 строк
- **Последнее обновление**: 2026-05-02 (mtime)
- **Суть**: Phase roadmap (Phase 0..4) с статусами и exit criteria. Phase 0 Infrastructure, 0.5 Engine validation, 1 Paper Journal Launch, 2 Operator Augmentation, 3 Tactical Bot Management, 4 Full Auto. Параллельные потоки (H10, validation, optimize). Принципы: никаких параллельных вселенных, идеи вне фазы → QUEUE как IDEA.
- **Ключевые решения**: TZ-PROJECT-MEMORY-DEFENSE v2 / TZ-CONFLICTS-TRIAGE / TZ-CALENDAR-REACTIVATION DONE; reconcile retry until GREEN/YELLOW.
- **Дубликаты/пересечения**: PLANS/MULTI_TRACK_ROADMAP.md (новее, multi-track P1-P8 структура от 2026-05-04, с Track A/B/C/D update 2026-05-06). Кардинально разная структура: ROADMAP.md = phase-linear; MULTI_TRACK = parallel tracks per pain.
- **Статус**: SUPERSEDED (MULTI_TRACK_ROADMAP — каноничный для week 2+)
- **Рекомендация**: ARCHIVE или MERGE_WITH_MULTI_TRACK
- **Аргумент**: PROJECT_KNOWLEDGE_SYNC: «MULTI_TRACK_ROADMAP.md — current status reframed to Track-A/B/C/D». ROADMAP.md = phase view, может быть полезен как «phase exit criteria reference».

### 31. STATE/QUEUE.md
- **Размер**: 135 строк
- **Последнее обновление**: 2026-05-02 (в тексте); mtime 2026-05-03
- **Суть**: Queue navigator от 02.05 — потоки A/B/C, TZ задачи с Trader-first меткой, статусы DONE/OPEN/BLOCKED. Перечисляет TZ-060..067, TZ-ENGINE-FIX-* по результатам RECONCILE-01-RETRY, debt DEBT-02..05.
- **Ключевые решения**: TZ-RECONCILE-01-RETRY DONE с RED (stale-init artifact); TZ-ENGINE-FIX-RESOLUTION OPEN (1s OHLCV блокер на 02.05 — потом DONE 04.05); TZ-051/067 — окно оператора.
- **Дубликаты/пересечения**: PENDING_TZ.md = более новая, фокус на ready-to-dispatch / current priority / done. STATE_CURRENT §4 = top-10 priority queue от 05.05.
- **Статус**: SUPERSEDED (snapshot от 02.05)
- **Рекомендация**: ARCHIVE
- **Аргумент**: PENDING_TZ.md более новая.

### 32. STATE/PENDING_TZ.md
- **Размер**: 60 строк
- **Последнее обновление**: 2026-05-06 — session close sync
- **Суть**: Канонический список TZ. Ready To Dispatch (TZ-DECISION-LAYER-CORE-WIRE и его dependents); Current Priority (BT-014-NOSTOP-COMPARISON, MANUAL-LAUNCH-CHECKLIST, POSITION-CLEANUP-SUPPORT, MARGIN-COEFFICIENT-INPUT-WIRE, DECISION-LAYER-DESIGN-v1.1); Foundation Extensions (BEAR-MARKET, CROSS-ASSET); Done/Closed by 2026-05-05+.
- **Ключевые решения**: DECISION_LAYER_v1 next; foundation closed for BTC bullish-year; manual launch path 1 active; regulation blocked on SHORT cleanup.
- **Дубликаты/пересечения**: STATE_CURRENT §4 (но было 05.05, PENDING_TZ — 06.05); QUEUE.md (старее).
- **Статус**: AUTHORITATIVE
- **Рекомендация**: KEEP
- **Аргумент**: Самый свежий queue.

### 33. STATE/PROJECT_MAP.md
- **Размер**: 508 строк
- **Последнее обновление**: 2026-05-07 (auto-generated)
- **Суть**: Auto-generated карта активных модулей в src/services/scripts/handlers/telegram_ui/collectors с line counts и docstrings.
- **Ключевые решения**: машинно-генерируемая инвентаризация для inventory-first protocol (skill `architect_inventory_first`).
- **Дубликаты/пересечения**: PROJECT_KNOWLEDGE_SYNC: «PROJECT_MAP.md — add stub в docs/ корне» + «docs/STATE/PROJECT_MAP.md — keep unchanged» → обе копии существуют.
- **Статус**: AUTHORITATIVE (auto-generated by scripts/state_snapshot.py)
- **Рекомендация**: KEEP
- **Аргумент**: Регенерируется скриптом; критично для project_inventory_first skill.

### 34. CANON/INDEX.md
- **Размер**: 35 строк
- **Последнее обновление**: 2026-04-30 (mtime)
- **Суть**: Index файлов CANON/: STRATEGY_CANON, HYPOTHESES_BACKLOG, OPERATOR_QUESTIONS, CUSTOM_BOTS_REGISTRY, RUNNING_SERVICES_INVENTORY. Декларирует «source of truth, читается ПЕРВЫМ». Ссылается на MASTER/PLAYBOOK/OPPORTUNITY_MAP_v1/SESSION_LOG как не-дубли.
- **Дубликаты/пересечения**: SESSION_LOG D-104 (CANON/* cleanup proposal awaiting operator decision); INC-014 — architectural amnesia ровно потому что CANON/* дублирует MASTER. Конфликтует с принципом Three-file rule из PROJECT_CONTEXT §9.
- **Статус**: UNCLEAR (operator решил KEEP, но cleanup awaiting; противоречит INC-014)
- **Рекомендация**: NEEDS_OPERATOR_DECISION
- **Аргумент**: SESSION_LOG D-104: «CANON/* — cleanup proposal задокументирован, ждёт operator decision».

### 35. CANON/STRATEGY_CANON_2026-04-30.md
- **Размер**: 405 строк
- **Последнее обновление**: 2026-04-30
- **Суть**: §1 архитектура двух движков (LONG USDT-M linear vs SHORT COIN-M inverse), volume metric first-class objective, метрики; §2 sizing rules; полная стратегия + интервенции + боли оператора. Источник для MASTER §16.
- **Ключевые решения**: реальный результат конкурса оператора $618k volume → 1-е место; 30-day target $10.5M volume; SHORT-grid currency cushion; net BTC exposure / currency hedge ratio как метрики.
- **Дубликаты/пересечения**: MASTER §16 (operator profile) явно ссылается на этот файл как источник; PROJECT_CONTEXT §3.
- **Статус**: REFERENCE (содержание частично инкорпорировано в MASTER §16)
- **Рекомендация**: NEEDS_OPERATOR_DECISION (KEEP как источник или ARCHIVE если §16 покрывает)
- **Аргумент**: Часть materialа уникальна (currency hedge ratio, $10.5M target). Возможно merge в MASTER.

### 36. CANON/RUNNING_SERVICES_INVENTORY_2026-04-30.md
- **Размер**: 278 строк
- **Последнее обновление**: 2026-04-30
- **Суть**: Inventory всех 11 asyncio tasks в app_runner с modules, telegram outputs, formats, gates, last commit, status. Generated by TZ-RUNNING-SERVICES-INVENTORY.
- **Ключевые решения**: orchestrator_loop ACTIVE; protection_alerts ACTIVE; и т.д.
- **Дубликаты/пересечения**: PROJECT_CONTEXT §7 = очень сжатая таблица; STATE/PROJECT_MAP.md = автогенерированный inventory с другой стороны.
- **Статус**: REFERENCE (snapshot 30.04, частично устарел)
- **Рекомендация**: NEEDS_OPERATOR_DECISION (KEEP / regenerate / merge в PROJECT_MAP)
- **Аргумент**: Содержит уникальные детали — формат Telegram сообщений, gate flags. Не дублируется PROJECT_MAP. Но нужна свежая регенерация.

### 37. CANON/HYPOTHESES_BACKLOG.md
- **Размер**: 127 строк
- **Последнее обновление**: 2026-04-30
- **Суть**: Backlog гипотез P-NN с status enum (DRAFT/BACKTEST_PENDING/.../CONFIRMED/REJECTED/HARD_BAN). P-15 rolling-trend-rebalance v2 (8 шагов цикл, 3 варианта обработки SHORT на trending up).
- **Ключевые решения**: P-15 — формализация устной идеи оператора 30.04; цикл impulse-retracement-close-reentry; safety net через P-4 PAUSED.
- **Дубликаты/пересечения**: PLAYBOOK.md = P-1..P-12 confirmed; этот файл = P-15+ draft. Не дублирует.
- **Статус**: REFERENCE (active backlog)
- **Рекомендация**: KEEP
- **Аргумент**: PLAYBOOK = confirmed only; backlog нужен где-то.

### 38. CANON/OPERATOR_QUESTIONS.md
- **Размер**: 100 строк
- **Последнее обновление**: 2026-04-30
- **Суть**: Q-1..Q-6 открытые вопросы оператора для backtest framework: контртрендовая позиция при затяжном тренде; порог критичности для частичного сброса; стоп vs ожидание; booster bot triggers; asymmetric param adjustment на trend; detection ложного выноса. Все PENDING.
- **Дубликаты/пересечения**: MASTER §16.6 (Gap 1–4 — частично пересекается, но Q-1..Q-6 другая нумерация и другие формулировки).
- **Статус**: REFERENCE (active backlog)
- **Рекомендация**: KEEP
- **Аргумент**: Уникальные формулировки оператора; backtest framework нацелен на эти Q.

### 39. CANON/CUSTOM_BOTS_REGISTRY.md
- **Размер**: 57 строк
- **Последнее обновление**: 2026-04-30
- **Суть**: Реестр live ботов: TEST_1/2/3 (SHORT linear), BTC-LONG-C/D (LONG inverse), Bot 6399265299 — Post-impulse SHORT booster (manual activation, P-16).
- **Ключевые решения**: booster bot — пример P-16 кандидата (см. MASTER §16.3); связан с Q-4.
- **Дубликаты/пересечения**: STATE/BOT_INVENTORY.md (упомянут в MULTI_TRACK_ROADMAP P2 = ✅ CLOSED 2026-05-05, 22 bots) — более новая версия.
- **Статус**: SUPERSEDED (BOT_INVENTORY.md в STATE/ — 22 bots, более полная)
- **Рекомендация**: ARCHIVE или MERGE
- **Аргумент**: TZ-BOT-STATE-INVENTORY (P2) закрылся с docs/STATE/BOT_INVENTORY.md = 22 bots; CUSTOM_BOTS_REGISTRY = 6 ботов от 30.04, fragment.

---

## СВОДКА

### Явные дубликаты

1. **REGULATION_v0_1.md ⊂ REGULATION_v0_1_1.md** — v0.1 явно superseded. **ARCHIVE v0.1**.
2. **NEXT_CHAT_PROMPT.md ⊂ MASTER §14 + MAIN_CHAT_OPENING_PROMPT_2026-05-04.md** — устарел. **ARCHIVE**.
3. **CANON/CUSTOM_BOTS_REGISTRY.md ⊂ STATE/BOT_INVENTORY.md** (22 ботов, 05.05). **MERGE или ARCHIVE**.
4. **STATE/QUEUE.md ⊂ STATE/PENDING_TZ.md**. **ARCHIVE QUEUE**.
5. **STATE/ROADMAP.md vs PLANS/MULTI_TRACK_ROADMAP.md** — разные парадигмы. PROJECT_KNOWLEDGE_SYNC: MULTI_TRACK current. **ARCHIVE ROADMAP** или оставить как «phase exit criteria».
6. **CONTEXT/STATE_CURRENT_2026-05-05_EOS.md vs STATE/STATE_CURRENT_2026-05-05_EOS.md** — обе копии существуют. **DELETE копию в CONTEXT/**.
7. **CLEANUP_GUIDE.md** — устаревшая инструкция эпохи «3 файла». **ARCHIVE**.

### SUPERSEDED файлы (закрыты другими)

| Файл | Закрыт чем |
|---|---|
| BASELINE_INVESTIGATION_DESIGN_v0.1 | TZ-044 (core/pipeline.py + tests/whatif/) |
| CALIBRATION_LOG_DESIGN_v0.1 | services/decision_log/, services/advise_v2/paper_journal.py |
| KILLSWITCH_DESIGN_v0.1 | services/protection_alerts/ + supervisor + auto_edge_alerts |
| ORCHESTRATOR_LOOP_DESIGN_v0.1 | core/orchestrator/orchestrator_loop.py |
| ORCHESTRATOR_TELEGRAM_DESIGN_v0.1 | services/telegram_runtime.py + DecisionLogAlertWorker |
| OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV | scripts/ohlcv_ingest.py + 31.5M bars в backtests/frozen/ |
| REGULATION_v0_1 | REGULATION_v0_1_1 |
| NEXT_CHAT_PROMPT | MAIN_CHAT_OPENING_PROMPT_2026-05-04 + MASTER §14 |
| CLEANUP_GUIDE | (устарел сам) |
| STATE/QUEUE | PENDING_TZ |
| OPPORTUNITY_MAP_v1 | v2 (но KEEP как baseline) |

### UNCLEAR — требуют решения оператора

1. **README.md** — пустая заглушка. Переписать на финальную из CLEANUP_GUIDE или удалить?
2. **CONTEXT/STATE_CURRENT_2026-05-05_EOS.md** — есть копия в STATE/. Удалить эту?
3. **CANON/INDEX.md + весь CANON/*** — INC-014: architectural amnesia parallel implementation. SESSION_LOG D-104: «CANON/* cleanup proposal awaiting operator decision». Что делать: KEEP, MERGE_WITH_MASTER (часть в §16, RUNNING_SERVICES в STATE/PROJECT_MAP, BOTS_REGISTRY в STATE/BOT_INVENTORY), или ARCHIVE целиком?
4. **CANON/STRATEGY_CANON_2026-04-30.md** — частично интегрирован в MASTER §16, но содержит уникальные метрики (currency hedge ratio, $10.5M volume target). Полное merge или KEEP?
5. **CANON/RUNNING_SERVICES_INVENTORY_2026-04-30.md** — снимок 30.04 устарел; регенерировать или мерджить с PROJECT_MAP?
6. **PROJECT_MANIFEST.md** — мёртвая оболочка, кроме одного правила про GRID/TRADER VIEW. Перенести правило в MASTER?

### Итог

Из 39 файлов:
- **KEEP твёрдо — 16**: MASTER, SESSION_LOG, PLAYBOOK, PLAYBOOK_MANUAL_LAUNCH_v1, REGULATION_v0_1_1, INCIDENTS, OPERATOR_DEDUP_MONITORING, OPPORTUNITY_MAP_v2, GINAREA_MECHANICS, PROJECT_CONTEXT, STATE_CURRENT, MAIN_PROJECT_SETUP_GUIDE, MAIN_CHAT_OPENING_PROMPT, PENDING_TZ, PROJECT_MAP, MULTI_TRACK_ROADMAP
- **KEEP с оговоркой — 5**: REAL_SUMMARY, ENGINE_BUG_HYPOTHESES, OPPORTUNITY_MAP_v1 (baseline), HYPOTHESES_BACKLOG, OPERATOR_QUESTIONS
- **ARCHIVE кандидаты — 12**: REGULATION_v0_1, NEXT_CHAT_PROMPT, CLEANUP_GUIDE, CUSTOM_BOTS_REGISTRY, QUEUE, ROADMAP (или merge), 5× DESIGN v0.1, OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV, PROJECT_MANIFEST, PROJECT_KNOWLEDGE_SYNC_2026-05-05
- **UNCLEAR — 6**: README, EOS-копия в CONTEXT, CANON/INDEX, STRATEGY_CANON, RUNNING_SERVICES_INVENTORY, PROJECT_MANIFEST (правило про GRID/TRADER VIEW)
