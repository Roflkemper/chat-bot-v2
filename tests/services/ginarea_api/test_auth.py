from __future__ import annotations

import os

import pyotp
import pytest

from services.ginarea_api.auth import GinAreaAuth, GinAreaCredentials
from services.ginarea_api.client import GinAreaClient
from services.ginarea_api.exceptions import GinAreaAuthError


def test_get_totp_code_six_digits():
    auth = GinAreaAuth(GinAreaCredentials("e@example.com", "sha1", pyotp.random_base32()))
    code = auth.get_totp_code()
    assert code.isdigit()
    assert len(code) == 6


def test_get_totp_code_changes_over_time():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    assert totp.at(0) != totp.at(30)


def test_login_two_factor_flow_success(httpx_mock, load_fixture):
    client = GinAreaClient(rate_limit_min_interval=0.0)
    auth = GinAreaAuth(GinAreaCredentials("e@example.com", "sha1", pyotp.random_base32()))
    httpx_mock.add_response(json={"twoFactorRequired": True})
    httpx_mock.add_response(json=load_fixture("twofactor_response.json"))
    token = auth.login(client)
    assert token == "REDACTED_BEARER_TOKEN"
    assert client.token == "REDACTED_BEARER_TOKEN"


def test_login_invalid_credentials_raises_ginarea_auth_error(httpx_mock):
    client = GinAreaClient(rate_limit_min_interval=0.0)
    auth = GinAreaAuth(GinAreaCredentials("e@example.com", "sha1", pyotp.random_base32()))
    httpx_mock.add_response(status_code=401, json={"message": "invalid"})
    with pytest.raises(GinAreaAuthError):
        auth.login(client)


def test_from_env_reads_three_vars(monkeypatch):
    monkeypatch.setenv("GINAREA_EMAIL", "a@example.com")
    monkeypatch.setenv("GINAREA_PASSWORD_SHA1", "abc")
    monkeypatch.setenv("GINAREA_TOTP_SECRET", "base32")
    auth = GinAreaAuth.from_env()
    assert auth.creds.email == "a@example.com"


def test_from_env_missing_var_raises_keyerror(monkeypatch):
    monkeypatch.delenv("GINAREA_EMAIL", raising=False)
    monkeypatch.delenv("GINAREA_PASSWORD_SHA1", raising=False)
    monkeypatch.delenv("GINAREA_TOTP_SECRET", raising=False)
    with pytest.raises(KeyError):
        GinAreaAuth.from_env()


def test_login_returns_bearer_token_from_response(httpx_mock):
    client = GinAreaClient(rate_limit_min_interval=0.0)
    auth = GinAreaAuth(GinAreaCredentials("e@example.com", "sha1", pyotp.random_base32()))
    httpx_mock.add_response(json={"token": "REDACTED_BEARER_TOKEN"})
    assert auth.login(client) == "REDACTED_BEARER_TOKEN"
