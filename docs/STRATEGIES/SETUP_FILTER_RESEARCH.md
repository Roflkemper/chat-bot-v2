# Setup filter research

**Period:** last 14,400 1m bars (~10d)
**Setups analyzed:** 1

## detect_long_div_bos_confirmed

- Total emits: 47
- Classes: {'NEUTRAL': 27, 'FALSE': 14, 'TRUE': 6}
- **Baseline:** {'n': 47, 'wr': 42.6, 'pf': 0.939, 'total_pnl_pct': -1.85, 'avg_pnl_pct': -0.0393}

### Top discriminating features (KS, T-mean vs F-mean)



### Filter built

```json
{}
```

**Filtered metrics:** {'n': 47, 'wr': 42.6, 'pf': 0.939, 'total_pnl_pct': -1.85, 'avg_pnl_pct': -0.0393}

**Confirmed-only (10m lag, +0.1% drift):** {'n': 3, 'wr': 0.0, 'pf': 0.0, 'total_pnl_pct': -3.7, 'avg_pnl_pct': -1.2341}

**Filter + Confirmation:** {'n': 3, 'wr': 0.0, 'pf': 0.0, 'total_pnl_pct': -3.7, 'avg_pnl_pct': -1.2341}

### Walk-forward (4 folds)

|   fold |   baseline_n |   baseline_pf |   baseline_pnl% |   filt_n |   filt_pf |   filt_pnl% |
|-------:|-------------:|--------------:|----------------:|---------:|----------:|------------:|
|      1 |           11 |         1.599 |            2.45 |       11 |     1.599 |        2.45 |
|      2 |           11 |         0.586 |           -2.78 |       11 |     0.586 |       -2.78 |
|      3 |           11 |         0.451 |           -4.85 |       11 |     0.451 |       -4.85 |
|      4 |           14 |         1.311 |            3.34 |       14 |     1.311 |        3.34 |

---
