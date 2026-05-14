# C2 — Strategy correlation matrix

**Source:** setups.jsonl (221 setups, 2026-05-01 03:19:41.769642+00:00 → 2026-05-10 08:59:46.838858+00:00)
**Window:** ±30 min co-firing
**Unique setup_types:** 10

## Per-type firing counts

| setup_type            |   count |
|:----------------------|--------:|
| short_rally_fade      |      55 |
| grid_booster          |      52 |
| short_pdh_rejection   |      50 |
| long_multi_divergence |      47 |
| long_dump_reversal    |       5 |
| long_pdl_bounce       |       4 |
| long_double_bottom    |       4 |
| short_mfi_multi_ga    |       2 |
| short_double_top      |       1 |
| short_div_bos_15m     |       1 |

## Top co-firing pairs (sorted by n_cofire desc)

**PMI** (Pointwise Mutual Information) > 0 means pair fires MORE than independent random; < 0 means LESS (orthogonal).

| type_a              | type_b                |   n_a |   n_b |   n_cofire |   p_cofire_% |   expected_indep_% |   pmi |
|:--------------------|:----------------------|------:|------:|-----------:|-------------:|-------------------:|------:|
| short_pdh_rejection | short_rally_fade      |    50 |    55 |        116 |        52.49 |              5.631 |  3.22 |
| grid_booster        | long_dump_reversal    |    52 |     5 |         54 |        24.43 |              0.532 |  5.52 |
| long_double_bottom  | long_multi_divergence |     4 |    47 |         50 |        22.62 |              0.385 |  5.88 |
| grid_booster        | long_pdl_bounce       |    52 |     4 |         36 |        16.29 |              0.426 |  5.26 |
| long_dump_reversal  | long_pdl_bounce       |     5 |     4 |         15 |         6.79 |              0.041 |  7.37 |
| short_mfi_multi_ga  | short_pdh_rejection   |     2 |    50 |          6 |         2.71 |              0.205 |  3.73 |

## Mega-setup candidates (3-detector confluence)

| a            | b                  | c               |   n |
|:-------------|:-------------------|:----------------|----:|
| grid_booster | long_dump_reversal | long_pdl_bounce |  20 |

## Interpretation

- **Pairs with PMI > 1** are highly correlated — likely measuring same regime. Combining them gives no extra signal.
- **Pairs with PMI < -1** never co-fire — true orthogonal indicators. Combining them is meaningful confluence.
- **Triples that fired N≥5 times** are the practical mega-setups: 3 independent signals agreeing.