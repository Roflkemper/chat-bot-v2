# DEDUP THRESHOLD TUNING V1

Date: 2026-05-04
Input log: `state/decision_log/events.jsonl` (2026-04-30 12:07 UTC -> 2026-05-04 20:08 UTC, 2257 events total).
Scope: `PNL_EVENT`, `BOUNDARY_BREACH`, `PNL_EXTREME` only.
Method: replay current decision-log events in memory with per-emitter cooldown + state-delta dedup; choose configs landing in the healthy suppression zone 20-70%.

## Baseline vs Tuned

| Emitter | Baseline config | Baseline suppression | Tuned config | Tuned suppression | Healthy zone hit? |
|---|---|---:|---|---:|---|
| PNL_EVENT | cooldown `900s`, delta `200.0`, cluster `0s` | 88.6% | cooldown `300s`, delta `25.0`, cluster `0s` | 48.4% | YES |
| BOUNDARY_BREACH | cooldown `600s`, delta `50.0`, cluster `0s` | 94.9% | cooldown `600s`, delta `0.0`, cluster `0s` | 49.1% | YES |
| PNL_EXTREME | cooldown `1800s`, delta `500.0`, cluster `0s` | 80.7% | cooldown `600s`, delta `25.0`, cluster `0s` | 49.6% | YES |

## Final Tuned Configs

| Emitter | Cooldown | Delta threshold | Cluster window | Final suppression rate | Why this setting |
|---|---:|---:|---:|---:|---|
| PNL_EVENT | 300s | 25 USD | 0s (disabled) | 48.4% | Keeps noisy 15m PnL drift from re-firing on tiny moves, but stops over-suppressing long same-direction sequences. |
| BOUNDARY_BREACH | 600s | 0 USD | 0s (disabled) | 49.1% | Price often stays pinned at the same level for many polls; zero delta lets cooldown do the dedup work and lands exactly in the healthy band. |
| PNL_EXTREME | 600s | 25 USD | 0s (disabled) | 49.6% | Extreme-PnL alerts should stay rare, but 30m/500 USD was too blunt; 10m + 25 USD restores meaningful follow-up without spam. |

## Rate Breakdown

| Emitter | Candidates | Would emit | Suppressed | Suppressed by cooldown | Suppressed by state delta | Suppression % |
|---|---:|---:|---:|---:|---:|---:|
| PNL_EVENT | 818 | 422 | 396 | 0 | 396 | 48.4% |
| BOUNDARY_BREACH | 1042 | 530 | 512 | 512 | 0 | 49.1% |
| PNL_EXTREME | 119 | 60 | 59 | 43 | 16 | 49.6% |

## Notes

- `PNL_EVENT` baseline was 88.6% suppression. Most of that came from the 200 USD state-delta threshold, not from cooldown alone. Lowering the delta to 25 USD fixes the over-suppression immediately.
- `BOUNDARY_BREACH` baseline was 94.9% suppression because the same price repeated while the bot stayed out-of-bounds. In this log, a non-zero price delta mostly acted as a second hard wall on top of cooldown. Setting delta to zero lets the 10-minute cooldown become the main control.
- `PNL_EXTREME` baseline was 80.7% suppression. The tuned version moves it to 49.6%, which is near the center of the target band while still keeping the emitter meaningfully quieter than raw events.
- Cluster window is left disabled (`0s`) for all three emitters in this v1 tuning. On this decision-log dataset, the healthy-zone fix came from cooldown/delta tuning alone; adding synthetic cluster collapse was unnecessary and would have mixed replay semantics with event-shape assumptions not present in the stored log.

## Suppression Examples Under Tuned Config

### PNL_EVENT
- `2026-04-30T14:36:04.838251+00:00` ? `state` ? Сильное изменение нереализованного PnL за 15 минут: +795 USD
- `2026-04-30T14:46:04.520139+00:00` ? `state` ? Сильное изменение нереализованного PnL за 15 минут: +821 USD
- `2026-04-30T14:56:09.191420+00:00` ? `state` ? Сильное изменение нереализованного PnL за 15 минут: +758 USD

### BOUNDARY_BREACH
- `2026-04-30T12:07:31.363293+00:00` ? `cooldown` ? Цена вышла выше верхней границы бота SHORT_ВЫХ
- `2026-04-30T12:07:31.363293+00:00` ? `cooldown` ? Цена вышла выше верхней границы бота ЛОНГ_1%
- `2026-04-30T12:07:31.363293+00:00` ? `cooldown` ? Цена вышла выше верхней границы бота SHORT_1%

### PNL_EXTREME
- `2026-04-30T12:07:31.363293+00:00` ? `cooldown` ? Новый минимум PnL за 24ч: 655 USD
- `2026-04-30T12:07:33.189638+00:00` ? `cooldown` ? Новый минимум PnL за 24ч: 655 USD
- `2026-04-30T12:11:00.006960+00:00` ? `cooldown` ? Новый максимум PnL за 24ч: 658 USD

