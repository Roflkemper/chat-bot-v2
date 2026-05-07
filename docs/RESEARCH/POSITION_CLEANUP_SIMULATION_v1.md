# POSITION_CLEANUP_SIMULATION_v1

- Это analytical support, NOT trading recommendation.
- Predictions цены = N/A; сценарии only use operator-provided price paths and target zone.
- Bot mechanics simplified to per-grid-level closure, not full BitMEX accounting.
- Funding held constant at observed `-0.0082%/8h`; actual funding may flip.
- Margin coefficient is an approximation calibrated to the current snapshot, not an exchange recompute.
- Hedge LONG mechanics simplified to grid plus indicator gate for first IN only.
- Cross-margin pool effects are approximated, not exact BitMEX recomputation.

## §1 Methodology and caveats

- Current-state arithmetic self-check: model short uPnL = `-3,562.66` USD vs input `-3,672.00` USD, diff `109.34` USD (`2.98%`).
- Short position uses linear BTC PnL `qty * (entry - price)`.
- Inverse LONG hedge uses USD-contract approximation `contracts * (price / entry - 1)` in USD terms.
- Margin coefficient approximation is anchored to current state and shifts by scenario PnL delta plus a capital-lock penalty for hedge variants.
- Continuous LONG hedge sizing check vs frozen bot shape: `100 USD * 220 = 22,000 USD` max configured notional. Variants V1/V2/V3 exceed that cap and are flagged as hypothetical beyond frozen bot shape.

## §2 Current state summary

| Metric | Value |
| --- | --- |
| Aggregate SHORT | 1.4160 BTC |
| Avg entry | 79017.0 |
| Current market | 81533.0 |
| Liquidation price | 95938.0 |
| uPnL now | -3,672.00 USD |
| Funding to short / day | 28.00 USD |
| Margin coefficient now | 0.9457 |
| Acceptable realized loss cap | 5,000 USD |

## §3 S1 layered TP results

### L1 conservative
| Depth | Last TP | Realized USD | Remaining BTC | Remaining uPnL @81533 | Eff. BE | Margin coeff |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 80500 | -370.75 | 1.166 | -2,933.66 | 78699 | 0.9447 |
| 2 | 80000 | -616.50 | 0.916 | -2,304.66 | 78344 | 0.9437 |
| 3 | 79500 | -737.25 | 0.666 | -1,675.66 | 77910 | 0.9423 |
| 4 | 79000 | -732.15 | 0.366 | -920.86 | 77017 | 0.9403 |
| 5 | 78500 | -542.93 | 0.000 | -0.00 | flat | 0.9374 |

### L2 balanced
| Depth | Last TP | Realized USD | Remaining BTC | Remaining uPnL @81533 | Eff. BE | Margin coeff |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 80000 | -245.75 | 1.166 | -2,933.66 | 78806 | 0.9444 |
| 2 | 79500 | -366.50 | 0.916 | -2,304.66 | 78617 | 0.9430 |
| 3 | 78500 | -237.25 | 0.666 | -1,675.66 | 78661 | 0.9410 |
| 4 | 78000 | 67.85 | 0.366 | -920.86 | 79202 | 0.9382 |
| 5 | 77500 | 623.07 | 0.000 | -0.00 | flat | 0.9343 |

### L3 operator-view
| Depth | Last TP | Realized USD | Remaining BTC | Remaining uPnL @81533 | Eff. BE | Margin coeff |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 80000 | -245.75 | 1.166 | -2,933.66 | 78806 | 0.9444 |
| 2 | 79000 | -241.50 | 0.916 | -2,304.66 | 78753 | 0.9427 |
| 3 | 78500 | -112.25 | 0.666 | -1,675.66 | 78848 | 0.9407 |
| 4 | 78000 | 192.85 | 0.366 | -920.86 | 79544 | 0.9379 |
| 5 | 77500 | 748.07 | 0.000 | -0.00 | flat | 0.9339 |

### L4 aggressive
| Depth | Last TP | Realized USD | Remaining BTC | Remaining uPnL @81533 | Eff. BE | Margin coeff |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 79500 | -120.75 | 1.166 | -2,933.66 | 78913 | 0.9441 |
| 2 | 78500 | 8.50 | 0.916 | -2,304.66 | 79026 | 0.9420 |
| 3 | 78000 | 262.75 | 0.666 | -1,675.66 | 79412 | 0.9397 |
| 4 | 77500 | 717.85 | 0.366 | -920.86 | 80978 | 0.9365 |
| 5 | 77000 | 1,456.07 | 0.000 | -0.00 | flat | 0.9320 |

### L5 deep-target
| Depth | Last TP | Realized USD | Remaining BTC | Remaining uPnL @81533 | Eff. BE | Margin coeff |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 79000 | 4.25 | 1.166 | -2,933.66 | 79021 | 0.9437 |
| 2 | 78000 | 258.50 | 0.916 | -2,304.66 | 79299 | 0.9414 |
| 3 | 77500 | 637.75 | 0.666 | -1,675.66 | 79975 | 0.9387 |
| 4 | 77000 | 1,242.85 | 0.366 | -920.86 | 82413 | 0.9351 |
| 5 | 76500 | 2,164.07 | 0.000 | -0.00 | flat | 0.9302 |

