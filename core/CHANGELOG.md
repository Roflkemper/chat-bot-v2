# CHANGELOG

## V17.10.46.4.4-requested-partial-dead-trade-tp3-tail
- partial size set to 30% in the backtest execution path (note: previous baseline used 25%, not 50%)
- added dead-trade market exit for pre-TP1 trades after 8+ bars when profit stays below 0.35% and ATR compresses vs entry ATR
- added optional TP3 tail for LONG entries in MARKUP medium phase: 10% tail remains open after TP2 and exits later via normal management/flip/timeout path
- added regression tests for dead-trade exit and TP3 tail handoff

## V17.10.46.3.5-expectancy-stabilization
- backtest expectancy profile stabilized: TP1 floor raised to >= 1R and TP2 normalized into ~1.9R with 2.2R cap
- BE de-aggressed further: larger BE buffer (0.35%) and later activation, reducing micro-profit stopouts
- partial size reduced to 25% so more position remains for TP2 expectancy
- timeout logic now extends mature profitable trades and partial winners longer before forced exit
- stop breathing room widened slightly via ATR/structural cap update, without breaking the existing pipeline
- added regression tests for expectancy target profile and timeout protection of mature winners

V17.10.46.3.4 — BE de-aggression + profit-preserving timeout + TP1>=1R + mild execution widening

## V17.10.46.3.3 — backtest expectancy tuning
- widened backtest breathing room with hybrid ATR/structural stop logic
- moved BE earlier before TP1 using a partial path trigger
- set TP2 to a stronger RR floor while keeping TP reachable on 1H history
- kept quality filters strict but loosened only the execution timing path
- cleaned stop handling after BE so protected trades exit at BE stop, not original stop

## V17.10.45-single-owner-release-flow

- release/push flow переведён под правило: один владелец репозитория, локальная ветка — источник истины
- `PUSH_RELEASE.bat` больше не делает `git pull --rebase`
- push теперь идёт через `git push --force-with-lease origin <branch>`
- добавлен авто-abort незавершённого `rebase`/`merge` перед релизным прогоном
- `MAKE_RELEASE.bat` теперь тоже автоматически чистит незавершённый rebase/merge перед локальной сборкой
- `tools/release_runner.ps1` синхронизирован с тем же single-owner release flow

## V17.10.44-if-then-plan

- Added a dedicated `IF-THEN PLAN` layer after decision assembly, without mixing it into the decision logic.
- `core/if_then_plan.py` now builds structured primary + flip scenarios with IF/THEN blocks: zone, trigger, context, action, entry, invalidation, and fallback.
- Pipeline now exposes both `if_then_layer` (structured object) and `if_then_plan` (renderer-ready lines) for downstream output and regression safety.
- Added regression tests for the new layer and pipeline integration.

- V17.10.43 hotfix1: fixed MAKE_RELEASE/PUSH_RELEASE manifest rebuild path; removed BOM issues from BAT files.
## V17.10.43 — EXIT STRATEGY DYNAMIC
- exit strategy теперь обновляется по streak состояния momentum
- правило `NEUTRAL x2 => momentum иссяк` вынесено в state и в рендер
- добавлены regression tests на double neutral streak и динамический exhaustion update

## V17.10.42-smoke-test-gate
- Added `SMOKE_TEST.bat` for one live API run before release.
- Added `tools/smoke_test.py` to run the bot once, verify non-empty Telegram output, and block release on Traceback/Exception.
- `MAKE_RELEASE.bat` now runs Regression Shield + live smoke test before ZIP build.
- `PUSH_RELEASE.bat` now runs Regression Shield + live smoke test before git push/release flow.

## V17.10.40-cleanup-base
- cleaned repository root and moved legacy release notes/checklists/manifests into docs/history/
- replaced root README.md with project-level quick-start and command map
- added docs/README.md and releases/README.md
- added .gitkeep placeholders for logs/, exports/, state/, releases/
- updated NEXT_CHAT_PROMPT.txt and manifest sources for post-cleanup baseline
- push_release.bat prepared for safer sync before push

## V17.10.39-regression-shield-hooks
- added .githooks with pre-commit and pre-push Regression Shield gates
- added INSTALL_GIT_HOOKS.bat and VERIFY_GIT_HOOKS.bat
- added tools/install_git_hooks.ps1 and HOOKS_README.md
- local commit/push is now blocked automatically if tests fail

## V17.10.38-regression-shield-release-gate-hotfix1
- fixed local release ZIP build path handling by moving packaging logic to tools/build_release_zip.ps1
- release packaging now skips excluded roots reliably, including releases/
- make_release_only.bat and push_release.bat now call the shared ZIP builder

﻿## V17.10.29
- Добавлен scaffold автоматической сборки PROJECT_MANIFEST.md
- Добавлены build_manifest.bat, make_release_only.bat, push_release.bat
- Добавлен .releaseignore и RELEASE_AUTOMATION_README.md

## V17.10.22
- Added permanent top signal line for DANGER / WAIT / near-breakout states.
- Removed ENTRY block from renderer when ACTION=WAIT.
- Added flip prep progress with explicit X/Y bars and confirmation level.
- Added composite bias score and absorption/time-at-level block.
- Added If-Then action plan and consolidated current action summary.
- Added structural 1h blocker wiring and ginarea priority sync.
- Restored build_execution_snapshot compatibility and fixed pattern_history_store.
- Added offline-safe market data fallbacks for local verification/tests.


