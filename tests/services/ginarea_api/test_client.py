from __future__ import annotations

import httpx
import pytest
import pyotp

from services.ginarea_api.auth import GinAreaAuth, GinAreaCredentials
from services.ginarea_api.client import GinAreaClient
from services.ginarea_api.exceptions import (
    GinAreaAPIError,
    GinAreaAuthError,
    GinAreaRateLimitError,
    GinAreaServerError,
)


def test_request_attaches_bearer_token(httpx_mock, mock_client):
    httpx_mock.add_response(json={"ok": True})
    mock_client.request("GET", "/bots")
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer TEST_BEARER_TOKEN"


def test_request_no_auth_omits_authorization_header(httpx_mock, mock_client):
    httpx_mock.add_response(json={"ok": True})
    mock_client.request("GET", "/public", requires_auth=False)
    request = httpx_mock.get_requests()[0]
    assert "Authorization" not in request.headers


def test_request_rate_limits_to_min_interval(httpx_mock, monkeypatch):
    client = GinAreaClient(token="t", rate_limit_min_interval=1.1)
    httpx_mock.add_response(json={"ok": True})
    monotonic_values = iter([10.0, 10.1, 11.3])
    slept: list[float] = []
    monkeypatch.setattr("services.ginarea_api.client.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr("services.ginarea_api.client.time.sleep", lambda seconds: slept.append(seconds))
    client._last_call_at = 9.5
    client.request("GET", "/bots")
    assert slept == pytest.approx([0.6])


def test_request_401_triggers_reauth_and_retry_once(httpx_mock):
    auth = GinAreaAuth(GinAreaCredentials("e@example.com", "sha1", pyotp.random_base32()))  # type: ignore[name-defined]
    client = GinAreaClient(auth=auth, token="old", rate_limit_min_interval=0.0)
    httpx_mock.add_response(status_code=401, json={"message": "expired"})
    httpx_mock.add_response(json={"token": "NEW_TOKEN"})
    httpx_mock.add_response(json={"ok": True})
    assert client.request("GET", "/bots") == {"ok": True}
    assert client.token == "NEW_TOKEN"


def test_request_401_second_time_raises_ginarea_auth_error(httpx_mock):
    auth = GinAreaAuth(GinAreaCredentials("e@example.com", "sha1", pyotp.random_base32()))  # type: ignore[name-defined]
    client = GinAreaClient(auth=auth, token="old", rate_limit_min_interval=0.0)
    httpx_mock.add_response(status_code=401, json={"message": "expired"})
    httpx_mock.add_response(json={"token": "NEW_TOKEN"})
    httpx_mock.add_response(status_code=401, json={"message": "still bad"})
    with pytest.raises(GinAreaAuthError):
        client.request("GET", "/bots")


def test_request_429_waits_121s_and_retries(httpx_mock, monkeypatch, mock_client):
    slept: list[float] = []
    monkeypatch.setattr("services.ginarea_api.client.time.sleep", lambda seconds: slept.append(seconds))
    httpx_mock.add_response(status_code=429, json={"message": "rate"})
    httpx_mock.add_response(json={"ok": True})
    assert mock_client.request("GET", "/bots") == {"ok": True}
    assert 121.0 in slept


def test_request_429_second_time_raises_ginarea_rate_limit_error(httpx_mock, monkeypatch, mock_client):
    monkeypatch.setattr("services.ginarea_api.client.time.sleep", lambda seconds: None)
    httpx_mock.add_response(status_code=429, json={"message": "rate"})
    httpx_mock.add_response(status_code=429, json={"message": "rate"})
    with pytest.raises(GinAreaRateLimitError):
        mock_client.request("GET", "/bots")


def test_request_5xx_exponential_backoff_succeeds_on_retry(httpx_mock, monkeypatch, mock_client):
    slept: list[float] = []
    monkeypatch.setattr("services.ginarea_api.client.time.sleep", lambda seconds: slept.append(seconds))
    httpx_mock.add_response(status_code=500, json={"message": "error"})
    httpx_mock.add_response(json={"ok": True})
    assert mock_client.request("GET", "/bots") == {"ok": True}
    assert slept == [1]


def test_request_5xx_max_retries_then_raises_ginarea_server_error(httpx_mock, monkeypatch):
    client = GinAreaClient(token="t", rate_limit_min_interval=0.0, max_retries_5xx=2)
    monkeypatch.setattr("services.ginarea_api.client.time.sleep", lambda seconds: None)
    httpx_mock.add_response(status_code=500, text="e1")
    httpx_mock.add_response(status_code=502, text="e2")
    httpx_mock.add_response(status_code=503, text="e3")
    with pytest.raises(GinAreaServerError):
        client.request("GET", "/bots")


def test_request_timeout_raises_ginarea_api_error(monkeypatch, mock_client):
    def _raise(*args, **kwargs):
        raise httpx.TimeoutException("boom")

    monkeypatch.setattr("services.ginarea_api.client.httpx.request", _raise)
    with pytest.raises(GinAreaAPIError):
        mock_client.request("GET", "/bots")


def test_request_200_returns_parsed_json(httpx_mock, mock_client):
    httpx_mock.add_response(json={"hello": "world"})
    assert mock_client.request("GET", "/bots") == {"hello": "world"}
