# Edge Roadmap — 2026-05-11

Roadmap из брейншторма [EDGE_BRAINSTORM_2026-05-11.md](./EDGE_BRAINSTORM_2026-05-11.md).
Оператор одобрил план "заносим все, последовательно, не забывая о текущем бектесте".

**Главное правило:** не катить новый детектор в prod без walk-forward на 2y данных
и paper-trade периода 7-14 дней. После каждой фазы — оценка precision_tracker и
сравнение с backtest expectation.

---

## Статус-легенда
- ⬜ pending
- 🔵 in_progress
- ✅ done
- ⏸️ blocked

---

## Фаза 0 — критические правки до новых edge

| # | Задача | Статус | Заметка |
|---|---|---|---|
| 0.1 | V4 expanded GinArea grid backtest — дождаться отчёта | 🔵 | CPU ~100 мин, ещё крутится |
| 0.2 | Fix P-15 dd_cap: backtest с cap 4-5% + менее агрессивный trend-gate + slippage | ⬜ | Live теряет −$926/мес, на real не катим до фикса |
| 0.3 | Cleanup: retire long_rsi_momentum_ga (0% emission), short_mfi_multi_ga (overfit) | ⬜ | Через `DISABLED_DETECTORS` + код |
| 0.4 | Retune long_dump_reversal: strength threshold 9→7 | ⬜ | Сейчас 0.2% emission |

---

## Фаза 1 — быстрые edge из готовых данных (Tier A)

Все 5 пунктов используют данные что уже live (funding/OI/LS/premium/volume).
Цель: 2 недели работы, 5 новых детекторов с walk-forward на 2y.

| # | Edge | Сложность | Статус |
|---|---|---|---|
| 1.1 | Liquidation imbalance per exchange — включить OKX/Hyperliquid в cascade_alert | L (1 день) | ⬜ |
| 1.2 | Funding extremes detector (>+0.05% / <−0.05% за 8h) | L (1-2 дня) | ⬜ |
| 1.3 | Premium index mean-reversion (mark vs spot ≥0.3%) | L (1 день) | ⬜ |
| 1.4 | L/S ratio + top-trader divergence (smart vs retail) | L (2-3 дня) | ⬜ |
| 1.5 | Volume z-score climax (z>3σ + close против движения) | L (1-2 дня) | ⬜ |

**Acceptance каждого детектора:**
- Бектест 1-2y, PF ≥ 1.5, walk-forward 3+/4 фолда положительные
- Code review + тесты (≥2 fixture тестов на детектор)
- Paper-trade 7 дней через `services/paper_trader`
- Если precision_tracker через 7 дней показывает live<backtest более чем на 30% — детектор DISABLED

---

## Фаза 2 — средняя сложность (Tier B)

| # | Edge | Сложность | Статус |
|---|---|---|---|
| 2.1 | Funding flip detector (переход sign + → −, редкое но точное) | M (3-4 дня) | ⬜ |
| 2.2 | Session breakouts (Asia/London/NY high-low first hour) | M (3-5 дней) | ⬜ |
| 2.3 | Multi-asset relative strength (XRP/ETH lead BTC, catch-up) | M (1 неделя) | ⬜ |
| 2.4 | Cross-exchange OI divergence (Binance vs Bybit) | M (1 неделя) | ⬜ |

---

## Фаза 3 — инфраструктура + большие edge (Tier C)

Сначала чинить инфраструктуру, потом edge.

| # | Задача | Сложность | Статус |
|---|---|---|---|
| 3.1 | Починить orderbook L2 collector (умер 2026-05-03) | M (2-3 дня) | ⬜ |
| 3.2 | Написать trade ticks collector (Binance aggTrade WS) | M (3-4 дня) | ⬜ |
| 3.3 | Volume Profile (POC/HVN/LVN) — после 3.2 | H (1 неделя + backtest) | ⏸️ blocked by 3.2 |
| 3.4 | Orderbook imbalance / whale walls — после 3.1 | H (1 неделя + backtest) | ⏸️ blocked by 3.1 |
| 3.5 | BTC.D regime switcher (portfolio-level allocation) | H (architectural, обсудить) | ⬜ |

---

## Что НЕ делаем

Из брейншторма — отказались по причинам:
- Ещё одна вариация RSI/MFI с другими порогами (overfit риск)
- Новый divergence detector (long_multi_divergence уже лучший)
- ML-модель на все данные (слишком много параметров)
- Усложнение setup_detector новыми filter'ами

---

## Параллельные процессы (не блокирующие фазы)

- **V4 backtest** доходит до завершения — отдельный отчёт после готовности
- **GC shadow mode** — собирает 1-2 недели данных, решать про HARD_BLOCK позже
- **short_pdh_rejection** — re-evaluation через 2 недели от 2026-05-11

---

## Прогресс

### 2026-05-11
- ✅ Brainstorm 14 edge-кандидатов
- ✅ Roadmap зафиксирован
- ✅ TG разделение каналов PRIMARY/ROUTINE + 🔴🟠🟡⚪ маркеры
- ✅ Cascade GinArea V3 backtest — SHORT каскад TD (0.20/0.35/0.60) +$10,156/yr
- 🔵 V4 expanded grid (продолжает считаться)
- ⬜ Старт Фазы 0.2 (P-15 dd_cap fix)

---

## Принципы исполнения

1. **Один edge за раз** — не катать параллельно несколько новых в prod
2. **Бектест перед prod** — никаких "выглядит правдоподобно, запускаем"
3. **Paper-trade обязательно** — 7-14 дней prior to live
4. **Precision tracker** — отслеживать live vs backtest, отключать deviation
5. **Walk-forward** — без него не верим бектесту
6. **Cleanup перед expansion** — выкинуть dead code прежде чем добавлять новый
