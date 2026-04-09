import requests

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

def get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 200):
    try:
        resp = requests.get(
            BINANCE_KLINES_URL,
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=8,
        )
        resp.raise_for_status()
        raw = resp.json()
        candles = []
        for row in raw:
            candles.append({
                "open_time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "close_time": int(row[6]),
            })
        return candles
    except Exception as e:
        raise RuntimeError(f"[market_data.ohlcv] не удалось получить свечи {symbol} {interval}: {e}")
