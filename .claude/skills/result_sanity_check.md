# result_sanity_check
Trigger: после backtest/validation/detector run, перед финальным отчётом.

Sanity flags (any → suspend reporting, investigate):
- win_rate >85% or <40%
- avg_pnl <$5 with volume >$10k (commission-eaten)
- setups_count <expected/10 or >expected*10 (operator gut-check vs actual)
- max_drawdown_pct = 0 (impossible)
- protective_stop never triggered across many cycles (suspicious)

On flag:
SANITY FLAG: [metric] = [value], expected [range].
Likely cause: [hypothesis].
NOT REPORTING SUCCESS until verified.

Investigate before claiming task done.
