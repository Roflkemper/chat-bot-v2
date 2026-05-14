# regression_baseline_keeper
Trigger: after any code change, before commit, ТЗ closing.

Run `RUN_TESTS.bat` and compare vs baseline in MASTER.md §11:
- failures > baseline → REJECT commit, investigate.
- failures < baseline → update baseline in MASTER §11.
- collection errors changed → separate report regardless of failures.

Format:
REGRESSION CHECK:

baseline: [N] failures (per MASTER §11)
current: [M] failures
delta: [+/-K]
collection errors: [E]
verdict: pass/fail/investigate


Do not commit without this check.
