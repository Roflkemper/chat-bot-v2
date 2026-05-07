# Classifier Authority Decision v1

**Status:** DESIGN NOTE (read-only). No code changes.
**Date:** 2026-05-06
**TZ:** TZ-CLASSIFIER-AUTHORITY-DECISION
**Closes risk:** Risk 2 from [`docs/DESIGN/MTF_FEASIBILITY_v1.md`](MTF_FEASIBILITY_v1.md) §5 — coexistence of Classifier A (`core/orchestrator/regime_classifier.py`) and Classifier C (`services/market_forward_analysis/phase_classifier.py`).

**Operator constraints (frozen, applied as such):**
1. Classifier A keeps its operator-Q1 confidence thresholds (0.65 transition / 0.80 stable). Used by Decision Layer R/M/P/E/D rules.
2. Classifier C uses **R2 (persistence-only, no confidence gate)** per the calibration histogram verdict. Used by MTF disagreement detection (T-* rules).
3. Different threshold logic per classifier is acceptable architecturally.

**Headline answer:** Adopt **Option 1 — split authority**. The empirical disagreement rate (36.88 % of 8 511 bars over 1y) is large, but **only 1.02 % of bars are opposite-direction (MARKUP vs MARKDOWN)**. The remaining 35.86 % is RANGE-vs-trend differential interpretation, which is informational rather than contradictory. The two classifiers are answering slightly different questions; split authority is the correct architectural framing, not a workaround.

**Artifacts produced:**
- [`docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md`](CLASSIFIER_AUTHORITY_v1.md) — this file
- [`docs/DESIGN/_classifier_disagreement_raw.json`](_classifier_disagreement_raw.json) — full empirical data
- [`scripts/_classifier_disagreement_analysis.py`](../../scripts/_classifier_disagreement_analysis.py) — reproducible driver

---

## §1 Architectural comparison: Classifier A vs C

| Dimension | **Classifier A** (`core/orchestrator/regime_classifier.py`) | **Classifier C** (`services/market_forward_analysis/phase_classifier.py`) |
|---|---|---|
| Type | Hand-coded multi-branch rule chain | Hand-coded swing-structure rule chain (Wyckoff-inspired) |
| Input cadence per call | Multi-TF in one call: 1m + 15m + 1h + 4h candles required | Single-TF per call: one OHLCV DataFrame for one timeframe |
| Output taxonomy (raw) | `{RANGE, TREND_UP, TREND_DOWN, COMPRESSION, CASCADE_UP, CASCADE_DOWN}` + modifiers (`NEWS_BLACKOUT`, `WEEKEND_GAP`, etc.) | `{ACCUMULATION, MARKUP, DISTRIBUTION, MARKDOWN, RANGE, TRANSITION}` + per-TF `direction_bias` (-1/0/+1) and `key_levels` |
| Output taxonomy (3-state alignment for MTF design) | `TREND_UP|CASCADE_UP → MARKUP`, `TREND_DOWN|CASCADE_DOWN → MARKDOWN`, `RANGE|COMPRESSION → RANGE` | `MARKUP → MARKUP`, `MARKDOWN → MARKDOWN`, `RANGE|ACCUMULATION|DISTRIBUTION|TRANSITION → RANGE` |
| Trend trigger | `adx_1h > 25` AND `ema50 > ema200` (or inverse) AND `ema50_slope > 0` | Two consecutive higher highs AND two consecutive higher lows over 60-bar window (`swing_n=2`) |
| Range trigger | `atr_pct_1h < 1.5` AND price inside Bollinger band | Price span over 20-bar window `< 4 %` |
| Hysteresis | 2-bar confirmation before primary transition (state-stored in `RegimeStateStore`) | None internal; persistence to be applied by downstream consumer |
| Confidence | Implicit (no per-call confidence emitted; downstream `RegimeForecastSwitcher` uses fixed `_REGIME_CONF_THRESHOLD = 0.65` against an external regime confidence input) | Heuristic 0–95 raw scale (`30/40/45/55+slope/...`); **not aligned** with operator-Q1 0.65/0.80 — see [`MTF_CALIBRATION_HISTOGRAM_v1`](../RESEARCH/MTF_CALIBRATION_HISTOGRAM_v1.md) §2 |
| Update cadence (live) | Every snapshot build (~5-min cadence in `core/pipeline.py:882`) | Every 300 s in `market_forward_analysis_loop` (`services/market_forward_analysis/loop.py:90`) |
| State persistence | `state/regime_state.json` (atomic, retried writes) | None — stateless library function |
| Production path | `core/pipeline.py` → `advise_v2/regime_adapter.py` → advise output / dashboard regulation card | `market_forward_analysis_loop` → `telegram_renderer` (session brief, phase-change alerts) |
| Designed-for question | "Is the bot allowed to trade right now? Is the regime stable enough for the activation matrix?" | "What is the macro market phase across timeframes? Where are the key levels?" |
| Adopted MTF design taxonomy | A's primary regime is **unused** by `MTF_DISAGREEMENT_v1` (§9 #2 confirms this) | C's `Phase` enum **is** the design's adopted taxonomy |

