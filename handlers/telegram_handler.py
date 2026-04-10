from core.pipeline import build_full_snapshot
from renderers.renderer import render_full_report

def run():
    print("V17.9.1.0 ACTIVE")
    snapshot = build_full_snapshot(symbol="BTCUSDT")
    message = render_full_report(snapshot)

    print("\n=== TELEGRAM OUTPUT ===\n")
    print(message)
