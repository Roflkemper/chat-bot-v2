# SESSION PLAN — следующая сессия (after 2026-05-09)

**Last session ended:** 2026-05-09 ~11:25 UTC
**Bot state:** running PID 18932, all trackers FRESH (<10min)
**Last commit:** `14bbd2e` (P-15 unblock + DL false-positive cleanup)

---

## ⚡ В ПЕРВЫЕ 5 МИНУТ — health check

```bash
# Проверь что бот живой и трекеры свежие
python tools/_dl_validate.py | tail -25
ls -la state/p15_state.json state/phase_state.json 2>&1
git log --oneline -5
```

**Зелёные флаги:**
- ✅ `state/p15_state.json` существует и обновлялся в последние 10 мин
- ✅ `tools/_dl_validate.py` показывает T-1/T-2/T-3 fires > 0
- ✅ M-4 fires count за 24h < 5 (было 22)
- ✅ R-3 fires < 5 (было 16)
- ✅ CAP-DIAG < 100/24h (было 1762)

Если что-то red — диагностика в первую очередь.

---

## 🎯 ПРИОРИТЕТЫ ПО УБЫВАНИЮ

### #1 — VERIFY P-15 lifecycle отработал в TG (must-check)

После последнего фикса (14bbd2e) P-15 detector должен был запуститься на XRPUSDT LONG (gate был True в момент рестарта). Проверь:

```bash
# Посчитать сколько P-15 cards пришло за последние сутки
grep -c "p15_" state/setups.jsonl  # должно быть >= 1
cat state/p15_state.json  # должен показывать активный leg
ls -la state/p15_paper_trades.jsonl  # должен существовать с записями
```

Если **0 P-15 событий за 24h** — investigate:
- Посмотри `logs/app.log | grep p15` — есть ли ошибки в detector
- Может быть combo_filter блокирует strength<6 (P-15 эмиттит strength=8)
- Check `_trend_gate()` на BTC/ETH/XRP вручную через REPL

### #2 — Volume farming optimization для $500k цели

Из ночного скриншота — оба наш бота дают суммарно ~$85k/сутки (17% от цели $500k).
Оператор сказал что цель не с этих двух — со всех 8 ботов в портфеле.

**Что сделать:**
- Запросить у оператора параметры остальных 6 ботов (или скриншоты статистики)
- Найти бутылочное горлышко: какой бот недогружен (низкий объём при том же size)
- Предложить расширение `boundaries` или увеличение `order_size` на 1-2 ботах

**НЕ делать:** не предлагать снижение `indicator threshold` — по доке GINAREA это
влияет только на первый запуск цикла (после full-close). Не путай как в этой
сессии.

### #3 — Daily P-15 dry-run report (через 7 дней)

P-15 paper-trader handler пишет в `state/p15_paper_trades.jsonl`. Через 7 дней
работы будет sample для acceptance criteria из HYPOTHESES_BACKLOG:
- 2-week dry-run + operator approval

**Что сделать:**
- Тула `tools/_p15_dry_run_report.py` — читает p15_paper_trades.jsonl, считает
  PnL, PF, Sharpe, walk-forward на live данных
- Сравнить с backtest +$67k/2y → есть ли расхождение

### #4 — Cleanup duplicate paper trades

37 дубликатов `long_multi_divergence` сейчас открыты (pre-fix остатки).
Они закроются по TP1 / SL / TIME_STOP естественно. Через 24-48 часов проверить:

```bash
python -c "
import json, collections
opens = []
closed = set()
with open('state/paper_trades.jsonl') as f:
    for l in f:
        e = json.loads(l)
        if e.get('action')=='OPEN': opens.append(e)
        elif e.get('action') in ('TP1','TP2','SL','EXPIRE','TIME_STOP'):
            closed.add(e.get('trade_id'))
open_now = [o for o in opens if o['trade_id'] not in closed]
print('open:', len(open_now), 'closed:', len(closed))
"
```

Если open > 20 через 48h — закрыть руками через `/papertrader_close <id>`.

### #5 — Health-checks для V1/V2 volume farming

Из `docs/STRATEGIES/VOLUME_FARMING_v1.md` Section TODO:
- Hourly TG sweep `[V-FARM] объём 4ч: $87k / прогноз сутки: $522k / цель: $500k`
- Idle alert (бот >6h без IN)
- Boundary breach alert
- Funding warn > 0.03%/8h
- Daily P&L summary 23:00 UTC

Эти tools НЕ требуют кода в bot7 — это **API-poll скрипт** который читает GinArea
API → пишет в TG. Сделать как `services/volume_farming/monitor.py`.

---

## 🛠 SECONDARY (если время остаётся)

### #6 — Walk-forward для остальных детекторов
- В прошлой сессии walkfwd показал OVERFIT для `long_div`/`short_div` (без BoS)
- НО в live они дали +$3k за 24h
- Это либо sample bias (один импульс), либо backtest broken
- **Расследование:** прогнать walkfwd_v2 с N>20 фильтром, hold_24h вместо hold_12h

### #7 — Watchdog post-mortem
- Логи keepalive показывали **бот рестартует каждые 2 мин** в течение пары часов
- Возможно из-за моих ручных kill'ов в той сессии
- Но добавить в supervisor.daemon **health-self-test** перед приёмом нового PID
- Если он сразу не отвечает на heartbeat 30s → не записывать PID, дать keepalive
  попробовать заново

