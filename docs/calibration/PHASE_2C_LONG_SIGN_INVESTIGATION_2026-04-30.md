# PHASE 2C — LONG K_realized SIGN ERROR INVESTIGATION — 2026-04-30

**TZ:** TZ-PHASE-2C-LONG-SIGN-ERROR-INVESTIGATION  
**Generated:** 2026-04-30  
**Scope:** Investigation only — no engine fixes applied.

---

## Problem statement

From calibration run 2026-04-30:

| TD | sim_realized (BTC) | ga_realized (BTC) | K_realized | Verdict |
|---:|---:|---:|---:|---|
| 0.25 | -0.1530 | +0.12486 | -0.82 | STABLE (sign flip) |
| 0.30 | -0.1551 | +0.13355 | -0.86 | STABLE (sign flip) |
| 0.45 | -0.1559 | +0.15423 | -0.99 | STABLE (sign flip) |

All LONG COIN-M (INVERSE) sim_realized values are negative; all GA values are positive.
K_realized is negative across the board — a consistent sign flip, not random noise.

Note: A1+B1 fix (cap/floor combo_stop_init at entry_price) was confirmed live for this run.
The fix does not apply to td=0.45 (since 0.45 > max_stop=0.30). That td=0.45 ALSO shows the
sign flip rules out A1+B1 as the root cause.

---

## Test 1 — INVERSE PnL formula sign

**File:** `src/backtest_lab/engine_v2/contracts.py`

INVERSE formula:
```python
def unrealized_pnl(side, qty, entry, current):
    # LONG: pnl = qty * (1/entry - 1/current)
    return qty * (1.0 / entry - 1.0 / current)
```

Verification:
```python
# Price rises from 80000 to 81000 (profitable LONG)
pnl = 200 * (1/80000 - 1/81000)
    = 200 * (12.5e-6 - 12.346e-6)
    = 200 * 1.543e-7 = +3.09e-5 BTC  ✓ POSITIVE
```

**Verdict: INVERSE PnL sign is CORRECT.**  
A LONG that closes above entry produces positive PnL. Sign is not inverted in the formula.

---

## Test 2 — Indicator direction for LONG

**File:** `src/backtest_lab/engine_v2/indicator.py`, line 40:

```python
def is_triggered(self) -> bool:
    v = self.value()  # N-bar close-to-close %
    if self.side == Side.SHORT:
        return v > self.threshold_pct   # fires on price RISE (short opportunity)
    return v < -self.threshold_pct      # fires on price DROP (long opportunity)
```

The sim LONG indicator fires when price **falls** by ≥ threshold_pct% over the period.
This is a contrarian "buy the dip" strategy.

**GinArea GA indicator direction: NOT VERIFIED.**  
If GinArea LONG fires when price **rises** (momentum), the sim operates in the opposite
direction — triggering on opposite market conditions → systematic sign flip of P&L.

**Verdict: B2 hypothesis INCONCLUSIVE — needs operator to confirm GA LONG indicator direction.**

---

## Test 3 — LONG CAN profit in dump+recovery scenario

Synthetic: 30-bar dump (BTC falls 1%), then 30-bar recovery (+1%),
with LONG INVERSE bot, period=30, threshold=0.3%.

```
Bot initialized, 30-bar dump: indicator fires at bar 30, last_in_price set.
30-bar recovery: orders fill, trigger, close profitably.
realized_pnl = +0.0000110 BTC  ✓ POSITIVE
```

The sim engine IS capable of producing positive LONG PnL under the right conditions.
The systematic negativity in the 2-year backtest is not an engine bug in the basic path.

**Verdict: Engine PnL calculation is correct for a normal dump+recovery cycle.**

---

## H4 hypothesis — Intrabar whipsaw on bearish bars

### Mechanism

`GinareaBot._bar_prices()` (`bot.py` line 146-149):
```python
def _bar_prices(self, bar: OHLCBar) -> list[float]:
    if bar.close >= bar.open:
        return [bar.open, bar.low, bar.high, bar.close]   # bullish
    return [bar.open, bar.high, bar.low, bar.close]        # bearish
```

For a **bearish bar**, the intrabar sequence processes **HIGH before LOW**.

For LONG:
- `_trigger_hit(price)` fires when `price >= order.trigger_price` — i.e. at HIGH.
- Immediately after trigger, `OutStopGroup` is created with:
  - `combo_stop_price = max(raw_stop, entry_price)` (A1+B1 fix applied)
  - `effective_stop = min(combo_stop_price, base_stop)` ≈ `entry_price`
- Then LOW is processed. If `LOW < effective_stop (≈ entry_price)`, the group closes at LOW.

This is a **whipsaw**: trigger fires at HIGH above entry, group immediately closes at LOW below
entry — in the same intrabar sequence. The trade loses on every such bar.

### Synthetic test (5 tests — all pass)

**File:** `tests/engine_v2/test_long_whipsaw_h4.py` (Codex repo)

