# bot7 keepalive scheduled task installer
# Registers a Windows task that runs every 2 minutes to ensure supervisor is alive.

$TaskName = "bot7-keepalive"
$BotRoot = "C:\bot7"
$Python = "$BotRoot\.venv\Scripts\pythonw.exe"
$KeepaliveScript = "$BotRoot\scripts\keepalive_check.py"
$WorkingDir = $BotRoot

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction -Execute $Python -Argument $KeepaliveScript -WorkingDirectory $WorkingDir
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(30) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 9999)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "bot7 keepalive checker"

Write-Host "Task '$TaskName' registered"
Write-Host "Logs path: $BotRoot\logs\autostart\keepalive.log"
