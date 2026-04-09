from core.execution import build_execution_snapshot
from renderers.renderer import render
from market_data.price_feed import get_price

def run():
    print("V17.8.7.1.2 ACTIVE")
    price = get_price()
    snapshot = build_execution_snapshot(price)
    msg = render(snapshot)

    print("\n=== TELEGRAM OUTPUT ===\n")
    print(msg)
