"""HTTP failure classification without response-body logging."""

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from ..errors import (
    AgreementRequiredError,
    ApiError,
    AppVersionError,
    AuthenticationError,
    CommunicationError,
    ProtocolError,
    RateLimitError,
)


def retry_delay(value: str | None) -> float:
    try:
        return min(86400.0, max(0.0, float(value)))
    except ValueError, TypeError:
        try:
            moment = parsedate_to_datetime(value)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
            return min(86400.0, max(0.0, (moment - datetime.now(UTC)).total_seconds()))
        except ValueError, TypeError, OverflowError:
            return 60.0


async def has_new_version_been_published(response) -> bool:
    try:
        return str(json.loads(await response.text()).get("code")) == "4106"
    except ValueError, AttributeError:
        return False


async def check_response(response, function_description, expected_status, payload=None):
    expected = expected_status if isinstance(expected_status, (list, tuple)) else [expected_status]
    if response.status in expected:
        return
    try:
        body = json.loads(await response.text())
        code = body.get("code", body.get("error")) if isinstance(body, dict) else None
        if not isinstance(code, (int, str)):
            code = None
    except ValueError:
        code = None
    raise failure(response.status, code, response.headers)


def failure(status: int, code, headers) -> ApiError:
    """Classify HTTP errors and known error envelopes inside HTTP 200."""
    if not isinstance(code, (int, str)):
        code = None
    kwargs = {"status": status, "code": code}
    if str(code) == "4103":
        return AgreementRequiredError("Review updated agreements in the Panasonic app", **kwargs)
    if str(code) == "4106":
        return AppVersionError("Update the app version in integration options", **kwargs)
    if status == 429 or str(code) == "429":
        return RateLimitError(
            "Panasonic rate limit; account cooling down",
            retry_after=retry_delay(headers.get("Retry-After")),
            **kwargs,
        )
    if status == 401 or code in {
        "invalid_grant",
        "invalid_user_password",
        "access_denied",
    }:
        return AuthenticationError("Panasonic sign-in must be renewed", **kwargs)
    # A generic 403 may be an unsupported device/endpoint, not bad credentials.
    if status >= 500 or status in {408, 425} or str(code) in {"5001", "5005"}:
        return CommunicationError("Panasonic cloud or adapter temporarily unavailable", **kwargs)
    if status in {200, 400, 403}:
        return ProtocolError("Panasonic rejected this request", **kwargs)
    return ApiError("Unexpected HTTP status from Panasonic", **kwargs)
