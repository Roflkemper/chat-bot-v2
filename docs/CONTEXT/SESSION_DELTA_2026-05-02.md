# SESSION DELTA — 2026-05-02
# Что изменилось за эту сессию. Transient документ.

---

## TZs закрыты

| TZ | Findings | Файлы |
|---|---|---|
| TZ-PROJECT-STATE-AUDIT | 3 operator actions разблокируют 4 TZ | reports/project_state_audit_2026-05-02.md |
| TZ-CLAUDE-TZ-VALIDATOR | Phase-aware validator для TZ proposals | tools/validate_tz.py, tests/tools/test_validate_tz.py |
| TZ-VERIFY-INDICATOR-GATE-MECHANICS | engine_v2 indicator gate CORRECT — no fix needed | reports/indicator_gate_mechanics_verification_2026-05-02.md |
| TZ-DIAGNOSE-TRACKER-FALSE-NEGATIVE | Root cause: stale PID + duplicate instances. Fixed. | src/supervisor/daemon.py, process_config.py, tests/supervisor/ |
| TZ-FIX-COMBO-STOP-GEOMETRY | K=-0.99 fix already applied (entry_floor guard). TD-dependent K structural. | reports/combo_stop_geometry_fix_2026-05-02.md, tests/engine_v2/test_long_combo_stop_geometry.py |
| TZ-DEDUP-SNAPSHOTS-CSV | 45k dupes removed, decisions 71→86 on clean data | ginarea_live/snapshots.csv, ginarea_tracker/storage.py, scripts/dedup_snapshots.py |
| TZ-CONTEXT-HANDOFF-SKILL | docs/CONTEXT/ 3-layer + tools/handoff.py CLI + Telegram /handoff + 6 тестов | docs/CONTEXT/, tools/handoff.py, .claude/skills/context_handoff.md |
| TZ-COORDINATED-GRID-TRIM-DETAILS | 1039 реальных trim событий (не 17); механика, распределение, playbook | reports/coordinated_grid_trim_practical_2026-05-02.md, services/coordinated_grid/trim_analyzer.py |
| TZ-HANDOFF-FIX-INCLUDE-FULL-SKILLS-AND-GAPS | handoff.py: PART 5 все 16 скилов + PART 6 gaps; 7-строчный onboarding | tools/handoff.py, .claude/skills/context_handoff.md |

## Key findings

1. **K_LONG TD-зависимость — структурная, не баг.** GridBotSim без instop → K монотонно убывает с ростом TD. Не фиксируется изменением group.py.

2. **Tracker false-negative mechanism:** Windows venv shim (PID) умирает → supervisor видит DEAD → на самом деле реальный Python жив. Fix: `_find_pid_by_cmdline()` fallback + PID file repair.

3. **Decisions extractor 71→86 (+15)** — не ошибка. Clean data раскрыла реальные transitions скрытые дублями.

4. **1623 garbage rows** в snapshots были CSV parse errors (emoji в bot_name → смещение колонок). Устранены фильтром _validate_row() который уже существовал в storage.py.

5. **engine_v2 indicator gate ПРАВИЛЬНЫЙ.** Операторское подтверждение: indicator fire once per grid start, не per-bar. Код уже реализует это корректно.

6. **Trim ≠ market close.** `asymmetric_trim` отменяет pending grid ордера — не исполняет рыночные. Реализованного убытка нет. 1039 trim событий за год (не 17 как думали — 17 = coordinated closes).

7. **Dashboard работает.** `http_server.py` подключён в `app_runner.py`, доступен на `http://127.0.0.1:8765/` при запущенном боте. Не баг, не gap.

8. **Handoff содержит 16 скилов verbatim.** Новый Claude сессии видит полный skills inventory в PART 5 без необходимости читать `.claude/skills/` отдельно.

## Decisions made

- `keep='last'` для varying duplicates в snapshots (24 race-condition groups) — most recent API response
- Idempotent write cache `_snapshot_written` — in-process, 500 keys max, deploy при следующем restart
- TD-dependent K_LONG = DOCUMENTED AS STRUCTURAL (не как долг к фиксу)
- asymmetric_trim_size_pct = 50% — фиксировано, не тестировалось отдельно; возможная оптимизация
- Handoff = единственный источник онбординга нового Claude (не SESSION_LOG, не MASTER.md)
- Каждый TZ заканчивается `Skills applied: <list>` — без этого TZ возвращается на доработку

## Not changed (intentional)

- LONG ground truth K=-0.99 в calibration данных до фикса — historical, не overwritten
- tracker.py Windows PID lock race — DEBT, не трогали (deploy при следующем restart)

## Next session priorities

1. **Operator: загрузить 1s OHLCV** → разблокирует TZ-ENGINE-FIX-RESOLUTION
2. **Operator: H10 overnight backtest** → разблокирует TZ-057/065/066
3. **Operator: подтвердить instop direction LONG** (Semant A or B?) → TZ-ENGINE-FIX-INSTOP-SEMANTICS-B
4. Phase 1 paper journal продолжение (Day 5+)
5. Когда backtest готов: TZ-057 H10 dedup → TZ-066 calibration → TZ-065 live deploy
