# SIZING MULTIPLIER — v0.1 design

**Status:** DRAFT for operator validation (D6 of TZ-SIZING-MULTIPLIER-ENGINE)
**Date:** 2026-05-05
**Track:** P1 (Actionability layer)
**Replaces:** ad-hoc operator sizing decisions ("перебираю/недобираю")

## Goal

Convert four already-computed signals into a single sizing multiplier in the range **0× — 2×** of operator's baseline position size, with an explicit one-paragraph reasoning string in Russian.

**v0.1 is rule-based.** No ML. The decision table fits on one page so the operator can audit any output and disagree out loud.

---

## Inputs (4)

| # | Input | Source | Type | Range |
|---|-------|--------|------|-------|
| 1 | **Regime** | `RegimeForecastSwitcher.state.last_regime` | string | `MARKUP` / `MARKDOWN` / `RANGE` / `DISTRIBUTION` |
| 2 | **Forecast Brier band (1h)** | `ForecastResult.confidence` derived from `_CV_BRIER` | enum | `green` (≤0.22) / `yellow` (0.22–0.265) / `red`/`qualitative` |
| 3 | **Setup confluence** | `setup_bridge.attach_setups()` → `setup_context.strength` | int | 0 (no setup) — 10 (max) |
| 4 | **Recent paper-journal win rate** | `virtual_trader.stats(window_days=7).win_rate_pct` | float% or `None` (insufficient data) | 0–100 |

The 1h forecast probability *direction* is also used (`prob_up >= 0.55` → long bias; `<= 0.45` → short bias) but only as a **gate** — it determines which setup directions are eligible, not the multiplier value directly.

---

## Output

```python
@dataclass
class SizingDecision:
    multiplier: float            # 0.0 .. 2.0, rounded to 1 decimal
    direction_bias: str          # "long" | "short" | "flat" | "either"
    reasoning_ru: str            # 1-2 sentences in Russian
    inputs_snapshot: dict        # frozen copy of the 4 inputs for audit
```

`reasoning_ru` is REQUIRED. No silent multipliers — every decision explains itself. Pattern:

> "MARKDOWN с 1h GREEN-прогнозом (0.20 Brier), strength-9 short-rally-fade сетап, недельный win-rate 60% — увеличиваем размер до 1.5×."

---

## Decision table (rule-based, v0.1)

Ordering: **regime first, then forecast band, then setup strength, then WR adjustment.**

### Step 1 — Base multiplier from regime + forecast

| Regime | 1h Forecast band | Base multiplier | Reasoning fragment |
|--------|------------------|-----------------|---------------------|
| MARKDOWN | green (≤0.22) | **1.4** | "bear-режим с надёжным 1h" |
| MARKDOWN | yellow | 1.0 | "bear-режим, 1h в YELLOW" |
| MARKDOWN | red/qual | 0.6 | "bear-режим, но 1h не numeric" |
| MARKUP | green | 1.4 | "trend-режим с надёжным 1h" |
| MARKUP | yellow | 1.0 | "trend-режим, 1h в YELLOW" |
| MARKUP | red/qual (incl. 1h qualitative по matrix) | 0.4 | "trend-режим, 1h только качественный" |
| RANGE | yellow | 0.8 | "RANGE — mean reversion, скромный размер" |
| RANGE | green | 1.0 | "RANGE с надёжным 1h" |
| RANGE | red | 0.5 | "RANGE без надёжного прогноза" |
| DISTRIBUTION | any | 0.0 | "DISTRIBUTION — априори флэт, не торгуем по модели" |

**Why these numbers (rationale):**
- MARKDOWN получил 1.4 при GREEN потому что это единственная ячейка матрицы с CV-mean Brier 0.204 — самый сильный реальный edge на 1h.
- MARKUP сравним с MARKDOWN на yellow/green бандах (1.0/1.4) но падает до 0.4 на 1h qualitative — это honest acknowledgment что MARKUP-1h ширм.
- RANGE никогда не получает > 1.0 потому что mean reversion — это fade, не follow-through; чрезмерный размер быстро превращает edge в дроудаун.
- DISTRIBUTION = 0 по решению оператора (априори qualitative, нет numeric edge ни на одном горизонте).

