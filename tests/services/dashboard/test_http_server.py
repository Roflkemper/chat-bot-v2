"""Tests for dashboard HTTP server — TZ-DASHBOARD-ACTIVATION."""
from __future__ import annotations

import http.server
import json
import threading
import urllib.request
from pathlib import Path


def _start_test_server(
    docs_dir: Path,
    state_path: Path,
) -> tuple[http.server.HTTPServer, int]:
    """Start a test HTTP server on OS-assigned port; return (server, port)."""
    from services.dashboard.http_server import _make_handler

    handler = _make_handler(docs_dir, state_path)
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)  # port 0 = OS picks
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


# ── test 1 ────────────────────────────────────────────────────────────────────

def test_http_server_serves_html(tmp_path):
    """GET / returns dashboard HTML with HTTP 200."""
    docs = tmp_path / "docs"
    docs.mkdir()
    state_dir = docs / "STATE"
    state_dir.mkdir()
    (docs / "dashboard.html").write_text(
        "<html><body>Grid Dashboard</body></html>", encoding="utf-8"
    )
    (state_dir / "dashboard_state.json").write_text(
        '{"last_updated_at":"2026-05-01T00:00:00Z"}', encoding="utf-8"
    )

    server, port = _start_test_server(docs, state_dir / "dashboard_state.json")
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert "Grid Dashboard" in body
    finally:
        server.shutdown()


# ── test 2 ────────────────────────────────────────────────────────────────────

def test_http_server_serves_state(tmp_path):
    """GET /state.json returns valid JSON with expected fields."""
    docs = tmp_path / "docs"
    docs.mkdir()
    state_dir = docs / "STATE"
    state_dir.mkdir()
    (docs / "dashboard.html").write_text("<html>ok</html>", encoding="utf-8")
    state_data = {
        "last_updated_at": "2026-05-01T00:00:00Z",
        "market": {"btc": {"price": 77000, "session_active": "ny_am"}},
    }
    (state_dir / "dashboard_state.json").write_text(
        json.dumps(state_data), encoding="utf-8"
    )

    server, port = _start_test_server(docs, state_dir / "dashboard_state.json")
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/state.json")
        assert resp.status == 200
        ct = resp.headers.get("Content-Type", "")
        assert "application/json" in ct
        loaded = json.loads(resp.read().decode("utf-8"))
        assert loaded["market"]["btc"]["price"] == 77000
    finally:
        server.shutdown()


# ── test 3 ────────────────────────────────────────────────────────────────────

def test_state_market_section_present(tmp_path):
    """build_state() includes current regime + positions sections.

    Forecast section was removed in TZ-FORECAST-DECOMMISSION
    (see FORECAST_CALIBRATION_DIAGNOSTIC_v1.md).
    """
    from services.dashboard.state_builder import build_state

    state = build_state(
        snapshots_path=tmp_path / "snapshots.csv",
        state_latest_path=tmp_path / "state.json",
        signals_path=tmp_path / "signals.jsonl",
        null_signals_path=tmp_path / "null.jsonl",
        events_path=tmp_path / "events.jsonl",
        liq_path=tmp_path / "liq.json",
        competition_path=tmp_path / "comp.json",
        engine_path=tmp_path / "engine.json",
    )
    assert "regime" in state, "regime section missing from dashboard state"
    assert "positions" in state, "positions section missing from dashboard state"
    assert "forecast" not in state, "forecast section must be removed (TZ-FORECAST-DECOMMISSION)"
    regime = state["regime"]
    assert set(regime.keys()) >= {"label", "confidence", "stability", "stable_bars"}


# ── test 4 ────────────────────────────────────────────────────────────────────

def test_state_portfolio_section_filtered(tmp_path):
    """positions aggregates long/short bots from snapshots under current schema."""
    import pandas as pd
    from services.dashboard.state_builder import build_state

    rows = [
        {
            "ts_utc": "2026-05-01T10:00:00Z", "bot_id": "111",
            "bot_name": "OP1", "alias": "OP_1",
            "status": "2", "position": "-0.5", "profit": 100.0, "current_profit": 50.0,
        },
        {
            "ts_utc": "2026-05-01T10:00:00Z", "bot_id": "999",
            "bot_name": "PUBLIC", "alias": "PUB",
            "status": "2", "position": "0.3", "profit": 9999.0, "current_profit": 8888.0,
        },
    ]
    csv_path = tmp_path / "snapshots.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    aliases = tmp_path / "bot_aliases.json"
    aliases.write_text('{"111": "OP_1"}', encoding="utf-8")

    state = build_state(
        snapshots_path=csv_path,
        state_latest_path=tmp_path / "state.json",
        signals_path=tmp_path / "signals.jsonl",
        null_signals_path=tmp_path / "null.jsonl",
        events_path=tmp_path / "events.jsonl",
        liq_path=tmp_path / "liq.json",
        competition_path=tmp_path / "comp.json",
        engine_path=tmp_path / "engine.json",
    )
    positions = state["positions"]
    short_aliases = {b["alias"] for b in positions["shorts"]["active_bots"]}
    long_aliases = {b["alias"] for b in positions["longs"]["active_bots"]}
    assert "OP_1" in short_aliases
    assert "PUB" in long_aliases
    assert positions["shorts"]["total_btc"] == -0.5
    assert positions["longs"]["total_usd"] == 0.0


# ── test 5 ────────────────────────────────────────────────────────────────────

def test_dashboard_localhost_only():
    """HTTP server bind host is 127.0.0.1, not 0.0.0.0 (localhost-only security)."""
    from services.dashboard.http_server import _BIND_HOST

    assert _BIND_HOST == "127.0.0.1", (
        f"dashboard HTTP server must bind to 127.0.0.1, got {_BIND_HOST!r} — "
        "binding to 0.0.0.0 would expose the dashboard on the network"
    )
