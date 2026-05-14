# DEPRECATED PATHS
# Назначение: consolidated record of approaches that were tried and abandoned.
# Читать перед началом новой TZ чтобы не повторить то что уже не работает.
# Обновлять при каждом kill/deprecate решении.

---

## DP-001 — K-factor calibration (single scalar K_SHORT / K_LONG)

**Status:** DEPRECATED 2026-05-02
**Was used in:** `services/calibration/runner.py`, GinArea SL/TP sizing
**Replacement:** Per-phase ensemble weights (`projection_v2.py` horizon weights)

**What it was:**
Single multiplicative scalar applied uniformly to position sizing:
`SL = entry_dist * K_SHORT` / `TP = entry_dist * K_LONG`

**Why abandoned:**
- K_LONG CV=24.9% (TD-dependent — varies with trend day fraction)
- K_SHORT CV=3.0% (stable but insufficient alone)
- Single scalar ignores phase/regime — loses edge in MARKDOWN, TRANSITION
- GinArea backtests: LONG ground truth = −0.5 BTC/year (K scaling does not help)

**What replaced it:**
- `services/market_forward_analysis/projection_v2.py` — 5-signal ensemble with per-horizon weights
- Phase-aware sizing still TODO (DEBT-04)

**Do NOT:**
- Re-introduce per-pair K scalars without multi-year multi-regime validation
- Treat K_LONG as stable — it is structurally TD-dependent

---

## DP-002 — WHATIF-V3 full rebuild simulation

**Status:** KILLED 2026-05-03 (Brier ceiling confirmed)
**Was used in:** `data/whatif_v3/`, `services/market_forward_analysis/feature_pipeline.py`
**Replacement:** Whatif data kept as feature input only; no standalone sim rebuild

**What it was:**
Full simulator rebuild using whatif-v3 OHLCV as ground truth for outcome labeling.
Goal: use 1m whatif bars as alternate price path to label "what would have happened."

**Why killed:**
- Feature ceiling confirmed at Brier ~0.257 on 105k bars × 44 features
- Systematic bearish bias in positioning/structural signals during 2026 bull run
- Adding whatif ground truth does not solve the rule-based signal inversion problem
- Sim rebuild = 3-5h operator compute with no expected improvement above ceiling

**What replaced it:**
- Whatif 1m bars are still ingested as microstructure feature inputs (volume, candle metrics)
- Brier CP3 result sent to operator for GO/NO-GO; further signal development TBD

**Do NOT:**
- Schedule another full whatif sim rebuild without first fixing signal inversion problem
- Treat 0.25 Brier as "no signal" — it's above random, but below operator threshold

---

## DP-003 — Operator-action reactive playbook (Playbook v1/v2)

**Status:** DEPRECATED 2026-05-03
**Was used in:** `docs/PLAYBOOK.md`, `data/countertrend_research/`, early TZ-COUNTERTREND-*
**Replacement:** Playbook v3 with early-intervention branches (`docs/PLANS/`, MAIN coordinator)

**What it was:**
Reactive decision tree: "if operator sees X signal → take action Y."
Operator would watch Telegram alerts and react to each signal individually.

**Why deprecated:**
- Anti-pattern: operator reacts to noise, not to state
- Caused "INERT-BOTS confusion" (see DRIFT_HISTORY.md DP-DRIFT-002)
- Playbook v1/v2 had no phase awareness — same action regardless of MARKUP/MARKDOWN
- 1ffdc12 research confirmed playbook vs real actions diverged significantly

**What replaced it:**
- Playbook v3 with early-intervention branch logic (commit db8f064)
- Phase-aware routing: MARKUP → different branch than MARKDOWN/RANGE
- Operator acts on daily brief, not on per-alert reaction
- MAIN coordinator owns daily brief generation (scripts/main_morning_brief.py)

**Do NOT:**
- Add new reactive rules to old playbook files
- Reference `docs/PLAYBOOK.md` as current — it is archived
- Build alert handlers that expect immediate operator reaction

---

## DP-004 — n=3 swing structure check in phase classifier

**Status:** DEPRECATED 2026-05-02 (changed to n=2)
**Was in:** `services/market_forward_analysis/phase_classifier.py`
**Lines:** `_hh_hl(highs, n=3)`, `_lh_ll(lows, n=3)`

**Why deprecated:**
- n=3 requires 3 consecutive higher-highs / lower-lows
- Real 1d data rarely produces 3 clean pivots → 90%+ bars classified TRANSITION
- n=2 matches actual market structure (2 swings = confirmed direction)

**What replaced it:**
- `n=2` in both `_hh_hl` and `_lh_ll` calls in `build_mtf_phase_state`

**Do NOT:**
- Revert to n=3 without A/B test showing improvement on real data

---

## DP-005 — 1% direction threshold in calibration

**Status:** DEPRECATED 2026-05-03 (changed to 0.3%)
**Was in:** `services/market_forward_analysis/calibration.py`
**Was:** `_DIRECTION_THRESHOLD_PCT = 1.0`

**Why deprecated:**
- At 1% threshold: 96% of 1h bars classified "range" → binary classification trivial/useless
- Training data severely imbalanced: 4% directional vs 96% range
- Brier score misleadingly low (predicting range always gives low Brier)

**What replaced it:**
- `_DIRECTION_THRESHOLD_PCT = 0.3` → ~17% up / 17% down / 67% range at 1h
- Gives meaningful binary split for signal evaluation

**Do NOT:**
- Use >0.5% threshold for 1h bars without checking class balance first
- Mistake low Brier at 1% for "good calibration"

---

## DP-006 — Trend-following features in unified forecast model

**Status:** REJECTED 2026-05-03 (Variant B from CP3 gate)
**Was proposed as:** Option B in CP3 GO/NO-GO (add EMA crossovers, momentum to fix signal inversion)
**Replacement:** Variant C hybrid — regime-conditional models (separate model per regime)

**What it was:**
Adding trend-following features (EMA crossovers, momentum signals) to the *unified* forecast model
to counter systematic bearish bias of contrarian signals in bull market conditions.

**Why rejected:**
- Strong overfit risk: training on 1y bull data (2025-2026) makes trend features bullish
- Trend features would fail in MARKDOWN, RANGE, DISTRIBUTION regimes
- Fixes symptom (wrong direction bias) not root cause (one model for all regimes is wrong)
- Operator decision 2026-05-03: "полноценная система что бы понимало и просчитывало все режимы рынка"

**What replaced it:**
- Regime-conditional models: separate calibrated model per regime (MARKUP, MARKDOWN, RANGE, DISTRIBUTION)
- Each regime's model trained on episodes of *that* regime only
- Auto-switching engine selects model based on real-time phase classification
- See WEEK_2026-05-04_to_2026-05-10.md ETAPs 2.1-2.3

**Do NOT:**
- Add trend-following features to the shared/unified forecast pipeline
- Propose "add momentum" as a fix when calibration fails — first check regime distribution
- Train one model on mixed-regime data and expect it to generalize