### Step 2 — Setup confluence boost

После step 1 имеем base multiplier `M`. Сетап даёт adjustment:

| Setup strength | Multiplier delta | Reasoning |
|----------------|-------------------|-----------|
| ≥9 | +0.4 | "strength-9+ сетап усиливает" |
| 7–8 | +0.2 | "strength-7+ сетап подтверждает" |
| 1–6 | +0.0 | "сетап слабый или отсутствует" |
| 0 (no setup detected) | −0.2 | "нет сетапа — отступление от модельного триггера" |

**Direction filter:** the setup's direction must agree with the 1h forecast direction. If forecast says `prob_up=0.62` (long bias) but the only setup is SHORT — the **direction conflict** caps the multiplier at min(M, 0.5) and reasoning notes the conflict.

### Step 3 — Recent paper-journal WR adjustment

After steps 1-2 we have `M_pre`. WR adjustment is **last**, applied as a multiplier (not a delta) to keep dimensional consistency:

| 7d WR (decided trades) | Multiplier on M_pre | Reasoning |
|------------------------|---------------------|-----------|
| ≥60% | × 1.1 | "недельная статистика подтверждает" |
| 40–59% (or `None` — fewer than 5 decided trades) | × 1.0 | "недельная статистика нейтральна" |
| <40% | × 0.7 | "недельная статистика против — снижаем" |

**Floor & ceiling:** final multiplier clamped to `[0.0, 2.0]`. Round to 1 decimal place.

---

## Worked examples

### Example 1 — Strong MARKDOWN signal

- regime = MARKDOWN
- 1h forecast: prob_up=0.40 (i.e. prob_down=0.60), brier=0.20 (GREEN)
- setup: SHORT_RALLY_FADE strength=8, direction=short, agrees with forecast direction
- 7d WR: 65% (over 12 decided trades)

Step 1: 1.4
Step 2: +0.2 (strength 8) → 1.6
Step 3: × 1.1 (WR ≥60%) → **1.76 → 1.8** after clamp/round

`reasoning_ru`: "MARKDOWN с 1h GREEN-прогнозом (0.20 Brier), strength-8 short-rally-fade сетап в направлении прогноза, недельный win-rate 65% — увеличиваем размер до 1.8×."

### Example 2 — MARKUP-1h qualitative trap

- regime = MARKUP
- 1h forecast: qualitative ("lean_up"), no numeric value, brier=0.273 (red band per matrix)
- setup: LONG_PDL_BOUNCE strength=7, direction=long
- 7d WR: 50%

Step 1: 0.4 (MARKUP / red-or-qual)
Step 2: +0.2 (strength 7) → 0.6
Step 3: × 1.0 (50% WR) → **0.6**

`reasoning_ru`: "MARKUP, но 1h только качественный (CV Brier 0.273) — несмотря на strength-7 LONG-сетап, держим размер 0.6× и ждём подтверждения 4h."

### Example 3 — Direction conflict caps result

- regime = MARKDOWN
- 1h forecast: prob_up=0.62 (long bias!), brier=0.20 GREEN
- setup: SHORT_PDH_REJECTION strength=9 (high but **wrong direction**)
- 7d WR: 70%

Step 1: 1.4 (MARKDOWN green)
Step 2: would-be +0.4 (strength 9), but direction conflict → cap at **0.5**
Step 3: × 1.1 → 0.55 → **0.5** (clamp lower)

`reasoning_ru`: "MARKDOWN GREEN на 1h, но прогноз говорит вверх (62%), а единственный найденный сетап — SHORT. Конфликт направлений — режем размер до 0.5× и ждём согласованности."

### Example 4 — RANGE neutral

- regime = RANGE
- 1h forecast: prob_up=0.52, brier=0.247 (yellow)
- setup: GRID_PAUSE_ENTRIES strength=7 → grid action, not directional
- 7d WR: None (insufficient data)

Step 1: 0.8 (RANGE / yellow)
Step 2: +0.0 (grid setup is informational, not direction) → 0.8
Step 3: × 1.0 (None WR) → **0.8**

