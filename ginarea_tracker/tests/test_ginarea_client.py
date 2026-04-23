"""Tests for ginarea_client.py — all network calls mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
import requests

from ginarea_tracker.ginarea_client import GinAreaClient, RETRY_MAX

# Minimal valid TOTP secret (BASE32)
_SECRET = "JBSWY3DPEHPK3PXP"
_URL = "https://api.example.com"


def _make_client(session: MagicMock | None = None) -> GinAreaClient:
    c = GinAreaClient(_URL, "user@test.com", "pass", _SECRET)
    if session is not None:
        c._session = session
    return c


def _mock_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or {}
    resp.raise_for_status.return_value = None
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(
            f"HTTP {status}", response=resp
        )
    return resp


# ── login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_success(self):
        session = MagicMock()
        session.post.return_value = _mock_response(200, {
            "accessToken": "acc123", "refreshToken": "ref456"
        })
        c = _make_client(session)
        c.login()
        assert c._access_token == "acc123"
        assert c._refresh_token == "ref456"
        assert session.post.call_count == 1
        args, kwargs = session.post.call_args
        assert "/auth/login" in args[0]

    def test_login_sends_totp(self):
        session = MagicMock()
        session.post.return_value = _mock_response(200, {
            "accessToken": "a", "refreshToken": "r"
        })
        c = _make_client(session)
        c.login()
        _, kwargs = session.post.call_args
        body = kwargs["json"]
        assert "totp" in body
        assert len(body["totp"]) == 6

    def test_login_raises_on_http_error(self):
        session = MagicMock()
        session.post.return_value = _mock_response(401)
        c = _make_client(session)
        with pytest.raises(requests.HTTPError):
            c.login()


# ── refresh ───────────────────────────────────────────────────────────────────

class TestRefresh:
    def test_refresh_success(self):
        session = MagicMock()
        session.post.return_value = _mock_response(200, {
            "accessToken": "new_acc", "refreshToken": "new_ref"
        })
        c = _make_client(session)
        c._refresh_token = "old_ref"
        result = c.refresh()
        assert result is True
        assert c._access_token == "new_acc"
        assert c._refresh_token == "new_ref"

    def test_refresh_returns_false_on_error(self):
        session = MagicMock()
        session.post.side_effect = requests.ConnectionError("no network")
        c = _make_client(session)
        c._refresh_token = "tok"
        assert c.refresh() is False

    def test_refresh_returns_false_when_no_token(self):
        c = _make_client()
        c._refresh_token = None
        assert c.refresh() is False


# ── 401 handling ──────────────────────────────────────────────────────────────

class TestTokenRefreshOn401:
    def test_401_triggers_refresh_then_retry(self):
        session = MagicMock()

        resp_401 = _mock_response(401)
        resp_ok = _mock_response(200, {"data": "ok"})
        resp_refresh = _mock_response(200, {"accessToken": "new_acc", "refreshToken": "new_ref"})

        # First GET → 401; POST /auth/refresh → ok; second GET → 200
        session.request.side_effect = [resp_401, resp_ok]
        session.post.return_value = resp_refresh

        c = _make_client(session)
        c._access_token = "old_acc"
        c._refresh_token = "ref"

        result = c._request("GET", "/bots")
        assert result == {"data": "ok"}
        assert session.request.call_count == 2

    def test_401_triggers_login_when_refresh_fails(self):
        session = MagicMock()

        resp_401 = _mock_response(401)
        resp_ok = _mock_response(200, {"data": "ok"})
        resp_login = _mock_response(200, {"accessToken": "fresh_acc", "refreshToken": "fresh_ref"})

        session.request.side_effect = [resp_401, resp_ok]
        # First post call = refresh (fails), second = login (succeeds)
        resp_refresh_fail = _mock_response(401)
        resp_refresh_fail.raise_for_status.side_effect = requests.HTTPError("fail")
        session.post.side_effect = [resp_refresh_fail, resp_login]

        c = _make_client(session)
        c._access_token = "old"
        c._refresh_token = "old_ref"

        result = c._request("GET", "/bots")
        assert result == {"data": "ok"}
        assert c._access_token == "fresh_acc"


# ── retry logic ───────────────────────────────────────────────────────────────

class TestRetryLogic:
    @patch("ginarea_tracker.ginarea_client.time.sleep")
    def test_retries_on_connection_error(self, mock_sleep):
        session = MagicMock()
        session.request.side_effect = [
            requests.ConnectionError("err"),
            requests.ConnectionError("err"),
            _mock_response(200, {"ok": True}),
        ]
        c = _make_client(session)
        c._access_token = "tok"
        result = c._request("GET", "/bots")
        assert result == {"ok": True}
        assert session.request.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("ginarea_tracker.ginarea_client.time.sleep")
    def test_retries_on_timeout(self, mock_sleep):
        session = MagicMock()
        session.request.side_effect = [
            requests.Timeout("timeout"),
            _mock_response(200, {"ok": True}),
        ]
        c = _make_client(session)
        c._access_token = "tok"
        result = c._request("GET", "/bots")
        assert result == {"ok": True}

    @patch("ginarea_tracker.ginarea_client.time.sleep")
    def test_retries_on_5xx(self, mock_sleep):
        session = MagicMock()
        resp_500 = _mock_response(500)
        resp_ok = _mock_response(200, {"ok": True})
        session.request.side_effect = [resp_500, resp_ok]
        c = _make_client(session)
        c._access_token = "tok"
        result = c._request("GET", "/bots")
        assert result == {"ok": True}

    @patch("ginarea_tracker.ginarea_client.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError("permanent failure")
        c = _make_client(session)
        c._access_token = "tok"
        with pytest.raises(requests.ConnectionError):
            c._request("GET", "/bots")
        assert session.request.call_count == RETRY_MAX

    @patch("ginarea_tracker.ginarea_client.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep):
        session = MagicMock()
        session.request.side_effect = [
            requests.ConnectionError(),
            requests.ConnectionError(),
            requests.ConnectionError(),
            _mock_response(200, {}),
        ]
        c = _make_client(session)
        c._access_token = "tok"
        c._request("GET", "/bots")
        delays = [c[0][0] for c in mock_sleep.call_args_list]
        # delays should be 1.0, 2.0, 4.0 ...
        assert delays[1] == delays[0] * 2


# ── public API methods ────────────────────────────────────────────────────────

class TestPublicApiMethods:
    def test_get_bots(self):
        session = MagicMock()
        session.request.return_value = _mock_response(200, [{"id": "1", "name": "BOT"}])
        c = _make_client(session)
        c._access_token = "tok"
        result = c.get_bots()
        assert result == [{"id": "1", "name": "BOT"}]
        _, kwargs = session.request.call_args
        assert "/bots" in session.request.call_args[0][1]

    def test_get_bot_stat(self):
        session = MagicMock()
        session.request.return_value = _mock_response(200, {"status": "active"})
        c = _make_client(session)
        c._access_token = "tok"
        result = c.get_bot_stat("999")
        assert result["status"] == "active"
        assert "/bots/999/stat" in session.request.call_args[0][1]

    def test_get_bot_params(self):
        session = MagicMock()
        session.request.return_value = _mock_response(200, {"side": "short"})
        c = _make_client(session)
        c._access_token = "tok"
        result = c.get_bot_params("999")
        assert result["side"] == "short"
        assert "/bots/999/params" in session.request.call_args[0][1]

    def test_auth_header_sent(self):
        session = MagicMock()
        session.request.return_value = _mock_response(200, {})
        c = _make_client(session)
        c._access_token = "mytoken"
        c._request("GET", "/bots")
        _, kwargs = session.request.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer mytoken"
