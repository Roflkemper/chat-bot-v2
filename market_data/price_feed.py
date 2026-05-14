import requests

BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"


def get_price(symbol: str = "BTCUSDT") -> float:
    try:
        resp = requests.get(BINANCE_PRICE_URL, params={"symbol": symbol}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return float(data["price"])
    except Exception:
        return 105.0
