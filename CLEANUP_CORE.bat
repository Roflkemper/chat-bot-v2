@echo off
REM =====================================================================
REM  CLEANUP_CORE.bat
REM  Second-pass cleanup: remove legacy duplicate packages and old
REM  release artifacts from core/ while preserving actual runtime code.
REM
REM  Run from C:\bot7.
REM  KEEPS in core/: all *.py files, core/orchestrator/, core/features/,
REM                  core/__init__.py, core/__pycache__/ (ignored by git).
REM  REMOVES:
REM    - 28 duplicate package folders inside core/ (not imported from outside)
REM    - All release-era files: bats, old release notes, duplicates
REM      of root-level config files (pytest.ini, requirements.txt, etc.)
REM    - Broken filename: "python run_backtest.bat"
REM    - Duplicate: "impulse_tracker (1).py"
REM =====================================================================

setlocal

if not exist "app_runner.py" (
    echo [ABORT] app_runner.py not found. Run from C:\bot7.
    exit /b 1
)

if not exist "core\orchestrator\" (
    echo [ABORT] core\orchestrator\ not found. Is this the right repo?
    exit /b 1
)

echo ==========================================================
echo   CLEANUP_CORE starting in: %CD%
echo ==========================================================
echo.

REM --- 1. Drop duplicate package folders inside core/ -----------------
echo [1/5] Removing 28 duplicate package folders inside core\...
for %%D in (
    advisor
    advisors
    analytics
    app
    backtests
    backtests_smoke
    core_facade
    data
    docs
    domain
    execution
    exports
    handlers
    interfaces
    logs
    manifest
    market_data
    models
    renderers
    reports
    services
    storage
    strategies
    telegram_runtime
    telegram_ui
    tests
    tools
    utils
) do (
    if exist "core\%%D\" (
        echo   rmdir core\%%D\
        rmdir /s /q "core\%%D"
    )
)

REM --- 2. Drop duplicate root files inside core/ ----------------------
echo.
echo [2/5] Removing root-file duplicates inside core\...
for %%F in (
    .env.example
    .releaseignore
    BACKTEST_TRACE_README.txt
    CHANGELOG.md
    DETERMINISTIC_BACKTEST_README.txt
    FIX_BACKTEST_PARAM_WIRING.txt
    INSTALL_GIT_HOOKS.bat
    MAKE_RELEASE.bat
    NEXT_CHAT_PROMPT.txt
    PROJECT_MANIFEST.md
    PUSH_RELEASE.bat
    README.md
    RELEASE_NOTES_V17.10.50.txt
    RELEASE_NOTES_V17.10.51.1_pattern_a_post_pass_hotfix.txt
    RUN_BACKTEST.bat
    RUN_BACKTEST_180D_FREEZE_DATA.bat
    RUN_BACKTEST_90D.bat
    RUN_BACKTEST_90D_FREEZE_DATA.bat
    RUN_BACKTEST_90D_LIVE.bat
    RUN_BACKTEST_TRACE_180D.bat
    RUN_BACKTEST_TRACE_90D.bat
    RUN_BOT.bat
    RUN_TESTS.bat
    SHOW_CURRENT_SETTINGS.bat
    SMOKE_TEST.bat
    VERSION.txt
    build_manifest.bat
    pytest.ini
    requirements.txt
    run_bitmex_dashboard.md
) do (
    if exist "core\%%F" (
        echo   del core\%%F
        del /f /q "core\%%F"
    )
)

REM --- 3. Remove broken-name file -------------------------------------
echo.
echo [3/5] Removing broken-name file "core\python run_backtest.bat"...
if exist "core\python run_backtest.bat" (
    echo   del "core\python run_backtest.bat"
    del /f /q "core\python run_backtest.bat"
)

REM --- 4. Remove "(1)"-duplicate --------------------------------------
echo.
echo [4/5] Removing "core\impulse_tracker (1).py"...
if exist "core\impulse_tracker (1).py" (
    echo   del "core\impulse_tracker (1).py"
    del /f /q "core\impulse_tracker (1).py"
)

REM --- 5. Summary ------------------------------------------------------
echo.
echo [5/5] Summary of what remains in core\:
echo.
echo   Subfolders in core\ (expect: orchestrator, features, __pycache__):
dir /b /ad core\
echo.
echo   Non-Python files in core\ (expect: empty or very short):
dir /b /a-d core\ 2^>nul | findstr /v /i "\.py$" | findstr /v "^__pycache__$"
echo.
echo   Python file count in core\ (excluding subfolders):
dir /b /a-d core\*.py 2^>nul | find /v /c ""
echo.
echo ==========================================================
echo   CLEANUP_CORE done.
echo.
echo   Next steps:
echo     1) RUN_TESTS.bat          (expect 248 passed, 1 skipped)
echo     2) Canary backtest 180d   (expect 24 / 75.0%% / +14.3393%% / -2.1542%%)
echo     3) git reset              (clear staged before we re-add)
echo     4) git add . ^&^& git status ^> staged.txt
echo     5) Send staged.txt
echo ==========================================================

endlocal