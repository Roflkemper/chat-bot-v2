---
# Skill: dataset provenance tracker

## For whom
Этот skill применяется ARCHITECT'ом и Code-исполнителем при
работе с любым input dataset (OHLCV CSV, parquet, snapshots,
ground truth JSON) который влияет на published результат.

## Trigger
Любое из:
- Code открывает `backtests/frozen/*.csv` или `*.parquet`
- Code открывает `data/calibration/ginarea_ground_truth_*.json`
- Code reads `state_latest.json`, `decisions.parquet`,
  `operator_journal/*`, `state_snapshot/*`
- TZ или report ссылается на dataset by filename
- Reconcile / backtest / calibration creates new artifact в
  `reports/`, `state/`, `data/`

## Rule
**Любой dataset используемый для published статистики MUST иметь
provenance: source URL/script + capture window + commit/version
+ row count + first/last ts:**

```
provenance_block = {
    source: "binance_public_rest" | "ginarea_screenshots" | "operator_manual" | ...
    capture_window: ISO start..end (period of data NOT capture date)
    capture_date: when ingest ran
    capture_method: script + commit hash, or "manual entry by operator"
    rows: int
    first_ts: ISO
    last_ts: ISO
    version: incremental version or hash of file content
    notes: known caveats
}
```

Provenance MUST быть discoverable from one of:
- File header / sidecar `.meta.json`
- `docs/STATE/ohlcv_ingest_log.jsonl` (existing for CSVs)
- Top of source script that produced it
- INCIDENTS.md if data was modified ad-hoc

## Mandatory steps BEFORE использования dataset в published result

1. Locate provenance:
   - For OHLCV CSVs: check `docs/STATE/ohlcv_ingest_log.jsonl`
   - For ground truth JSON: check `version`/`captured_at` field в файле
   - For state snapshots: `_metadata.json` или git log of containing commit
   - For reports: header of source script with commit hash

2. Verify provenance is current:
   - capture_window covers period needed for analysis
   - rows count matches expected (no truncation)
   - last_ts ≥ analysis_window.end (data not stale)

3. Если provenance missing or incomplete:
   - STOP. Не использовать в published result.
   - Открыть TZ-INVENTORY-DATASET-{name} для backfill metadata.

4. Если dataset modified vs original ingest (manual edit, dedup,
   filter):
   - Log в INCIDENTS.md or change-log inside dataset folder.
   - Note modification в final report under "data caveats".

## Forbidden
- Использовать dataset без provenance в operator-facing report.
- "Я уверен что файл правильный, проверять не буду".
- Регенерировать frozen baseline без сохранения предыдущей версии
  и записи в provenance что rebuild.
- Mixing data from разных capture windows в один dataset без явной
  разметки.

## Allowed
- Skip provenance check для:
  - Pure exploratory ad-hoc анализ где результат явно "EXPLORATORY".
  - Smoke tests с synthetic data.
  - Re-run on same dataset что уже использовался в predecessor TZ
    (provenance walked once, не нужно перепроверять каждую TZ).

## Recovery
Если obvious provenance gap обнаружен post-publication:
- Записать в INCIDENTS.md.
- Update report с "provenance reconstructed from ..." блоком.
- Open TZ-FIX-PROVENANCE-{dataset} если дыра systematic.

## Why
Из проектной истории:
- `BTCUSDT_1s_2y.csv` имел misleading filename ("_2y") хотя
  фактически содержал только 30 days. Без provenance check легко
  использовать как "год данных" → false K calibration.
- 4 месяца назад был бы restored module из `_recovery/`. Если бы
  его использовали без provenance check, не отследили бы что он
  устарел vs current state.
- `ginarea_ground_truth_v1.json` имеет period=1y но screenshots
  captured at single point — provenance явно перечисляет в notes.

PROJECT_CONTEXT §9 trader-first filter (б) "тестирование hypothesis
на real data" — без provenance не известно НАСКОЛЬКО real эта data.

Without dataset provenance discipline:
- Calibration K computed on stale/wrong data → wrong /advise.
- Backtest runs on partially-modified frozen → false confidence.
- Re-run "on same data" produces different result because someone
  silently rotated the file.

Это complement к param_provenance_tracker (который про CONSTANTS).
Этот skill — про DATA.

Related skills: param_provenance_tracker (constants), 
data_freshness_check (recency only), trader_first_filter.
