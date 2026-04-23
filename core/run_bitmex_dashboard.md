import requests
import pandas as pd
import numpy as np
import threading
import time
from telegram import Bot
import matplotlib.pyplot as plt
import io

# =========================
# CONFIGURATION
# =========================
SYMBOL = "XBTUSD"
TELEGRAM_TOKEN = "YOUR_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
CHECK_INTERVAL = 60  # seconds
RISK_PER_TRADE = 0.01
SL_ATR_MULT = 1.5
TP_RR = 2

bot = Bot(token=TELEGRAM_TOKEN)

# =========================
# DATA FUNCTIONS
# =========================
def get_data():
    url = "https://www.bitmex.com/api/v1/trade/bucketed"
    params = {"symbol": SYMBOL, "binSize": "1m", "count": 1000, "reverse": True}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception as e:
        print(f"⚠️ Ошибка запроса к BitMEX: {e}")
        return pd.DataFrame()

    if not data:
        print("⚠️ Пустой ответ от BitMEX")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    if 'timestamp' not in df.columns:
        print("⚠️ Нет колонки 'timestamp'")
        return pd.DataFrame()

    df['time'] = pd.to_datetime(df['timestamp'])
    df = df[::-1]

    df['ema'] = df['close'].ewm(span=20).mean()
    df['dev'] = (df['close'] - df['ema']) / df['ema'] * 100
    df['momentum'] = df['close'].pct_change() * 100
    df['atr'] = (df['high'] - df['low']).rolling(14).mean()

    return df.dropna()

# =========================
# FUNDING AND OPEN INTEREST
# =========================
def get_funding():
    try:
        r = requests.get("https://www.bitmex.com/api/v1/funding", params={"symbol": SYMBOL, "count": 1, "reverse": True}, timeout=10).json()
        return r[0]['fundingRate'] * 100
    except:
        return 0


def get_oi():
    try:
        r = requests.get("https://www.bitmex.com/api/v1/instrument", params={"symbol": SYMBOL}, timeout=10).json()
        return r[0]['openInterest']
    except:
        return 0

# =========================
# SIGNAL GENERATOR
# =========================
def generate_signal(df):
    if df.empty:
        return None, None, 0, 0

    last = df.iloc[-1]
    funding = get_funding()
    oi = get_oi()

    strong_signal = None

    if abs(last['dev']) > 2.5 and abs(last['momentum']) > 0.5:
        if last['dev'] < 0 and funding < 0:
            strong_signal = 'STRONG LONG'
        elif last['dev'] > 0 and funding > 0:
            strong_signal = 'STRONG SHORT'

    return strong_signal, last, funding, oi

# =========================
# TELEGRAM AUTO SIGNAL WITH EQUITY GRAPH
# =========================
last_signal = None

def send_signal():
    global last_signal
    equity_curve = []

    while True:
        df = get_data()
        signal, last, funding, oi = generate_signal(df)

        if signal and signal != last_signal and last is not None:
            price = last['close']
            atr = last['atr']

            if 'LONG' in signal:
                sl = price - atr * SL_ATR_MULT
                tp = price + (price - sl) * TP_RR
            else:
                sl = price + atr * SL_ATR_MULT
                tp = price - (sl - price) * TP_RR

            msg = f"""
🔥 {signal}

Entry: {price}
SL: {sl:.1f}
TP: {tp:.1f}

Funding: {funding:.4f}%
Open Interest: {oi}
"""

            equity_curve.append(price)
            plt.figure(figsize=(6,3))
            plt.plot(equity_curve, color='green')
            plt.title('Equity Curve')
            plt.xlabel('Trade')
            plt.ylabel('Price')

            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)

            try:
                bot.send_photo(chat_id=CHAT_ID, photo=buf, caption=msg)
            except Exception as e:
                print(f"⚠️ Не удалось отправить сигнал в Telegram: {e}")

            buf.close()
            plt.close()
            last_signal = signal

        time.sleep(CHECK_INTERVAL)

# =========================
# BACKTEST FUNCTION
# =========================
def backtest():
    df = get_data()
    if df.empty:
        print("⚠️ Нет данных для backtest")
        return 0, [], []

    balance = 100000
    position = None
    entry_price = 0
    equity_curve = []
    trades = []

    for i in range(50, len(df)):
        row = df.iloc[i]
        funding = get_funding()

        signal = None
        if abs(row['dev']) > 2.5 and abs(row['momentum']) > 0.5:
            if row['dev'] < 0 and funding < 0:
                signal = 'LONG'
            elif row['dev'] > 0 and funding > 0:
                signal = 'SHORT'

        price = row['close']
        atr = row['atr']

        if not position and signal:
            position = signal
            entry_price = price
            sl = entry_price - atr * SL_ATR_MULT if signal=='LONG' else entry_price + atr * SL_ATR_MULT
            tp = entry_price + (entry_price - sl) * TP_RR if signal=='LONG' else entry_price - (sl - entry_price) * TP_RR

        elif position:
            if position == 'LONG' and (price >= tp or price <= sl):
                profit = (price - entry_price) / entry_price * balance
                balance += profit
                trades.append(profit)
                position = None
            elif position == 'SHORT' and (price <= tp or price >= sl):
                profit = (entry_price - price) / entry_price * balance
                balance += profit
                trades.append(profit)
                position = None

        equity_curve.append(balance)

    plt.figure(figsize=(8,4))
    plt.plot(equity_curve, color='blue')
    plt.title('Backtest Equity Curve')
    plt.xlabel('Trades')
    plt.ylabel('Balance')
    plt.show()

    return balance, trades, equity_curve

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    threading.Thread(target=send_signal, daemon=True).start()
    print("Auto Telegram strong signals running with Equity Graph...")

    final_balance, trades, equity_curve = backtest()
    print(f"Backtest Final Balance: {final_balance:.2f}, Trades: {len(trades)}")

