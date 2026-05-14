"""Open the dashboard in the default browser."""
import webbrowser

try:
    from services.dashboard.http_server import BOUND_PORT
    port = BOUND_PORT or 8765
except ImportError:
    port = 8765

url = f"http://127.0.0.1:{port}/"
print(f"Opening {url}")
webbrowser.open(url)
