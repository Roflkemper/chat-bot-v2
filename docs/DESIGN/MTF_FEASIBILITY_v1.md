# MTF Per-TF Independent Classification — Feasibility Report v1

**Status:** INVESTIGATION (read-only). No code changes.
**Date:** 2026-05-05
**TZ:** TZ-MTF-FEASIBILITY-CHECK
**Companion design:** [`MTF_DISAGREEMENT_v1.md`](MTF_DISAGREEMENT_v1.md)
**Notes on inputs:** `docs/PROJECT_MAP.md` was missing when this investigation ran; a stub was later restored in `TZ-DOCUMENTATION-FIXES` (2026-05-05). The brief's own input list also referred to `services/regime_classifier/*` and `ml/*` — neither directory exists in the repo. The actual classifier code lives in three places enumerated in §1 below.

---

## §1 Current architecture summary

### 1.1 Three coexisting classifiers (verified by reading source)

| # | Path | Type | TF input | Output | Live? |
|---|---|---|---|---|---|
| **A** | [`core/orchestrator/regime_classifier.py`](../../core/orchestrator/regime_classifier.py) | Hand-coded rule chain (~600 LOC) | Multi-TF (1m + 15m + 1h + 4h candles consumed inside one call) | **Single label** from `{RANGE, TREND_UP, TREND_DOWN, COMPRESSION, CASCADE_UP, CASCADE_DOWN}` + modifier set | **Yes** — wired in [`core/pipeline.py:42,882`](../../core/pipeline.py#L42-L892) (calls `classify(...)` once per snapshot build); output consumed by advise_v2 via [`services/advise_v2/regime_adapter.py`](../../services/advise_v2/regime_adapter.py) |
| **B** | [`services/regime_red_green/`](../../services/regime_red_green/) (`runner.py`, `features.py`, `rules.py`) | sklearn `DecisionTreeClassifier` (depth ≤4) trained offline; auto-generates Python rule code | Single TF (1h only — `resampler.py` resamples 1m→1h) | Single label from `{TREND, RANGE, AMBIGUOUS}` (binary tree, AMBIGUOUS when leaf conf <0.60) | **Offline only** — CLI tool (`extract`/`train`/`validate`); trained 77.5 % accuracy on btc_1h_v1.json. Not invoked at runtime. |
| **C** | [`services/market_forward_analysis/phase_classifier.py`](../../services/market_forward_analysis/phase_classifier.py) | Hand-coded swing-structure rules (Wyckoff-inspired) | Per-TF independent — `classify_phase(df, timeframe)` runs on the TF's own OHLCV; `build_mtf_phase_state(frames)` accepts `{"1d", "4h", "1h", "15m"}` and classifies each independently | **Per-TF labels** from `Phase ∈ {ACCUMULATION, MARKUP, DISTRIBUTION, MARKDOWN, RANGE, TRANSITION}` plus per-TF `confidence`, `direction_bias`, `bars_in_phase`, `key_levels`, `notes` | **Yes** — wired in [`services/market_forward_analysis/loop.py:90`](../../services/market_forward_analysis/loop.py#L90), invoked every 300 s by `market_forward_analysis_loop`; data feed = `ForwardAnalysisDataLoader.all_frames()` returning all four TFs |

There is also [`services/managed_grid_sim/regime_classifier.py`](../../services/managed_grid_sim/regime_classifier.py) — a small simulator-only classifier used by `managed_grid_sim` for offline backtests. Not relevant to live runtime.

[`services/market_forward_analysis/regime_switcher.py`](../../services/market_forward_analysis/regime_switcher.py) (`RegimeForecastSwitcher`) is **not a classifier** despite the name — it's a forecast router that *consumes* a regime label as an input argument and routes to per-regime calibration models. It does not produce regime labels.

### 1.2 Data flow at runtime

```
get_klines(1m, 15m, 1h, 4h) ─► Classifier A (core/orchestrator) ──► single label ──► advise_v2 + dashboard
                                                                                       │
ForwardAnalysisDataLoader (1m CSV → resample 15m/1h/4h/1d, +derivatives)               │
                          └─► Classifier C (phase_classifier) ──► per-TF labels ──────►┤ ──► telegram session brief / phase-change alerts
                                                                                       │
                                              MTF_DISAGREEMENT_v1 design target ◄──────┘
```

### 1.3 Feature coupling — the brief's premise re-examined

The brief's framing — *"existing regime classifier consumes multi-TF features but emits single label"* — is **literally true of Classifier A only**. A's `_compute_metrics` reads bars from all four TFs in one call and produces composites like `last_move_pct_15m`, `atr_pct_4h` etc. that flow into one big rule chain emitting one regime. That's the classifier the **decision layer / advise_v2** sees today.

But the **MTF design (`MTF_DISAGREEMENT_v1` §1, §9 #2)** does **not** want A's output extended. The design explicitly:

- Adopts the `MARKUP/MARKDOWN/RANGE` taxonomy (Wyckoff / regulation-aligned).
- States A's `RANGE/TREND_UP/COMPRESSION/CASCADE_*` taxonomy is **unused** by the disagreement design.
- Names `RegimeForecastSwitcher` (incorrectly — it's actually `phase_classifier`) as the source.

Once you read the code rather than the design's prose, the **per-TF independent classifier the design asks for already exists as Classifier C**, runs in production, and emits the exact `Phase` enum values the design adopts (`MARKUP / MARKDOWN / RANGE` plus three the design says are reserved/unused: `ACCUMULATION / DISTRIBUTION / TRANSITION`).

This is the single most important finding of the investigation and reframes every option below.

---

## §2 Per-option assessment

The four options remain those enumerated in the brief, but the evidence redistributes their relative cost dramatically.

### Option A — Run classifier 3× with TF-filtered features

**Interpretation:** take Classifier A and call it three times with subsets of (15m, 1h, 4h) features.

**Verdict:** **Not viable as written, and unnecessary.**

- A is not feature-decomposable. Its rule chain interleaves per-TF metrics in nested `elif` branches (`detect_cascade_*` reads `last_move_pct_15m / 1h / 4h` jointly; `detect_trend_*` requires `ema200_1h` and `adx_1h` regardless of which TF you wanted to "isolate"; `detect_compression` consumes `atr_history_1h` + `bb_width_history_1h`). You cannot run it on a 4h-only feature subset and get a meaningful "4h regime" — the rules literally hard-code `_1h` suffixes.
- It would also be redundant: Classifier C **already does** what this option set out to fake. Re-deriving per-TF labels from A by feature filtering would produce a less faithful version of what C produces directly.

**Effort if forced through anyway:** 3-5 days of risky decomposition with worse output than the existing C path. **Do not pursue.**

### Option B — Multi-head classifier (single training run produces 3 outputs)

**Interpretation:** retrain a model with three classification heads (one per TF).

**Verdict:** **Not applicable.** B is only meaningful for an *ML* classifier. The two live classifiers (A and C) are both **rule-based**, hand-coded if/elif chains. There is no model to multi-head. Classifier B (regime_red_green) is the only ML path, but it is offline-only, single-TF, and binary (TREND/RANGE only — no MARKUP/MARKDOWN distinction).

The only way B becomes meaningful is to **build** a multi-head ML classifier from scratch as a replacement. That is option D, not option B. **Do not pursue.**

### Option C — Post-hoc decomposition

**Interpretation:** synthesize per-TF labels by inspecting TF-specific input features after a single A inference (e.g. "classify 15m as MARKUP if `last_move_pct_15m > 1 % AND ema_stack_1h ≥ 1`").

**Verdict:** **Don't bother.** This is the workaround you'd write only if C didn't exist. Since C exists, runs in production, and emits per-TF Wyckoff phases independently, post-hoc decomposition would be deliberately producing a worse signal (via heuristics over single-call features) when a better one is sitting on disk. It also fails MTF design §3.1's confidence-eligibility requirement (`regime_confidence ≥ 0.65`) because synthesized labels have no calibrated confidence — only the underlying features' values.

**Effort if forced through:** 1-2 days; but the output would be inferior to C's existing output. **Do not pursue.**

### Option D — Full classifier rebuild

**Verdict:** **Not needed.** This is the escape hatch when nothing else works. Nothing requires escaping.

### Option E (new) — Adopt Classifier C, harden it, wire MTF_DISAGREEMENT on top

This option does not appear in the brief because the brief's premise didn't anticipate that the per-TF classifier already exists. Adding it explicitly:

- C already produces per-TF labels for `1d / 4h / 1h / 15m`, the exact TF set the MTF design specifies (§2 of MTF design).
- C's `Phase` enum is a **superset** of the design's adopted taxonomy. The mapping is direct: `MARKUP → MARKUP`, `MARKDOWN → MARKDOWN`, `RANGE / ACCUMULATION / DISTRIBUTION / TRANSITION → RANGE` (or, with operator preference, expose ACCUMULATION/DISTRIBUTION as informational sub-states). The design itself reserves `DISTRIBUTION` (§2 Signal A), so the surface they want is a strict subset.
- C already publishes `direction_bias ∈ {-1, 0, +1}` per TF — that is **Signal B** of the MTF design, with no extra computation needed.
- C does **not** currently publish a calibrated `regime_confidence` — it produces a `confidence` field on a 0–100 scale derived from rule-fired heuristics (e.g. `55 + min(30, vol_slope * 30)`). The MTF design uses 0–1 confidence with an eligibility floor of 0.65 (= 65 on C's scale). Mapping is `c_normalized = c_raw / 100`, and the floor at 65 is reachable; the small gap is calibration, not architecture.
- C does **not** currently publish Signal C (volatility regime `low/normal/high` per TF). It internally computes `_atr_percentile(...)` per TF; exposing that as a third output field is a ~20-line change.
- C **already runs at 5-minute cadence** in production via `market_forward_analysis_loop` and its output is already serialized by `telegram_renderer`/`projection_v2`. Adding a `phase_state` block to `dashboard_state.json` (per MTF design §6) is wiring, not classification.

**Pros:**
- No model retrain, no new ML.
- No taxonomy invention — design's MARKUP/MARKDOWN/RANGE is exactly C's output.
- Per-TF independence guaranteed by construction (each TF's classification reads only that TF's bars; `build_mtf_phase_state` does no cross-TF feature leak).
- Already replay-validatable on `data/forecast_features/full_features_1y.parquet` since `run_phase_history` walks the historical OHLCV and emits per-bar per-TF labels — directly usable for the MTF design's §7.1 acceptance criteria.

**Cons / required adjustments:**
- Confidence calibration (0–100 → 0–1 + threshold-fit). 1-2 days.
- Add Signal C (vol regime) as exposed field. ~½ day, 20 LOC + tests.
- C uses 1-bar-per-call (not bar-by-bar history); the persistence-tracker (`MTF_DISAGREEMENT` §3.4) lives downstream in the disagreement detector, not in C itself — fine, but means C's output cannot itself say "regime stable for N bars at this TF." Either ride C's existing `bars_in_phase` (already there) or maintain that state in the new disagreement service. Trivial design choice.
- C uses `swing_n=2` swings on 15m/1h and `swing_n=3` on 4h/1d. Operator should sanity-check these are not too noisy on 15m before the MTF detector starts gating real alerts.
- C's range-detection threshold (`range_pct=4.0` over 20 bars) and direction-trigger heuristics were tuned for the forward-analysis brief use, not the disagreement use. Behaviour may need calibration before alerting goes live (this matches MTF design §9 #3 — already flagged as expected work).

**Effort estimate:** **3-5 days** to (a) calibrate confidence to 0–1 with operator-validated 0.65 floor, (b) expose vol_regime field, (c) add `phase_state` block to `dashboard_state.json`, (d) write the disagreement detector itself (`MTF_DISAGREEMENT` design §3 — that's a separate TZ but is the natural follow-on). These three days are *only* the prereq the design called "Step 1 of §8" (`TZ-MTF-CLASSIFIER-PER-TF`). The disagreement core (Step 3) and wire-up (Steps 4-5) remain separate-scope TZs.

---

## §3 Recommended approach

**Recommendation: Option E — adopt the existing `phase_classifier`. Effort 3-5 days for the prereq; per-TF independent classification is effectively done.**

**Reasoning:**

1. **The premise of options A/B/C/D is empirically wrong for this codebase.** The brief assumed the per-TF capability didn't exist and the work was to manufacture it. Reading the source shows it does exist, runs in production, and uses the design's own adopted taxonomy.
2. **The MTF design itself implicitly chose this path** (§9 #1 of `MTF_DISAGREEMENT_v1` says "Cost estimate: 1-2 weeks to extend the classifier, depending on whether we reuse `RegimeForecastSwitcher` per-TF or build a parallel classifier matching `core/orchestrator/regime_classifier.py`'s primary regime taxonomy"). Re-reading that with full code context: the first horn ("reuse RegimeForecastSwitcher") was a **mis-naming** — the actual reusable classifier is `phase_classifier.py`, and reusing it costs ~3-5 days, not 1-2 weeks.
3. **Anti-recommendation:** do **not** extend Classifier A (`core/orchestrator/regime_classifier.py`). Doing so would either (a) fork its rule chain four times (inflates a 600-LOC module to ~2 400 LOC of brittle hand-coded duplication) or (b) decompose its multi-TF features (Option A), which produces strictly worse signals than C already provides. Resist the temptation to extend A simply because A is what advise_v2 currently consumes — that consumption pattern is a pipeline coupling, not an MTF-classification requirement.
4. **Anti-recommendation:** do **not** train a new ML classifier (Options B/D). The taxonomy match alone (MARKUP/MARKDOWN/RANGE both in C and in regulation) makes this gratuitous; ML adds calibration debt, training-data debt, and OOS validation overhead the project already paid for and does not need to repay.

---

## §4 Implementation TZ outline (rough scope) — for the Option E prereq only

Title: **`TZ-MTF-CLASSIFIER-PER-TF-WIRE` (replacement for `MTF_DISAGREEMENT_v1` §8 Step 1)**

Scope:
1. **Confidence calibration.** Normalize `phase_classifier.classify_phase().confidence` from 0–100 to 0–1. Verify the 0.65 eligibility floor (= 65 on raw scale) corresponds to operator-sensible "we trust this label." Run `run_phase_history` over the 1-year frozen OHLCV; histogram the confidence distribution per TF; report `% bars below 0.65` per TF. If a TF (likely 15m) gets >50 % of bars suppressed by the floor, raise to operator before threshold finalization. Output: `confidence_norm` field added to `PhaseResult`.
2. **Volatility regime field.** Expose `_atr_percentile(...)` as a third output field on `PhaseResult` (`vol_regime ∈ {"low", "normal", "high"}` with thresholds from MTF design §2 Signal C). ~20 LOC + a test that exercises each branch on synthetic data.
3. **Taxonomy contraction option (operator decision).** For the MTF disagreement detector, expose a field `regime_label_3state ∈ {MARKUP, MARKDOWN, RANGE}` that maps the 6-Phase enum down to the 3 the design uses (`ACCUMULATION → RANGE`, `DISTRIBUTION → RANGE`, `TRANSITION → RANGE` per current design §2; or alternatively expose ACCUMULATION/DISTRIBUTION as informational only for dashboard, not for disagreement detection). Operator preference required.
4. **`phase_state` block in `dashboard_state.json`.** Already partially populated by `market_forward_analysis_loop`; serialize per-TF `{label_3state, confidence_norm, direction_bias, vol_regime, bars_in_phase}` block under `phase_state` top-level. State_builder change ~30 LOC + golden-snapshot test update.
5. **Tests.** Reuse `core/tests/test_market_forward_analysis.py` golden cases; add per-TF independence test (assert `classify_phase(df_15m, "15m")` does not reach into `df_1h` etc.); add confidence-floor histogram test as a guardrail.
6. **Replay-validation harness preparation.** `run_phase_history` already exists; thin wrapper to dump `(ts, tf, label, confidence_norm, direction_bias, vol_regime)` tuples into a parquet for the disagreement detector's §7.1 acceptance to consume. ~½ day.

Effort: 3-5 working days, single thread, no operator-blocking sub-tasks. Outputs feed directly into `MTF_DISAGREEMENT_v1` §8 Steps 2-6 unchanged.

---

## §5 Risks and unknowns

**Honestly flagged — what this investigation did not fully resolve.**

1. **Confidence-calibration unknown until the histogram lands.** The 0.65 floor on a 0–1 scale corresponds to 65 on `phase_classifier`'s raw 0–95 cap. Heuristics like `55 + min(30, vol_slope * 30)` produce a non-uniform distribution; without running `run_phase_history` over the full year I cannot promise the floor isn't aggressively cropping (esp. on 15m, which uses `swing_n=2`, more swings, possibly noisier confidence). **Mitigation:** the calibration step in §4 #1 above. Risk class: medium. Detection: at the prereq's first deliverable.

2. **15m TF noise.** `phase_classifier` has been operationally validated as `1d / 4h / 1h` (e.g. `run_phase_history`'s default signature accepts only those three; `loop.py:117` iterates over whatever `phase_state.phases` contains). I read no evidence of 15m being run through `run_phase_history` in production. Whether 15m's swing structure with `swing_n=2` produces the operator-sensible labels at that cadence is empirical. **Mitigation:** include 15m in the calibration histogram; if too noisy, fall back to MTF design covering only `1d / 4h / 1h` (drop 15m as Signal A source while keeping it as Signal B/C). Risk class: medium.

3. **Coexistence of two live regime taxonomies.** Classifier A (`core/orchestrator`) and Classifier C (`phase_classifier`) **both run in production**, on different cadences, emitting **incompatible label sets**. Today they don't conflict because they feed disjoint downstream consumers (A → advise_v2 / dashboard regime block; C → market_forward_analysis loop / telegram session brief). After Option E, the dashboard and decision layer will show *both* a "regime" (from A) and a "phase_state" (from C). This is honest reporting, but the operator will ask "which is the regime?" Resolution is a UX decision, not a feasibility blocker — flag for operator. Listed in `MTF_DISAGREEMENT_v1` §9 #2 as well. Risk class: low (cosmetic), high (perceived).

4. **Persistence-tracker placement.** `MTF_DISAGREEMENT_v1` §3.4 wants persistence in LTF bars (12 bars at 15m = 3 h). `phase_classifier` is called every 300 s by `loop.py`, which is 5-min ticks; 12 ticks ≈ 1 h, not 3 h. Either the disagreement detector tracks persistence in its own bar-aware ring buffer (already designed §3.4), or `phase_classifier` is upgraded to bar-driven invocation. The latter is bigger — recommend the former. Not a blocker, just a decision the disagreement-detector TZ needs to make explicit.

5. **`market_forward_analysis` deprecation status partly unclear.** `docs/CONTEXT/DEPRECATED_PATHS.md` mentions the `market_forward_analysis` package multiple times in deprecation context (DP-002 references `projection_v2.py`, DP-004 references `phase_classifier.py`'s `n=3` swing change). I read the entries — DP-004 is a **parameter change** within `phase_classifier`, not a deprecation of the file. DP-002 deprecates `whatif_v3` standalone sim, with a side-mention of `market_forward_analysis/feature_pipeline.py` as a *consumer* of its data. **Conclusion: `phase_classifier.py` is not deprecated; only its old `swing_n=3` parameter is.** I am ~90 % confident on this read. **Mitigation:** the prereq TZ's first action should be to confirm with operator that `market_forward_analysis_loop` is intended to remain live, since Option E load-bears on that loop continuing to drive `phase_classifier`. If the loop is being decommissioned (e.g. in favor of Decision Layer absorbing its functions), Option E's "already runs in production" claim weakens — the classifier itself still works as a library, but the cadence story changes.

6. **MTF design's mis-naming of the source classifier.** `MTF_DISAGREEMENT_v1` §1 names `services/market_forward_analysis/regime_switcher.py` as "current MARKUP / MARKDOWN / RANGE classifier." It is not — it is a forecast router consuming a regime label as input. The classifier producing those labels for `regime_switcher` to consume is `phase_classifier.py` (via `loop.py` → `regime_switcher.forecast()` indirectly through `projection_v2`/setup_bridge). This is a documentation bug, not a code bug; this report names the right module. Worth fixing in `MTF_DISAGREEMENT_v1` §1 in a follow-up edit, otherwise future readers will be sent to the wrong file.

---

## CP report

- **Output path:** [`docs/DESIGN/MTF_FEASIBILITY_v1.md`](MTF_FEASIBILITY_v1.md)
- **Recommended option:** **E — adopt existing `services/market_forward_analysis/phase_classifier.py`** (Options A/B/C/D all rejected; B/D unnecessary, A/C produce inferior signal vs. existing C path).
- **Effort estimate for recommended option:** **3-5 working days** for the prereq TZ (confidence normalization + vol_regime exposure + dashboard wire + replay harness). Disagreement-detector core is a separate downstream TZ.
- **Critical risks identified:** (a) 15m confidence may suppress >50 % of bars under the 0.65 floor — calibration histogram needed before threshold finalization; (b) coexistence of Classifier A and Classifier C taxonomies will surface an operator UX question ("which regime is *the* regime"); (c) `market_forward_analysis_loop` continued-life assumption needs operator confirmation; (d) MTF design §1 names the wrong source file — documentation fix recommended.
- **Anti-drift compliance:**
  - ✅ No code changes (read-only investigation).
  - ✅ Effort estimates grounded in line-counts of the actual changes (~50 LOC of additions across `phase_classifier.py`, `state_builder.py`, tests).
  - ✅ Recommendation tracks evidence; the brief's options A-D were assessed on their own terms before introducing E, and E is justified by code that exists in `git log` and runs in production.
  - ✅ Honest §5: I flagged five real unknowns including one I'm only 90 % confident on (deprecation read).
- **Compute time:** ~25 minutes of investigation + writing.
