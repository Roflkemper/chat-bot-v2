# PROJECT KNOWLEDGE SYNC — 2026-05-05

## UPDATE

- `PENDING_TZ.md` — use [PENDING_TZ.md](C:/bot7/docs/STATE/PENDING_TZ.md). Reason: session-close update of done/ready/dispatched status.
- `DRIFT_HISTORY.md` — use [DRIFT_HISTORY.md](C:/bot7/docs/CONTEXT/DRIFT_HISTORY.md). Reason: session meta-pattern additions and prevention-rule updates.
- `MULTI_TRACK_ROADMAP.md` — use [MULTI_TRACK_ROADMAP.md](C:/bot7/docs/PLANS/MULTI_TRACK_ROADMAP.md). Reason: current status reframed to Track-A/B/C/D with implementation readiness.
- `HANDOFF_2026-05-06.md` — use [HANDOFF_2026-05-06.md](C:/bot7/docs/HANDOFF_2026-05-06.md). Reason: replace earlier execution-prep handoff with implementation-dispatch handoff.

## CREATE

- `STATE_CURRENT_2026-05-05_EOS.md` — add [STATE_CURRENT_2026-05-05_EOS.md](C:/bot7/docs/STATE/STATE_CURRENT_2026-05-05_EOS.md). New canonical session-close state snapshot.
- `BACKLOG_TRIGGERS.md` — add [BACKLOG_TRIGGERS.md](C:/bot7/docs/BACKLOG_TRIGGERS.md). Trigger-based deferred work registry.
- `PROJECT_MAP.md` — add [PROJECT_MAP.md](C:/bot7/docs/PROJECT_MAP.md). Stub created to resolve live references.
- `DECISION_LAYER_v1.md` — add [DECISION_LAYER_v1.md](C:/bot7/docs/DESIGN/DECISION_LAYER_v1.md). Decision Layer MVP design artifact.
- `MTF_DISAGREEMENT_v1.md` — add [MTF_DISAGREEMENT_v1.md](C:/bot7/docs/DESIGN/MTF_DISAGREEMENT_v1.md). MTF disagreement design artifact.
- `MTF_FEASIBILITY_v1.md` — add [MTF_FEASIBILITY_v1.md](C:/bot7/docs/DESIGN/MTF_FEASIBILITY_v1.md). Feasibility verdict with Option E.
- `CLASSIFIER_AUTHORITY_v1.md` — add [CLASSIFIER_AUTHORITY_v1.md](C:/bot7/docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md). Split-authority decision record.
- `FORECAST_CALIBRATION_DIAGNOSTIC_v1.md` — add [FORECAST_CALIBRATION_DIAGNOSTIC_v1.md](C:/bot7/docs/RESEARCH/FORECAST_CALIBRATION_DIAGNOSTIC_v1.md). Forecast decommission diagnostic source.
- `MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md` — add [MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md](C:/bot7/docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md). Independent research variant.
- `MARKET_DECISION_SUPPORT_RESEARCH_v1_codex.md` — add [MARKET_DECISION_SUPPORT_RESEARCH_v1_codex.md](C:/bot7/docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_codex.md). Independent research variant.
- `FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md` — add [FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md](C:/bot7/docs/RESEARCH/FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md). Independent rebuild research variant.
- `FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md` — add [FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md](C:/bot7/docs/RESEARCH/FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md). Independent rebuild research variant.
- `MTF_CALIBRATION_HISTOGRAM_v1.md` — add [MTF_CALIBRATION_HISTOGRAM_v1.md](C:/bot7/docs/RESEARCH/MTF_CALIBRATION_HISTOGRAM_v1.md). Confidence-scale verification before threshold semantics.

## DELETE

- `REGULATION_v0_1.md` — remove from Project Knowledge in favor of [REGULATION_v0_1_1.md](C:/bot7/docs/REGULATION_v0_1_1.md). Reason: superseded version.
- `docs/CONTEXT/STATE_CURRENT_2026-05-05_EOS.md` — remove from Project Knowledge if present. Reason: superseded by canonical [STATE_CURRENT_2026-05-05_EOS.md](C:/bot7/docs/STATE/STATE_CURRENT_2026-05-05_EOS.md) in the `STATE` tree.

## KEEP UNCHANGED

- `REGULATION_v0_1_1.md` — active operational regulation.
- `REGIME_OVERLAY_v2_1.md` — overlay source of truth.
- `REGIME_OVERLAY_v3.md` — infeasibility/constraint companion.
- `TRANSITION_MODE_COMPARE_v2.md` — transition-policy evidence.
- `HYSTERESIS_CALIBRATION_v1.md` — H=1 calibration evidence.
- `REGIME_PERIODS_2025_2026.md` — regime distribution reference.
- `BACKTEST_AUDIT.md` — audit anchor and closure map source.
- `P8_DUAL_MODE_COORDINATOR_v0_1.md` — historical design with Q2 reframe note.
- `docs/STATE/PROJECT_MAP.md` — keep unchanged if already present in Project Knowledge; do not merge automatically with the root stub.

## ARCHIVE

- Raw structured companions from this session may stay on disk only unless operator wants Project Knowledge retention:
  - `_market_decision_support_research_raw_claude.json`
  - `_market_decision_support_research_raw_codex.json`
  - `_forecast_model_replacement_research_raw_claude.json`
  - `_forecast_model_replacement_research_raw_codex.json`
- Earlier handoff/state snapshots superseded by the 2026-05-05 EOS state may be archived from Project Knowledge while kept on disk for chronology:
  - `HANDOFF_2026-05-04.md`
  - older `STATE_CURRENT_*` snapshots replaced by the 2026-05-05 EOS canonical state

## Notes

- This inventory recommends sync actions only. No files should be deleted or moved on disk by this document.
- If Project Knowledge currently stores both `docs/PROJECT_MAP.md` and `docs/STATE/PROJECT_MAP.md`, treat that as a manual cleanup question rather than auto-deleting one of them.
