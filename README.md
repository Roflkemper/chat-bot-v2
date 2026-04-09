# V17.8.7.1 LIVE DATA (Binance)

Минимальный модуль для получения текущей цены BTCUSDT с Binance.

## Использование
```python
from market_data.price_feed import get_price

price = get_price()  # float
```

## Зависимости
- requests

## Поведение при ошибке
Бросает RuntimeError с понятным сообщением.
