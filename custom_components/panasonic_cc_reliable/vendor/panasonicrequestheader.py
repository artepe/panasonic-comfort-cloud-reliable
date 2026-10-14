"""Request signing, adapted from the MIT upstream protocol implementation."""

import hashlib
from datetime import UTC, datetime


class PanasonicRequestHeader:
    @staticmethod
    async def get(settings, app_version, include_client_id=True):
        now = datetime.now(UTC).replace(microsecond=0)
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        milliseconds = str(int(now.timestamp()) * 1000)
        material = (
            "Comfort Cloud"
            + "521325fb2dd486bf4831b47644317fca"
            + milliseconds
            + "Bearer "
            + settings.access_token
        )
        digest = hashlib.sha256(material.encode()).hexdigest()
        headers = {
            "accept": "application/json; charset=utf-8",
            "content-type": "application/json",
            "user-agent": "G-RAC",
            "x-app-name": "Comfort Cloud",
            "x-app-timestamp": stamp,
            "x-app-type": "1",
            "x-app-version": await app_version.get(),
            "x-cfc-api-key": digest[:9] + "cfc" + digest[9:],
            "x-user-authorization-v2": "Bearer " + settings.access_token,
        }
        if include_client_id and settings.clientId:
            headers["x-client-id"] = settings.clientId
        return headers
