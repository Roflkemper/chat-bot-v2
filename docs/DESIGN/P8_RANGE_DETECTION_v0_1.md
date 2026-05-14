# P8 Range Detection — v0.1 design

**Status:** DRAFT (TZ-RGE-RANGE-DETECTION, P8)
**Date:** 2026-05-05
**Track:** P8 (Regime-driven multi-bot ensemble)
**Pre-req for:** TZ-RGE-BREAKOUT-CONDITIONS, TZ-RGE-DUAL-MODE-DESIGN

## Goal

Define **range boundaries** — the upper and lower edges within which "range bots" (small-grid) operate, and outside of which "trend bots" (large-grid) get activated. The boundaries must be:

- **Computable on every 5m bar** (or whatever cadence the ensemble coordinator runs at).
- **Stable enough not to whipsaw** (small noise must not redefine boundaries every bar).
- **Tied to the regime classifier** so we don't fight signals from `RegimeForecastSwitcher` — boundaries are most actionable when `regime == RANGE`.
- **Auditable** — operator can read the latest boundary calc and understand which level came from where.

This document picks **one method for v0.1** and explicitly defers the others to v0.2+.

---

## Inputs available today

Already sitting in the codebase:

1. **ICT levels** (`data/ict_levels/BTCUSDT_ict_levels_1m.parquet`) — 78 columns including:
   - PDH/PDL (prior day H/L), PWH/PWL (prior week H/L), D_open
   - Session highs/lows: asia/london/ny_am/ny_pm — including mitigation timestamps
   - Kill-zone midpoints
   - Unmitigated high/low closest to price + age
   - All distances pre-computed in `dist_to_*_pct`

2. **Forecast-features parquet** (`data/forecast_features/full_features_1y.parquet`) — 84 cols:
   - ATR(14), realized_vol_pctile_24h, vol_regime_int (0=low/1=mid/2=high)
   - vol_profile_poc_dist_pct, vol_profile_va_high/low_dist_pct (Tier-2 from this week)
   - Brought-forward `regime_int` from the Wyckoff classifier

3. **OHLCV** (1m raw, 1s for last year) — for any custom roll-forward computation.

4. **Switcher state** (`data/regime/switcher_state.json` after bootstrap) — current regime label + hysteresis state.

---

## Candidate methods (4)

### Method A — ICT-based boundaries

**Definition:**
- Upper bound = `max(PDH, PWH, nearest_unmitigated_high)` filtered to those within ±N% of price (else fall back to next-broader level).
- Lower bound = `min(PDL, PWL, nearest_unmitigated_low)` similarly.

**Pros:**
- Zero new computation — everything already in ict_levels parquet.
- Operator already thinks in these levels (PDH/PDL is part of every brief).
- Levels have **structural meaning**: prior day's H/L was where someone got filled, so price reactions there are real.
- Mitigation timestamps tell us when a level becomes stale.

