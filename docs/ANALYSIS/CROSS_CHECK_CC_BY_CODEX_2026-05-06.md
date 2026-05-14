# CROSS-CHECK CC BY CODEX — 2026-05-06

## §1 Summary verdict

Numerical core:
`MEDIUM`.
По OI block совпадение высокое, по PnL для одинаковых уровней совпадение полное, но по extended backtest и по "reconciled group" у двух прогонов разные definitions.

Критические проблемы:
- Claude Code корректно воспроизвёл `406` overlap и `1339` extended raw analogs, но в финальном exit-документе смешал `reconciled v3` с собственной subgroup `n=31/32`.
- Claude Code использовал time-based statements и estimated probabilities без точного `n`, что противоречит исходным правилам письма.
- Codex в своём OI документе завысил `current OI divergence`: на source-consistent historical proxy это `False`, не `True`.

Использовать обе работы как foundation:
`частично`.
Для extended raw analog search и overlap continuity сильнее работа Claude Code.
Для OI core usable обе.
Для final operator-facing reconciliation нужен отдельный unified TZ.

## §2 Comparison tables

### Блок 1 — Extended backtest

| Metric | Codex | Claude Code | Diff |
|---|---|---|---|
| Period covered | 2024-04-25 → 2026-04-29 | 2024-01-01 → 2026-05-03 | CC шире по периоду |
| Source data file | `data/whatif_v3/btc_1m_enriched_2y.parquet` | `state/pattern_memory_BTCUSDT_1h_2024/2025/2026.csv` | другой source |
| Search criterion | 7–12%, 4–8 дней, max pullback ≤5%, local max | original-style 6d, +8..11%, off_high≤1.5%, anchor age 96–143h | definitions разные |
| Total analogs | 401 | 1339 | `+938` у CC |
| 1y overlap count | 154 на codex criterion | 406 | не сопоставимо напрямую |
| Distribution down/up/pull/side | 19.5 / 38.4 / 33.2 / 9.0 | 25.2 / 37.8 / 22.7 / 14.3 | materially different |
| Reconciled group reproduction | ref only: `n=52`, `0 / 46.2 / 53.8 / 0` | independent: `n=31`, `0 / 74.2 / 25.8 / 0` | существенное расхождение |

Verdict:
`401 vs 1339` не доказывает bug у CC.
Это следствие разных criteria.
Для continuity с original `406` Claude Code ближе к source-of-truth.

### Блок 2 — OI deep dive

| OI Bucket | Codex | Claude Code | Match? |
|---|---|---|---|
| OI_up >5% | `n=208`, `25.5 / 26.9 / 32.2 / 15.4` | `n=208`, `25.5 / 26.9 / 32.2 / 15.4` | YES |
| OI_flat ±5% | `n=156`, `3.2 / 28.8 / 35.9 / 32.1` | `n=156`, `3.2 / 28.8 / 35.9 / 32.1` | YES |
| OI_down >5% | `n=42`, `0 / 0 / 100 / 0` | `n=42`, `0 / 0 / 100 / 0` | YES |
| OI divergence | `n=96`, `5.2 / 5.2 / 84.4 / 5.2` | `n=96`, `5.2 / 5.2 / 84.4 / 5.2` | YES |
| Current OI bucket | stable ±5% | stable ±5% | YES |
| Current OI change | `-0.94%` | `-0.94%` | YES |
| Current OI divergence | `True` | `False` | NO |

Verdict:
OI distributions совпали полностью.
Единственный конфликт — `current OI divergence`, и здесь source-consistent calculation у Claude Code сильнее.

### Блок 3 — 3 варианта

| Aspect | Codex | Claude Code | Verdict |
|---|---|---|---|
| Category coverage | защитный + opportunistic + hybrid | защитный + opportunistic + hybrid | match |
| Stop ladder | `82,400 / 84,000 / 85,000` | `82,400 / 83,000 / 84,000 / 85,000` | CC добавил extra tier |
| Pullback ladder | `80,000 / 79,036 / 77,000` | `80,000 / 79,036 / 78,000 / 77,000` | CC добавил extra tier |
| PnL common stop levels | same | same | YES |
| PnL common pullback levels | same | same | YES |
| Probability basis | reconciled `n=52` + OI buckets | mixed: `n=31/32`, `n=42`, plus estimated bands | CC weaker |
| Timing-free requirement | mostly respected | violated (`median 65h`, `24h after flip`) | FAIL in CC |

## §3 Audit findings

### Bugs / issues found

1. Mislabelled reconciled group in CC final document.  
Files:
- [docs/ANALYSIS/EXIT_VARIANTS_2026-05-06_cc.md](C:/bot7/docs/ANALYSIS/EXIT_VARIANTS_2026-05-06_cc.md:29)
- [scripts/_extended_analog_search_cc.py](C:/bot7/scripts/_extended_analog_search_cc.py:233)

Issue:
CC labels `n=31/32` subgroup as `reconciled v3`, but published reconciled v3 reference is `n=52`, `46.2 / 53.8`.
The CC subgroup is an independent recomputation with different factor definition, not the same published group.

2. Current OI note has timestamp inconsistency.  
File:
- [scripts/_oi_deep_dive_cc.py](C:/bot7/scripts/_oi_deep_dive_cc.py:187)

