# Stage E2 — LLM-based market regime narrator

## Что это

Каждый час (или по триггеру) LLM (Claude/GPT-4) принимает на вход
агрегированные derived features за последние 6h: regime label, OI delta,
funding, taker dominance, recent setups, ICT levels, regime classifier
verdict. Возвращает короткий narrative на русском в TG.

## Что это даст тебе

### 1. Большая картина без копания в логах
Сейчас чтобы понять "что вообще происходит" — нужно открыть DL log,
deriv_live.json, regime_state.json, recent setups, посмотреть свечи.
Минут 5-10 ручной работы. LLM делает это **за тебя** каждый час и
выдаёт 3-4 строки:

```
🌅 Рынок 14:00-20:00 UTC

Range $80,200-$80,500 уже 4 часа. ОИ +0.8% но funding отрицательный
(-0.04%/8h) — шорты не уверены, лонги набирают позицию против шортов.
Top traders: 50/50, ритейл: 43% long. Похоже на pre-impulse паттерн —
объём накапливается без движения.

Что наблюдаю:
  • short_pdh_rejection 2× за час → resistance $80,500 крепкая
  • spike_alert тихий, нет крупных движений
  • regime: COMPRESSION (4ч), Classifier B говорит RANGE — согласны

Что значит для ботов:
  • TEST_1/2/3 в флете, накопили 25-30% positional bag — типично
  • LONG-B/C ловят 0.25% колебания норм
  • Если cascadeUP в ближайшие 2 часа — SHORT-bag поплатится $1-1.5k
```

### 2. Раннее обнаружение редких паттернов
LLM может узнать комбинации (особенно из training data на крипто-форумах,
research articles), которые **не закодированы** в наших правилах.
Например: "funding flip-flop в RANGE → 70% reversal в течение 3-х
свечей" — это не правило, но Claude может это знать и отметить.

### 3. Operator-friendly briefings
Можно настроить **типы алертов**:
- **Hourly briefing** — что происходит, что наблюдаю
- **Pre-event** — перед US news / funding / major macro
- **Post-mortem** — после крупного движения, объяснение причин
- **Daily summary** — на конец дня UTC, тренды, top trades

### 4. Сравнение с кваном
LLM видит **качественные** паттерны (сентимент, narrative). Quant rules
видят **количественные** триггеры. Расхождение — interesting:
- LLM bullish + R-3 fires negative → обсуждать сценарий
- Оба согласны → сильный сигнал

## Сколько стоит

### Вариант A: Anthropic Claude API (рекомендую)
- **Sonnet 4.5:** $3/M input, $15/M output tokens
- **Haiku 4.5:** $0.80/M input, $4/M output tokens
- **Opus 4.7:** $15/M input, $75/M output tokens

Один narrative ~1500 input + ~400 output:
- **Sonnet hourly (24×30=720/мес):** ~$3.50 / месяц
- **Haiku hourly:** ~$1.00 / месяц
- **Opus hourly:** ~$18 / месяц

С prompt caching (одна и та же инструкция переиспользуется): ещё **−40%**.
Реально **Sonnet ~$2/мес** при hourly, **Haiku ~$0.60/мес**.

### Вариант B: OpenAI GPT-4o
- **GPT-4o:** $5/M input, $15/M output. Очень похожая цена.
- **GPT-4o-mini:** $0.15/M input, $0.60/M output. **Самый дешёвый: ~$0.20/мес**.

### Вариант C: локальный Llama 3.3 70B
- 0$/мес, но **40+ GB RAM** + **GPU 80GB+** или CPU очень медленно.
- Качество анализа ниже Claude/GPT-4 на сложных финансовых паттернах.
- Setup сложнее.

**Моя рекомендация:**
1. **Старт — Haiku или GPT-4o-mini** (~$0.50-1/мес) для проверки концепции
2. После 2 недель — если narrative полезный → upgrade на Sonnet
3. Если не используешь — disable, ничего не платишь

## Архитектура (когда соберём)

### Сервис `services/regime_narrator/`

```python
async def regime_narrator_loop(stop_event, interval_sec=3600):
    while not stop_event.is_set():
        # 1. Aggregate context (deterministic Python — не LLM)
        ctx = collect_market_context_6h()
        # ctx = {
        #   "regime_a": "COMPRESSION",
        #   "regime_b": "RANGE",
        #   "btc_close_now": 80250,
        #   "btc_range_6h": (80100, 80500),
        #   "oi_change_6h_pct": 0.8,
        #   "funding_8h": -0.0004,
        #   "taker_buy_pct_avg": 53,
        #   "recent_setups": [...],  # top 5 by strength
        #   "dl_events_recent": [...],  # PRIMARY events last 6h
        #   "vol_z_score_now": 1.2,
        # }

        # 2. Build prompt (template + ctx)
        prompt = build_narrator_prompt(ctx)

        # 3. Call LLM (cached system prompt)
        narrative = call_claude(prompt, model="claude-haiku-4-5-20251001",
                                 max_tokens=500, system=SYSTEM_PROMPT)

        # 4. Send to TG
        send_fn(narrative)

        # 5. Log for audit
        log_narrative(ctx, narrative)

        await stop_event.wait_for(interval_sec)
```

### System prompt (примерно)
```
Ты — quant analyst, читаешь снимок крипторынка и пишешь 4-5 предложений
narrative для оператора торгового бота. Стиль: разговорный, на русском,
без markdown, без emoji кроме в начале строки. Структура:
  1. Что наблюдаешь (regime, прайс, движение)
  2. Что значит для боев бота (LONG/SHORT contracts на BTC)
  3. Опасности в ближайшие 2-4 часа

Никогда не давай trade signals. Никогда не говори "купи/продай".
Только описание состояния и рисков для существующих позиций.
```

## Когда запускать

E2 нужен **меньше всего** вычислительно (0.5 сек на narrative), но требует
3 решения от тебя:

1. **API provider:** Claude / OpenAI / локально?
2. **Cost budget:** $1-3/мес OK или хочешь $0?
3. **Frequency:** hourly / 4-hour / on-event / on-demand?

После твоих ответов я делаю сервис за ~2 часа. Всего ~150 LOC + тесты.

## Что **не** делает

- Не торгует, не предлагает trade. Только narrative.
- Не пишет в DL — narrative идёт прямо в TG + log file.
- Не reflects на CRON timing с точностью до секунды — ±1 мин по design.
- Не учится на feedback — это не RL, чисто one-shot prompt каждый раз.
- Не даёт SL/TP rec — это работа detector'ов, не narrator'а.

## Risks

1. **API outage** — LLM недоступен. Fallback: skip cycle, log warning.
2. **Hallucination** — LLM может выдумать "тренд" которого нет.
   Mitigation: prompt template даёт **только числа**, LLM описывает их;
   если описание противоречит cтруктурным фактам — log mismatch.
3. **Cost overrun** — по ошибке вызвать LLM в loop без cooldown.
   Mitigation: hard-coded `interval_sec >= 1800` (мин 30 мин).
