"""In-memory token state; Home Assistant Store owns persistence."""

from __future__ import annotations

import base64
import json
import time


class PanasonicSettings:
    def __init__(self, data: dict | None = None):
        self.data = dict(data or {})
        self.changed = False

    @property
    def access_token(self):
        return self.data.get("access_token")

    @property
    def refresh_token(self):
        return self.data.get("refresh_token")

    @property
    def scope(self):
        return self.data.get("scope", "openid offline_access comfortcloud.control a2w.control")

    @property
    def clientId(self):
        return self.data.get("client_id")

    @clientId.setter
    def clientId(self, value):
        if value != self.clientId:
            self.data["client_id"] = value
            self.changed = True

    @property
    def is_access_token_valid(self) -> bool:
        if not self.access_token:
            return False
        expiries = []
        stored = self.data.get("expires_at")
        if isinstance(stored, (int, float)):
            expiries.append(stored)
        try:
            segment = self.access_token.split(".")[1]
            payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
            expiry = payload.get("exp")
            if isinstance(expiry, (int, float)):
                expiries.append(expiry)
        except IndexError, ValueError, TypeError:
            pass
        # An unverified JWT is used ONLY as an upper bound on local lifetime.
        # The server authenticates the token. One future expiry must not mask
        # another expired one, and a token without a lifetime is refreshed.
        return bool(expiries) and time.time() + 90 < min(expiries)

    def set_token(
        self, access_token=None, refresh_token=None, access_token_expires=None, scope=None
    ):
        for key, value in (
            ("access_token", access_token),
            ("refresh_token", refresh_token),
            ("expires_at", access_token_expires),
            ("scope", scope),
        ):
            if value is not None:
                self.data[key] = value
        self.changed = True
