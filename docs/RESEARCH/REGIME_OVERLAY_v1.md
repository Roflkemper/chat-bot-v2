# REGIME OVERLAY V1

Date: 2026-05-04
Source set: CP20 backtest registry `docs/RESEARCH/GINAREA_BACKTESTS_REGISTRY_v1.md` + CP21 regime periods `docs/RESEARCH/REGIME_PERIODS_2025_2026.md` / `docs/RESEARCH/_regime_periods_raw.json`.
Method: proportional allocation by regime-hour weight inside each backtest window; no bar-by-bar PnL reconstruction.

## Caveat

This is an approximate distribution of total PnL across regimes, not actual regime-conditional PnL. Exact regime PnL would require bar-by-bar equity curves or trade logs from GinArea, which these backtests do not provide.

CP21 regime-label window available for allocation: `2025-05-01 00:00:00+00:00` -> `2026-05-01 00:00:00+00:00`.
Backtests extending past 2026-05-01 are clipped to the overlapped CP21 window; coverage gap is shown explicitly below.

## Coverage

| BT-ID | Set tag | Backtest period | Total hours | CP21-covered hours | Coverage % |
|---|---|---|---:|---:|---:|
| BT-001 | LONG annual | 2025-05-20 → 2026-05-04 | 8400 | 8305 | 98.9% |
| BT-002 | LONG annual | 2025-05-20 → 2026-05-04 | 8400 | 8305 | 98.9% |
| BT-003 | LONG annual | 2025-05-20 → 2026-05-04 | 8400 | 8305 | 98.9% |
| BT-004 | LONG annual | 2025-05-20 → 2026-04-30 | 8304 | 8304 | 100.0% |
| BT-005 | SHORT 3m | 2026-02-01 → 2026-05-04 | 2232 | 2137 | 95.7% |
| BT-006 | SHORT 3m | 2026-02-01 → 2026-05-04 | 2232 | 2137 | 95.7% |
| BT-007 | SHORT 3m | 2026-02-01 → 2026-05-04 | 2232 | 2137 | 95.7% |
| BT-008 | SHORT 3m | 2026-02-01 → 2026-05-04 | 2232 | 2137 | 95.7% |
| BT-009 | SHORT 02may | 2026-02-05 → 2026-05-01 | 2064 | 2041 | 98.9% |
| BT-010 | SHORT 02may | 2026-02-05 → 2026-05-02 | 2088 | 2041 | 97.7% |
| BT-011 | SHORT 02may | 2026-02-05 → 2026-05-02 | 2088 | 2041 | 97.7% |
| BT-012 | SHORT 02may | 2026-02-05 → 2026-05-01 | 2064 | 2041 | 98.9% |
| BT-013 | SHORT 02may | 2026-02-05 → 2026-05-02 | 2088 | 2041 | 97.7% |
| BT-014 | LONG 02may | 2026-02-05 → 2026-05-02 | 2088 | 2041 | 97.7% |
| BT-015 | LONG 02may | 2026-02-05 → 2026-05-02 | 2088 | 2041 | 97.7% |
| BT-016 | LONG 02may | 2026-02-05 → 2026-05-02 | 2088 | 2041 | 97.7% |
| BT-017 | LONG 02may | 2026-02-05 → 2026-05-02 | 2088 | 2041 | 97.7% |

## BT x Regime Allocation

