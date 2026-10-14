"""Typed, deliberately body-free errors for the undocumented cloud API."""

from __future__ import annotations


class ApiError(Exception):
    """A remote failure; response bodies, URLs and credentials stay private."""

    def __init__(
        self,
        message: str = "Cloud request failed",
        *,
        status: int = 0,
        code: int | str | None = None,
        retry_after: float = 0,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = retry_after


class AuthenticationError(ApiError):
    """The account must explicitly sign in again."""


class RateLimitError(ApiError):
    """Pause the whole account until the server's cooldown expires."""


class AgreementRequiredError(ApiError):
    """Review updated agreements in the official Panasonic app."""


class AppVersionError(ApiError):
    """The app protocol version needs an update, not a new password."""


class CommunicationError(ApiError):
    """A transient network, cloud or adapter failure."""


class ProtocolError(ApiError):
    """An unexpected or unsupported response."""


class CommandUncertainError(ApiError):
    """A write may have reached the device; never silently replay it."""