**Cons:**
- Levels exist at **discrete points in time** (PDH = yesterday's high). When price drifts far away over multiple days, ICT boundaries become wide and meaningless ("range" of $5k+).
- No notion of *current* volatility — a tight $200 chop overnight gets the same PDH/PDL boundary as a $5k swing day.
- Doesn't update intraday — boundaries are fixed once PDH/PDL are written at midnight UTC.

### Method B — ATR-based dynamic

**Definition:**
- Upper bound = `rolling_high(N=24, 1h bars) + k * ATR(14, 1h)`, where N defaults 24, k defaults 0.5.
- Lower bound = `rolling_low(N=24) − k * ATR(14)`.

**Pros:**
- Always-current — boundaries breathe with intraday volatility.
- Single tuneable knob (k) operator can adjust for asset.
- Independent of ICT data, so works on any asset (XRP applicability built-in).

**Cons:**
- Pure technicals — no structural meaning. A boundary at $76,234 has no significance to anyone except the formula.
- N-bar rolling window is a lag — after a fast trend leg the upper boundary stays elevated for N bars even though regime has clearly shifted.
- k must be calibrated per asset / per timeframe — adds tuning surface.

### Method C — Manual operator config

**Definition:**
- `data/ensemble/range_config.json`: per-asset `{upper, lower, set_at, set_by}`.
- Operator updates manually when they see range broken / re-established.

**Pros:**
- Maximum operator control — no surprises.
- Simplest possible implementation (read a JSON file).
- Forces operator to commit to a structural read of the market.

**Cons:**
- **Defeats the purpose**: P8's whole pitch is automating "перебираю/недобираю" pain. Manual config moves the work to a different surface, doesn't eliminate it.
- Boundaries get stale within hours if operator isn't watching.
- Unsuitable for unattended/overnight operation.

### Method D — Hybrid (ICT primary + ATR fallback)

**Definition:**
1. Try ICT-based (Method A) first.
2. If ICT boundaries are wider than `MAX_BOUNDARY_PCT` (e.g. 4%) or ICT density is too low (no unmitigated level within ±2% of price), fall back to ATR-based (Method B).
3. Cache the chosen method in audit log.

**Pros:**
- Combines structural meaning (ICT) with dynamic adaptation (ATR).
- Never returns "boundaries unavailable" — always has a fallback.
- Per-bar audit trail tells operator which method drove this minute's decision.

**Cons:**
- Two code paths to test and tune.
- Method-switching itself can introduce hysteresis bugs (boundaries jump when method flips ICT→ATR).
- `MAX_BOUNDARY_PCT` and "density" thresholds are new tuning knobs.

---

## Pros/cons matrix (summary)

| Aspect | A: ICT | B: ATR | C: Manual | D: Hybrid |
|--------|--------|--------|-----------|-----------|
| Data ready today | ✅ | ✅ | ⚠️ (need new file) | ✅ |
| Updates intraday | ❌ (fixed at midnight) | ✅ | ❌ | ✅ |
| Structural meaning | ✅ | ❌ | ✅ (operator-defined) | ✅ |
| New tuning knobs | 1 (filter %) | 2 (N, k) | 0 | 4 (1+2+threshold+density) |
| Operator workload | low | low | **high** | low |
| Asset-portable (XRP) | ⚠️ (XRP ICT data thinner) | ✅ | ✅ | ✅ |
| Fails gracefully | ❌ (when no nearby level) | ✅ | ❌ (stale config) | ✅ |
| Whipsaw risk | low (levels discrete) | medium (rolling drift) | low | low (with hysteresis) |

---

## Recommendation: **Method D (Hybrid) for v0.1**

**Reasoning:**
1. We already have ICT levels (zero new compute) and ATR (already in features). The "hybrid" is mostly dispatch logic, not new math.
2. Method A alone fails when price drifts far from the nearest ICT level — common after multi-day trends. Hybrid makes this a non-failure.
3. Method B alone has no structural meaning, which makes operator audits useless ("why is the boundary $76,234? Because the formula said so" is not a satisfying answer).
4. Method C is rejected outright — it makes P8 worse, not better, on the operator-pain dimension.
5. The added tuning surface from D vs A is small in practice: `MAX_BOUNDARY_PCT` defaults to 4% and `density_threshold` defaults to "≥1 unmitigated level within ±2%". Both will sit at defaults for week 3 and only get tuned if backtests show edge cases.

### v0.1 algorithm (concrete)

```python
def detect_range(bar_idx, ict_row, ohlcv_window, regime, atr_14):
    """Return (upper, lower, source) for the current bar."""
    price = ict_row["close"]

    # Step 1: ICT method
    candidates_high = [
        ict_row.get(c) for c in
        ("pdh_close_price", "pwh_close_price", "nearest_unmitigated_high_price")
        if ict_row.get(c) is not None
    ]
    candidates_low = [
        ict_row.get(c) for c in
        ("pdl_close_price", "pwl_close_price", "nearest_unmitigated_low_price")
        if ict_row.get(c) is not None
    ]
    candidates_high = [v for v in candidates_high if 0 < (v - price) / price < 0.04]
    candidates_low  = [v for v in candidates_low  if 0 < (price - v) / price < 0.04]

    # Density check: at least 1 above + 1 below within ±2%
    density_ok = (
        any(0 < (v - price) / price < 0.02 for v in candidates_high) and
        any(0 < (price - v) / price < 0.02 for v in candidates_low)
    )

    if candidates_high and candidates_low and density_ok:
        upper = min(candidates_high)   # nearest above
        lower = max(candidates_low)    # nearest below
        return (upper, lower, "ict")

    # Step 2: ATR fallback
    rolling_high = ohlcv_window["high"].tail(24).max()  # 24×1h = 1 day
    rolling_low  = ohlcv_window["low"].tail(24).min()
    upper = rolling_high + 0.5 * atr_14
    lower = rolling_low  - 0.5 * atr_14
    return (upper, lower, "atr_fallback")
```

Boundaries returned per bar; coordinator stores last 24h history for hysteresis (boundary doesn't move more than 0.3% per bar unless triggered by regime change — anti-whipsaw clamp).

---

## Edge cases

### E1. False breakout (price pierces boundary, returns within N bars)

Boundaries should NOT redefine themselves on a single piercing close. Resolution:
- Boundary update lags by 3 bars after a breach
- If price returns inside the old boundary within those 3 bars → boundary holds, breach is logged as "rejected"
- If price stays beyond old boundary for 3+ bars → boundary updates AND ensemble coordinator promotes to trend mode

This is intentionally a deferred decision — formal breakout-confirmation logic lives in **TZ-RGE-BREAKOUT-CONDITIONS**, not here. Range detection just provides the candidate level.

### E2. Regime classifier says RANGE but ICT density is low

Method D's fallback to ATR handles this. The audit field `source = "atr_fallback"` lets operator know that this minute's boundaries are technical, not structural.

### E3. Price already outside calculated boundary

Means the previous range broke and we're catching up. v0.1 behavior:
- Don't crash.
- Return boundaries anyway (they're useful for "how far above the upper edge").
- Coordinator interprets `price > upper` as "active breakout" → trend mode.

### E4. Insufficient data (first N hours after pipeline start)

If `ohlcv_window` has fewer than 24 bars, return `(None, None, "insufficient_data")`. Coordinator must handle by deferring decisions.

### E5. Tie-in with regime classifier — gate or always-on?

**v0.1 decision: always compute boundaries.** Regime classifier is consulted by the **coordinator**, not by `detect_range()`. This separation means:
- `detect_range()` is pure: same inputs → same outputs, no regime dependency.
- Coordinator decides "are we in RANGE? if yes, use these boundaries to gate range bots; if no, use them as breakout reference for trend bots."
- Easier to test — boundary detection unit tests don't need switcher state mocking.

---

## 5 worked examples (recent BTC price action, late Apr–early May 2026)

Using actual data from `backtests/frozen/BTCUSDT_1h_2y.csv` and `data/ict_levels/`.

### Example 1 — Tight overnight range (mid-April-style)

Recent 7-day window: high $79,486, low $75,666 — actually ~5% spread. Methods:

- **A (ICT):** PDH ≈ $79,200, PDL ≈ $75,800 → both within ±2.5% of $77,800 mid → **density ok**, returns `($79,200, $75,800, "ict")`
- **B (ATR):** rolling 24h high $79,486 + 0.5×ATR(150) ≈ **$79,560**; rolling low $75,666 − 0.5×ATR ≈ **$75,591**
- **D (Hybrid):** ICT density passes → returns ICT, identical to A

Operator outcome: range bots gated to operate between ~$75,800 – $79,200, trend bots stay paused.

### Example 2 — Drift after multi-day uptrend

Hypothetical: price ran from $74k to $79.5k over 4 days, now sitting at $79.5k. PDH = $79,486 (today's close), PDL = $77,300. Yesterday's range was already absorbed.

- **A (ICT):** candidates_high above $79,500 → none within 2%; density_ok = **False**
- **D fallback to B:** rolling_high $79,500 + 0.5×ATR ≈ **$79,575**, rolling_low $77,300 − 0.5×ATR ≈ **$77,225**
- Output: `($79,575, $77,225, "atr_fallback")`

Operator outcome: boundaries computed from technicals because no fresh ICT structure overhead. If price breaks $79,575 on confirmation, trend mode activates.

### Example 3 — Inside Asia session, low volatility

Price = $77,800, asia_high = $77,950, asia_low = $77,650. London_high (yesterday) = $78,200, london_low = $77,400.

- **A (ICT):** candidates_high {$77,950, $78,200} both within 0.5%; candidates_low {$77,650, $77,400} similar → density_ok = True → upper = $77,950 (nearest), lower = $77,650
- Output: `($77,950, $77,650, "ict")`

Operator outcome: tight range bots active, $300 spread, very tight grid.

### Example 4 — Breakout in progress

Price = $80,200, upper boundary from previous bar = $79,200. Price > upper.

- **A (ICT):** candidates_high above $80,200 may be empty or very far → density fails → fallback
- **D:** ATR fallback computes new boundaries above current price (rolling_high $80,200 + 0.5×ATR), reflecting the new regime
- Boundary update is deferred 3 bars per E1; meanwhile, coordinator sees `price > old_upper` and starts breakout-confirmation logic per **TZ-RGE-BREAKOUT-CONDITIONS**.

### Example 5 — XRP applicability check

XRP ICT levels parquet doesn't exist yet (`data/ict_levels/BTCUSDT_ict_levels_1m.parquet` — BTC-only). For XRP:
- **A (ICT):** unavailable → density check fails immediately
- **D:** ATR fallback always wins → XRP boundaries computed from ATR alone
- Until XRP ICT levels are generated (deferred TZ), XRP runs in pure-B mode through the same `detect_range()` interface

This is the intended graceful degradation. P8 ensemble can run on XRP with ATR-only boundaries.

---

## Open questions (3 max — applying lesson from sizing v0.1)

1. **What constitutes "ICT density" precisely?** v0.1 default: ≥1 unmitigated/PDH/PWH above price within 2%, AND ≥1 below within 2%. Operator may want a stricter rule (e.g., 2+ levels each side) — this is the only knob likely to need tuning before backtest.

2. **Should boundary updates be quantized to fixed intervals** (e.g., every 5 min only) **or recomputed per-bar**? v0.1 implementation will recompute per-bar because the data is cheap — but operator may prefer quantization to reduce log noise. Defer to coordinator design (TZ-RGE-DUAL-MODE-DESIGN).

3. **When ICT method works for upper but fails density for lower** (or vice versa), should we use **mixed** (ICT-upper + ATR-lower)? v0.1 says no — either both or fallback both — for simplicity. Mixed is a v0.2 option if backtests show real edge cases.

---

## What this design deliberately does NOT do

- **No breakout activation logic.** That's the next TZ. Range detection only provides the candidate boundary.
- **No regime gating inside `detect_range()`.** Coordinator's job.
- **No ML or learned thresholds** (per anti-drift). All thresholds are explicit constants tunable by operator.
- **No special handling of non-BTC assets beyond graceful XRP fallback.** Multi-asset is a deployment concern, not a design concern.
- **No volume profile (POC/VA) integration.** Tier-2 features added today have POC distance — could be a Method E "volume-profile-based boundaries" — explicitly deferred to v0.2 because it adds dimensions before we've validated v0.1 on backtest.

---

## Acceptance for v0.1 (next TZ — implementation)

When `detect_range()` is implemented:
- All 5 worked examples reproducible from impl
- Each call returns `(upper, lower, source)` triple, all numeric or all-None on insufficient data
- `source` ∈ {"ict", "atr_fallback", "insufficient_data"}
- Per-bar audit log written to `data/ensemble/range_detection_log.jsonl`
- Test coverage: 8+ tests covering each branch + each edge case + XRP fallback + insufficient data

Implementation is a **separate TZ** — TZ-RGE-RANGE-DETECTION-IMPL — once operator validates this design.
