# PHASE 1 FIX STATUS — 2026-04-30

**TZ:** TZ-ENGINE-BUG-FIX-PHASE-1  
**Generated:** 2026-04-30  
**Purpose:** Clarify exact applied/deferred status of all 3 fixes

---

## A2 — verdict() classifier (abs CV)

- **Status:** APPLIED ✓
- **Commit:** `27c4588`
- **Files changed:**
  - `tools/calibrate_ginarea.py` — `verdict()` now uses `abs_cv = abs(cv)` for all threshold comparisons
  - `tools/calibrate_ginarea.py` — added `has_sign_flip(st: dict) -> bool` helper
  - `tools/calibrate_ginarea.py` — `write_report()` labels sign-flip groups as `FRACTURED_SIGN_FLIP` in per-group table and Conclusions section
  - `tools/calibrate_ginarea.py` — added `fill_normalized_realized(rows, groups)` (see A3)
- **Tests:** 9 new tests in `TestVerdictAbsCV` + `TestHasSignFlip` — **all green**
- **Verified diff lines:**
  ```
  +    abs_cv = abs(cv)
  +    if abs_cv < 15:
  +    if abs_cv < 35:
  +def has_sign_flip(st: dict) -> bool:
  +            vlabel = "FRACTURED_SIGN_FLIP" if has_sign_flip(st) else verdict(st["cv"])
  +        v = "FRACTURED_SIGN_FLIP" if has_sign_flip(st_re) else verdict(st_re["cv"])
  +        elif v == "FRACTURED_SIGN_FLIP":
  ```
- **Effect on calibration report:** SHORT group (CV = -676.2%) will now show `FRACTURED_SIGN_FLIP` instead of `STABLE`. The false recommendation "Use K = -37.641 as fixed calibration multiplier" is eliminated.

---

## A3 — normalized_sim_realized filled

- **Status:** APPLIED ✓
- **Commit:** `27c4588` (same commit as A2)
- **Files changed:**
  - `tools/calibrate_ginarea.py` — `fill_normalized_realized(rows, groups)` added as standalone helper
  - `tools/calibrate_ginarea.py` — called in `main()` after groups are built
- **Tests:** 3 new tests in `tests/tools/test_normalized_realized_filled.py` — **all green**
- **Verified diff line:** `+    fill_normalized_realized(rows, groups)`
- **Effect:** `CalibRow.normalized_sim_realized` is now correctly set to `sim_realized × group_mean_K_realized` for all 9 rows. Previously the field was always `0.0` despite the `# filled below` comment — the inline computation in `write_report()` never wrote back to the object.

---

## A1+B1 — combo_stop_init in engine_v2/group.py

- **Status:** NOT APPLIED — BLOCKED (escalation required)
- **Reason:** `engine_v2/group.py` is NOT in the bot7 repository.
  - **bot7 path checked:** `c:\bot7\src\backtest_lab\engine_v2\group.py` → **NOT FOUND**
  - **Actual location:** `C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src\backtest_lab\engine_v2\group.py` → external Codex repo
  - **TZ instruction followed:** "Если src/backtest_lab/ не в bot7 repo — STOP, эскалация architect'а"
  - Code stopped per safety rule (option **a** from TZ variants) — did not edit external repo without authorization
- **What the fix should do (for architect action):**
  ```python
  # File: C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src\backtest_lab\engine_v2\group.py
  # Lines 40-55 — from_triggered()

  # SHORT (current, buggy):
  init_stop = extreme * (1.0 + max_stop_pct / 100.0)
  # SHORT (fixed):
  raw_stop = extreme * (1.0 + max_stop_pct / 100.0)
  init_stop = min(raw_stop, entry_price)  # cap at entry — no loss on immediate reversal

  # LONG (current, buggy):
  init_stop = extreme * (1.0 - max_stop_pct / 100.0)
  # LONG (fixed):
  raw_stop = extreme * (1.0 - max_stop_pct / 100.0)
  init_stop = max(raw_stop, entry_price)  # floor at entry — no loss on immediate reversal
  ```
- **Impact of NOT applying:** SHORT K_realized will remain sign-unstable for td < max_stop_pct (0.04%). The calibration report will correctly show `FRACTURED_SIGN_FLIP` for SHORT group (A2 fix active), so the operator will NOT be misled into using the broken K. The fix is described in `docs/ENGINE_BUG_HYPOTHESES_2026-04-30.md` (H1 for SHORT, B1 for LONG).

---

## Recalibration status

- **Whether ran:** PENDING — operator is running `python tools/calibrate_ginarea.py` now (8-15 min)
- **Why not ran by Code:** per project memory rule — heavy simulations (Y1 OHLCV, 9 bots) run by operator on their PC, not by Code
- **Expected output location:** `docs/calibration/CALIBRATION_VS_GINAREA_2026-04-30.md` (default output path)
- **What will change in the new report vs the old:**
  | Metric | Old report | New report |
  |---|---|---|
  | SHORT K_realized verdict | `STABLE` (bug — CV was -676.2%) | `FRACTURED_SIGN_FLIP` |
  | SHORT Conclusions line | "Use K = -37.641 as fixed calibration multiplier" | "sign flip detected. fix engine bug before calibrating" |
  | normalized_sim_realized column | inline only, CalibRow field = 0.0 | correctly filled per group mean K |
  | LONG K_realized verdict | `STABLE` (CV ≈ -1%) | `STABLE` (no change expected) |
  | sim_realized / K_realized values | same | **same** — engine not touched, only report classifier fixed |

---

## Recommended next steps for operator

1. **Receive calibration results** from the running `calibrate_ginarea.py` — confirm SHORT verdict shows `FRACTURED_SIGN_FLIP`, not `STABLE`.

2. **Apply A1+B1 fix in Codex repo** — edit `C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src\backtest_lab\engine_v2\group.py` lines 40-55 per the fix text above. Run TC-1 and TC-2 synthetic tests from `docs/ENGINE_BUG_HYPOTHESES_2026-04-30.md`.

3. **Re-run calibration after A1+B1** — after the engine fix, SHORT K_realized at td ≥ max_stop should stabilize (no more sign flips). Expected: CV drops from -676% to something within 15-50% range. LONG behaviour depends on B2 (indicator direction) — separate TZ.

4. **TZ Phase 2 candidates (architect to prioritize):**
   - B2 (LONG indicator fires on price fall, not rise) — needs operator confirmation of GinArea LONG strategy semantics before fixing
   - B3 (combined order PnL base price) — needs isolated unit test in Codex repo
   - C1/C2/C3 (K_volume unit mismatch) — needs GinArea UI inspection for volume units
