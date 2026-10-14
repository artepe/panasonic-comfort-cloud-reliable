"""Account-wide bounded transport independent of the upstream device client."""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from urllib.parse import quote_plus, urlencode, urlsplit

import aiohttp

from .const import BASE_URL, MIN_REQUEST_GAP
from .errors import (
    AuthenticationError,
    CommandUncertainError,
    CommunicationError,
    ProtocolError,
    RateLimitError,
)
from .models import Device, discover, validate_status
from .vendor.ccappversion import CCAppVersion
from .vendor.helpers import check_response, failure, retry_delay
from .vendor.panasonicauthentication import PanasonicAuthentication
from .vendor.panasonicrequestheader import PanasonicRequestHeader
from .vendor.panasonicsettings import PanasonicSettings

TokenSaver = Callable[[dict], Awaitable[None]]


class RequestSession:
    """Private cookie jar, finite timeouts, pacing and no body/URL logs."""

    def __init__(self, session: aiohttp.ClientSession, gap: float = MIN_REQUEST_GAP):
        self.session = session
        self.gap = gap
        self.last_request = 0.0
        self.cooldown_until = 0.0
        self.requests = 0
        self.cookie_jar = session.cookie_jar

    async def request(self, method: str, url: str, **kwargs):
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or not (
            host == "panasonic.com" or host.endswith(".panasonic.com")
        ):
            raise ProtocolError("Sign-in attempted an unrecognized destination")
        kwargs.setdefault("allow_redirects", False)
        remaining = self.cooldown_until - time.monotonic()
        if remaining > 0:
            raise RateLimitError("Account is cooling down", retry_after=remaining)
        delay = self.gap - (time.monotonic() - self.last_request)
        if delay > 0:
            await asyncio.sleep(delay)
        self.last_request = time.monotonic()
        self.requests += 1
        try:
            response = await self.session.request(
                method, url, timeout=aiohttp.ClientTimeout(total=30), **kwargs
            )
            try:
                await response.read()
            finally:
                response.release()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CommunicationError("Request timed out or the cloud connection failed") from err
        if response.status == 429:
            self.cooldown_until = time.monotonic() + max(
                1, retry_delay(response.headers.get("Retry-After"))
            )
        return response

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url=None, **kwargs):
        return await self.request("POST", url, **kwargs)


