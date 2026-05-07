# REAL_SUMMARY_2026-04-28 (TZ-041)

Цель: пересчитать CI 95% для P-6 vs P-7 на real tracker snapshots (окно tracker coverage),
и сравнить с synth (SUMMARY 2026-04-27).

## Окно

Окно выбирается по tracker snapshots (TEST_3, BTC-LONG-B, BTC-LONG-C) и клипается по coverage `features_out`,
т.к. генератор episodes (`src/episodes/extractor.py`) требует валидные feature partitions с DatetimeIndex.

- start_ts: 2026-04-24T09:35:32+00:00
- end_ts:   2026-04-24T23:00:00+00:00

Файл: `whatif/episodes_window.json`

## Результат

В этом окне не найдено ни одного эпизода типов `rally_strong`, `rally_critical`, `dump_strong`, `dump_critical`
(генератор episodes вернул 0 строк).

Следствие:
- real-replay для P-1/P-2/P-6/P-7 на этом окне не может дать rows>0
- bootstrap CI 95% на real data для P-6/P-7 не пересчитывается (нет выборки)
- synth-vs-real delta не считается

## Что нужно дальше

1) Расширить coverage `features_out` на даты tracker (2026-04-25..2026-04-28), затем повторить TZ-041.
2) Либо накопить больше tracker времени на период, где в `features_out` будут эпизоды rally/dump.

