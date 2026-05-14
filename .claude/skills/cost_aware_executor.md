# cost_aware_executor
Trigger: long-running operation, full backtest, grid search, ML training, full repo scan.

Before starting:
1. Estimate runtime in minutes.
2. If >30 min CODE LOCAL → propose OPERATOR LOCAL instead.
3. If repeatable (same data, same params) → OPERATOR LOCAL always.

Format:
LONG OP: estimated [N] minutes for [operation].
Recommendation: OPERATOR LOCAL via [exact command].
Reason: [why operator local is better].

Do not start hoping it finishes. Do not extrapolate from smoke results.
