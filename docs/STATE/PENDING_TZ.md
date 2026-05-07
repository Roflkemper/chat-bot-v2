# PENDING TZ
# Update when TZs open or close.
# Last update: 2026-05-06 — session close sync

---

## Ready To Dispatch

| ID | Description | Status | Blocker |
|---|---|---|---|
| TZ-DECISION-LAYER-CORE-WIRE | Implement Decision Layer MVP core wire per `DECISION_LAYER_v1.md` | READY | operator dispatch only |
| TZ-DECISION-LAYER-CONFIG | Add config layer after CORE-WIRE lands | READY-AFTER | requires `TZ-DECISION-LAYER-CORE-WIRE` |
| TZ-MTF-CLASSIFIER-PER-TF-WIRE | Wire per-timeframe classifier path after core/config chain | READY-AFTER | requires CORE-WIRE + CONFIG |

## Current Priority

| ID | Description | Status | Blocker |
|---|---|---|---|
| TZ-BT-014-NOSTOP-COMPARISON | Operator GinArea 4-run no-stop comparison for BT-014..017 mirror; required for CFG-L-FAR upgrade path | OPEN | operator GinArea run |
| TZ-MANUAL-LAUNCH-CHECKLIST | Manual launch checklist for execution phase path 1 | OPEN | implementation dispatch order should be known |
| TZ-POSITION-CLEANUP-SUPPORT | Analytics/support for operator-led cleanup of live SHORT exposure before regulation activation | OPEN | operator-driven |
| TZ-MARGIN-COEFFICIENT-INPUT-WIRE | Add margin_coefficient computation to upstream state_latest.json producer. Без этого M-* family dormant в production. | OPEN | operator подтверждает источник данных биржи |
| TZ-DECISION-LAYER-DESIGN-v1.1 | Resolution для DESIGN-OPERATOR-GAP-1 (M-4 emergency vs cap) и возможно GAP-3 (dedup architecture). Formal amendment §2.7 дизайна. | OPEN | operator-defined scope |

## Foundation Extensions

| ID | Description | Status | Blocker |
|---|---|---|---|
| TZ-BEAR-MARKET-DATA-ACQUISITION | Separate larger work: collect bear-market dataset and matching validation runs | OPEN | dataset acquisition |
| TZ-CROSS-ASSET-VALIDATION | ETH / cross-asset validation after BTC-only foundation close | OPEN | additional assets and run registry |

## Done / Closed By 2026-05-05+ Session

| ID | Description | Status | Note |
|---|---|---|---|
| TZ-TRANSITION-MODE-COMPARE | Transition mode question closed via Block 2 plus `TRANSITION_MODE_COMPARE_v2.md` | DONE | closed by H=1 reframe and sign-conditional result |
| TZ-PURE-INDICATOR-AB-ISOLATION | Pure indicator A/B isolation closed via Pack E + Pack C comparison in finalized foundation | DONE | no longer pending as a separate foundation blocker |
| TZ-K-RECALIBRATE-PRODUCTION-CONFIGS | Production-config K recalibration executed and documented with research-grade limitation retained | DONE (deferred for stronger closure) | CP19 structural caveat remains; future clean closure belongs to bear-market / richer-data phase |
| TZ-FORECAST-CALIBRATION-DIAGNOSTIC | Reliability-diagram + Platt/isotonic diagnostic on full-year forecast replay | DONE | verdict fundamentally weak; resolution ≈ 0; calibrated Brier = 0.2500 baseline; see `FORECAST_CALIBRATION_DIAGNOSTIC_v1.md` |
| TZ-FORECAST-DECOMMISSION | Removed forecast block from dashboard/state surfaces; preserved regime classifier and regulation card | DONE | forecast retired from active operator workflow |
| TZ-FORECAST-FEED-RESTORE-FROZEN | Restore frozen-derivatives input data to revive existing pipeline | NOT-NEEDED | superseded by decommission verdict |
| TZ-FORECAST-LIVE-WORKER | Build live forecast worker around current model | NOT-NEEDED | same; current model has no deployable resolution |
| TZ-MARKET-DECISION-SUPPORT-RESEARCH | Independent external research on operator-actionable decision support | DONE | Claude + Codex variants completed |
| TZ-FORECAST-MODEL-REPLACEMENT-RESEARCH | Independent forecast-rebuild research with realistic probability assessment | DONE | Claude + Codex variants completed |
| TZ-DECISION-LAYER-DESIGN | Decision Layer MVP design artifact | DONE | `docs/DESIGN/DECISION_LAYER_v1.md` |
| TZ-MTF-DISAGREEMENT-DETECTION-DESIGN | MTF disagreement design artifact | DONE | `docs/DESIGN/MTF_DISAGREEMENT_v1.md` |
| TZ-MTF-FEASIBILITY-CHECK | Feasibility verdict for MTF implementation path | DONE | Option E — adopt `phase_classifier.py` |
| TZ-CREATE-BACKLOG-TRIGGERS | Create trigger-based deferred work registry | DONE | `docs/BACKLOG_TRIGGERS.md` |
| TZ-DOCUMENTATION-FIXES | Repair stale doc references and missing project-map references | DONE | `docs/PROJECT_MAP.md` stub created; docs synced |
| TZ-MTF-CALIBRATION-HISTOGRAM | Check real classifier score distribution before threshold semantics | DONE | verdict R2 — persistence-only |
| TZ-CLASSIFIER-AUTHORITY-DECISION | Quantify and decide classifier authority split | DONE | split authority confirmed; opposite-direction disagreement `1.02%` |

## Notes

- Foundation scope is complete for the current BTC bullish-year dataset.
- Execution preparation is complete. Implementation is ready to start with the Decision Layer chain above.
- Manual launch path 1 remains the current execution path.
- Regulation activation remains blocked until live SHORT position cleanup completes.
- Decision Layer Q1-Q12 answers are considered captured input, not open discovery.
- Deferred future work is tracked in [BACKLOG_TRIGGERS.md](C:/bot7/docs/BACKLOG_TRIGGERS.md).