### #8 — Migration P-15 на 5m данные?
- 15m PnL = +$67k/2y, 1h = +$19k. Что если 5m даст +$200k?
- Но fees растут линейно, edge per trade падает quadratic
- Прикинуть math: при R=0.1% и K=0.3% на 5m, fees per trade ~0.07%, net ≈ 0
- **Решение:** не пробовать без хорошего sim model — может быть waste. Или
  попробовать на ОЧЕНЬ ограниченном sample (1 неделя 5m данных)

---

## 📋 OPEN QUESTIONS для оператора

1. **Параметры остальных 6 ботов** для volume farming → нужен инвентарь чтобы
   добить $500k

2. **V2 на выходных запускается?** (combo-trailing exploit). Хочешь чтобы я
   перенастроил параметры в пятницу вечером или сам?

3. **/advise в режиме observation на флете** — на сегодняшнем флете вердикт
   HOLD корректен. Но операторы обычно хотят что-то делать. Может добавить
   режим "smart pause" — bot прямо предлагает «не торгуй сегодня, покажет
   через 4ч когда будет setup» вместо просто HOLD?

---

## 📊 METRICS WATCH (что должно меняться)

Сравни через 24-48h после next-session start:

| Метрика | Прошлое (до 14bbd2e) | Цель |
|---|---|---|
| P-15 fires/24h | 0 | >= 1 (хотя бы XRP LONG) |
| M-4 fires/24h | 22 | < 3 |
| R-3 fires/24h | 16 | < 3 |
| CAP-DIAG/24h | 1762 | < 100 |
| paper_trades open | 42 | < 20 (после закрытия дубликатов) |

---

## 🚫 НЕ ДЕЛАТЬ (lessons learned)

1. **НЕ путать GinArea indicator с trigger** — indicator работает только при
   первом запуске цикла. Снижение threshold не даст больше IN-ордеров.

2. **НЕ удалять/добавлять много PRIMARY rules сразу** — каждый изменяет CAP
   bucket distribution. Лучше один за раз с 24h window между ними.

3. **НЕ перезапускать бота вручную** в начале сессии — keepalive (Windows
   Task Scheduler) делает это сам каждые 2 мин если supervisor мёртв.
   Лучше посмотреть `logs/autostart/keepalive.log` чтобы понять что там было.

4. **НЕ предлагать "почистим дубли"** в paper_trades.jsonl — operator
   journal append-only, чистка ломает audit. Дубли закрываются по TP/SL/timeout.

5. **НЕ спрашивать "хочешь чтоб я сделал?"** — operator уже сказал делать
   последовательно весь backlog. Продолжай работу, скажи только если ОБЪЁМ
   слишком большой и нужно разбить.

---

## 🎬 БЫСТРЫЙ ПЕРВЫЙ ХОД

```
- Check P-15 fired (must)
- /papertrader status compare к прошлой сессии
- Проверить bottom-line: PnL за 24h, объём за 24h, drawdown
- Доложить оператору 3 строки и спросить "что дальше?"
```

Если operator silent — продолжать с #2 (volume farming с 6-ю ботами).

---

## 🗂 КОНТЕКСТ ДЛЯ AGENT_NEXT_SESSION

**Главное что нужно знать:**

1. **P-15** — стратегия rolling-trend rebalance, validated +$67k/2y BTC 15m,
   confirmed на 6/6 ног (BTC/ETH/XRP × LONG/SHORT). Сейчас в production как
   detector + paper trader. Параметры R=0.3%, K=1.0%, dd_cap=3.0%.

2. **GinArea boты на BitMEX** — оператор запустил V1+V2 (volume farming) с
   target=0.08-0.12%, min_stop=0.01-0.015%. Цель $500k объёма/сутки со ВСЕХ
   ботов (~8 штук в портфеле). Detector НЕ управляет ими — это GinArea side.

3. **Decision Layer** имеет 17 rules (R-*, M-*, P-*, T-*, D-*). После 14bbd2e
   фикса должно быть тихо в флете и громко при реальной угрозе.

4. **MTF (T-*) rules** — после рестарта phase_state.json пишется, T-1/T-2/T-3
   должны заработать. Через 24h проверить fires count.

5. **Бот = supervisor (PID file) + 5 components**:
   - app_runner (main detection loop)
   - tracker (live position polling)
   - collectors (market data)
   - state_snapshot (every 5min)
   - dashboard (HTTP 127.0.0.1:8765)

   Keepalive task в Windows Scheduler перезапускает supervisor каждые 2 мин
   если он мёртв.

6. **Логи:**
   - `logs/app.log` — main bot
   - `logs/current/supervisor.log` — supervisor
   - `logs/autostart/keepalive.log` — task scheduler heartbeats
   - `logs/errors.log` — only ERROR/WARN

7. **Ключевые тулы (`tools/`):**
   - `_dl_validate.py` — health audit DL
   - `backtest.py --list` — все бэктесты
   - `_backtest_p15_full.py` — главный P-15 backtest
   - `_backtest_p15_multi_asset.py` — BTC/ETH/XRP
   - `_walkfwd_all_detectors.py` — overfit-detection

---

**Конец плана. Удачи в следующей сессии.**
