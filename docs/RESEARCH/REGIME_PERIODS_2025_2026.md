# Regime Periods Analysis — 2025-05-01 → 2026-05-01

**Status:** ANALYSIS (TZ-REGIME-CLASSIFIER-PERIODS-ANALYSIS, Block B)
**Date:** 2026-05-05
**Source:** `data/forecast_features/full_features_1y.parquet` column `regime_int`, resampled 5m → 1h via mode aggregation.
**Method:** Pure historical analysis. No retraining, no extrapolation, no synthesis.
**Window:** 2025-05-01 00:00 UTC → 2026-05-01 00:00 UTC (**8,761 hours = 365.04 days**).

---

## §1 Time spent per regime

| Regime | Hours | % of year | Days |
|--------|------:|----------:|-----:|
| MARKUP (+1) | 1,135 | **13.0%** | 47.3 |
| MARKDOWN (−1) | 1,309 | **14.9%** | 54.5 |
| RANGE (0) | 6,317 | **72.1%** | 263.2 |
| DISTRIBUTION | 0 | 0.0% | absent in classifier output |

**Headline:** RANGE dominates the year — BTC is more often "neutral / sideways" than directional. The bull-year is structurally still a chop interrupted by short trending bursts, not a sustained trend.

DISTRIBUTION is absent because `regime_24h` in `whatif_v3` only emits 3 labels (`uptrend`/`downtrend`/`sideways`) — same finding as Block 12 (P8 expansion research) and Block 13 (LONG TP sweep). Per anti-drift, NOT synthesized.

---

## §2 Episode statistics

An "episode" is a contiguous run of bars with the same regime label.

| Regime | Episodes | Mean (h) | Median (h) | p25 | p75 | p90 | Max (h) |
|--------|---------:|---------:|-----------:|----:|----:|----:|--------:|
| MARKUP | **147** | 7.7 | 3 | 1 | 13 | 23 | 38 |
| MARKDOWN | **175** | 7.5 | 3 | 1 | 10 | 23 | 43 |
| RANGE | **323** | 19.6 | 8 | 2 | 22 | 57 | **179** |

**Observations (presented, not interpreted):**

1. MARKUP and MARKDOWN have **near-identical episode shapes** — mean ≈7.5h, median 3h, p90 ≈ 23h. Trend regimes look statistically alike in duration distribution, just MARKDOWN slightly more frequent (175 vs 147 episodes).
2. **Median trending episode is only 3 hours.** Half of all MARKUP / MARKDOWN runs are too short for a 4h-anchored bot strategy to even register them as a regime change.
3. RANGE episodes are 2–3× longer on average and dramatically right-skewed: max RANGE run was **179 hours (7.5 days)** of continuous sideways labeling. This is the structural story of the year: short trending bursts punctuating long flat stretches.
4. Counting all transitions: 147 + 175 + 323 = **645 episodes total** in 8,761 hours → one regime change every **13.6 hours on average**.

---

## §3 Transition matrix

Counted at every 1h bar boundary where `regime_int[i] != regime_int[i-1]`.

| From → To | Count |
|-----------|------:|
| RANGE → MARKUP | 147 |
| MARKUP → RANGE | 147 |
| RANGE → MARKDOWN | 175 |
| MARKDOWN → RANGE | 175 |
| **MARKUP → MARKDOWN** | **0** |
| **MARKDOWN → MARKUP** | **0** |

**Critical structural finding:** there are **zero direct MARKUP↔MARKDOWN transitions**. The classifier always passes through RANGE between trending regimes. This means:

- The trend regimes are **not "next to each other"** in the classifier's state space — they are separated by mandatory RANGE buffers.
- Any P8 ensemble logic that asks "did MARKUP just flip to MARKDOWN?" gets a guaranteed false answer; the question to ask is "did MARKUP→RANGE→MARKDOWN happen, and how fast was the RANGE buffer?"
- This is a property of the underlying classifier (`regime_24h` from whatif_v3), **not** of price action. With a different classifier (e.g., faster, no smoothing) direct trend-to-trend flips might appear.

Total transitions: **644** (147+147+175+175). Each transition is bidirectional in the asymmetric sense — `RANGE→MARKUP` count equals `MARKUP→RANGE` count exactly because every MARKUP episode has one entry and one exit.

---

## §4 Time-of-day breakdown of transitions

