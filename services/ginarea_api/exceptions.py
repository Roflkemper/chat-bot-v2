from __future__ import annotations


class GinAreaAPIError(Exception):
    """Base exception for GinArea API errors."""


class GinAreaAuthError(GinAreaAPIError):
    """Raised on authentication failures."""


class GinAreaRateLimitError(GinAreaAPIError):
    """Raised when the GinArea API rate limits requests."""


class GinAreaServerError(GinAreaAPIError):
    """Raised when the GinArea API returns persistent 5xx responses."""


class GinAreaTestFailedError(GinAreaAPIError):
    """Raised when a GinArea backtest finishes with FAILED status."""

    def __init__(self, test_id: int, error_code: int, message: str) -> None:
        super().__init__(message)
        self.test_id = test_id
        self.error_code = error_code


class GinAreaTestTimeoutError(GinAreaAPIError):
    """Raised when a GinArea backtest does not finish in time."""


class GinAreaProductionBotGuardError(GinAreaAPIError):
    """Raised on attempt to mutate a bot in production set."""