`reasoning_ru`: "RANGE с YELLOW 1h-прогнозом (0.247) и grid-сигналом — нейтральный размер 0.8×, недельной статистики пока недостаточно."

### Example 5 — DISTRIBUTION shutdown

- regime = DISTRIBUTION (top-of-trend or unstable)
- forecast: any
- setup: any
- WR: any

Step 1: 0.0 → short-circuit, return immediately.

`reasoning_ru`: "DISTRIBUTION-режим — модель не выдаёт numeric edge; не торгуем по модели, флэт."

---

## Implementation skeleton (preview, not for D6)

```python
def compute_sizing(
    regime: str,
    forecast_1h: ForecastResult,
    setup_context: dict | None,
    win_rate_7d: float | None,
) -> SizingDecision:
    if regime == "DISTRIBUTION":
        return SizingDecision(0.0, "flat",
            "DISTRIBUTION-режим — модель не выдаёт numeric edge; не торгуем по модели, флэт.",
            inputs_snapshot=...)

    band = forecast_1h.confidence_to_band()  # green/yellow/red/qual
    base, base_frag = _BASE_TABLE[(regime, band)]

    setup_delta, setup_frag, conflict = _setup_adjustment(setup_context, forecast_1h)
    pre = base + setup_delta
    if conflict:
        pre = min(pre, 0.5)

    wr_mult, wr_frag = _wr_adjustment(win_rate_7d)
    final = max(0.0, min(2.0, round(pre * wr_mult, 1)))

    return SizingDecision(
        multiplier=final,
        direction_bias=...,
        reasoning_ru=f"{base_frag}, {setup_frag}, {wr_frag} — размер {final}×.",
        inputs_snapshot={
            "regime": regime, "forecast_1h_brier": forecast_1h.brier,
            "setup": setup_context, "win_rate_7d": win_rate_7d,
        },
    )
```

---

## What v0.1 deliberately does NOT do

- **No ATR-scaling.** Operator's baseline already accounts for volatility regime via personal sizing rules. Adding ATR here double-counts.
- **No regime-stability gating beyond DISTRIBUTION.** MARKUP-1d gating lives in switcher; sizing trusts switcher's output.
- **No ML.** Decision table is auditable line-by-line. Once we have ≥4 weeks of paper journal data, v0.2 can introduce a learned weighting layer — but only with explicit operator approval (per failure rule).
- **No multi-position sizing.** v0.1 outputs one multiplier per signal. Aggregation across simultaneous setups is operator's job.
- **No GinArea grid sizing.** GinArea LONG is broken (DP-001 confirmed today via direct_k); applying this multiplier to LONG grid creates compounded uncertainty. Grid sizing stays manual until DP-001 has a replacement.

---

## Open questions for operator

1. **Are 1.4 / 1.0 / 0.6 the right base multipliers** for MARKDOWN green/yellow/red? They are calibrated to today's CV-mean Brier ranking; if you have intuitions from your own trade history that disagree, we adjust before implementation.
2. **WR threshold of 5 decided trades** — too low? Too high? With paper journal at Day 5/14 we don't have much data yet, so the `None` branch (ignore WR) will fire often during week 2.
3. **Direction conflict handling** — should the cap be 0.5 or 0.0? Argument for 0.0: any conflict = abstain. Argument for 0.5: occasional small position to test the hypothesis.
4. **Reasoning string language** — Russian fixed, or operator wants both RU and EN?
5. **Where does `SizingDecision` get rendered** — only in the morning brief (alongside forecast), or also as a Telegram alert when a strong signal fires mid-day?

---

## Acceptance for v0.1 implementation (next TZ)

- All 5 worked examples reproducible from the implementation
- Reasoning string is non-empty and matches the rule fragments above
- 0 ≤ multiplier ≤ 2 always
- DISTRIBUTION → 0 always
- No setup → not 0 by itself (the −0.2 floor still allows positive multiplier; no setup ≠ no signal)
- Test coverage: 8+ tests covering each branch of the decision table
