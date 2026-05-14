# param_provenance_tracker
Trigger: any change to strategy thresholds, grid sizes, TP/SL, risk constants.

Every strategy parameter must have provenance comment:
```python
C1_THRESHOLD = 0.015  # source: trader methodology MASTER §10, validated TZ-056
```

Before changing parameter:
1. Read existing provenance.
2. If absent — STOP, ask operator: "parameter [name] without provenance, source unknown, need approval before change".
3. If present — REJECT change unless ТЗ explicitly authorizes from operator.
4. After authorized change — update provenance with new TZ reference.

Silent parameter change = severe violation (see PROJECT_RULES.md Parameters).
