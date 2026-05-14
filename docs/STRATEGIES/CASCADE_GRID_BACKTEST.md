# Cascade Grid Backtest — 3-tier laddered shorts+longs

**Период:** 2y BTCUSDT 1m  (1,174,306 bars)
**Триггер:** high-low range за 30 мин
**Tier-1:** trigger 1%, size $1000, TP +1%, SL -3%
**Tier-2:** trigger 2%, size $2000, TP +2%, SL -6%
**Tier-3:** trigger 3%, size $3000, TP +3%, SL -9%
**Cooldown:** 60min между bundles, max hold 1440min
**Fees:** 0.165% RT

## Сравнение hedge-exit вариантов (full 2y)

| variant | описание | PnL ($) | PF | WR% | N trades | N bundles | MaxDD ($) |
|---|---|---:|---:|---:|---:|---:|---:|
| A | Hedge A: 1-я зkr когда 2-я TP | -3,270 | 0.77 | 67.0 | 1460 | 1307 | 3,368 |
| B | Hedge B: 1-я зкr когда 2-я +0.5xTP | -3,270 | 0.77 | 67.0 | 1460 | 1307 | 3,368 |
| C | Hedge C: 1-я зkr когда 2-я И 3-я TP | -3,270 | 0.77 | 67.0 | 1460 | 1307 | 3,368 |
| none | Без hedge: каждый tier сам | -3,270 | 0.77 | 67.0 | 1460 | 1307 | 3,368 |

## Walk-forward (variant A: Hedge A: 1-я зkr когда 2-я TP)

| fold | PnL ($) | PF | WR% | N | MaxDD ($) |
|---|---:|---:|---:|---:|---:|
| 1 | -946 | 0.81 | 67.5 | 489 | 1,115 |
| 2 | -455 | 0.88 | 67.7 | 409 | 840 |
| 3 | -689 | 0.60 | 60.9 | 184 | 755 |
| 4 | -1,311 | 0.66 | 68.3 | 378 | 1,330 |

**Pos folds:** 0/4

## Verdict

❌ Best variant **A** has PF 0.77 < 1.0 — стратегия убыточна на 2y. Triggers/sizes/TP needs tuning.