
from core.execution import build_execution_snapshot
from renderers.renderer import render

def run():
    print("V17.8.7 ACTIVE")

    # mock price (replace with real data loader)
    price = 72000

    snapshot = build_execution_snapshot(price)
    msg = render(snapshot)

    print("\n=== TELEGRAM OUTPUT ===\n")
    print(msg)
