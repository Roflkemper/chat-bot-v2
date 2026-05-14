@echo off
set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%"
set "REPO_URL=https://github.com/Roflkemper/chat-bot-v2.git"
set "DEFAULT_BRANCH=main"
set "GIT_EXE="
set "GH_EXE="
set "AUTO_COMMIT_MSG=Project update"
set "AUTO_TAG_NAME=v17.7.3"

call :resolve_git
if errorlevel 1 exit /b 1
call :resolve_gh
call :load_version
exit /b 0

:resolve_git
where git >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%i in ('where git') do (
    set "GIT_EXE=%%i"
    goto :git_found
  )
)

for %%p in (
  "%ProgramFiles%\Git\cmd\git.exe"
  "%ProgramFiles(x86)%\Git\cmd\git.exe"
  "%LocalAppData%\Programs\Git\cmd\git.exe"
  "%LocalAppData%\GitHubDesktop\bin\git.exe"
) do (
  if exist %%~p (
    set "GIT_EXE=%%~p"
    goto :git_found
  )
)

for /d %%d in ("%LocalAppData%\GitHubDesktop\app-*") do (
  if exist "%%~fd\resources\app\git\cmd\git.exe" (
    set "GIT_EXE=%%~fd\resources\app\git\cmd\git.exe"
    goto :git_found
  )
)

echo [ERROR] Git was not found.
echo [HINT] Install Git for Windows or GitHub Desktop, then run again.
exit /b 1

:git_found
echo [OK] Git detected: %GIT_EXE%
exit /b 0

:resolve_gh
where gh >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%i in ('where gh') do (
    set "GH_EXE=%%i"
    goto :gh_found
  )
)

for %%p in (
  "%ProgramFiles%\GitHub CLI\gh.exe"
  "%LocalAppData%\Programs\GitHub CLI\gh.exe"
  "%ProgramW6432%\GitHub CLI\gh.exe"
) do (
  if exist %%~p (
    set "GH_EXE=%%~p"
    goto :gh_found
  )
)

set "GH_EXE="
exit /b 0

:gh_found
echo [OK] GitHub CLI detected: %GH_EXE%
exit /b 0

:load_version
if exist VERSION.txt (
  set /p AUTO_COMMIT_MSG=<VERSION.txt
  if "%AUTO_COMMIT_MSG%"=="" set "AUTO_COMMIT_MSG=Project update"
  set "AUTO_TAG_NAME=%AUTO_COMMIT_MSG%"
  set "AUTO_TAG_NAME=%AUTO_TAG_NAME: =%"
  for /f "tokens=1 delims=-" %%i in ("%AUTO_TAG_NAME%") do set "AUTO_TAG_NAME=%%~i"
)
if "%AUTO_TAG_NAME%"=="" set "AUTO_TAG_NAME=v17.7.3"
exit /b 0
