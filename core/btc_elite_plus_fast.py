# BTC ELITE+ AI SYSTEM (Optimized + Model Saving + Telegram)

import pandas as pd
import numpy as np
import requests
import streamlit as st
import talib
from sklearn.preprocessing import MinMaxScaler
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.mixture import GaussianMixture
from tensorflow.keras.models import Model, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input, Attention
from tensorflow.keras.optimizers import Adam
import plotly.graph_objects as go
import os

MODEL_PATH = "lstm_model.h5"

BOT_TOKEN = "YOUR_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

def send_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

@st.cache_data(ttl=300)
def load_data(limit=1000):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol":"BTCUSDT","interval":"1h","limit":limit}
    data = requests.get(url, params=params).json()
    df = pd.DataFrame(data, columns=["t","o","h","l","c","v","ct","q","n","tb","tq","i"])
    df = df.astype(float)
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("t", inplace=True)
    return df

def features(df):
    df['rsi'] = talib.RSI(df['c'],14)
    macd, macds, _ = talib.MACD(df['c'])
    df['macd'], df['macds'] = macd, macds
    df['sma'] = talib.SMA(df['c'],50)
    df['atr'] = talib.ATR(df['h'],df['l'],df['c'],14)
    df['ret'] = df['c'].pct_change()
    df['vol'] = df['ret'].rolling(20).std()
    df.dropna(inplace=True)
    return df

def regime(df):
    gmm = GaussianMixture(n_components=3)
    df['regime'] = gmm.fit_predict(df[['ret','vol']])
    return df

def prepare(df, seq):
    scaler = MinMaxScaler()
    data = scaler.fit_transform(df)
    X,y = [],[]
    for i in range(seq,len(data)-1):
        X.append(data[i-seq:i])
        y.append(1 if data[i+1][3]>data[i][3] else 0)
    return np.array(X), np.array(y)

def build(seq,f):
    inp = Input(shape=(seq,f))
    x = LSTM(64, return_sequences=True)(inp)
    x = Attention()([x,x])
    x = LSTM(32)(x)
    x = Dropout(0.2)(x)
    out = Dense(1,activation='sigmoid')(x)
    m = Model(inp,out)
    m.compile(optimizer=Adam(), loss='binary_crossentropy')
    return m

def backtest(df, lstm_p, gb_p):
    capital = 1000
    equity = []
    fee = 0.0004
    slippage = 0.0002

    for i in range(len(lstm_p)):
        weight = 0.7 if lstm_p[i] > gb_p[i] else 0.3
        p = weight*lstm_p[i] + (1-weight)*gb_p[i]
        size = max(0, p - (1-p)/2)

        move = df['c'].iloc[i+1] - df['c'].iloc[i]
        pnl = move * size if p>0.5 else -move * size
        pnl -= abs(pnl)*(fee+slippage)

        capital += pnl
        equity.append(capital)

    equity = np.array(equity)
    dd = np.max(np.maximum.accumulate(equity)-equity)
    return equity, capital, dd

st.title("BTC ELITE+ AI SYSTEM (FAST)")

seq = st.sidebar.slider("SEQ",6,24,12)

df = load_data()
df = features(df)
df = regime(df)

X,y = prepare(df,seq)

split = int(len(X)*0.7)
X_train,X_test = X[:split],X[split:]
y_train,y_test = y[:split],y[split:]

# Load or train model
if os.path.exists(MODEL_PATH):
    lstm = load_model(MODEL_PATH)
else:
    lstm = build(seq,X.shape[2])
    lstm.fit(X_train,y_train,epochs=3,verbose=0)
    lstm.save(MODEL_PATH)

gb = GradientBoostingClassifier()
gb.fit(X_train.reshape(len(X_train),-1),y_train)

lstm_p = lstm.predict(X_test,verbose=0).flatten()
gb_p = gb.predict_proba(X_test.reshape(len(X_test),-1))[:,1]

equity, capital, dd = backtest(df.iloc[-len(lstm_p)-1:], lstm_p, gb_p)

# Telegram signal (last prediction)
last_p = (lstm_p[-1] + gb_p[-1]) / 2
if last_p > 0.75:
    send_telegram(f"🚀 BTC LONG {last_p*100:.1f}%")
elif last_p < 0.25:
    send_telegram(f"📉 BTC SHORT {last_p*100:.1f}%")

st.metric("Capital", f"{capital:.2f}")
st.metric("Drawdown", f"{dd:.2f}")

fig = go.Figure()
fig.add_trace(go.Scatter(y=equity, name="Equity"))
st.plotly_chart(fig)

st.line_chart(df['rsi'])
st.line_chart(df[['macd','macds']])
