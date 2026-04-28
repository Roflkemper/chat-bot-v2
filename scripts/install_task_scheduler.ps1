# Регистрирует задачу Windows Task Scheduler: запускает bot7 supervisor при входе
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\install_task_scheduler.ps1

$TaskName   = "bot7-supervisor"
$BotRoot    = "C:\bot7"
$Python     = "$BotRoot\.venv\Scripts\python.exe"
$Args       = "-m bot7 start"
$WorkingDir = $BotRoot

# Удалить старую задачу если есть
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action  = New-ScheduledTaskAction -Execute $Python -Argument $Args -WorkingDirectory $WorkingDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit 0 `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $Action `
    -Trigger  $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Description "bot7 supervisor — starts app_runner, tracker, collectors on login"

Write-Host "Task '$TaskName' registered. It will run at next login."
Write-Host "To start now: Start-ScheduledTask -TaskName '$TaskName'"