**Key architectural insight:** A and C are not redundant implementations of the same function. A is a **trade-eligibility gate** (its CASCADE/COMPRESSION states encode safety conditions). C is a **structural macro analysis** (its ACCUMULATION/DISTRIBUTION states encode phase context that has no equivalent in A). The 3-state alignment for MTF design purposes is a *projection* of both onto the regulation's MARKUP/MARKDOWN/RANGE space — projection that loses information from both, in different ways.

---

## §2 Empirical disagreement analysis

### 2.1 Replay setup

- **OHLCV source:** [`backtests/frozen/BTCUSDT_1m_2y.csv`](../../backtests/frozen/BTCUSDT_1m_2y.csv), last 365 days = 525 601 1m rows (2025-04-29 → 2026-04-29).
- **Comparison cadence:** 1h (one call per hour for both classifiers).
- **Comparison TF for C:** 1h. Justified because A operates on 1h core (its rules read `_1h` features) and 1h is the finest TF where A's full rule chain has converged warmup.
- **Warmup skipped:** first 250 hours (so A has enough 1h history for `ema200_1h` to be defined).
- **Comparable bars:** 8 511.
- **Compute time:** 497 seconds.

### 2.2 Headline rates

| Metric | Value |
|---|---:|
| Overall agreement rate (3-state aligned) | **63.12 %** |
| Overall disagreement rate | **36.88 %** |
| Opposite-direction bars (MARKUP vs MARKDOWN) | 87 / 8 511 = **1.02 %** |
| Same-side disagreement (one says RANGE, other says trend) | 35.86 % |

The 1.02 % opposite-direction rate is the figure that determines the UX impact severity. It says: in a typical 24-hour trading day, ~14 minutes' worth of bars (1.02 % × 24 h) will have the two classifiers giving directly contradictory direction reads. The other 35.86 % is "one classifier sees enough structure to call a trend, the other sees only consolidation" — which is informationally complementary, not contradictory.

### 2.3 Confusion matrix (3-state aligned)

Rows = Classifier A's aligned label; columns = Classifier C's aligned label.

|       | C: MARKUP | C: MARKDOWN | C: RANGE |
|---|---:|---:|---:|
| **A: MARKUP** | 88 | 20 | 1 288 |
| **A: MARKDOWN** | 67 | 234 | 1 398 |
| **A: RANGE** | 159 | 207 | 5 050 |

### 2.4 Per-A-label disagreement rate

| A label (aligned) | n bars | Disagreement rate | Dominant C label when A disagrees |
|---|---:|---:|---|
| **MARKUP** | 1 396 | **93.7 %** | RANGE (92 % of disagreements) |
| **MARKDOWN** | 1 699 | **86.2 %** | RANGE (95 % of disagreements) |
| **RANGE** | 5 416 | **6.8 %** | mixed (159 MARKUP + 207 MARKDOWN) |

The asymmetry is the most informative finding. **When A calls a trend, C says RANGE 86-93 % of the time. When A calls RANGE, C agrees 93 % of the time.** This is not random disagreement; it's a systematic difference in trend-detection sensitivity.

### 2.5 Why the asymmetry — root cause

