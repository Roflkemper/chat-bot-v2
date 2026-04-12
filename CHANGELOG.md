## V17.10.44-if-then-plan

- Added a dedicated `IF-THEN PLAN` layer after decision assembly, without mixing it into the decision logic.
- `core/if_then_plan.py` now builds structured primary + flip scenarios with IF/THEN blocks: zone, trigger, context, action, entry, invalidation, and fallback.
- Pipeline now exposes both `if_then_layer` (structured object) and `if_then_plan` (renderer-ready lines) for downstream output and regression safety.
- Added regression tests for the new layer and pipeline integration.

- V17.10.43 hotfix1: fixed MAKE_RELEASE/PUSH_RELEASE manifest rebuild path; removed BOM issues from BAT files.
# Changelog

## V17.10.43 — EXIT STRATEGY DYNAMIC
- exit strategy теперь обновляется по streak состояния momentum
- правило `NEUTRAL x2 => momentum иссяк` вынесено в state и в рендер
- добавлены regression tests на double neutral streak и динамический exhaustion update

## V17.10.42-smoke-test-gate
- Added `SMOKE_TEST.bat` for one live API run before release.
- Added `tools/smoke_test.py` to run the bot once, verify non-empty Telegram output, and block release on Traceback/Exception.
- `MAKE_RELEASE.bat` now runs Regression Shield + live smoke test before ZIP build.
- `PUSH_RELEASE.bat` now runs Regression Shield + live smoke test before git push/release flow.

# CHANGELOG

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
