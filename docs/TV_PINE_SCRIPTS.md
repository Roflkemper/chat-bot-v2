# TradingView → bot7 интеграция: Pine Script templates

Готовые Pine Script фрагменты для алертов которые форвардятся в TG → парсятся ботом
через handle_text TV-bridge (см. `services/manual_levels.py`).

## Setup workflow

1. **TV Pro+** настройка алерта:
   - Открываешь скрипт на BTC chart
   - `Alert` → выбираешь "Pine condition" (если индикатор)
   - **Message**: пиши строго в формате который парсит бот (см. ниже)
   - **Notifications**: enable Telegram (если настроен TV→TG bot) ИЛИ webhook URL (если поднимешь webhook receiver, future)
2. Бот ловит сообщение в TG, видит префикс `LEVELS` / `TV:LEVELS` / `VPVR`, парсит, сохраняет в `state/manual_levels.json`.
3. Range Hunter / cascade_alert при следующем сигнале snap'ятся к VAL/VAH.

---

## 1. Daily VPVR levels (POC/VAH/VAL)

Pine Script v5 — выполняется на 1D timeframe, фаерит один раз в начале сессии US (15:00 UTC = NY open). Использует встроенный `volume_profile` API.

```pinescript
//@version=5
indicator("VPVR levels emit", overlay=true)

// Параметры
session_start = input.session("0930-1600", "RTH session (US)")
lookback_bars = input.int(1, "Sessions lookback", minval=1, maxval=5)

// Считаем VPVR за RTH сессию (можно поменять на 24h)
[vah, val, poc] = ta.vwap.poc_vah_val(volume, lookback_bars)  // подставь свой расчёт
// Если хочешь готовый indicator — используй встроенный "Volume Profile Session"
// и доставай vah/val/poc через library

// Alert message — STRICT FORMAT для bot7
alert_msg = "LEVELS BTCUSD POC=" + str.tostring(math.round(poc, 1)) +
            " VAH=" + str.tostring(math.round(vah, 1)) +
            " VAL=" + str.tostring(math.round(val, 1)) +
            " ttl_hours=24"

// Fire раз в день в 15:00 UTC
if hour == 15 and minute == 0 and barstate.isconfirmed
    alert(alert_msg, alert.freq_once_per_bar)
```

**Note**: TV в чистом виде не даёт прямой доступ к VPVR через Pine Script. Реальный способ:
- Использовать готовый indicator "Volume Profile Visible Range" (LuxAlgo, etc.) из public library с alert hooks
- ИЛИ вручную смотреть VPVR на чарте и слать `/levels BTCUSD poc=X vah=Y val=Z` команду в бот

Простейший hybrid: оператор раз в день смотрит VPVR глазами, шлёт `/levels`.

---

## 2. CVD divergence alert

Cumulative Volume Delta — TV имеет встроенный CVD indicator (Premium).

```pinescript
//@version=5
indicator("CVD divergence emit", overlay=false)

// CVD из TV builtin или library
cvd = request.security(syminfo.tickerid, "1m", ta.cum(volume * (close - open)))
// Альтернатива: request.security_lower_tf для true tick-volume

price_pct_1h = (close / close[60] - 1) * 100  // % move за 1h
cvd_pct_1h = (cvd - cvd[60]) / math.abs(cvd[60] + 0.001) * 100

bearish_div = price_pct_1h > 0.3 and cvd_pct_1h < -5  // price ↑, CVD ↓
bullish_div = price_pct_1h < -0.3 and cvd_pct_1h > 5  // price ↓, CVD ↑

if bearish_div
    alert("TV:SIGNAL BEARISH_DIV BTCUSD price_chg=" + str.tostring(price_pct_1h, "#.##") +
          " cvd_chg=" + str.tostring(cvd_pct_1h, "#.##"), alert.freq_once_per_bar)

if bullish_div
    alert("TV:SIGNAL BULLISH_DIV BTCUSD price_chg=" + str.tostring(price_pct_1h, "#.##") +
          " cvd_chg=" + str.tostring(cvd_pct_1h, "#.##"), alert.freq_once_per_bar)
```

**Note**: бот пока парсит только `LEVELS` сообщения; для `TV:SIGNAL ...` нужен дополнительный handler — TODO в `services/manual_levels.py` или новый `services/tv_signals.py`.

---

## 3. Session high/low + key swings

```pinescript
//@version=5
indicator("Session levels emit", overlay=true)

session = input.session("0000-2400", "Tracked session (UTC)")
in_session = session.isin(session)

var float session_hi = na
var float session_lo = na

if in_session
    session_hi := math.max(nz(session_hi, high), high)
    session_lo := math.min(nz(session_lo, low), low)

// Fire в начале каждого дня UTC
if dayofweek != dayofweek[1] and barstate.isconfirmed
    alert_msg = "LEVELS BTCUSD session_high=" + str.tostring(math.round(session_hi, 1)) +
                " session_low=" + str.tostring(math.round(session_lo, 1))
    alert(alert_msg, alert.freq_once_per_bar)
    session_hi := high
    session_lo := low
```

---

## 4. HVN/LVN ranking (advanced, требует TV Premium + custom indicator)

Один раз в день, после daily close. Использует Volume Profile со встроенным getValueAt API (LuxAlgo VPVR PRO или альтернативы).

```
LEVELS BTCUSD hvn=82100,81100,79500 lvn=81800,80300
```

---

## Что делает бот при получении

`services/telegram_runtime.py` → `handle_text` (TV-bridge):
- Видит префикс `LEVELS`, `TV:LEVELS`, `VPVR`
- Парсит через `parse_levels_text()` → dict
- Сохраняет в `state/manual_levels.json` с timestamp + source="tv_tg_bridge"
- Range Hunter `signal.py` при свежих VAL/VAH snap'ит к ним buy/sell levels

## Quick manual test без Pine Script

Просто отправь боту в TG:
```
LEVELS BTCUSD poc=81500 vah=82200 val=80800 session_high=82800 session_low=80100
```
Бот ответит `📊 LEVELS BTCUSD сохранено ...`. Range Hunter будет использовать эти значения 24h.