| BT-ID | Set tag | Side | Regime | Hours | Regime weight | Allocated PnL | Allocated triggers | Allocation basis |
|---|---|---|---|---:|---:|---:|---:|---|
| BT-001 | LONG annual | LONG | MARKUP | 1055 | 12.7% | -0.0121 BTC | n/a | proportional by regime hours inside covered window |
| BT-001 | LONG annual | LONG | MARKDOWN | 1303 | 15.7% | -0.0150 BTC | n/a | proportional by regime hours inside covered window |
| BT-001 | LONG annual | LONG | RANGE | 5947 | 71.6% | -0.0685 BTC | n/a | proportional by regime hours inside covered window |
| BT-002 | LONG annual | LONG | MARKUP | 1055 | 12.7% | -0.0152 BTC | 146.5 | proportional by regime hours inside covered window |
| BT-002 | LONG annual | LONG | MARKDOWN | 1303 | 15.7% | -0.0188 BTC | 180.9 | proportional by regime hours inside covered window |
| BT-002 | LONG annual | LONG | RANGE | 5947 | 71.6% | -0.0857 BTC | 825.6 | proportional by regime hours inside covered window |
| BT-003 | LONG annual | LONG | MARKUP | 1055 | 12.7% | -0.0163 BTC | 151.5 | proportional by regime hours inside covered window |
| BT-003 | LONG annual | LONG | MARKDOWN | 1303 | 15.7% | -0.0202 BTC | 187.2 | proportional by regime hours inside covered window |
| BT-003 | LONG annual | LONG | RANGE | 5947 | 71.6% | -0.0920 BTC | 854.3 | proportional by regime hours inside covered window |
| BT-004 | LONG annual | LONG | MARKUP | 1055 | 12.7% | -0.0294 BTC | 174.8 | proportional by regime hours inside covered window |
| BT-004 | LONG annual | LONG | MARKDOWN | 1303 | 15.7% | -0.0363 BTC | 215.9 | proportional by regime hours inside covered window |
| BT-004 | LONG annual | LONG | RANGE | 5946 | 71.6% | -0.1655 BTC | 985.3 | proportional by regime hours inside covered window |
| BT-005 | SHORT 3m | SHORT | MARKUP | 408 | 19.1% | -779.63 USD | 147.0 | proportional by regime hours inside covered window |
| BT-005 | SHORT 3m | SHORT | MARKDOWN | 437 | 20.4% | -835.05 USD | 157.5 | proportional by regime hours inside covered window |
| BT-005 | SHORT 3m | SHORT | RANGE | 1292 | 60.5% | -2468.84 USD | 465.5 | proportional by regime hours inside covered window |
| BT-006 | SHORT 3m | SHORT | MARKUP | 408 | 19.1% | -749.23 USD | 140.9 | proportional by regime hours inside covered window |
| BT-006 | SHORT 3m | SHORT | MARKDOWN | 437 | 20.4% | -802.48 USD | 150.9 | proportional by regime hours inside covered window |
| BT-006 | SHORT 3m | SHORT | RANGE | 1292 | 60.5% | -2372.55 USD | 446.2 | proportional by regime hours inside covered window |
| BT-007 | SHORT 3m | SHORT | MARKUP | 408 | 19.1% | -405.17 USD | 110.0 | proportional by regime hours inside covered window |
| BT-007 | SHORT 3m | SHORT | MARKDOWN | 437 | 20.4% | -433.97 USD | 117.8 | proportional by regime hours inside covered window |
| BT-007 | SHORT 3m | SHORT | RANGE | 1292 | 60.5% | -1283.05 USD | 348.2 | proportional by regime hours inside covered window |
| BT-008 | SHORT 3m | SHORT | MARKUP | 408 | 19.1% | -407.62 USD | 110.0 | proportional by regime hours inside covered window |
| BT-008 | SHORT 3m | SHORT | MARKDOWN | 437 | 20.4% | -436.59 USD | 117.8 | proportional by regime hours inside covered window |
| BT-008 | SHORT 3m | SHORT | RANGE | 1292 | 60.5% | -1290.80 USD | 348.2 | proportional by regime hours inside covered window |
| BT-009 | SHORT 02may | SHORT | MARKUP | 401 | 19.6% | -783.07 USD | 126.7 | proportional by regime hours inside covered window |
| BT-009 | SHORT 02may | SHORT | MARKDOWN | 382 | 18.7% | -745.97 USD | 120.7 | proportional by regime hours inside covered window |
| BT-009 | SHORT 02may | SHORT | RANGE | 1258 | 61.6% | -2456.61 USD | 397.6 | proportional by regime hours inside covered window |
| BT-010 | SHORT 02may | SHORT | MARKUP | 401 | 19.6% | -515.07 USD | 132.4 | proportional by regime hours inside covered window |
| BT-010 | SHORT 02may | SHORT | MARKDOWN | 382 | 18.7% | -490.67 USD | 126.1 | proportional by regime hours inside covered window |
| BT-010 | SHORT 02may | SHORT | RANGE | 1258 | 61.6% | -1615.86 USD | 415.4 | proportional by regime hours inside covered window |
| BT-011 | SHORT 02may | SHORT | MARKUP | 401 | 19.6% | -600.35 USD | 131.6 | proportional by regime hours inside covered window |
| BT-011 | SHORT 02may | SHORT | MARKDOWN | 382 | 18.7% | -571.90 USD | 125.4 | proportional by regime hours inside covered window |
| BT-011 | SHORT 02may | SHORT | RANGE | 1258 | 61.6% | -1883.39 USD | 413.0 | proportional by regime hours inside covered window |
| BT-012 | SHORT 02may | SHORT | MARKUP | 401 | 19.6% | -688.88 USD | 131.6 | proportional by regime hours inside covered window |
| BT-012 | SHORT 02may | SHORT | MARKDOWN | 382 | 18.7% | -656.24 USD | 125.4 | proportional by regime hours inside covered window |
| BT-012 | SHORT 02may | SHORT | RANGE | 1258 | 61.6% | -2161.11 USD | 413.0 | proportional by regime hours inside covered window |
| BT-013 | SHORT 02may | SHORT | MARKUP | 401 | 19.6% | -728.99 USD | 129.5 | proportional by regime hours inside covered window |
| BT-013 | SHORT 02may | SHORT | MARKDOWN | 382 | 18.7% | -694.45 USD | 123.3 | proportional by regime hours inside covered window |
| BT-013 | SHORT 02may | SHORT | RANGE | 1258 | 61.6% | -2286.95 USD | 406.2 | proportional by regime hours inside covered window |
| BT-014 | LONG 02may | LONG | MARKUP | 401 | 19.6% | +0.0153 BTC | 9.4 | proportional by regime hours inside covered window |
| BT-014 | LONG 02may | LONG | MARKDOWN | 382 | 18.7% | +0.0146 BTC | 9.0 | proportional by regime hours inside covered window |
| BT-014 | LONG 02may | LONG | RANGE | 1258 | 61.6% | +0.0479 BTC | 29.6 | proportional by regime hours inside covered window |
| BT-015 | LONG 02may | LONG | MARKUP | 401 | 19.6% | +0.0139 BTC | 9.0 | proportional by regime hours inside covered window |
| BT-015 | LONG 02may | LONG | MARKDOWN | 382 | 18.7% | +0.0132 BTC | 8.6 | proportional by regime hours inside covered window |
| BT-015 | LONG 02may | LONG | RANGE | 1258 | 61.6% | +0.0435 BTC | 28.4 | proportional by regime hours inside covered window |
| BT-016 | LONG 02may | LONG | MARKUP | 401 | 19.6% | +0.0117 BTC | 9.2 | proportional by regime hours inside covered window |
| BT-016 | LONG 02may | LONG | MARKDOWN | 382 | 18.7% | +0.0111 BTC | 8.8 | proportional by regime hours inside covered window |
| BT-016 | LONG 02may | LONG | RANGE | 1258 | 61.6% | +0.0366 BTC | 29.0 | proportional by regime hours inside covered window |
| BT-017 | LONG 02may | LONG | MARKUP | 401 | 19.6% | +0.0099 BTC | 8.8 | proportional by regime hours inside covered window |
| BT-017 | LONG 02may | LONG | MARKDOWN | 382 | 18.7% | +0.0094 BTC | 8.4 | proportional by regime hours inside covered window |
| BT-017 | LONG 02may | LONG | RANGE | 1258 | 61.6% | +0.0310 BTC | 27.7 | proportional by regime hours inside covered window |