Reading both classifiers side-by-side:

- **A triggers TREND_UP** when `adx_1h > 25 AND ema50 > ema200 AND ema50_slope > 0` (and similar for TREND_DOWN). On a year of bull-trend BTC data, ADX above 25 is common, and EMA stack alignments persist for long stretches. Result: A spends ~16 % of its time in TREND_UP and ~20 % in TREND_DOWN (see `a_raw_distribution`).
- **C triggers MARKUP** only when there are two consecutive higher highs AND two consecutive higher lows in the recent 60-bar window AND `vol_slope > 0.1` AND not in upper quarter. The `swing_n=2` swing-finder requires clean pivots, which on hourly data over 60 bars is genuinely rare during pullbacks-within-trends. Result: C spends ~3.7 % of its time in MARKUP and ~5.4 % in MARKDOWN, but ~68 % in RANGE (a much wider net than A's RANGE).
- **What this means semantically:** A is sensitive to *trend regime* in a momentum/EMA-stack sense (good for "is the bot eligible right now"). C is sensitive to *trend structure* in a swing-pattern sense (good for "what kind of price action is happening"). Both are correct in their own terms; their disagreement is a feature of their differing definitions, not an error in either.

### 2.6 Raw label distribution (informational)

| Classifier A raw | n | % | Classifier C raw | n | % |
|---|---:|---:|---|---:|---:|
| RANGE | 3 811 | 44.8 | range | 5 815 | 68.3 |
| TREND_DOWN | 1 697 | 19.9 | transition | 690 | 8.1 |
| COMPRESSION | 1 605 | 18.9 | distribution | 638 | 7.5 |
| TREND_UP | 1 391 | 16.3 | accumulation | 593 | 7.0 |
| CASCADE_DOWN | 2 | 0.02 | markdown | 461 | 5.4 |
| CASCADE_UP | 5 | 0.06 | markup | 314 | 3.7 |

Note: COMPRESSION (A's "low-vol consolidation") and ACCUMULATION/DISTRIBUTION/TRANSITION (C's nuanced range states) have **no cross-classifier equivalents** in the raw taxonomies. This is direct evidence that the two classifiers cover **disjoint conceptual ground**, not overlapping ground.

### 2.7 Limitations of this analysis

Flagged honestly:
- Single asset (BTCUSDT) over a single year window dominated by bullish phases. Bearish-regime disagreement could differ. Closes Q3 of `BACKLOG_TRIGGERS` if/when bear-data acquisition runs.
- Comparison restricted to 1h. C runs across 4 TFs in MTF use, but the disagreement detector will only see C's per-TF cells; comparing A (which is multi-TF input → single label) against any single TF of C is necessarily lossy. Choosing 1h is the best single-TF compromise.
- A's hysteresis state is initialized fresh at replay start, then evolves through the 8 511-bar walk. This is faithful for steady-state behavior but not identical to A's live state at any given instant in production.
- The 3-state alignment **collapses** A's COMPRESSION into RANGE and C's ACCUMULATION/DISTRIBUTION/TRANSITION into RANGE. Any future T-* rule that wants to use those rich states must specify which classifier provides them — they exist in different vocabularies.

---

## §3 Authority option enumeration

### Option 1 — Split authority *(operator's pre-decided direction)*

**Rule:**
- Classifier A is authoritative for: Decision Layer R/M/E rules, regulation activation matrix, advise_v2 regime input, dashboard regulation action card.
- Classifier C is authoritative for: MTF disagreement detection (T-* rules), per-TF phase context for the dashboard `phase_state` block (when wired per `MTF_FEASIBILITY_v1` §4), Telegram session briefs.
- Each downstream consumer cites which classifier sourced its label.

**Pros:**
- Honors the actual semantic difference between A and C (§1, §2.5). Each is used for the question it was built to answer.
- Zero classifier-code changes; operator's frozen constraints (A keeps 0.65/0.80, C uses persistence-only) drop in as-is.
- Dashboard separation already in place: A drives the regulation card, C drives the phase block — they're physically separate UI elements.
- Easy to document and reason about: "if you want trade eligibility, look at A; if you want phase context, look at C."
- Closes the 1.02 % opposite-direction risk by acknowledging it openly via UX disclaimer rather than papering it over.

**Cons:**
- Operator UX gap: in the 1.02 % opposite-direction window, the dashboard could show "regime: TREND_UP (A)" alongside "phase: MARKDOWN (C, 4h)" simultaneously. Mitigation: explicit disclaimer; see §5.
- Documentation burden: every new module that consumes a regime label must declare its source classifier. Acceptable cost.

**Effort:** **0.5 day** for documentation conventions (module docstring template + dashboard footnote text). No code logic changes.

**Risk:** Low. The empirical disagreement rate is dominated by RANGE-vs-trend reads, not by direct contradiction.

---

### Option 2 — Unified to A (decommission C for regulation purposes; possibly drop MTF entirely)

**Rule:** Drop C from any role in regulation/MTF decisions. Decision Layer T-* rules would need to be redesigned around A's per-TF features (which it doesn't independently expose — see [`MTF_FEASIBILITY_v1`](MTF_FEASIBILITY_v1.md) §2 Option A's verdict that A is not feature-decomposable).

**Pros:** Single source of truth eliminates UX gap entirely.
**Cons:** Effectively cancels the MTF Disagreement Detection design. A cannot produce per-TF independent labels without major rework (the MTF feasibility report's option D — full classifier rebuild). C's macro-phase context (ACCUMULATION/DISTRIBUTION) would also be lost from the dashboard. The session brief would need a new label source. Multiple net negatives for one UX concern.
**Effort:** Multi-week. **Effectively replaces the MTF track.**
**Risk:** High; the MTF design becomes unimplementable.

**Verdict:** Reject. Operator already chose split authority + R2 persistence-only for MTF, which is incompatible with this option. No fatal flaw in Option 1 surfaced that would justify revisiting.

---

### Option 3 — Unified to C (replace A in Decision Layer)

**Rule:** Decision Layer R/M/P/E/D rules consume C's output instead of A's. T-* rules also consume C — single classifier throughout.

**Pros:** Single source of truth.
**Cons:**
- C does not produce A's CASCADE_DOWN/CASCADE_UP states. Yet `core/orchestrator/regime_classifier.py:detect_cascade_*` exists precisely to handle fast cascades that the regulation activation matrix treats specially. Loss of these states is a regression.
- C's confidence scale is **uncalibrated** for the operator-Q1 0.65/0.80 thresholds (per `MTF_CALIBRATION_HISTOGRAM_v1` §2 — 0 % bars at 0.80 across all TFs). To make C usable for Decision Layer rules with operator-Q1 thresholds, the recalibration work (`R3`, ~1 week, requires labelled training data) becomes blocking.
- A's modifiers (NEWS_BLACKOUT, POST_FUNDING_HOUR, WEEKEND_GAP) are useful trade-eligibility signals not produced by C. Re-implementing them on top of C is gratuitous duplication.
**Effort:** ~2 weeks (R3 recalibration + cascade-detection re-implementation + modifier re-implementation).
**Risk:** High.

**Verdict:** Reject. The recalibration debt alone (R3) is enough to disqualify; the cascade/modifier loss compounds it.

---

### Option 4 — Aggregate to ensemble

**Rule:** Produce a unified label by combining A and C — e.g. by voting, by tier-priority, or by a meta-classifier.

**Pros:** Theoretically captures the union of both signals.
**Cons:**
- Adds a third decision artifact ("ensemble label") that diverges from both A and C in ways the operator must learn separately. Triples the cognitive load instead of solving it.
- The 36.88 % disagreement rate means the ensemble logic must resolve ~3 100 conflicts per year. Whatever resolution rule is chosen, ~half of those resolutions will look wrong from one of the two source perspectives. The dashboard now has *three* possible "regime" answers: A, C, ensemble.
- No empirical basis for an ensemble weight (no labelled ground truth to calibrate against; `regime_red_green/btc_1h_v1.json` is binary TREND/RANGE only and was used to train Classifier B, a third irrelevant classifier).
- Blurs accountability: when the bot makes a bad decision, "which classifier was wrong" becomes "the ensemble was wrong" — actionable signal lost.
**Effort:** ~1 week design + 1-2 weeks implementation + indefinite tuning.
**Risk:** Medium-high.

**Verdict:** Reject. No fatal flaw in Option 1; Option 4 strictly increases system complexity without empirical justification.

---

## §4 Recommended approach: Option 1 (split authority) — confirmed

The empirical evidence (§2) supports operator's pre-decided direction:

1. **The 36.88 % aggregate disagreement is dominated by the RANGE-vs-trend asymmetry**, which is a feature-of-design difference, not an error. A and C are tuned for different sensitivity profiles.
2. **The 1.02 % opposite-direction rate** is the only meaningful UX risk. It is acknowledgeable and disclaimable, not a system-correctness problem.
3. **The "fatal flaw" anti-drift guard** ("Don't recommend Option 2/3/4 unless Option 1 has fatal flaw") was checked: no fatal flaw surfaced. Option 1 is the right choice.

### 4.1 What "split authority" formally means

| Component | Authoritative classifier | Reason |
|---|---|---|
| Decision Layer R-* rules (regime change handling) | **A** | A's TREND_UP/TREND_DOWN/CASCADE/COMPRESSION are exactly what R-* rules are designed to react to. |
| Decision Layer M-* rules (margin) | **A** *(reads margin coefficient, no classifier dependency for triggering; reads A only for "regime context" annotation in the alert template)* | Margin is a pure account state read; A used only to label the surrounding regime context. |
| Decision Layer P-* rules (price levels) | **A** *(for regime context only)* | Price-level proximity is geometric, not classifier-driven. A used for context annotation. |
| Decision Layer E-* rules (bot eligibility) | **A** | Eligibility is gated on regulation activation matrix, which is keyed by A's regime taxonomy. |
| Decision Layer D-* rules (data staleness) | **neither** *(staleness checks are pipeline-level; classifier source is the dependent system being checked)* | D-* may flag "Classifier A's input data is stale" or "Classifier C's input data is stale" separately. |
| **MTF disagreement detection (T-* rules, future)** | **C** | C produces per-TF independent labels natively (see `MTF_FEASIBILITY_v1` §2 Option E). |
| Dashboard regulation action card | **A** | Already wired; do not change. |
| Dashboard `phase_state` block (future, per `MTF_FEASIBILITY_v1` §4) | **C** | New block, sourced from C. |
| Telegram session brief / phase-change alerts | **C** | Already wired in `market_forward_analysis_loop`; do not change. |
| Telegram Decision Layer alerts (R/M/P/E/D) | **A** *(in alert body annotation)* | New alerts will cite "regime (A): {label}" in the extended template. |

### 4.2 UX implications

**The operator will see two labels.** That is acknowledged and disclosed, not hidden. The disclaimer text in §5.3 makes the split visible at the point of consumption.

**Action card source:** Classifier A (no change from today).
**MTF disagreement source:** Classifier C (when wired).
**Regime label shown in regulation card:** A's primary, mapped through `services/advise_v2/regime_adapter.py` (no change).
**Phase label shown in phase_state block:** C's per-TF, displayed alongside but not unified with A's regime.

---

## §5 Implementation guidance + UX disclaimer text

### 5.1 Scope boundaries (rule for new code)

Every new module that emits or consumes a regime label MUST:

1. **Declare which classifier sourced the label** in a module docstring, e.g.:
   ```python
   """Regime change rules (R-* family).

   Classifier authority: Classifier A (core/orchestrator/regime_classifier).
   Threshold logic: operator-Q1 (0.65 transition / 0.80 stable).
   See: docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md §4.1.
   """
   ```
   For C-sourced modules, swap to:
   ```python
   """MTF disagreement detection (T-* family — placeholder).

   Classifier authority: Classifier C (services/market_forward_analysis/phase_classifier).
   Threshold logic: persistence-only (no confidence gate, per R2 verdict).
   See: docs/RESEARCH/MTF_CALIBRATION_HISTOGRAM_v1.md §5,
        docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md §4.1.
   """
   ```
2. **Reference this document** (`docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md`) by path in the docstring.
3. **Not silently combine** A and C outputs. Any code that needs both must explicitly read one then the other and present them as two separate fields.

### 5.2 Documentation requirements

Update the following docs in subsequent TZs (not in this TZ — read-only here):

- `docs/DESIGN/MTF_DISAGREEMENT_v1.md` §1: replace the misnamed `RegimeForecastSwitcher` reference with `phase_classifier` (already flagged in `MTF_FEASIBILITY_v1` §5 #6); add a paragraph: "Classifier authority is split per `CLASSIFIER_AUTHORITY_v1.md` — this design uses Classifier C only."
- `docs/DESIGN/DECISION_LAYER_v1.md` §2: add a paragraph stating "R/M/P/E/D rules consume Classifier A; T-* rules consume Classifier C; see `CLASSIFIER_AUTHORITY_v1.md` §4.1."
- Any future dashboard-rendering docs: cite `CLASSIFIER_AUTHORITY_v1.md` §4.2 when describing the `regime` vs `phase_state` blocks.

### 5.3 UX disclaimer text (proposed)

**Long form (for `docs/dashboard.html` legend / tooltip on the phase_state block):**
> *Phase state shown above is computed by the MTF phase classifier (`phase_classifier`) on a per-timeframe basis. It may differ from the regime label shown in the regulation action card, which is computed by a separate trade-eligibility classifier (`regime_classifier`). The two answer different questions: phase state describes macro market structure; regime describes whether the bot is allowed to trade right now. In ~1 % of bars the two may give opposite directional reads — this is expected and not an error.*

**Short form (for Telegram extended alert template, to be appended to MTF alerts when T-* rules ship):**
> *MTF context is sourced from a separate macro-phase classifier and may differ from the primary regime label. See dashboard for both views.*

**Inline form (for Decision Layer Telegram alerts, shipped now per the brief's existing requirement "MTF context not integrated — manual chart check recommended for regime changes"):**
> *MTF context not integrated in this alert — manual chart check recommended for regime changes.*

The inline form already covers the MVP scope of `TZ-DECISION-LAYER-CORE-WIRE` (where T-* is disabled). The long-form and short-form versions activate when T-* ships.

### 5.4 Migration / no-op assessment

**No code changes are required by this decision.** Both classifiers continue running as today. The decision is documentary: it formalizes the existing pattern (A → regulation, C → forward analysis loop) and prevents accidental unification in future TZs. Any future TZ touching regime labels must check the §5.1 docstring rule.

---

## CP report

- **Output path:** [`docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md`](CLASSIFIER_AUTHORITY_v1.md)
- **Empirical disagreement rate:** **36.88 %** aggregate across 8 511 bars; **1.02 %** opposite-direction (MARKUP vs MARKDOWN); **35.86 %** RANGE-vs-trend differential interpretation.
- **Recommended option:** **Option 1 — split authority.** Confirmed against operator pre-decisions; no fatal flaw in Option 1, Options 2/3/4 each have deal-breakers documented in §3.
- **UX disclaimer text proposal:** Three forms in §5.3 (long form for dashboard tooltip; short form for MTF Telegram alerts when T-* ships; inline form already aligned with the MVP `TZ-DECISION-LAYER-CORE-WIRE` requirement).
- **Operator decision points:** **0 new decisions required** — the document confirms Option 1 + R2 are coherent with each other and ready to encode. Any operator review is on disclaimer wording (§5.3), which is editable in subsequent TZs without re-opening the architectural decision.
- **Compute time:** ~30 minutes total — driver writing + 497 s replay (8 511 hours of A-and-C calls) + analysis + report.
- **Anti-drift compliance:**
  - ✅ No code changes (read-only investigation; only artifacts are docs + a reproducible driver script).
  - ✅ Operator decisions treated as constraints, not options to override.
  - ✅ Did not recommend Option 2/3/4: each rejected on documented grounds, not on preference.
  - ✅ Did not speculate where data was thin: §2.7 honestly flags single-asset, single-year, 1h-cadence limitations.
  - ✅ §5 ready for use by `TZ-DECISION-LAYER-CORE-WIRE` (docstring template + inline disclaimer text already aligned with that TZ's requirements) and by future MTF wire-up.