## §4 S2 hold-and-wait results

| Price | uPnL USD | Margin coeff | Dist. to liq | 7d fund | 30d fund | 60d fund | 90d fund | 90d eff. BE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 76000 | 4,272.07 | 0.9246 | 26.23% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 77000 | 2,856.07 | 0.9283 | 24.59% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 78000 | 1,440.07 | 0.9321 | 23.00% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 78500 | 732.07 | 0.9340 | 22.21% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 78779 | 337.01 | 0.9350 | 21.78% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 79000 | 24.07 | 0.9359 | 21.44% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 80000 | -1,391.93 | 0.9396 | 19.92% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 81000 | -2,807.93 | 0.9434 | 18.44% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 81533 | -3,562.66 | 0.9454 | 17.67% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 82000 | -4,223.93 | 0.9472 | 17.00% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 83000 | -5,639.93 | 0.9509 | 15.59% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 85000 | -8,471.93 | 0.9585 | 12.87% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 90000 | -15,551.93 | 0.9773 | 6.60% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |
| 95000 | -22,631.93 | 0.9962 | 0.99% | 196.00 | 840.00 | 1,680.00 | 2,520.00 | 80797 |

## §5 S3 active bot dynamics results

| Path | Mode | Realized USD | Final BTC | Final uPnL | Final total PnL | Margin coeff |
| --- | --- | --- | --- | --- | --- | --- |
| Path-A | unlimited | 268.53 | 0.000 | 0.00 | 268.53 | 0.9352 |
| Path-A | capped_1_416 | 268.53 | 0.000 | 0.00 | 268.53 | 0.9352 |
| Path-B | unlimited | 268.53 | 0.000 | 0.00 | 268.53 | 0.9352 |
| Path-B | capped_1_416 | 268.53 | 0.000 | 0.00 | 268.53 | 0.9352 |
| Path-C | unlimited | 322.27 | 0.000 | 0.00 | 322.27 | 0.9351 |
| Path-C | capped_1_416 | 268.53 | 0.000 | 0.00 | 268.53 | 0.9352 |
| Path-D | unlimited | 0.00 | 1.494 | -4,823.50 | -4,823.50 | 0.9488 |
| Path-D | capped_1_416 | 0.00 | 1.416 | -4,790.33 | -4,790.33 | 0.9487 |
| Path-E | unlimited | 283.88 | 0.000 | 0.00 | 283.88 | 0.9352 |
| Path-E | capped_1_416 | 268.53 | 0.000 | 0.00 | 268.53 | 0.9352 |

## §6 S4 mixed (no hedge) results

| Horizon | Path | Bot mode | L3 depth | Realized+funding | Remaining BTC | Final total PnL | Margin coeff |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 7d | Path-B | unlimited | 4 | 461.38 | 0.000 | 461.38 | 0.9347 |
| 7d | Path-B | capped_1_416 | 4 | 461.38 | 0.000 | 461.38 | 0.9347 |
| 30d | Path-C | unlimited | 4 | 515.12 | 0.000 | 515.12 | 0.9346 |
| 30d | Path-C | capped_1_416 | 4 | 461.38 | 0.000 | 461.38 | 0.9347 |
| 60d | Path-E | unlimited | 4 | 476.73 | 0.000 | 476.73 | 0.9347 |
| 60d | Path-E | capped_1_416 | 4 | 461.38 | 0.000 | 461.38 | 0.9347 |

## §7 S5 stress test

- Manual-close abort level for full position at realized loss `-5,000 USD`: approx price `82548`.
- S1: All requested TP ladders are below avg entry and therefore realize gains, not losses.
- S2 worst hold node: price `95000`, uPnL `-22,631.93` USD, coeff `0.9962`.
- S3 worst path/mode: `Path-D` / `unlimited`, final total PnL `-4,823.50` USD.
- S4 worst horizon/mode: `7d` / `unlimited`, final total PnL `461.38` USD.

## §8 S6 hedge strategy comparison (P-3 + parallel LONG)

### S6.A P-3 cascade hedge
| Scenario | Size | Entry | Exit | Hedge realized | Combined short state | Exit reason |
| --- | --- | --- | --- | --- | --- | --- |
| A1 now_trigger_81533_to_80000 | 10% deposit | 81533 | 80962 | -14.00 | -2,768.50 | stop |
| A1 now_trigger_81533_to_80000 | 20% deposit | 81533 | 80962 | -28.00 | -2,782.50 | stop |
| A2 decline_trigger_80500_to_79700 | 10% deposit | 80500 | 79936 | -14.00 | -1,316.01 | stop |
| A2 decline_trigger_80500_to_79700 | 20% deposit | 80500 | 79936 | -28.00 | -1,330.01 | stop |
| A3 no_cascade | 10% deposit | n/a | n/a | 0.00 | -3,672.00 | no trigger |
| A3 no_cascade | 20% deposit | n/a | n/a | 0.00 | -3,672.00 | no trigger |