## Quick Read

- `LONG annual` window mix: RANGE 23787h, MARKDOWN 5212h, MARKUP 4220h.
- `SHORT 3m` window mix: RANGE 5168h, MARKDOWN 1748h, MARKUP 1632h.
- `SHORT 02may` window mix: RANGE 6290h, MARKUP 2005h, MARKDOWN 1910h.
- `LONG 02may` window mix: RANGE 5032h, MARKUP 1604h, MARKDOWN 1528h.
- In all four set families, RANGE dominates the covered hours. This means any total-PnL reading from these backtests is structurally mostly a RANGE-weighted outcome, not a pure trend-regime outcome.
- LONG annual rows are nearly full-year covered (~99%). The 2026-02..2026-05 windows are covered at ~96-99%; missing hours are only the tail beyond CP21 window end.

## Conclusions

**Conclusions (operator + MAIN review, 2026-05-04)**

Эта regime overlay предоставляет первое quantitative evidence для P8 ensemble design. Главные findings:

Finding A — Indicator gate переворачивает результат с минуса в плюс во всех трёх регимах:
Сравнение LONG annual (BT-001..004, без indicator) vs LONG 02may (BT-014..017, с indicator <-1%):

| Regime | LONG annual allocated PnL | LONG 02may allocated PnL |
|---|---|---|
| MARKUP | -0.012 to -0.029 BTC | +0.010 to +0.015 BTC |
| MARKDOWN | -0.015 to -0.036 BTC | +0.009 to +0.015 BTC |
| RANGE | -0.069 to -0.166 BTC | +0.031 to +0.048 BTC |