```
Bar 0: O=H=L=C=80000 — primes indicator buffer
Bar 1: O=H=L=C=79700 — v=-0.375% < -0.3% → LONG indicator fires, last_in_price=79700
Bar 2: O=79300, H=79510, L=79200, C=79280 — BEARISH
  _bar_prices → [79300, 79510, 79200, 79280]

  @ 79300 (O): _open_immediate opens at next_lvl=79304.5, entry=79304.5, trigger=79502.98
  @ 79510 (H): trigger fires → OutStopGroup(combo_stop=79304.5)
  @ 79200 (L): 79200 ≤ effective_stop(79304.5) → CLOSES at 79200

closed_orders = 1
realized_pnl = 200*(1/79304.5 - 1/79200) ≈ -3.3e-6 BTC  ← NEGATIVE
```

Confirmed:
- H4 mechanism is real and produces negative PnL per whipsaw trade
- Close price is the intrabar LOW (not the combo_stop_price)
- Bullish bars do NOT produce whipsaw (L processed before H → trigger fires last in bar)

### Effect of A1+B1 fix on H4

Before fix: `combo_stop = raw_stop = extreme * (1 - max_stop/100) < entry`  
After fix:  `combo_stop = max(raw_stop, entry_price) = entry_price`

The fix RAISES the effective stop. Cases:

| LOW vs thresholds | Before fix | After fix |
|---|---|---|
| LOW < raw_stop < entry | Closes at LOW (loss) | Closes at LOW (same loss) |
| raw_stop < LOW < entry | No close — group stays open | Closes at LOW (new small loss!) |
| LOW > entry | No close | No close |

In the intermediate zone (raw_stop < LOW < entry), the fix causes closes that didn't happen before.
However, when the group stays open without fix, the subsequent bar prices (typically falling further)
tend to produce a larger loss later. The net effect: **fix reduces average whipsaw loss magnitude.**

### Does H4 explain the sign flip?

The whipsaw frequency depends on how often a bearish 1-minute bar has:
- HIGH ≥ LONG trigger (just 0.25%-0.45% above entry) AND
- LOW < entry

For BTC/USD on volatile 1m bars this can occur frequently. However:
- td=0.45% (where the A1+B1 fix has NO effect) still shows negative K_realized (-0.99)
- The sign flip is consistent across ALL td values
- GA shows positive PnL for all td values, including td=0.45

**Verdict: H4 (whipsaw) contributes to negative sim_realized but CANNOT be the sole cause**  
of the sign flip. A structural difference between sim and GA strategy remains unexplained.

---

## Root cause summary

| Hypothesis | Status | Evidence |
|---|---|---|
| A: INVERSE PnL formula wrong | **REJECTED** | Formula verified correct |
| B1: A1+B1 fix not applied | **REJECTED** | Fix confirmed live (PHASE_1_VERIFY_DEEP) |
| B2: Indicator fires opposite direction vs GA | **INCONCLUSIVE** | Sim fires on DROP; GA direction unknown |
| B3: Combined order PnL averaging wrong | **NOT INVESTIGATED** | Would need multi-order sim trace |
| H4: Bearish bar whipsaw | **CONFIRMED (partial)** | 5 tests pass; explains losses, not full sign flip |

---

## Most likely root cause

**B2 — Indicator direction mismatch.**

The consistent sign flip across ALL td values (0.25, 0.30, 0.45) — including td=0.45 where
A1+B1 has no effect — points to a structural difference in which market conditions trigger
entries, not a stop-placement bug.

If GinArea LONG fires on price RISE (momentum buy) while the sim fires on price DROP
(contrarian buy), the sim would consistently be entering opposite to the profitable direction.
A momentum strategy on BTC would show positive GA PnL; the sim entering on dips in a trending
market would show losses.

This cannot be confirmed from engine code alone — it requires checking GinArea UI/docs.

---

## Recommended next steps (Phase 3)

### Phase 3a: Operator — verify B2 (1 hour)

Check GinArea LONG bot settings:
- What is the "Индикатор Прайс%" threshold direction for LONG?
- Does it fire when price RISES above +threshold (momentum) or FALLS below -threshold (contrarian)?
- Compare to `PricePercentIndicator.is_triggered()` in `indicator.py` line 40.

If direction is opposite: that is the root cause. Fix would be to change the inequality in
`indicator.py` for LONG (1-line change with significant calibration impact).

### Phase 3b: Estimate whipsaw frequency (1-2 hours)

Run calibrate tool with whipsaw-counter instrumentation (no code change needed — add prints):
```python
# In GinareaBot: count bars where trigger fires AND group closes same bar
```
Quantify: what fraction of LONG closed trades are whipsaw (same-bar trigger+close)?
If >50% of trades → H4 is dominant, and may also contribute to sign flip.

### Phase 3c: Investigate B3 — combined order averaging

For multi-order groups (when several IN orders merge into one OutStopGroup), verify that
`close_all()` uses each order's individual `entry_price`, not the group average.
From `group.py` line 159-163: ✓ each order's entry_price used individually.
**B3 appears correct — but should be verified with a multi-order synthetic test.**

---

## Acceptance

- `tests/engine_v2/test_long_whipsaw_h4.py`: 5 tests, all green ✓
- Full engine_v2 test suite: 143 tests pass (138 prior + 5 new) ✓
- Bot7 tests: no regression ✓ (investigation only, no engine changes)
- Production engine_v2 code: **UNCHANGED** ✓
