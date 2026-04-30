# PHASE 1 — POST-FIX STATUS & RECALIBRATION REPORT — 2026-04-30

**TZ:** TZ-ENGINE-BUG-FIX-PHASE-1 (continuation)  
**Recalibration:** PENDING — operator to run `python tools/calibrate_ginarea.py` after applying A1+B1 fix

---

## What was done — External repo (Codex engine_v2)

**File:** `C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src\backtest_lab\engine_v2\group.py`  
**Commit:** `db557f8` in Codex repo  
**Change:** `from_triggered()` lines 45-55 — cap/floor `combo_stop_init` at `entry_price`

```python
# SHORT — before (buggy):
init_stop = extreme * (1.0 + max_stop_pct / 100.0)

# SHORT — after (fixed):
raw_stop = extreme * (1.0 + max_stop_pct / 100.0)
entry_cap = min(o.entry_price for o in orders)
init_stop = min(raw_stop, entry_cap)

# LONG — before (buggy):
init_stop = extreme * (1.0 - max_stop_pct / 100.0)

# LONG — after (fixed):
raw_stop = extreme * (1.0 - max_stop_pct / 100.0)
entry_floor = max(o.entry_price for o in orders)
init_stop = max(raw_stop, entry_floor)
```

**Tests added:** `tests/engine_v2/test_combo_stop_init.py` — 8 tests, all green  
**Regression:** 32/32 out_stop tests pass (24 existing + 8 new)  
**No API change** — `entry_price` sourced from `o.entry_price` on existing orders  
**Other files in repo untouched** — pre-existing uncommitted changes in bot.py/interventions.py/run_scenario.py/validate_engine.py left as-is

---

## What was done — bot7 repo

**Commit:** `27c4588`

| Fix | Change |
|---|---|
| A2 — verdict() | `abs(cv)` instead of `cv`; sign-flip → `FRACTURED_SIGN_FLIP` |
| A3 — normalized_realized | `fill_normalized_realized()` called in `main()` after groups built |

**Tests:** 12 new tests in bot7, all green

---

## Expected calibration impact (analysis before running)

### SHORT / USDT-M (LINEAR) — `max_stop=0.04%`

| TD | td > max_stop? | A1+B1 effect |
|---|---|---|
| 0.19% | YES (0.19 > 0.04) | **NO EFFECT** |
| 0.21% | YES | **NO EFFECT** |
| 0.25% | YES | **NO EFFECT** |
| 0.30% | YES | **NO EFFECT** |
| 0.35% | YES | **NO EFFECT** |
| 0.45% | YES | **NO EFFECT** |

**Conclusion:** The A1+B1 fix does NOT affect SHORT because `max_stop=0.04%` is smaller than every TD tested. `raw_stop` is always below `entry_price` for SHORT in these params.

**Implication:** If SHORT K_realized remains sign-unstable after recalibration, the root cause is something OTHER than A1 (hypothesis A1 may have been derived for a different param set where SHORT max_stop=0.30%). Phase 2 investigation required.

### LONG / COIN-M (INVERSE) — `max_stop=0.30%`

| TD | td vs max_stop | A1+B1 effect |
|---|---|---|
| 0.25% | td < max_stop | **APPLIES** — raw_stop < entry → capped at entry |
| 0.30% | td ≈ max_stop | **MARGINAL** — raw_stop ≈ entry*(1-0.000009) ≈ entry |
| 0.45% | td > max_stop | **NO EFFECT** |

**Expected:** LONG td=0.25% and marginally td=0.30% `sim_realized` should shift toward 0 or positive. K_realized for those rows may change sign. Overall LONG group K_realized distribution may narrow.

---

## Recalibration results (to be filled by operator)

Operator runs: `python tools/calibrate_ginarea.py`  
Expected output: `docs/calibration/CALIBRATION_VS_GINAREA_2026-04-30.md` (overwrites)

### Before fixes (from hypotheses doc, calibration run 2026-04-30 10:36)

| Dir | TD | sim_realized | K_realized | Verdict (before A2 fix) |
|---|---:|---:|---:|---|
| SHORT | 0.19 | -63.86 | -497.11 | STABLE (bug) |
| SHORT | 0.21 | +130.23 | +267.15 | STABLE (bug) |
| SHORT | 0.25 | -384.13 | -101.29 | STABLE (bug) |
| SHORT | 0.30 | +1,129.06 | +37.75 | STABLE (bug) |
| SHORT | 0.35 | +1,339.32 | +34.47 | STABLE (bug) |
| SHORT | 0.45 | +1,499.71 | +33.19 | STABLE (bug) |
| LONG | 0.25 | -0.1530 | -0.82 | STABLE |
| LONG | 0.30 | -0.1551 | -0.86 | STABLE |
| LONG | 0.45 | -0.1559 | -0.99 | STABLE |

**Group stats before:**
- SHORT K_realized: mean=-37.641, CV=-676.2% → verdict was `STABLE` (A2 bug)
- LONG K_realized: mean≈-0.89, CV≈-10% → verdict was `STABLE`

### After fixes — expected (fill in actual numbers after run)

| Dir | TD | sim_realized | K_realized | Verdict (with A2 fix) |
|---|---:|---:|---:|---|
| SHORT | 0.19 | **same** | **same** | `FRACTURED_SIGN_FLIP` |
| SHORT | 0.21 | **same** | **same** | `FRACTURED_SIGN_FLIP` |
| SHORT | 0.25 | **same** | **same** | `FRACTURED_SIGN_FLIP` |
| SHORT | 0.30 | **same** | **same** | `FRACTURED_SIGN_FLIP` |
| SHORT | 0.35 | **same** | **same** | `FRACTURED_SIGN_FLIP` |
| SHORT | 0.45 | **same** | **same** | `FRACTURED_SIGN_FLIP` |
| LONG | 0.25 | **↑ (less negative or +)** | **↑** | TBD |
| LONG | 0.30 | **↑ (marginal)** | **↑ (marginal)** | TBD |
| LONG | 0.45 | **same** | **same** | TBD |

*Fill in actual values from new report here.*

---

## Key figures summary (to be completed)

| Metric | Before | After |
|---|---|---|
| SHORT K_realized CV | -676.2% | -676.2% (unchanged — A1 had no effect on SHORT) |
| SHORT verdict | STABLE (bug) | **FRACTURED_SIGN_FLIP** (A2 fixed) |
| LONG K_realized CV | ≈-10% | TBD (A1+B1 affects td=0.25, 0.30) |
| LONG verdict | STABLE | TBD |
| normalized_sim_realized | always 0.0 | now filled (A3 fixed) |

---

## Recommended next steps

1. **Run `python tools/calibrate_ginarea.py`** and paste SHORT group CV + LONG K_realized row for td=0.25 into this doc.

2. **If SHORT K_realized remains sign-unstable after recalibration:**  
   Root cause of SHORT instability at td < 0.30 is NOT the A1 combo_stop bug (which doesn't fire at SHORT max_stop=0.04%). Escalate to Phase 2 investigation. Candidates: instop behaviour, combined order PnL (B3), or indicator trigger pattern (B2).

3. **If LONG K_realized for td=0.25 shifts toward +1.0 (from -0.82):**  
   A1+B1 fix confirmed as root cause of part of LONG sign error. Check td=0.30 and td=0.45 for remaining gap.

4. **If LONG K_realized does NOT change:**  
   A1+B1 fix had no measurable effect despite the mathematical expectation. Deeper bug (B2 indicator direction or B3 combined order averaging) dominates. Phase 2 required.

5. **Do not push external repo to remote without operator authorization.**
