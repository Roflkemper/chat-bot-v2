# DEBT Classification - 2026-05-02

## DEBT-02: Re-arm logic в bt-симуляторе

**Description:** Backtest simulator does not model re-arm/re-entry behavior the same way the historical operator/backtest workflow expects on larger windows.  
**Location:** `services/setup_backtest/`, references in [docs/SESSION_LOG.md](C:/bot7/docs/SESSION_LOG.md), [docs/MASTER.md](C:/bot7/docs/MASTER.md), [docs/HANDOFF_2026-04-29.md](C:/bot7/docs/HANDOFF_2026-04-29.md)  
**Investigation findings:** Existing documentation says the issue was intentionally deferred because What-If architecture covers most immediate use-cases. The risk is methodological: longer-horizon backtest/research can under-model repeated re-entry cycles unless split into short segments.  
**Severity:** P2  
**Impact на Phase 1:** Не блокирует  
**Impact на Phase 2:** Не блокирует  
**Impact на Phase 3:** Может блокировать отдельные optimize/research TZs  
**Decision:** FIX-WHEN-TOUCH-AREA  
**Reasoning:** This is not a live trading or paper-journal blocker today, but it matters when the team re-enters setup-backtest optimization or relies on long-window replay for decision rules.  
**Estimated fix time:** ~2-4h  
**Linked TZ if any:** Existing references only; no active TZ open

## DEBT-03: 12 pre-existing failures в test_protection_alerts.py

**Description:** Historical notes refer to flaky/order-dependent failures in `test_protection_alerts.py`.  
**Location:** [tests/test_protection_alerts.py](C:/bot7/tests/test_protection_alerts.py), [services/protection_alerts.py](C:/bot7/services/protection_alerts.py)  
**Investigation findings:** Current direct run shows `11 passed` and no failures: `python -m pytest tests/test_protection_alerts.py -v`. The debt entry is stale in its original wording. When the full suite fails to collect this file, the failure is caused by global import-path/collection problems, not by assertions inside this module.  
**Severity:** P3  
**Impact на Phase 1:** Не блокирует  
**Impact на Phase 2:** Не блокирует  
**Impact на Phase 3:** Не блокирует  
**Decision:** ACCEPTED  
**Reasoning:** As a standalone module, the file is green. The remaining problem belongs to suite-wide collection infrastructure and should be tracked under DEBT-04, not under a separate “12 failures” item.  
**Estimated fix time:** 0h for this debt entry itself; underlying infra is covered by DEBT-04  
**Linked TZ if any:** None

## DEBT-04: 49 collection errors в RUN_TESTS

**Description:** Full pytest collection is structurally broken for a large portion of the repo.  
**Location:** cross-cutting; current examples include `tests/test_grid_context.py`, `tests/test_killswitch.py`, `tests/test_telegram_runtime.py`, `tests/services/*`, `tests/whatif/*`, `tools/smoke_test.py`  
**Investigation findings:** Current `python -m pytest --collect-only` reports **91 collection errors**, not 49. Main error categories:
- import-path/package resolution failures: `ModuleNotFoundError` for `features.*`, `renderers.*`, `services.*`, `whatif.*`, `core.confluence_engine`
- missing symbol/API drift: e.g. `cannot import name 'atomic_append_line' from utils.safe_io`
- duplicate basename/import mismatch: `tools/smoke_test.py` vs `core/tools/smoke_test.py`
This is test infrastructure debt, not direct evidence of broken production runtime. But it makes the full regression shield unreliable outside targeted runs.
**Severity:** P1  
**Impact на Phase 1:** Не блокирует  
**Impact на Phase 2:** Blocks  
**Impact на Phase 3:** Blocks  
**Decision:** FIX-BEFORE-PHASE-2  
**Reasoning:** Phase 1 can continue with targeted tests and live/paper evidence, but operator augmentation and later automation phases need a trustworthy repo-wide regression surface.  
**Estimated fix time:** ~4-8h  
**Linked TZ if any:** Should be split later into import-path cleanup + duplicate-module cleanup

## DEBT-05: Naming sync collectors vs market_collector в docs

**Description:** Documentation uses overlapping names for collector-related concepts.  
**Location:** docs only; examples in [docs/PROJECT_MAP.md](C:/bot7/docs/PROJECT_MAP.md), [docs/SESSION_LOG.md](C:/bot7/docs/SESSION_LOG.md), [docs/STATE/QUEUE.md](C:/bot7/docs/STATE/QUEUE.md)  
**Investigation findings:** Active code consistently uses `collectors/` package and related runtime names. I did not find an active code path centered on `market_collector` that would indicate a live naming collision in code. This is a documentation vocabulary drift, not a runtime inconsistency.  
**Severity:** P3  
**Impact на Phase 1:** Не блокирует  
**Impact на Phase 2:** Не блокирует  
**Impact на Phase 3:** Не блокирует  
**Decision:** ACCEPTED  
**Reasoning:** The issue is documentation hygiene only. It should be cleaned when docs in this area are touched, but it is not a delivery blocker.  
**Estimated fix time:** ~15-30m  
**Linked TZ if any:** None
