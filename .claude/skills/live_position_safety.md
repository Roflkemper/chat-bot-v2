# live_position_safety
Trigger: live, rollout, deploy, kill, restart daemon, taskkill, supervisor restart.

Before any task touching live processes/bots:
1. ТЗ must specify operator's open positions (count, direction, breakeven).
2. ТЗ must specify safe execution window (operator not actively trading).
3. ТЗ must specify rollback plan if action fails.

Missing any → REJECT:
LIVE SAFETY MISSING: [items]. Cannot proceed during active trading.

After execution: verify all live processes healthy via supervisor /status before reporting done.