Issue:
`as_of_bar` is `2026-05-01T00:00:00+00:00`, but note says `2026-04-30 23:00 UTC`.
This is minor, but the report should use one timestamp convention.

3. CC OI JSON is not fully auditable because records are truncated to first 50.  
File:
- [scripts/_oi_deep_dive_cc.py](C:/bot7/scripts/_oi_deep_dive_cc.py:207)

Issue:
The script claims `n=42` with `100% pullback_continuation`, but output JSON stores only `enriched[:50]`.
The calculation may still be correct, but the artifact is weaker for third-party audit.

4. CC exit document violates no-timing / no-estimate rule.  
File:
- [docs/ANALYSIS/EXIT_VARIANTS_2026-05-06_cc.md](C:/bot7/docs/ANALYSIS/EXIT_VARIANTS_2026-05-06_cc.md:104)

Issue:
Uses `median 65h`, `24h after flip`, and `estimated 25-35%`.
These are outside the stated document constraints.

### Sanity checks

| Check | Result | Verdict |
|---|---|---|
| `pattern_memory_2024/2025/2026.csv` coverage | `2024-01-01 -> 2026-05-03`, rows `8785 / 8761 / 2929` | PASS |
| CC extended JSON record count | `1339` records, `406 overlap`, `933 pre-1y` | PASS |
| CC overlap vs original 406 | exact `406` | PASS |
| `OI_down >5%` all pullback | `42/42`, no exceptions in aggregate | PASS |
| OI bucket threshold | both use `±5%` | PASS |
| Current OI bucket | both `stable ±5%`, `oi_change=-0.94%` | PASS |
| PnL arithmetic for 1.416 BTC | `82,400=-4763`, `84,000=-7029`, `77,000=+2883` | PASS |

### Edge cases

| Edge case | Observation |
|---|---|
| Current OI divergence | historical source gives `False`, because last 144h price fell `77541.63 -> 75923.86` while OI also fell |
| CC triple cross `OI_flat ±5% + funding_negative` | `n=2`, too small for operator-facing probability |
| CC final doc | still references that tiny / alternate subgroup indirectly in operator logic |

## §4 Конфликты разобраны

### Конфликт 1 — Total analogs `401` vs `1339`

Verdict:
`правее Claude Code`, если цель — extended version of original analog search.

Почему:
- Claude Code использует original-style search: `144h`, `+8..11%`, `off_high<=1.5%`, `anchor_age 96..143`.
- Это подтверждается exact overlap `406` в периоде `2025-05-01 -> 2026-05-01`.
- Codex использовал другой later-TZ criterion: `7–12%`, `4–8 дней`, `max pullback<=5%`, local max.

Итог:
`1339` и `401` — это не "кто-то ошибся в счёте".
Это разные universes.

### Конфликт 2 — Reconciled group reproduction

Verdict:
`правее published v3 reference`, не Claude и не Codex independent run.

Почему:
- Published source-of-truth: [docs/ANALYSIS/SHORT_EXIT_OPTIONS_2026-05-06.md](C:/bot7/docs/ANALYSIS/SHORT_EXIT_OPTIONS_2026-05-06.md) закрепляет `n=52`, `46.2% up_extension / 53.8% pullback_continuation`.
- В `_short_exit_multifactor.py` group definition is `(fund_now < 0) AND (vola_trend == compressing)`, не `funding_negative < -5e-5`.
- Claude Code uses stricter `funding_negative` cutoff plus independent volatility from `pattern_memory`, поэтому получает `n=31`.

Итог:
`n=31` — valid independent subgroup, но не valid replacement for reconciled v3.
В operator-facing document его нельзя маркировать как `reconciled v3`.

### Конфликт 3 — Current OI bucket / divergence

Verdict:
- Bucket: `оба правы`, `stable ±5%`.
- Divergence: `правее Claude Code` на source-consistent historical proxy.

Почему:
- На последнем 1y bar `oi_change=-0.94%`.
- За тот же 144h window price went `77541.63 -> 75923.86`, то есть `price_up=False`.
- Значит `price↑ + OI↓` на этом source нет.

Итог:
Codex own doc здесь смешал live setup direction с stale historical OI snapshot.
Для historical proxy divergence should be `False`.

## §5 Recommendation

Primary use:
- Для extended raw analog count и continuity with original `406` использовать Claude Code Block 1.
- Для OI distributions можно использовать любую из двух работ: numerical core совпал.
- Для final operator-facing exit document ни одну версию нельзя брать как final без reconciliation pass.

Что исправить перед reconciliation:
1. Зафиксировать два разных universes:
   `original-style extended search` vs `later best-effort price-only search`.
2. Явно развести group names:
   `published reconciled v3 n=52` vs `independent strict fund_neg subgroup n=31`.
3. В OI current-state использовать один source:
   либо historical proxy целиком, либо live price + live OI.
   Микс из live price и stale OI не использовать.
4. Убрать из final document:
   time-based statements, estimated ranges without exact `n`, and subgroup labels that mimic v3.

Что MAIN’у нужно решить в reconciliation TZ:
- Какой exact criterion считать canonical for extended search.
- Какой exact funding threshold считать canonical: `<0` или `<-5e-5`.
- Какой source считать canonical for current-state OI: historical last bar or live state.
- Какой subgroup должен быть operator-facing probability base: published `n=52` или new strict subgroup after formal redefinition.