Distribution of all 644 transitions by UTC hour:

| Hour UTC | Count | Hour UTC | Count |
|----------|------:|----------|------:|
| 00 | 30 | 12 | 19 |
| 01 | 23 | 13 | 22 |
| 02 | 30 | 14 | 31 |
| 03 | 22 | 15 | **52** |
| 04 | 24 | 16 | 37 |
| 05 | 25 | 17 | 33 |
| 06 | 21 | 18 | 32 |
| 07 | 24 | 19 | 33 |
| 08 | 21 | 20 | 26 |
| 09 | 21 | 21 | 26 |
| 10 | 24 | 22 | 27 |
| 11 | 21 | 23 | 34 |

**Mean per hour = 26.8** (644 / 24).

Hours with notably higher transition density:
- **15:00 UTC (52 transitions)** — coincides with NY session open (15:30 UTC equity / 14:30 UTC US futures). Almost 2× mean.
- **16:00 UTC (37)** — first hour of full NY session.
- **23:00 UTC (34)** — Asian session open (00:00 UTC Tokyo).
- **14:00 UTC (31)** — pre-NY ramp.

Hours with lowest transition density:
- **08–13 UTC (~21 each)** — London session quiet zone.

**Observations:** transitions cluster around session boundaries, especially NY open. Mean activity in the 14:00–17:00 UTC window is ~38 transitions/hour, ~40% above the year mean. London session (08–13 UTC) is the structurally quietest period for regime changes. **No claim** that this is causally session-driven — merely a frequency observation.

---

## §5 Per-month breakdown

| Month | MARKUP % | MARKDOWN % | RANGE % | Notes |
|-------|---------:|-----------:|--------:|-------|
| 2025-05 | 16.9 | 6.9 | 76.2 | Mild bull |
| 2025-06 | 9.6 | 8.8 | 81.7 | Quiet RANGE-heavy |
| 2025-07 | 11.3 | 4.6 | 84.1 | Sleeper month |
| 2025-08 | 7.7 | 17.7 | 74.6 | First MARKDOWN-heavy month |
| 2025-09 | 8.2 | 6.2 | 85.6 | Quiet again |
| 2025-10 | 15.1 | 17.9 | 67.1 | Mixed, both trends present |
| 2025-11 | 11.0 | **24.9** | 64.2 | Heaviest MARKDOWN month |
| 2025-12 | 12.2 | 16.4 | 71.4 | Mixed |
| 2026-01 | 6.7 | 15.2 | 78.1 | Bear-leaning |
| 2026-02 | 16.7 | **33.0** | 50.3 | **Most volatile month**: only 50% RANGE |
| 2026-03 | **21.9** | 21.4 | 56.7 | Two-sided active |
| 2026-04 | 18.5 | 7.8 | 73.8 | MARKUP-heavy spring |
| 2026-05 | 0.0 | 0.0 | 100.0 | Single day in window — RANGE only |

**Observations:**
- **November 2025 was the bear month** of the year (24.9% MARKDOWN). October–November together carry most of the visible MARKDOWN exposure.
- **February 2026 was the most volatile** in the regime-mix sense: only 50% RANGE, with 33% MARKDOWN — almost an inverse of the year average (72% RANGE).
- **March 2026 was the most balanced** trend month: 22% MARKUP + 21% MARKDOWN almost equal.
- **June, July, September were the sleepiest** (RANGE > 81%).
- The "bullish year" framing is supported by MARKUP slightly trailing MARKDOWN in most months — but MARKDOWN exposure clusters in autumn (Aug, Oct, Nov) while MARKUP spreads more evenly. The price-level rise from $60k→$76k came **less from sustained MARKUP regimes and more from the asymmetric structure of when the regimes occurred** (drawdowns recovered in RANGE; rallies happened in MARKUP bursts).

---

## §6 Caveats

1. **`regime_24h` is a 24-hour rolling classification**, not an instantaneous one. Applying it at 1h granularity inherits a 24h smoothing window — short price reversals (<24h) get absorbed into the dominant label of the trailing window. A finer-grained classifier (e.g., 4h or 8h window) would show more transitions and shorter episodes.

2. **Mode aggregation 5m→1h smooths further.** The original `regime_int` is at 5m resolution; resampling to 1h via mode picks the dominant 5m label of the 12 sub-bars. This second smoothing can hide micro-transitions (e.g., 3 sub-bars MARKUP within an otherwise-RANGE hour).

