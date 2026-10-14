"""Compatibility exception names for the adapted authentication flow."""

from ..errors import ApiError


class ResponseError(ApiError):
    """Unrecognized login response, with a fixed non-sensitive message."""

    def __init__(self, *args, **kwargs):
        super().__init__("Unexpected Panasonic sign-in response")


class MFARequiredError(ApiError):
    """An interactive second factor is required; never store the OTP."""

    def __init__(self, mfa_token=None):
        super().__init__("Panasonic requires a one-time verification code")


LoginError = ResponseError
