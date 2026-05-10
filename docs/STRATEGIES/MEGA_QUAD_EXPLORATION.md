# LONG mega quad/quintet exploration

**Period:** 365d 1m honest engine | **Window:** ±60min | **Dedup:** 4h
**Trade:** SL=-0.8% TP1=+2.0% TP2=+4.0% hold=240min
**Min triggers for evaluation:** 10
**Base pair (proven mega-triple):** detect_long_dump_reversal + detect_long_pdl_bounce

## Results (sorted by total_pnl_pct desc)

| combo                          |   n_constituents |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct | wf_pos_folds   |
|:-------------------------------|-----------------:|----:|-----:|------:|----------------:|--------------:|:---------------|
| BASE pair (dump+pdl)           |                2 | 120 | 49.2 | 1.268 |            8.57 |        0.0714 | 2/4            |
| + detect_long_multi_divergence |                3 |  17 | 52.9 | 1.644 |            2.26 |        0.133  | 0/4            |

## Verdict

🟡 **Adding 3rd/4th detector does NOT improve base.** Base pair (N=120, PF=1.268, PnL=8.57%) remains best. Triple/quad combos give fewer triggers and similar/worse PF — confluence already extracted by the pair.