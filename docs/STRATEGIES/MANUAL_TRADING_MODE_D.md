# Manual Trading Mode (Phase D) — bot предлагает, ты подтверждаешь

**Контекст:** GinArea grid-боты отключаются. Bot7 продолжает работать как **decision support system** — на каждый сетап-сигнал шлёт в TG карточку с inline-кнопками "Open" / "Skip" / "Edit". При подтверждении бот **сам открывает ордер на BitMEX**.

Через 1-2 нед сбора статистики какие типы сетапов ты обычно одобряешь — переход к **Phase B** (auto для проверенных типов).

## Что уже есть (можно использовать)

- ✅ **Paper Trader** (`services/paper_trader/trader.py`) — `open_paper_trade(setup)` создаёт виртуальную сделку, сейчас уже шлёт уведомления типа `📈 PAPER LONG @ 79605 | SL 78968 | TP1 81197 | TP2 82789 | RR 2.5`
- ✅ **Setup Detector** — генерирует setup-сигналы (Double top/bottom, Mega-setup, P-15 OPEN, и т.д.)
- ✅ **TG callback_query handler** — уже работает для decision_log (`services/telegram_runtime.py:2360`)
- ✅ **BitMEX read-only API** — auth, signing, account snapshots (`services/bitmex_account/poller.py`)

## Что нужно добавить

### 1. BitMEX trade API (POST для размещения ордеров)

Расширить `services/bitmex_account/poller.py` или создать `services/bitmex_account/trader.py`:

```python
def place_limit_order(key, secret, *, symbol, side, qty_btc, price, ord_type="Limit",
                     stop_px=None, time_in_force="GoodTillCancel") -> dict:
    """POST /api/v1/order — лимитный ордер."""
    # body = {symbol, side, orderQty (в USD для inverse), price, ordType, ...}
    # sign + POST
    # return resp.json()

def place_market_order(...):
    """POST /api/v1/order ordType=Market"""

def cancel_order(key, secret, *, order_id):
    """DELETE /api/v1/order"""

def amend_order(key, secret, *, order_id, **kwargs):
    """PUT /api/v1/order"""
```

⚠ **Важно:** BitMEX inverse contracts (XBTUSD) считают qty в **USD-контрактах** (1 контракт = 1 USD). Для linear (XBTUSDT) — в native.

### 2. Inline-кнопки в TG-карточках сетапов

В существующих setup-картах добавить `reply_markup`:

```python
from telebot import types

def build_setup_keyboard(setup_id: str):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("✅ Open", callback_data=f"setup_act:open:{setup_id}"),
        types.InlineKeyboardButton("⏭ Skip", callback_data=f"setup_act:skip:{setup_id}"),
        types.InlineKeyboardButton("⚙ Edit", callback_data=f"setup_act:edit:{setup_id}"),
    )
    return kb

# В services/setup_detector/loop.py (или где setup отправляется):
self.bot.send_message(chat_id, setup_text, reply_markup=build_setup_keyboard(setup.id))
```

### 3. Callback handler — обработка нажатий

В `services/telegram_runtime.py`:

```python
@self.bot.callback_query_handler(func=lambda call: str(call.data).startswith("setup_act:"))
def _handle_setup_action(call):
    _, action, setup_id = call.data.split(":", 2)

    if action == "open":
        # Загрузить setup из state/setups_active.json по ID
        setup = load_setup(setup_id)
        # Открыть на BitMEX
        from services.bitmex_account.trader import place_limit_order
        # Размер позиции из ADVISOR_DEPO_TOTAL × % allocation
        size_usd = compute_position_size(setup, deposit=15145)
        result = place_limit_order(
            key=BITMEX_KEY, secret=BITMEX_SECRET,
            symbol="XBTUSD",
            side="Buy" if setup.direction == "long" else "Sell",
            qty_btc=size_usd / setup.entry_price,
            price=setup.entry_price,
        )
        # Записать в state/real_trades.jsonl
        record_real_trade(setup, result)
        # Подтвердить пользователю
        self.bot.answer_callback_query(call.id, f"✅ Opened: {result['orderID'][:8]}")
        # Обновить сообщение — заменить кнопки на "ORDER ID: xxx"
        self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                          reply_markup=None)
        self.bot.send_message(chat_id, f"🟢 Real order placed: {result['orderID']}")

    elif action == "skip":
        # Просто пометить в paper_trades что не открыли
        mark_setup_skipped(setup_id)
        self.bot.answer_callback_query(call.id, "Skipped (для статистики)")

    elif action == "edit":
        # Спросить новый size — через ForceReply
        # ...
```

### 4. Position sizing (advisor)

Уже есть `ADVISOR_DEPO_TOTAL=15145` в env. Нужна функция:

```python
def compute_position_size(setup, deposit: float) -> float:
    """Returns position size in USD based on setup confidence and R:R."""
    # Базовая аллокация — 2-5% депо на сделку
    base_pct = 0.03  # 3% = $450
    # Buster для high-conf setup
    if setup.confidence >= 80:
        base_pct = 0.05  # 5% = $750
    return deposit * base_pct
```

### 5. SL/TP размещение после fill

Когда BitMEX заполняет entry-ордер, надо разместить stop-limit (SL) и take-profit (TP). Два варианта:

