# launchd templates for Mac

Replace `USERNAME` with your Mac username everywhere, then:
```
launchctl load ~/Library/LaunchAgents/com.bot7.<task>.plist
```

To unload (stop):
```
launchctl unload ~/Library/LaunchAgents/com.bot7.<task>.plist
```

To check status:
```
launchctl list | grep com.bot7
```

## Template files

| File | Equivalent on Windows | Schedule |
|---|---|---|
| `com.bot7.watchdog.plist` | bot7-watchdog | every 2 min |
| `com.bot7.rotate-journals.plist` | bot7-rotate-journals-06am | daily 06:00 |
| `com.bot7.precision-tracker.plist` | bot7-precision-tracker-daily-08am | daily 08:00 |
| `com.bot7.daily-kpi.plist` | bot7-daily-kpi-09am | daily 09:00 |
| `com.bot7.change-log.plist` | bot7-daily-change-log-09am30 | daily 09:30 |
| `com.bot7.refresh-ict.plist` | bot7-refresh-ict-weekly | Sunday 05:00 |
| `com.bot7.restart-check.plist` | bot7-restart-check-hourly | hourly |
| `com.bot7.pipeline-growth.plist` | bot7-pipeline-growth-6h | every 6h |

## launchctl notes

- `RunAtLoad=true` means task runs immediately on load.
- `StartInterval` = seconds between runs (countdown from previous start).
- `StartCalendarInterval` = cron-style: keys Hour, Minute, Weekday (0=Sun).
- `KeepAlive=false` (default) means task exits after completion; launchd respawns at next interval.
- For watchdog (every 2 min), use StartInterval=120. Don't use KeepAlive — watchdog should exit fast.

## Logs

All templates write to `/Users/USERNAME/bot7/logs/launchd_<task>.log` and `.err`.
Tail these to debug:
```
tail -f ~/bot7/logs/launchd_watchdog.log
```
