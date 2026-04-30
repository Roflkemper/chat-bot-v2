# ENGINE BUG FIX — PHASE 1 SUMMARY — 2026-04-30

**TZ:** TZ-ENGINE-BUG-FIX-PHASE-1  
**Source:** `docs/ENGINE_BUG_HYPOTHESES_2026-04-30.md`

---

## Inventory & Bug Reproduction (Audit)

### File locations

| File | Location | Status |
|---|---|---|
| `tools/calibrate_ginarea.py` | `c:\bot7\tools\calibrate_ginarea.py` | IN BOT7 REPO ✓ |
| `engine_v2/group.py` | `C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src\backtest_lab\engine_v2\group.py` | EXTERNAL REPO |

### Fix 3 (A1+B1) — ESCALATION REQUIRED

`engine_v2/group.py` is in the external Codex repo, not in bot7.  
Per TZ: "Если src/backtest_lab/ не в bot7 repo — STOP, эскалация architect'а."

**Action required from operator/architect:** Fix `group.py:40-55` in the Codex repo. Fix text from TZ:
```python
# SHORT: cap combo_stop_init at entry_price when td < max_stop_pct
raw_stop = extreme * (1.0 + max_stop_pct / 100.0)
init_stop = min(raw_stop, entry_price)

# LONG: floor combo_stop_init at entry_price when td < max_stop_pct  
raw_stop = extreme * (1.0 - max_stop_pct / 100.0)
init_stop = max(raw_stop, entry_price)
```

Tests TC-1 and TC-2 (from hypotheses doc) should be written in the Codex repo.

### Bug Reproduction Confirmed (TC-3)

```python
# Bug A2: verdict(-676.2) returns 'STABLE' — CONFIRMED
verdict(-676.2) == 'STABLE'   # BUG: should be FRACTURED

# Sign flip group (SHORT K values from calibration data):
ks = [-497.11, 267.15, -101.29, 37.75, 34.47, 33.19]
# mean=-37.64, cv=-676.3%, min=-497.11, max=267.15
# verdict(cv=-676.3) == 'STABLE'   # BUG: should be FRACTURED_SIGN_FLIP

# Bug A3: CalibRow.normalized_sim_realized stays 0.0 after main()
# CalibRow(normalized_sim_realized=0.0) — never filled by loop  # CONFIRMED
```

---

## Fixes Applied in This PR

### Fix 1 — A2: `verdict()` abs(cv) correction

**File:** `tools/calibrate_ginarea.py:212-219`

**Change:** Use `abs(cv)` instead of `cv` for threshold comparisons.  
**Added:** `has_sign_flip(st: dict) -> bool` helper — returns True when `st["min"] < 0 < st["max"]`.  
**Report:** `write_report()` now labels groups with sign flip as `FRACTURED_SIGN_FLIP` instead of using raw cv verdict.

**Before:** `verdict(-676.2)` → `"STABLE"` (false — was recommending K = -37.641 as multiplier)  
**After:** `verdict(-676.2)` → `"FRACTURED"` + sign flip → `"FRACTURED_SIGN_FLIP"` in report

### Fix 2 — A3: `normalized_sim_realized` filled after group construction

**File:** `tools/calibrate_ginarea.py`

**Change:** Extracted `fill_normalized_realized(rows, groups)` helper; called in `main()` after groups are built.  
Formula: `r.normalized_sim_realized = r.sim_realized * group_mean_k_realized`

**Before:** All `CalibRow.normalized_sim_realized == 0.0` from `main()` output  
**After:** Each row has `normalized_sim_realized` set to `sim_realized × group_mean_K_realized`

### Fix 3 — A1+B1: `combo_stop_init` in `group.py` — BLOCKED (external repo)

Not applied in this TZ. See escalation note above.

---

## Tests Added

| File | Tests |
|---|---|
| `tests/tools/test_calibrate_ginarea.py` | `TestVerdictAbsCV` — 4 tests for negative/positive CV handling |
| `tests/tools/test_normalized_realized_filled.py` | 3 tests: filled after call, uses group mean K, handles zero-mean group |

---

## Expected Impact on Calibration Run

After operator re-runs `python tools/calibrate_ginarea.py`:

| What changes | Before fix | After fix |
|---|---|---|
| SHORT group verdict (K_realized CV = -676%) | `STABLE → Use K = -37.641` | `FRACTURED_SIGN_FLIP → Do not use single multiplier` |
| Normalized sim_realized in report | Computed inline but `CalibRow.normalized_sim_realized = 0.0` | Correctly set in CalibRow objects |
| LONG group verdict (CV ≈ -1%) | `STABLE` (was technically correct: abs(-1) < 15) | `STABLE` (unchanged — LONG K is genuinely stable near -1) |

Fix 3 (combo_stop_init) required to address SHORT/LONG sign errors in sim_realized. Without it, K_realized for SHORT td < max_stop will remain sign-unstable.
