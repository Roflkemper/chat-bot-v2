# HYSTERESIS CALIBRATION V1

**Date:** 2026-05-05
**TZ:** TZ-HYSTERESIS-CALIBRATION
**Goal:** Find the smallest `hysteresis_bars` value that lands the data-driven TRANSITION share inside the 5-15 % sanity range, given the regime-label time series in `full_features_1y.parquet`.

**Driver:** [`scripts/_hysteresis_calibration.py`](../../scripts/_hysteresis_calibration.py)
**Raw output:** [`_hysteresis_calibration_raw.json`](_hysteresis_calibration_raw.json)
**Compute:** ~1.4 s.

**Window:** 1y, 2025-05-01 00:00 UTC → 2026-05-01 00:00 UTC, **8 761 hourly bars**.

---

## §1 Methodology

### TRANSITION operational definition
For each hourly bar `h` and a given `hysteresis_bars` parameter `H`:
- `h` is `TRANSITION` ⇔ rolling window `[h-H, h]` (size `H+1`) contains **≥2 distinct `regime_int`** values.
- Rule (a) only — no classifier-confidence column exists in `full_features_1y.parquet`, so the optional confidence-gate (rule b in Block 2) is skipped uniformly across all swept values.

### Sweep
Primary sweep (per brief): `H ∈ {3, 6, 9, 12, 15, 18, 24}`.
**Diagnostic extension** (added when no primary value landed in band): `H ∈ {1, 2}`.

### Metrics per `H`
- `transition_pct` = TRANSITION hours / 8 761
- `n_transition_segments` = count of contiguous TRANSITION runs (start when 0→1, end when 1→0)
- `mean_transition_segment_hours` = mean run length of those segments
- `stable_regime_breakdown` = composition of NON-TRANSITION hours by regime label

### Recommendation rule
- If any swept `H` gives `transition_pct ∈ [5, 15]`, recommend the value **closest to 10 % midpoint** among in-range values (rationale: avoids both rare-flag and saturated-flag failure modes).
- Otherwise: closest to 10 % across all swept values, flagged as out-of-band fallback.

---

## §2 Sweep results

### Primary sweep (per-brief 7 values)
| `hysteresis_bars` | TRANSITION % | TRANSITION h | Stable h | Segments | Mean seg len (h) | In [5,15] ? |
|---:|---:|---:|---:|---:|---:|:---:|
| 3 | 17.90 | 1 568 | 7 193 | 364 | 4.3 | no |
| 6 | 29.38 | 2 574 | 6 187 | 285 | 9.0 | no |
| 9 | 38.58 | 3 379 | 5 382 | 243 | 13.9 | no |
| 12 | 46.48 | 4 072 | 4 689 | 211 | 19.3 | no |
| 15 | 53.20 | 4 661 | 4 100 | 173 | 26.9 | no |
| 18 | 58.81 | 5 153 | 3 608 | 143 | 36.0 | no |
| 24 | 67.41 | 5 906 | 2 855 | 93 | 63.5 | no |

**No primary value lands in [5, 15].** Even the smallest swept value (H=3) yields TRANSITION = 17.9 %.

### Diagnostic extension
| `hysteresis_bars` | TRANSITION % | TRANSITION h | Segments | Mean seg len (h) | In [5,15] ? |
|---:|---:|---:|---:|---:|:---:|
| **1** | **7.35** | 644 | 505 | 1.3 | **yes** |
| **2** | **13.12** | 1 149 | 419 | 2.7 | **yes** |

Two diagnostic values land in band: `H=1` at the lower edge (7.35 %), `H=2` near the upper edge (13.12 %).

### Stable regime breakdown (background)
At every swept `H`, the NON-TRANSITION hours retain a regime mix close to the underlying year mix (RANGE ~72 %, MARKDOWN ~15 %, MARKUP ~13 %). The breakdown does not flip with `H` — TRANSITION simply extracts more or fewer hours symmetrically across regimes. (Full stable-regime numbers per H in `_hysteresis_calibration_raw.json` → `sweep[*].stable_regime_breakdown`.)

---

## §3 Visual: TRANSITION % vs `hysteresis_bars`

```
TRANSITION % of year  (sanity band [5, 15] in [ ])

H= 1   7.35 % | ##.................. [INSIDE BAND]
H= 2  13.12 % | ###................. [INSIDE BAND]
H= 3  17.90 % | ####................
H= 6  29.38 % | ######..............
H= 9  38.58 % | ########............
H=12  46.48 % | ##########..........  <-- current production value
H=15  53.20 % | ###########.........
H=18  58.81 % | ############........
H=24  67.41 % | #############.......
                0          50         100 %
                |          |          |
Sanity band:     [#########]
                  5%        15%
```

