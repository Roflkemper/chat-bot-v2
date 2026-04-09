from core.pipeline import build_full_snapshot
from renderers.renderer import render_full_report

def run():
    print("V17.8.7.9 ACTIVE")
    snapshot = build_full_snapshot(symbol="BTCUSDT")
    message = render_full_report(snapshot)

    print("\n=== TELEGRAM OUTPUT ===\n")
    print(message)