## V17.8.4.4
- project manifest system
- github integration
- next chat prompt system

## V17.9.3.0
- Added GRID ACTION ENGINE wiring.
- Added liquidity_structure-based 1h structure detection for GRID VIEW.
- Split report into TRADER VIEW and GRID VIEW.
- Fixed execution_side NameError in pipeline.

## V17.10.30
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 16:22:03

## V17.10.31
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 16:25:25

## V17.10.32
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 16:32:33

## V17.10.33
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 16:34:50

## V17.10.34
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 21:00:03

## V17.10.35
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 21:16:25

## V17.10.36
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 22:38:29

## V17.10.37
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: 2026-04-12 23:25:45


## V17.10.38-regression-shield-release-gate
- added RUN_TESTS.bat for manual Regression Shield запуск
- make_release_only.bat now blocks ZIP build if tests fail
- push_release.bat now blocks push/release if tests fail
- GitHub workflows now install pytest and run Regression Shield before build/release
## V17.10.38-regression-shield-release-gate-hotfix2
- fixed ZIP verification by moving it to tools/verify_release_zip.ps1
- make_release_only.bat uses the shared verifier
- push_release.bat uses the shared verifier


## V17.10.41-clean-bat-layout
- корень релиза очищен до минимального набора bat-файлов
- `make_release_only.bat` переименован в `MAKE_RELEASE.bat`
- `push_release.bat` переименован в `PUSH_RELEASE.bat`
- старые bat/cmd-файлы перенесены в `tools/legacy_bat/`
- `INSTALL_GIT_HOOKS.bat` теперь сразу проверяет установленный hooks path


## V17.10.46-backtesting-90d
- добавлен отдельный `core/backtest_engine.py` для 90-дневного backtesting без ломки pipeline
- backtest использует текущий snapshot/decision/if-then слой на rolling history
- добавлены `run_backtest.py` и `RUN_BACKTEST_90D.bat`
- отчёт сохраняется в `backtests/backtest_90d_report.json` и `.txt`
- Regression Shield расширен тестами для backtest engine
- зафиксировано правило single-owner repo: локальная ветка пользователя — источник истины


## V17.10.46.1-backtest-non-zero-hotfix
- исправлен backtest hotfix: пустой прогон 90d больше не считается валидным
- добавен historical execution fallback для IF-THEN flip pressure без ломки decision/pipeline
- backtest теперь исполняет сценарии при pressure flip / confirmed flip / native enter
- Regression Shield усилен: 0 trades / 0 triggered / 0 executed теперь ловятся тестами


## V17.10.46.2-backtest-realism-gating-hotfix
- backtest execution path переведён в реалистичный режим: TP_HIT / STOP / TIMEOUT
- TP/SL теперь проверяются по high/low бара, а не только по close
- добавлен quality gate на основе уже существующих snapshot-полей: context, bias, session conflict
- weak context / low bias / high session conflict теперь режут слабые входы в backtest
- обновлён RUN_BACKTEST_90D.bat: окно не закрывается сразу, показывается exit code
- Regression Shield усилен тестами на TP_HIT path и quality filters


## V17.10.46.3-backtest-trade-plan-realism
- backtest lifecycle переведён на trade-plan realism: TP1 partial -> BE -> TP2 / STOP / TIMEOUT
- в отчёт добавлены execution counters: triggered / armed / entered / closed
- в summary добавлены exit counters: tp_hit / stop / timeout
- flip-входы (PRESSURE_FLIP_ARM / MID_CROSS_FLIP / FLIP_CONFIRM) теперь требуют более сильного качества: stronger context, bias и edge/confidence
- pnl в backtest теперь учитывает partial take-profit и остаток позиции отдельно
- Regression Shield расширен тестами на partial+BE и cleanup execution accounting

V17.10.46.3.1 — backtest arm bridge hotfix
- restored historical trigger -> armed -> entered bridge in backtest
- relaxed flip gate from impossible STRONG-only threshold to VALID/STRONG with pressure/score support
- run_backtest.py now returns non-zero when backtest triggers exist but no entries are executed


V17.10.46.3.2 — ATR TP/SL normalization + dynamic timeout
- backtest trade plan switched from invalidation-percent sizing to ATR-normalized TP1/TP2/SL
- added hard max stop cap (1.5%) and min stop floor to avoid oversized backtest losses
- added dynamic timeout extension when trade makes real progress or volatility is compressed
- preserved existing quality gate and trigger->arm->enter bridge


V17.10.46.3.4.1 - TP priority restore + partial path restore.


## V17.10.46.3.6-timeout-leakage-cut-runner-protection
- timeout logic разделена на dead trade timeout и productive runner timeout без ломки pipeline
- timeout теперь учитывает peak progress / peak pnl / last meaningful progress, а не только текущее состояние бара
- runner после partial/TP1 получает дополнительную защиту от преждевременного timeout
- stagnant сделки без реального прогресса теперь закрываются базовым timeout без лишнего leakage
- Regression Shield усилен тестами на peak-progress protection и dead-trade timeout
