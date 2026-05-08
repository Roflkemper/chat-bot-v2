"""Localhost HTTP server for dashboard — serves docs/ on 127.0.0.1:8765."""
from __future__ import annotations

import asyncio
import http.server
import logging
import socket
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DOCS_DIR = _ROOT / "docs"
_STATE_JSON_PATH = _DOCS_DIR / "STATE" / "dashboard_state.json"

_BIND_HOST = "127.0.0.1"
_DEFAULT_PORTS = (8765, 8766, 8767)

# Set after successful bind; readable by tools/dashboard_open.py
BOUND_PORT: int | None = None


def _make_handler(docs_dir: Path, state_path: Path) -> type[http.server.BaseHTTPRequestHandler]:
    """Return a request handler class closed over docs_dir and state_path."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        _ROUTES: dict[str, tuple[Path, str]] = {}

        def do_GET(self) -> None:
            url_path = self.path.split("?")[0].rstrip("/") or "/"
            routes = {
                "/": (docs_dir / "dashboard.html", "text/html; charset=utf-8"),
                "/index.html": (docs_dir / "dashboard.html", "text/html; charset=utf-8"),
                "/state.json": (state_path, "application/json; charset=utf-8"),
                "/dashboard.js": (docs_dir / "dashboard.js", "application/javascript; charset=utf-8"),
                "/dashboard.css": (docs_dir / "dashboard.css", "text/css; charset=utf-8"),
                "/state_inline.js": (docs_dir / "state_inline.js", "application/javascript; charset=utf-8"),
            }
            entry = routes.get(url_path)
            if entry is None:
                self.send_error(404)
                return
            file_path, content_type = entry
            self._send_file(file_path, content_type)

        def _send_file(self, path: Path, content_type: str) -> None:
            if not path.exists():
                self.send_error(404)
                return
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args: object) -> None:
            pass  # suppress per-request console noise

    return _Handler


def _find_free_port() -> int | None:
    for port in _DEFAULT_PORTS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((_BIND_HOST, port))
            return port
        except OSError:
            logger.warning("dashboard_http.port_busy port=%d", port)
    return None


async def dashboard_http_server(stop_event: asyncio.Event) -> None:
    """Async task: start HTTP server on localhost, stop when stop_event fires."""
    global BOUND_PORT

    port = _find_free_port()
    if port is None:
        logger.error("dashboard_http.no_port_available tried=%s", _DEFAULT_PORTS)
        return

    handler = _make_handler(_DOCS_DIR, _STATE_JSON_PATH)
    server = http.server.HTTPServer((_BIND_HOST, port), handler)
    server.timeout = 1.0
    BOUND_PORT = port
    logger.info("dashboard_http.started url=http://%s:%d/", _BIND_HOST, port)

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="dashboard_http",
    )
    thread.start()

    await stop_event.wait()

    server.shutdown()
    BOUND_PORT = None
    logger.info("dashboard_http.stopped")