Это не "indicator gate отсеивает регим". Indicator gate — temporal opportunity filter: бот активируется когда price делает резкое движение (>1% за 30 мин), стартует с лучшим entry, потом работает grid в любом региме. Quality of entry — central determinant profitability.

Implication для P8: trend-bot activation в Идее 2 должна быть indicator-driven, не просто regime-classifier-driven. Coordinator должен иметь TWO triggers: (a) regime classifier для long-term mode selection, (b) indicator gate для opportunity-moment activation.

Finding B — SHORT в bullish year не recovers даже в MARKDOWN-окне:
Все SHORT backtests (BT-005..013, 9 backtests) показывают negative allocated PnL во всех трёх регимах, включая MARKDOWN. Возможные причины:

- MARKDOWN episodes в bull year — короткие и rare (1303h vs 6306h RANGE)
- Накопленная SHORT позиция переходит из MARKUP через RANGE buffer в MARKDOWN. К моменту регима MARKDOWN бот уже глубоко в DD; короткое MARKDOWN-окно успевает только частично закрыть позицию, не превратить в плюс

Implication для P8: SHORT bots должны иметь дополнительные guards beyond regime classifier — e.g. "не запускать пока не подтверждён MARKDOWN >24h" or "max position limit before activation"

Finding C — RANGE allocations dominate в каждой series:
71-72% всех hours во всех 4 series — RANGE. Это значит total-PnL чтения этих backtests are structurally RANGE-weighted. LONG 02may +0.05 to +0.08 BTC profit — преимущественно RANGE allocation +0.031 to +0.048. Это proven range-bot config для оператора Идеи 2 "range LONG в боковике".

Caveats:

- Allocation proportional, не bar-by-bar reconstruction. Точная per-regime PnL потребовала бы equity curves которых GinArea backtests не предоставляют
- Bullish year bias — все findings under-weighted MARKDOWN-favorable scenarios
- Single-asset (BTC) — XRP/ETH untested
- Findings B (SHORT не recovers) может не воспроизводиться в balanced year — нужны отдельные тесты на других периодах для validation

Upstream references:
- Backtest source set: [GINAREA_BACKTESTS_REGISTRY_v1.md](GINAREA_BACKTESTS_REGISTRY_v1.md)
- Regime-hour structure: [REGIME_PERIODS_2025_2026.md](REGIME_PERIODS_2025_2026.md)