class ComfortCloudClient:
    """One token lifecycle and one request queue per Panasonic account."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        app_version: str,
        tokens=None,
        token_saver: TokenSaver | None = None,
        gap=MIN_REQUEST_GAP,
    ):
        self.transport = RequestSession(session, gap)
        self.settings = PanasonicSettings(tokens)
        self.app_version = CCAppVersion(app_version)
        self.auth = PanasonicAuthentication(self.transport, self.settings, self.app_version)
        self._lock = asyncio.Lock()
        self._token_saver = token_saver
        self.refreshes = 0

    async def _persist(self):
        if self.settings.changed and self._token_saver:
            await self._token_saver(dict(self.settings.data))
            self.settings.changed = False

    async def login(self, username: str, password: str, otp: str | None = None):
        async with self._lock:
            try:
                async with asyncio.timeout(90):
                    await self.auth.authenticate(username, password, otp)
            except (KeyError, TypeError, ValueError) as err:
                raise ProtocolError("Panasonic sign-in format changed") from err
            finally:
                await self._persist()

    async def complete_mfa(self, otp: str):
        async with self._lock:
            try:
                async with asyncio.timeout(90):
                    await self.auth.verify_mfa(otp)
                    await self.auth._retrieve_client_acc()
            except (KeyError, TypeError, ValueError) as err:
                raise ProtocolError("Panasonic MFA response format changed") from err
            finally:
                await self._persist()

    async def _ensure_auth(self, force=False):
        if not force and self.settings.is_access_token_valid and self.settings.clientId:
            return
        if not self.settings.refresh_token:
            raise AuthenticationError("Sign in again to Panasonic Comfort Cloud")
        try:
            if force or not self.settings.is_access_token_valid:
                await self.auth.refresh_token()
                self.refreshes += 1
            if force or not self.settings.clientId:
                await self.auth._retrieve_client_acc()
        except (KeyError, TypeError, ValueError) as err:
            raise ProtocolError("Unexpected token response") from err
        finally:
            # Persist a rotated refresh token even if client registration fails.
            await self._persist()

    async def request(self, method: str, path: str, payload=None, *, read_only=True) -> dict:
        """Retry reads twice; writes are sent once and never replayed."""
        async with self._lock:
            await self._ensure_auth()
            auth_retried = False
            for attempt in range(3 if read_only else 1):
                try:
                    headers = await PanasonicRequestHeader.get(self.settings, self.app_version)
                    response = await self.transport.request(
                        method,
                        BASE_URL + path,
                        headers=headers,
                        json=payload,
                        allow_redirects=False,
                    )
                    await check_response(response, "cloud_request", 200)
                    try:
                        data = json.loads(await response.text())
                    except ValueError as err:
                        raise ProtocolError("Cloud returned invalid JSON") from err
                    if not isinstance(data, dict):
                        raise ProtocolError("Cloud returned an unexpected data shape")
                    # Some gateways return an API failure inside HTTP 200.
                    if data.get("code") not in (None, 0, 200, "0", "200") and (
                        "message" in data or "error" in data
                    ):
                        error = failure(200, data.get("code"), response.headers)
                        if isinstance(error, RateLimitError):
                            self.transport.cooldown_until = time.monotonic() + max(
                                1, error.retry_after
                            )
                        raise error
                    return data
                except AuthenticationError:
                    if not read_only or auth_retried:
                        raise
                    auth_retried = True
                    await self._ensure_auth(force=True)
                    if attempt == 2:
                        raise
                except RateLimitError:
                    raise
                except CommunicationError as err:
                    if not read_only:
                        raise CommandUncertainError(
                            "Command delivery is uncertain; refresh status before trying again"
                        ) from err
                    if str(err.code) in {"5001", "5005"}:
                        # Known adapter-offline responses should reach the
                        # labeled cache path immediately, not spend three calls.
                        raise
                    if attempt == 2:
                        raise
                    await asyncio.sleep(min(5, 2**attempt + random.random()))
            raise CommunicationError("Cloud request did not complete")

    async def devices(self) -> list[Device]:
        return discover(await self.request("GET", "/device/group"))

    async def status(self, device: Device) -> tuple[dict, str]:
        if device.kind == "unknown":
            raise ProtocolError("Unsupported device type; inspect redacted diagnostics")
        if device.kind == "hws":
            # HWS per-device AC calls are rejected. Use only the group listing.
            rows = await self.devices()
            row = next((item for item in rows if item.id == device.id), None)
            if row is None:
                raise ProtocolError("Device is no longer in the account")
            return validate_status(device, row.listing), "group_listing"
        try:
            data = await self._status_request(device, direct=True)
            return validate_status(device, data), "live"
        except CommunicationError:
            # Only adapter/cloud communication failures permit a cache fallback.
            # Rate limits, rejected auth and malformed schemas must propagate.
            data = await self._status_request(device, direct=False)
            return validate_status(device, data), "cached"

    async def _status_request(self, device: Device, direct: bool) -> dict:
        if device.kind == "aquarea":
            query = urlencode({"gwid": device.guid, "deviceDirect": int(direct)})
            return await self.request(
                "POST",
                "/remote/v1/app/common/transfer",
                {"apiName": "/remote/v1/api/devices?" + query, "requestMethod": "GET"},
            )
        # The app uses slash -> 'f' substitution before URL encoding.
        guid = quote_plus(device.guid.replace("/", "f"))
        return await self.request("GET", "/deviceStatus/" + ("" if direct else "now/") + guid)

    async def control(self, device: Device, parameters: dict) -> None:
        if device.kind != "ac":
            raise ProtocolError("This release only enables AC controls")
        allowed = {
            "operate",
            "operationMode",
            "temperatureSet",
            "fanSpeed",
            "ecoMode",
            "nanoe",
            "airSwingUD",
            "airSwingLR",
            "fanAutoMode",
        }
        if not parameters or not parameters.keys() <= allowed:
            raise ProtocolError("Unsupported control parameter")
        await self.request(
            "POST",
            "/deviceStatus/control",
            {"deviceGuid": device.guid, "parameters": parameters},
            read_only=False,
        )

    async def energy(self, device: Device, day: str, timezone: str) -> dict:
        if device.kind != "ac":
            raise ProtocolError("Energy history is currently enabled only for AC devices")
        return await self.request(
            "POST",
            "/deviceHistoryData",
            {
                "deviceGuid": device.guid,
                "dataMode": 2,
                "date": day,
                "osTimezone": comfort_cloud_timezone(timezone),
            },
        )

    def statistics(self) -> dict:
        return {
            "requests": self.transport.requests,
            "token_refreshes": self.refreshes,
            "cooldown_seconds": max(0, self.transport.cooldown_until - time.monotonic()),
        }


def comfort_cloud_timezone(name, at=None):
    """The history API expects an offset, not an IANA zone name."""
    import re
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    if isinstance(name, str) and re.fullmatch(r"[+-](?:0\d|1[0-4]):[0-5]\d", name):
        return name
    try:
        moment = at or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ValueError("A timezone-aware time is required")
        offset = moment.astimezone(ZoneInfo(name)).utcoffset()
        seconds = int(offset.total_seconds())
    except (ZoneInfoNotFoundError, TypeError, ValueError, AttributeError) as err:
        raise ProtocolError("Cannot determine Comfort Cloud timezone offset") from err
    hours, remainder = divmod(abs(seconds), 3600)
    return f"{'+' if seconds >= 0 else '-'}{hours:02d}:{remainder // 60:02d}"