### S6.B Continuous parallel LONG hedge
#### V1 full_neutral
| Path | Net PnL USD | Net BTC delta | Margin coeff | Locked margin | Exceeds frozen cfg cap |
| --- | --- | --- | --- | --- | --- |
| Path-A | 1,440.07 | 1.416 | 1.2175 | 115,450.73 | YES |
| Path-B | 1,440.07 | 1.416 | 1.2175 | 115,450.73 | YES |
| Path-C | 1,440.07 | 1.416 | 1.2175 | 115,450.73 | YES |
| Path-D | -4,790.33 | 1.416 | 1.2341 | 115,450.73 | YES |
| Path-E | 1,440.07 | 1.416 | 1.2175 | 115,450.73 | YES |

#### V2 partial_50
| Path | Net PnL USD | Net BTC delta | Margin coeff | Locked margin | Exceeds frozen cfg cap |
| --- | --- | --- | --- | --- | --- |
| Path-A | 1,454.07 | 1.416 | 1.0748 | 57,725.36 | YES |
| Path-B | 1,538.07 | 1.416 | 1.0746 | 57,725.36 | YES |
| Path-C | 1,510.07 | 1.416 | 1.0746 | 57,725.36 | YES |
| Path-D | -4,776.33 | 1.416 | 1.0914 | 57,725.36 | YES |
| Path-E | 1,468.07 | 1.416 | 1.0747 | 57,725.36 | YES |

#### V3 partial_25
| Path | Net PnL USD | Net BTC delta | Margin coeff | Locked margin | Exceeds frozen cfg cap |
| --- | --- | --- | --- | --- | --- |
| Path-A | 1,461.07 | 1.416 | 1.0034 | 28,862.68 | YES |
| Path-B | 1,587.07 | 1.416 | 1.0031 | 28,862.68 | YES |
| Path-C | 1,545.07 | 1.416 | 1.0032 | 28,862.68 | YES |
| Path-D | -4,769.33 | 1.416 | 1.0200 | 28,862.68 | YES |
| Path-E | 1,482.07 | 1.416 | 1.0033 | 28,862.68 | YES |

#### V4 minimal_15
| Path | Net PnL USD | Net BTC delta | Margin coeff | Locked margin | Exceeds frozen cfg cap |
| --- | --- | --- | --- | --- | --- |
| Path-A | 1,463.88 | 1.416 | 0.9748 | 17,285.00 | NO |
| Path-B | 1,606.73 | 1.416 | 0.9744 | 17,285.00 | NO |
| Path-C | 1,559.11 | 1.416 | 0.9745 | 17,285.00 | NO |
| Path-D | -4,766.52 | 1.416 | 0.9914 | 17,285.00 | NO |
| Path-E | 1,487.69 | 1.416 | 0.9747 | 17,285.00 | NO |

### S6.C Hedge cost analysis
| Variant | BTC eq | Notional USD | Locked margin | % of available balance | Net funding/day | Within frozen cfg |
| --- | --- | --- | --- | --- | --- | --- |
| V1 full_neutral | 1.416 | 115,450.73 | 115,450.73 | 570.9% | 0.00 | NO |
| V2 partial_50 | 0.708 | 57,725.36 | 57,725.36 | 285.5% | 14.00 | NO |
| V3 partial_25 | 0.354 | 28,862.68 | 28,862.68 | 142.7% | 21.00 | NO |
| V4 minimal_15 | 0.212 | 17,285.00 | 17,285.00 | 85.5% | 23.81 | YES |

## §9 S7 decision matrix synthesis

| Rank | Option | Best-case PnL | Worst-case PnL | Cap. eff. | Complexity | Robustness | Avg coeff | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | O1 Pure hold | 1,636.07 | -4,762.33 | 0.1431 | 1 | -4,762.33 | 0.9352 | -1838.55 |
| 2 | O5 Wait cascade, P-3 only | 1,636.07 | -4,762.33 | 0.1297 | 2 | -4,762.33 | 0.9352 | -1889.90 |
| 3 | O2 L3 ladder only | 615.73 | -4,762.33 | 0.2901 | 2 | -4,762.33 | 0.9372 | -2078.33 |
| 4 | O3 L3 + capped bot | 461.38 | -4,762.33 | 0.5986 | 3 | -4,762.33 | 0.9375 | -2128.41 |
| 5 | O6 O3 + opportunistic P-3 | 461.38 | -4,762.33 | 0.5852 | 4 | -4,762.33 | 0.9375 | -2179.76 |
| 6 | O4 O3 + parallel LONG V3 | 454.38 | -4,769.33 | 0.0122 | 4 | -4,769.33 | 1.0089 | -2255.88 |

_Compute time: 0.19s_
