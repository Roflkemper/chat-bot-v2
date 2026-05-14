# Mega-pair early exit via GC

**Period:** 730d | **GC early-exit threshold:** up>=4
**Trade params:** SL=-0.8%, TP1=+2.0%, hold=240min

## Results

| mode          |   n |   wr |    pf |   pnl_pct |   avg_pnl_pct |
|:--------------|----:|-----:|------:|----------:|--------------:|
| BASELINE      | 213 | 50.2 | 1.399 |     23.35 |        0.1096 |
| GC_EARLY_EXIT | 213 | 50.2 | 1.252 |     14.74 |        0.0692 |

**Baseline exit distribution:** {'EXPIRE': 146, 'SL': 52, 'TP1': 10, 'TP2': 5}
**GC mode exit distribution:** {'TIMEOUT': 146, 'SL': 52, 'TP1': 15}
**Trades flagged for GC early exit:** 0

## Verdict

❌ **GC exit HURTS by 8.61pp.** Don't wire — TP gives better exit.