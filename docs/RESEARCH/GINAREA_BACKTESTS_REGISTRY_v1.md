# GinArea Backtests Registry — v1

**Status:** REGISTRY (TZ-BACKTEST-DATA-CONSOLIDATION, Block A)
**Date:** 2026-05-05
**Source:** Operator-collected GinArea platform backtest results, manually transcribed from screenshots into the briefing chat.
**Method:** Pure structuring — no recompute, no synthesis, no winner-picking.
**Scope:** All 17 backtests provided by the operator on 2026-05-04.

---

## §1 Master table

Sequential local IDs (BT-001 … BT-017) for cross-reference in downstream docs.

| BT-ID | Set tag | GinArea ID | Side | Contract | Strategy | Period | TP % | gs % | order_size | order_count | Indicator | Instop % | Min/Max stop % | P&L Trail | Realized PnL | Triggers | Volume |
|-------|---------|------------|------|----------|----------|--------|-----:|-----:|-----------|------------:|-----------|---------:|---------------:|-----------|-------------:|---------:|-------:|
| BT-001 | LONG annual | 5914176825 | LONG | COIN_FUTURES | DEFAULT | 2025-05-20 → 2026-05-04 | 0.25 | 0.03 | $100 | 5400 | OFF | 0 | 0.01 / 0.3 | OFF | −0.0956 BTC | n/a | n/a |
| BT-002 | LONG annual | 5279999948 | LONG | COIN_FUTURES | DEFAULT | 2025-05-20 → 2026-05-04 | 0.25 | 0.03 | $100 | 5400 | OFF | 0.018 | 0.01 / 0.3 | OFF | −0.1197 BTC | 1153 | $16.35M |
| BT-003 | LONG annual | 5029973000 | LONG | COIN_FUTURES | DEFAULT | 2025-05-20 → 2026-05-04 | 0.25 | 0.03 | $100 | 5400 | OFF | 0.05 | 0.01 / 0.3 | OFF | −0.1285 BTC | 1193 | $16.95M |
| BT-004 | LONG annual | 5559313663 | LONG | COIN_FUTURES | DEFAULT | 2025-05-20 → 2026-04-30 | 0.25 | 0.03 | $100 | 5400 | OFF | 0.10 | 0.01 / 0.3 | OFF | −0.2311 BTC | 1376 | $17.11M |
| BT-005 | SHORT 3m | 4760273429 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-01 → 2026-05-04 | 0.25 | 0.03 | 0.001 BTC | 5000 | > 0.3% | 0 | 0.01 / 0.04 | OFF | −$4083.52 | 770 | $4.47M |
| BT-006 | SHORT 3m | 4366151988 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-01 → 2026-05-04 | 0.25 | 0.03 | 0.001 BTC | 5000 | > 1% | 0.018 | 0.008 / 0.025 | OFF | −$3924.25 | 738 | $4.36M |
| BT-007 | SHORT 3m | 4871843422 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-01 → 2026-05-04 | 0.25 | 0.03 | 0.001 BTC | 5000 | > 1% | 0.03 | 0.006 / 0.015 | OFF | −$2122.20 | 576 | $3.60M |
| BT-008 | SHORT 3m | 5960456245 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-01 → 2026-05-04 | 0.25 | 0.03 | 0.001 BTC | 5000 | > 1% | 0 | 0.001 / 0.004 | OFF | −$2135.01 | 576 | n/a |
| BT-009 | SHORT 02may | 5307069608 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-05 → 2026-05-01 | 0.21 | 0.03 | 0.001 BTC | 800 | > 1% | 0.03 | 0.01 / 0.04 | ON 0.8/8 | −$3985.64 | 645 | $3.91M |
| BT-010 | SHORT 02may | 5159596681 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-05 → 2026-05-02 | 0.50 | 0.03 | 0.001 BTC | 800 | > 1% | 0.03 | 0.01 / 0.04 | ON 0.8/8 | −$2621.59 | 674 | $1.96M |
| BT-011 | SHORT 02may | 5749038744 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-05 → 2026-05-02 | 0.40 | 0.03 | 0.001 BTC | 800 | > 1% | 0.03 | 0.01 / 0.04 | ON 0.8/8 | −$3055.64 | 670 | $2.35M |
| BT-012 | SHORT 02may | 4308357396 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-05 → 2026-05-01 | 0.30 | 0.03 | 0.001 BTC | 800 | > 1% | 0.03 | 0.01 / 0.04 | ON 0.8/8 | −$3506.22 | 670 | $2.97M |
| BT-013 | SHORT 02may | 5570514383 | SHORT | USDT_FUTURES | INDICATOR | 2026-02-05 → 2026-05-02 | 0.25 | 0.03 | 0.001 BTC | 800 | > 1% | 0.03 | 0.01 / 0.04 | ON 0.8/8 | −$3710.38 | 659 | $3.43M |
| BT-014 | LONG 02may | 5818418497 | LONG | COIN_FUTURES | INDICATOR | 2026-02-05 → 2026-05-02 | 0.50 | 0.03 | $100 | 800 | < −1% | 0.018 | 0.01 / 0.03 | OFF | +0.07779 BTC | 48 | $2.93M |
| BT-015 | LONG 02may | 5162684485 | LONG | COIN_FUTURES | INDICATOR | 2026-02-05 → 2026-05-02 | 0.40 | 0.03 | $100 | 800 | < −1% | 0.018 | 0.01 / 0.03 | OFF | +0.07054 BTC | 46 | $3.44M |
| BT-016 | LONG 02may | 4951646669 | LONG | COIN_FUTURES | INDICATOR | 2026-02-05 → 2026-05-02 | 0.30 | 0.03 | $100 | 800 | < −1% | 0.018 | 0.01 / 0.03 | OFF | +0.05930 BTC | 47 | $4.33M |
| BT-017 | LONG 02may | 6327245950 | LONG | COIN_FUTURES | INDICATOR | 2026-02-05 → 2026-05-02 | 0.25 | 0.03 | $100 | 800 | < −1% | 0.018 | 0.01 / 0.03 | OFF | +0.05022 BTC | 45 | $4.99M |

