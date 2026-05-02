"""GinArea HTTP API client with JWT auth, auto TOTP, and retry logic."""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import pyotp
import requests

logger = logging.getLogger(__name__)

RETRY_MAX = 5
RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt


class AuthError(Exception):
    pass


class GinAreaClient:
    def __init__(
        self,
        api_url: str,
        email: str,
        password: str,
        totp_secret: str,
        session: requests.Session | None = None,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._email = email
        self._password = password
        # Strip spaces and uppercase — matches Google Authenticator export format
        self._totp = pyotp.TOTP(totp_secret.replace(" ", "").upper())
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._session = session or requests.Session()

    # --- Public API ---

    def login(self) -> None:
        """Two-step login: /accounts/login → /accounts/twoFactor (TOTP)."""
        step1 = self._post_noauth("/accounts/login", {
            "email": self._email,
            "password": hashlib.sha1(self._password.encode()).hexdigest(),
        })
        if step1.get("twoFactorEnable"):
            initial_token = step1["accessToken"]
            resp = self._session.post(
                self._api_url + "/accounts/twoFactor",
                json={"code": self._totp.now()},
                headers={"Authorization": f"Bearer {initial_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            final = resp.json()
            self._access_token = final["accessToken"]
            self._refresh_token = final["refreshToken"]
            logger.info("Login successful (2FA)")
        else:
            self._access_token = step1["accessToken"]
            self._refresh_token = step1["refreshToken"]
            logger.info("Login successful (no 2FA)")

    def refresh(self) -> bool:
        """Refresh access token via refreshToken. Returns True on success."""
        if not self._refresh_token:
            return False
        try:
            data = self._post_noauth("/accounts/refresh", {"refreshToken": self._refresh_token})
            self._access_token = data["accessToken"]
            if "refreshToken" in data:
                self._refresh_token = data["refreshToken"]
            logger.debug("Token refreshed")
            return True
        except Exception as exc:
            logger.warning("Token refresh failed: %s", exc)
            return False

    def get_bots(self) -> list[dict]:
        return self._get("/bots")

    def get_bot_stat(self, bot_id: str) -> dict:
        return self._get(f"/bots/{bot_id}/stat")

    def get_bot_params(self, bot_id: str) -> dict:
        return self._get(f"/bots/{bot_id}/params")

    # --- Internal ---

    def _get(self, path: str) -> Any:
        return self._request("GET", path)

    def _post_noauth(self, path: str, body: dict) -> dict:
        resp = self._session.post(self._api_url + path, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _request(self, method: str, path: str) -> Any:
        url = self._api_url + path
        last_exc: Exception | None = None

        for attempt in range(RETRY_MAX):
            try:
                headers = self._auth_headers()
                resp = self._session.request(method, url, headers=headers, timeout=30)

                if resp.status_code == 401:
                    logger.info("401 — attempting token refresh")
                    if not self.refresh():
                        logger.info("Refresh failed — re-logging in")
                        self.login()
                    headers = self._auth_headers()
                    resp = self._session.request(method, url, headers=headers, timeout=30)

                if resp.status_code >= 500:
                    raise requests.HTTPError(
                        f"Server error {resp.status_code}", response=resp
                    )

                resp.raise_for_status()
                return resp.json()

            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_exc = exc
                if attempt < RETRY_MAX - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Attempt %d/%d failed: %s — retry in %.1fs",
                        attempt + 1, RETRY_MAX, exc, delay,
                    )
                    time.sleep(delay)

        raise last_exc  # type: ignore[misc]

    def _auth_headers(self) -> dict[str, str]:
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}
