import requests

def get_price(symbol: str = "BTCUSDT") -> float:
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        r = requests.get(url, params={"symbol": symbol}, timeout=5)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        raise RuntimeError(f"[market_data] error: {e}")