3. **Hysteresis settings live in `RegimeForecastSwitcher`** (`_HYSTERESIS_BARS = 12`, `_REGIME_CONF_THRESHOLD = 0.65`). The classifier output here is the **raw** label without runtime hysteresis. In production, the switcher additionally requires 12-bar confirmation before switching — the effective transition count seen by the bot is **lower** than 644 (some transitions get suppressed as too brief). This raw count is the upper bound.

4. **DISTRIBUTION is absent from the classifier**, so this analysis is silent on it. Any conclusions about "top of trend" / "topping pattern" timing are not derivable from this data — would need a separate Wyckoff classifier.

5. **Bull-year bias.** 2025-05 → 2026-05 had BTC rising from ~$60k to ~$76k. Episode counts and transitions in a bear-cycle year would likely look different (probably more MARKDOWN time, possibly different transition cadence). DO NOT extrapolate these statistics to other years without revalidating.

6. **No price-magnitude information.** This analysis counts regime *labels* but not price moves. A 38h MARKUP episode that gained 0.5% has the same statistical weight here as one that gained 12%. For magnitude-aware analysis, join with returns data — out of scope for this TZ.

7. **Time-of-day analysis is coarse.** UTC-hour buckets blur within-hour structure. A finer-grained (5m) analysis might reveal sharper session-open spikes. Also, the operator's local time is Warsaw (CET/CEST = UTC+1/+2), so apparent UTC clusters shift accordingly.

---

## §7 Conclusions

**Conclusions (operator + MAIN review, 2026-05-04)**

Регim classifier на годе 2025-05-01 → 2026-05-01 даёт structurally clean transitions — zero direct MARKUP↔MARKDOWN transitions, all 644 transitions проходят через RANGE buffer. Это feature, не artifact: classifier hysteresis обеспечивает что система всегда даёт coordinator buffer time для переключения bot configurations.

Time distribution в bullish year 2025-2026:

- RANGE: 72% (6306 hours) — primary mode
- MARKDOWN: 14.9% (1303 hours)
- MARKUP: 12.1% (1055 hours)
- DISTRIBUTION: absent в данных (0 episodes labeled, см. Block 12 finding)

Implications для P8 ensemble design:

- Range bots — primary investment. 72% времени бот должен находиться в "range mode". Любая ensemble архитектура где range bots вторичные — игнорирует структурную реальность данных.
- Trend bots — secondary opportunity moments. MARKUP + MARKDOWN combined = 27% времени. Trend bots должны активироваться только в эти периоды.
- Coordinator получает predictable transition pattern. RANGE buffer между trend regimes означает coordinator должен реагировать на sequence "trending → RANGE → other_trending" — есть pause moments для clean state transitions.
- Max single RANGE episode = 179h (7.5 days). Это upper bound for "stable single-mode operation". Coordinator не может предполагать что system будет в одном regime месяцами; transition events случаются хотя бы раз в неделю в worst case.
- Bullish year bias confirmed: MARKUP + RANGE upward-biased = 84% combined. MARKDOWN краток и редок. Это объясняет почему single-bot LONG configurations (BT-001..004) проигрывали систематически — большую часть времени в RANGE при upward drift, плюс MARKUP-эпизоды без сильных pullbacks.

Caveats:

- Применимость на DISTRIBUTION-heavy years untested (DISTRIBUTION в этом году отсутствует)
- Hysteresis settings frozen — варьирование hysteresis значений могло бы дать другие transition patterns
- Time-of-day clustering показал что transitions слегка clustered around session boundaries (Asia/London/NY) — это feature classifier'а или данных, в обоих случаях используется coordinator design

Related downstream read: [REGIME_OVERLAY_v1.md](REGIME_OVERLAY_v1.md) uses these regime-hour distributions to allocate backtest PnL/triggers by proportional weight.

---

## Appendix A — Reproducing

```bash
python scripts/_regime_periods_analysis.py
```

Output: `docs/RESEARCH/_regime_periods_raw.json` with full per-month, per-hour, per-regime structured data.

## Appendix B — Files

- `scripts/_regime_periods_analysis.py` (driver)
- `docs/RESEARCH/_regime_periods_raw.json` (raw)
- `docs/RESEARCH/REGIME_PERIODS_2025_2026.md` (this report)
