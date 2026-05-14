import requests

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def _offline_fallback(limit: int = 200):
    candles = []
    price = 100.0
    for i in range(limit):
        candles.append({
            "open_time": i,
            "open": price,
            "high": price + 10.0,
            "low": price - 10.0,
            "close": price + 5.0,
            "volume": 100.0,
            "close_time": i + 1,
        })
    return candles


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
    except Exception:
        return _offline_fallback(limit=limit)
