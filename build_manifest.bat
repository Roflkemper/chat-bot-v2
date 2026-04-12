@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

if not exist "manifest" (
    echo [ERROR] Folder "manifest" not found.
    exit /b 1
)

> "PROJECT_MANIFEST.md" (
    type "manifest\manifest_header.md"
    echo.
    type "manifest\project_rules.md"
    echo.
    type "manifest\architecture.md"
    echo.
    type "manifest\current_status.md"
    echo.
    type "manifest\roadmap.md"
    echo.
    type "manifest\release_policy.md"
    echo.
    type "manifest\next_chat_template.md"
)

if errorlevel 1 (
    echo [ERROR] Failed to build PROJECT_MANIFEST.md
    exit /b 1
)

echo [OK] PROJECT_MANIFEST.md updated
exit /b 0