**A. OCO order сразу** (One-Cancels-Other):
```python
# BitMEX поддерживает contingent orders
# Placed at entry time, fires when entry fills
```

**B. WebSocket trade subscription**:
```python
# Subscribe to user trade stream, when entry fills — place SL+TP
```

A проще. Использовать BitMEX `execInst="Close"` для SL/TP.

### 6. State journal — `state/real_trades.jsonl`

Каждое реальное открытие → запись:
```json
{
  "ts": "2026-05-14T01:30:00Z",
  "setup_id": "abc123",
  "setup_type": "long_mega_setup",
  "confidence": 81,
  "entry": 79605,
  "sl": 78968,
  "tp1": 81197,
  "size_usd": 750,
  "bitmex_order_id": "xxx",
  "user_action": "open"  // или "skip"
}
```

Через 2 нед — анализ: какие типы setup ты одобряешь, какие пропускаешь, какой реальный win-rate.

## Объём работы по фазам

### Phase D.1 (3-5 дней): минимальная имплементация

- [ ] `services/bitmex_account/trader.py` — `place_limit_order`, `cancel_order` (без OCO)
- [ ] Inline-кнопки в setup-карточках (только Mega-setup и P-15 OPEN — самые проверенные)
- [ ] Callback handler "Open" / "Skip"
- [ ] `state/real_trades.jsonl` журнал
- [ ] Тест на **paper** (read-only ключ) — убедиться что POST правильно подписывается, но не лезет в реал

### Phase D.2 (1 нед): SL/TP + monitoring

- [ ] OCO orders для SL/TP
- [ ] Track open positions в `state/real_positions.jsonl`
- [ ] TG-команда `/positions` — список открытых
- [ ] TG-команда `/close <id>` — ручное закрытие
- [ ] Edge case: что если entry не fills (cancel через 30 мин)

### Phase D.3 (1 нед): расширение и статистика

- [ ] Inline-кнопки на **всех** setup-типах (не только Mega)
- [ ] Daily report: количество approve/skip, реальный PnL vs paper
- [ ] Edit-кнопка для изменения size перед открытием

### Phase E (опционально, после 2 нед statistics в D)

- [ ] Авто-open для сетапов с user_action="open" rate > 90%
- [ ] Размер позиции из learning (увеличить для сетапов с лучшим реальным WR)

## Critical risks

1. **BitMEX API ошибки** — order rejected (margin, price limits, и т.д.). Нужно ловить и **обязательно** уведомлять оператора.
2. **Network partition** — если сеть упала после `place_order` но до confirmation, бот не знает открылась ли позиция. Решение: polling через `getOrder` после place.
3. **Double-fill** — два callback за одно нажатие кнопки → 2 ордера. Решение: idempotency (по setup_id) — если уже есть запись в `real_trades.jsonl` с этим setup_id, не открывать.
4. **SL не сработал** — бывает при flash crashes (BitMEX freeze). Решение: WebSocket monitoring + ручной /close.
5. **Слишком много сетапов в час** — захлебнёшься нажимать кнопки. Решение: throttle (max 3 open positions одновременно).

## Что делать с текущими GinArea ботами

### Опция X — отключить сразу

- Остановить через GinArea UI (stop bot)
- Можно сразу или после первого успешного дня D-режима

### Опция Y — оставить параллельно

- GinArea крутит rebate-фарм на BTC
- Bot7 делает directional trades на сетапах
- Риск: дублирование позиций в одну сторону

### Опция Z — постепенный перенос

- 1 неделя: D-режим на 5% депо ($750), GinArea на остальные 95%
- Если D показывает PnL — увеличить allocation до 20%, GinArea уменьшить
- Через 1-2 мес — full D, GinArea off

**Рекомендую Z** — снижает риск что D просто не сработает.

## Roadmap

| Неделя | Что делаем |
|---|---|
| **0 (сейчас)** | Решить опцию X/Y/Z по GinArea, начать Phase D.1 |
| **1** | D.1 готов, paper-тест BitMEX trader |
| **2** | D.2: SL/TP + positions tracking, live с 5% депо |
| **3-4** | D.3: расширение setup-типов, статистика собирается |
| **5-6** | Анализ статистики, переход к Phase E (авто для approved типов) |
| **7+** | Full auto для проверенных, остальное в D-режиме |

## Альтернатива — если не хочется кодить trader

Если **разработка BitMEX trader страшит** — можно сделать **proxy-режим**:
- Бот шлёт setup в TG с **готовой ссылкой** "Open on BitMEX" → откроет BitMEX trading UI с предзаполненным ордером (через deeplink)
- Ты тапнул ссылку → одно подтверждение → BitMEX UI открывает ордер
- Не нужен `place_order` код, но всё равно требует подтверждения вручную

Минус: BitMEX не имеет deeplink для авто-pre-fill ордера. Пока неприменимо.

## Что нужно решить **сейчас**

1. Опция X/Y/Z по GinArea — отключить полностью / параллельно / постепенно?
2. С какой суммой начать D-режим? ($500 first week? $1000?)
3. Какие BitMEX-инструменты приоритет? Только XBTUSD inverse (твой основной) или сразу ETH/XRP тоже?