Monotonic: every additional bar of hysteresis pushes TRANSITION % up by 2-7 percentage points. This reflects the fact that the underlying regime-change density is high (644 hour-to-hour changes / 8 761 hours = 7.35 %) and any positive-length window expands each change forward, accumulating overlap.

---

## §4 Recommendation

### Recommended `hysteresis_bars = 1`

**Rationale:**
- Among in-band candidates {1, 2}, `H=1` is closest to the 10 % midpoint (|7.35-10| = 2.65 vs |13.12-10| = 3.12).
- `H=1` also gives the most informative segmentation: 505 short TRANSITION segments (mean 1.3 h) vs 419 segments at H=2 (mean 2.7 h). Shorter, more frequent transitions track raw regime-change events more faithfully.
- TRANSITION at H=1 (7.35 %) **equals the raw hour-to-hour regime-change rate** (644 / 8 761), which is the lower bound for any non-trivial transition definition. H=1 is essentially "flag a hour iff its regime label differs from the previous hour's."

### Alternative: `hysteresis_bars = 2`
Operator may prefer H=2 (13.12 %, mean segment 2.7 h) if the design goal is to **bridge brief 1-bar regime flickers** into a 2-3 hour settling window. H=2 still lands in band and produces longer, more "settled" TRANSITION segments. Choice between H=1 and H=2 is a design preference, not a sanity-driven mandate.

### What's wrong with H=12 (current production)
H=12 gives TRANSITION = 46.48 %, mean segment 19.3 hours — **roughly half the year is flagged TRANSITION**, with each transition span lasting nearly a full day. This is incompatible with the typical "transitions are rare and brief" assumption used by TRANSITION-aware policies (Block 2 §6 caveat 1). With `H=12`, any policy that treats TRANSITION specially is acting on the majority of the year.

### Out-of-scope alternative — episode-length pre-condition
A more sophisticated definition would require the **prior stable run** to be ≥N hours before flagging a transition (filter out flickers in advance, not just after). That is a methodology change beyond this TZ's scope and would warrant its own TZ.

---

## §5 Implication for P8 §9 Q2 (note only — no policy decision)

Block 2 (`TRANSITION_MODE_COMPARE_v1`) computed Policy A / B / C using `H=12`, where TRANSITION = 46.48 %. Under that definition, Policies A and B-DR2 silence close to half of every BT window — making the headline policy deltas hard to interpret as "what would actually happen if the coordinator paused during real transitions."

If the coordinator's TRANSITION definition is recalibrated to `H=1` (TRANSITION = 7.35 %) or `H=2` (TRANSITION = 13.12 %), the policy comparison would change dramatically:
- Policy A (Pause-All) would silence ~7-13 % of every BT window instead of ~47-54 %, producing a much smaller PnL delta.
- Policy C (×0.5 sizing) would correspondingly have a smaller absolute effect.
- Policy B-DR2 (G1 trend-pause) would also shrink in impact.

**This is a note, not a policy recommendation.** The choice of `hysteresis_bars` for the production coordinator state machine is a design decision that depends on more than just the sanity-band fit (e.g. how often the operator wants the coordinator to react, latency tolerances, expected episode-length distribution in future market regimes). Re-running Block 2 with the recalibrated `H` is the natural follow-up if the operator decides to lock in a new value.

This TZ does not modify production code, does not pick `H`, and does not re-run `TRANSITION_MODE_COMPARE`.

---

## CP report

- **Output paths:**
  - [docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md](HYSTERESIS_CALIBRATION_v1.md)
  - [docs/RESEARCH/_hysteresis_calibration_raw.json](_hysteresis_calibration_raw.json)
  - [scripts/_hysteresis_calibration.py](../../scripts/_hysteresis_calibration.py)
- **Recommended `hysteresis_bars`:** **1** (alternative: 2)
- **TRANSITION % at recommended value:** **7.35 %** (644 / 8 761 hours)
- **Compute time:** ~1.4 s (well below any threshold)

### Anti-drift adherence
- ✅ All 7 brief-specified hysteresis values computed.
- ✅ No regime classifier modification.
- ✅ No production code touched (`services/` untouched).
- ✅ No new TZs spawned.
- ✅ §5 contains note only, no policy decision.
- ⚠ Sweep extended diagnostically with `H ∈ {1, 2}` because no primary value landed in [5, 15] band — declared explicitly in §2.

---

## References
- Block 2 raw data: [`_transition_mode_compare_raw.json`](_transition_mode_compare_raw.json) (4 072 transition hours @ H=12, baseline)
- Episode statistics: [`_regime_periods_raw.json`](_regime_periods_raw.json) (645 episodes baseline)
- Regime period source: [`REGIME_PERIODS_2025_2026.md`](REGIME_PERIODS_2025_2026.md)