**Format notes:**
- **TP** and **gs** (grid step) are percentages.
- **order_size** unit depends on contract type: BTC for USDT_FUTURES (linear), USD for COIN_FUTURES (inverse).
- **Indicator** column: `OFF` means strategy=DEFAULT; `> X%` / `< X%` means INDICATOR strategy with threshold.
- **Instop %** and **Min/Max stop %** are protection params. **0** = disabled.
- **P&L Trail** ON 0.8/8 = trailing on with 0.8% min profit / 8% trail width (operator's GinArea-side setting).
- "n/a" entries are missing in operator's source data — preserved verbatim, not synthesized.

---

## §2 Categorization (D60)

Grouped by **{direction × strategy × indicator}**.

### Group G1 — LONG annual / DEFAULT (4 rows: BT-001 … BT-004)
- Side: LONG, contract: COIN_FUTURES, strategy: DEFAULT, no indicator
- Period: 350 days (2025-05-20 → 2026-05-04)
- All identical EXCEPT `instop_pct` ∈ {0, 0.018, 0.05, 0.10}
- **Sweep variable: instop_pct only** → clean A/B/C/D test
- **All four are losing trades** (−0.096 to −0.231 BTC)
- Sub-finding: PnL monotonically deteriorates with higher instop (BT-001 best, BT-004 worst)

### Group G2 — SHORT 3m / INDICATOR (4 rows: BT-005 … BT-008)
- Side: SHORT, contract: USDT_FUTURES, strategy: INDICATOR
- Period: 92 days (2026-02-01 → 2026-05-04)
- TP=0.25, gs=0.03, order_size=0.001 BTC, order_count=5000 — all constant
- **Confounded sweep**: `Indicator threshold` AND `instop_pct` AND `min_stop` AND `max_stop` all vary together
- All four are losing (−$2122 … −$4083)
- Cross-row comparisons within this group are NOT clean A/B (multiple variables change simultaneously)

### Group G3 — SHORT 02may / INDICATOR (5 rows: BT-009 … BT-013)
- Side: SHORT, contract: USDT_FUTURES, strategy: INDICATOR + P&L Trail ON 0.8/8
- Period: ~86 days (2026-02-05 → 2026-05-02)
- All constant EXCEPT `TP` ∈ {0.21, 0.25, 0.30, 0.40, 0.50}
- **Sweep variable: TP only** → clean TP-sensitivity A/B/C/D/E test
- **All five are losing** (−$2621 … −$3985)
- Sub-finding: PnL is NOT monotonic in TP — TP=0.50 is best (−$2621), TP=0.21 is worst (−$3985)

### Group G4 — LONG 02may / INDICATOR (4 rows: BT-014 … BT-017)
- Side: LONG, contract: COIN_FUTURES, strategy: INDICATOR
- Period: ~86 days (2026-02-05 → 2026-05-02)
- All constant EXCEPT `TP` ∈ {0.25, 0.30, 0.40, 0.50}
- **Sweep variable: TP only** → clean TP-sensitivity A/B/C/D test
- **All four are profitable** (+0.05022 to +0.07779 BTC)
- Sub-finding: PnL IS monotonic in TP — higher TP = higher BTC gain (consistent with longer holds capturing more price drift in a still-bullish window)

---

## §3 Quality flags per row (D61)

| BT-ID | Group | Variable swept | Confound flag | Comparable to |
|-------|-------|----------------|---------------|---------------|
| BT-001 | G1 | instop=0 | clean | BT-002, 003, 004 |
| BT-002 | G1 | instop=0.018 | clean | BT-001, 003, 004 |
| BT-003 | G1 | instop=0.05 | clean | BT-001, 002, 004 |
| BT-004 | G1 | instop=0.10 | clean | BT-001, 002, 003 |
| BT-005 | G2 | thr=0.3, instop=0, min/max=0.01/0.04 | **CONFOUNDED** (3 vars vary) | partial only |
| BT-006 | G2 | thr=1, instop=0.018, min/max=0.008/0.025 | **CONFOUNDED** | partial only |
| BT-007 | G2 | thr=1, instop=0.03, min/max=0.006/0.015 | **CONFOUNDED** | partial only |
| BT-008 | G2 | thr=1, instop=0, min/max=0.001/0.004 | **CONFOUNDED** | partial only |
| BT-009 | G3 | TP=0.21 | clean | BT-010 … 013 |
| BT-010 | G3 | TP=0.50 | clean | BT-009, 011, 012, 013 |
| BT-011 | G3 | TP=0.40 | clean | BT-009, 010, 012, 013 |
| BT-012 | G3 | TP=0.30 | clean | BT-009, 010, 011, 013 |
| BT-013 | G3 | TP=0.25 | clean | BT-009 … 012 |
| BT-014 | G4 | TP=0.50 | clean | BT-015, 016, 017 |
| BT-015 | G4 | TP=0.40 | clean | BT-014, 016, 017 |
| BT-016 | G4 | TP=0.30 | clean | BT-014, 015, 017 |
| BT-017 | G4 | TP=0.25 | clean | BT-014, 015, 016 |

**Summary:** 13 of 17 rows are clean A/B (G1 + G3 + G4). 4 rows in G2 are confounded — operator can extract directional readings but not single-variable conclusions.

---

## §4 Open data gaps (D62)

What the current 17-row set does **not** contain that future GinArea runs could fill:

### Symmetry gaps
- **No SHORT annual mirror to G1** (LONG annual / DEFAULT). G1 has 4 LONG annual / DEFAULT instop sweep; the SHORT-equivalent annual sweep is missing. Direct comparison "does instop hurt SHORT the same way it hurts LONG over a year?" is impossible from this set.
- **No LONG 3m mirror to G2** (SHORT 3m / INDICATOR confounded sweep). Even though G2 is confounded, having a LONG counterpart would let the operator estimate whether the sign of a parameter's effect flips with side.

### Variable-isolation gaps
- **G2's confounding is unfixable from this dataset.** A clean instop-only sweep on SHORT 3m / INDICATOR would require 4 new runs holding `Indicator threshold` and `min/max stop` constant.
- **No instop sweep on G3/G4 (02may window).** All five SHORT 02may rows have `instop=0.03`; all four LONG 02may rows have `instop=0.018`. Effect of varying instop within an already-INDICATOR-gated bot is unknown.
- **No grid step (gs) sweep anywhere.** All 17 rows use gs=0.03. Effect of widening grid is untested empirically.
- **No order_size sweep anywhere.** All SHORT use 0.001 BTC; all LONG use $100. Sensitivity to size is untested.

### Period-coverage gaps
- **No bear-only window (e.g., 2025-Q4)** to stress-test LONG/SHORT in genuinely adverse conditions. G1, G2, G3, G4 all overlap with bullish 2025–early-2026 BTC trajectory.
- **No same-period comparison** between G1 (LONG annual DEFAULT) and a hypothetical "LONG annual INDICATOR" — would isolate the value of indicator-gated entry vs always-on.

### Strategy-mix gaps
- **No P&L Trail variation.** G3 uses Trail ON; G4 uses Trail OFF; everything else is OFF. Direct A/B for Trail effect on the same side+TP is missing.
- **No grid_count sweep.** SHORT 3m uses 5000, SHORT 02may uses 800. The 86-day window with 800 vs 5000 count would reveal if max_orders binds.

### Asset-coverage gaps
- **All 17 are BTC.** No XRP / ETH / other-pair backtests in the operator's set. Cross-asset transferability of any conclusions is untested.

### Methodological note
This list is **not** a recommendation to run all of these — it's a roadmap of what's *not* answerable from the current 17. Many of these gaps may be low-priority depending on what the operator decides to optimize next. The list exists so future TZ briefs can reference "we still don't have X" without rediscovering.

---

## §5 Provenance

- **Source:** Operator-collected GinArea platform backtest results.
- **Date received:** 2026-05-04.
- **Method:** Manually transcribed by operator from GinArea UI screenshots into the briefing chat.
- **Verification:** Worker has not cross-verified numbers against any GinArea API; transcription is taken at face value per the brief.
- **Caveats inherent to source:**
  - GinArea reports are platform-realized, including platform-specific slippage, fees, funding accruals — **these numbers ARE production-realistic** in a way the calibration sim numbers (audited in BACKTEST_AUDIT.md §1) are not. This is the most production-aligned data we have.
  - Transcription introduces small risk of typos (especially in the 4 GinArea ID columns and PnL signs/magnitudes). Worth double-checking against original screenshots before any decision-grade use.
  - "n/a" entries (BT-001 triggers/volume; BT-008 volume) are preserved verbatim — likely incomplete operator transcription rather than missing GinArea data.

---

## §6 What this registry does NOT do (anti-drift)

- No interpretation of which TP/instop/strategy is "best."
- No regeneration of any backtest result.
- No synthesis of missing values (n/a stays n/a).
- No assessment of GinArea engine vs our calibration sim — that's the audit doc's scope.
- No regime classifier overlay — that's TZ-REGIME-OVERLAY, a downstream TZ.
- No claim that these 17 represent the "true" GinArea performance distribution — they're operator-curated experiments, not random samples.

This registry is a structural input to downstream work, not a decision artifact in its own right.
