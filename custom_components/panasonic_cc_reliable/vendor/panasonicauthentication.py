"""Panasonic Auth0 login and MFA compatibility.

Derived from sockless-coding/aio-panasonic-comfort-cloud at
89bc6f608fab2268e39ca8699878542569f8f9c3 (2026-10-13).
Copyright (c) 2020-2025 Jimmy Everling. MIT License; see vendor/LICENSE.
Local changes: no credential/body/redirect logging, secure PKCE randomness,
correct cookie value, urljoin redirects, UTC-independent epoch timestamps,
explicit scope, in-memory settings and a bounded HTTP facade.
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
import secrets
import string
import time
import urllib
import urllib.parse

import aiohttp
from bs4 import BeautifulSoup

from . import exceptions
from .ccappversion import CCAppVersion
from .constants import (
    APP_CLIENT_ID,
    AUTH_0_CLIENT,
    AUTH_API_USER_AGENT,
    AUTH_BROWSER_USER_AGENT,
    BASE_PATH_ACC,
    BASE_PATH_AUTH,
    REDIRECT_URI,
)
from .helpers import check_response, has_new_version_been_published
from .panasonicrequestheader import PanasonicRequestHeader
from .panasonicsettings import PanasonicSettings

_LOGGER = logging.getLogger(__name__)


def generate_random_string(length):
    return "".join((secrets.choice(string.ascii_letters + string.digits) for _ in range(length)))


def get_querystring_parameter_from_header_entry_url(
    response: aiohttp.ClientResponse, header_entry, querystring_parameter
):
    header_entry_value = response.headers[header_entry]
    parsed_url = urllib.parse.urlparse(header_entry_value)
    params = urllib.parse.parse_qs(parsed_url.query)
    return params.get(querystring_parameter, [None])[0]


def get_querystring_parameter_from_url(url: str, querystring_parameter: str):
    """Extract a query parameter from a plain URL string."""
    parsed_url = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed_url.query)
    return params.get(querystring_parameter, [None])[0]


_GUARDIAN_CONFIG_KEYS = ("postActionURL", "serviceUrl", "requestToken", "stateCheckingMechanism")


def _extract_guardian_config(html_text: str) -> dict | None:
    """Extract the inline ``window.__g_config = {...}`` object embedded in
    Auth0 Guardian's hosted MFA widget page ("Panasonic Digital Platform -
    MFA Standard"), served instead of the classic Universal Login MFA
    prompt (whose hidden ``mfa_token`` form field is checked separately)
    for accounts enrolled via Guardian. The object isn't valid JSON
    (unquoted keys, JS comments), so its string-valued fields are pulled
    out with a simple regex rather than parsed structurally.

    Returns None if the page doesn't contain a Guardian config.
    """
    if "__g_config" not in html_text:
        return None
    config = {}
    for key in _GUARDIAN_CONFIG_KEYS:
        match = re.search(f'{key}\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"', html_text)
        if match:
            config[key] = match.group(1)
    if (
        not config.get("requestToken")
        or not config.get("serviceUrl")
        or (not config.get("postActionURL"))
    ):
        return None
    config.setdefault("stateCheckingMechanism", "polling")
    return config


class PanasonicAuthentication:
    def __init__(
        self, client: aiohttp.ClientSession, settings: PanasonicSettings, app_version: CCAppVersion
    ):
        self._client = client
        self._settings = settings
        self._app_version = app_version
        self._mfa_token = None
        self._mfa_parameters = {}
        self._guardian_mfa_config = None
        self._code_verifier = None

    async def authenticate(self, username: str, password: str, otp_code: str | None = None):
        self._client.cookie_jar.clear_domain("authglb.digital.panasonic.com")
        self._mfa_token = None
        self._mfa_parameters = {}
        self._guardian_mfa_config = None
        code_verifier = generate_random_string(43)
        self._code_verifier = code_verifier
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
            .split("=".encode("utf-8"))[0]
            .decode("utf-8")
        )
        authorization_response = await self._authorize(code_challenge)
        authorization_redirect = authorization_response.headers["Location"]
        pass
        if authorization_redirect.startswith(REDIRECT_URI):
            code = get_querystring_parameter_from_header_entry_url(
                authorization_response, "Location", "code"
            )
            await self._request_new_token(code, code_verifier)
        else:
            try:
                code = await self._login(authorization_response, username, password)
                await self._request_new_token(code, code_verifier)
            except exceptions.MFARequiredError:
                if otp_code is None:
                    raise
                pass
                await self.verify_mfa(otp_code)
        await self._retrieve_client_acc()

    async def verify_mfa(self, otp_code: str):
        """Complete a pending MFA/2FA challenge.

        Panasonic's Auth0 tenant serves one of two different challenge
        pages depending on the account's MFA enrollment, detected in
        _login()/the "MFA challenge candidate" branch below:

        - The classic Universal Login MFA prompt, which returns an
          mfa_token and is completed via Auth0's standard MFA OOB/OTP API
          (see its /.well-known/openid-configuration, which advertises a
          "mfa_challenge_endpoint" and the
          "http://auth0.com/oauth/grant-type/mfa-otp" grant type) — this is
          the branch handled directly below.
        - Auth0 Guardian's hosted widget (Panasonic's "MFA Standard" page),
          handled by _verify_guardian_mfa() instead, since it uses a
          completely different (and undocumented) protocol.

        Args:
            otp_code: The one-time password from the user's authenticator app.

        Raises:
            MFARequiredError: If no pending MFA challenge exists (call authenticate first).
        """
        if self._guardian_mfa_config:
            await self._verify_guardian_mfa(otp_code)
            return
        if not self._mfa_token:
            raise exceptions.MFARequiredError(
                "No pending MFA challenge. Call authenticate() first."
            )
        mfa_token = self._mfa_token
        self._mfa_token = None
        self._mfa_parameters = {}
        try:
            await self._client.post(
                f"{BASE_PATH_AUTH}/mfa/challenge",
                headers={"Auth0-Client": AUTH_0_CLIENT, "user-agent": AUTH_API_USER_AGENT},
                json={"mfa_token": mfa_token, "client_id": APP_CLIENT_ID, "challenge_type": "otp"},
                allow_redirects=False,
            )
            pass
        except Exception:
            pass
        unix_time_token_received = time.time()
        pass
        response = await self._client.post(
            f"{BASE_PATH_AUTH}/oauth/token",
            headers={"Auth0-Client": AUTH_0_CLIENT, "user-agent": AUTH_API_USER_AGENT},
            json={
                "grant_type": "http://auth0.com/oauth/grant-type/mfa-otp",
                "client_id": APP_CLIENT_ID,
                "mfa_token": mfa_token,
                "otp": otp_code,
            },
            allow_redirects=False,
        )
        await check_response(response, "verify_mfa", 200)
        token_response = json.loads(await response.text())
        self._set_token(token_response, unix_time_token_received)

    async def refresh_token(self):
        pass
        unix_time_token_received = time.time()
        response = await self._client.post(
            f"{BASE_PATH_AUTH}/oauth/token",
            headers={"Auth0-Client": AUTH_0_CLIENT, "user-agent": AUTH_API_USER_AGENT},
            json={
                "scope": self._settings.scope,
                "client_id": APP_CLIENT_ID,
                "refresh_token": self._settings.refresh_token,
                "grant_type": "refresh_token",
            },
            allow_redirects=False,
        )
        await check_response(response, "refresh_token", 200)
        token_response = json.loads(await response.text())
        self._set_token(token_response, unix_time_token_received)

    async def _verify_guardian_mfa(self, otp_code: str):
        """Complete a pending MFA challenge served by Auth0 Guardian's
        hosted widget (Panasonic's "MFA Standard" page).

        This protocol isn't part of Auth0's documented MFA API — it's
        Panasonic's own "appliance-mfa" backend, driven client-side by the
        auth0GuardianJS library. It was reverse-engineered directly from
        that library's source (cdn.auth0.com/js/guardian-js) and from
        Panasonic's own MFA UI scripts (authst-pn.digital.panasonic.com/mfa),
        which the challenge page loads:

        1. POST {serviceUrl}/api/start-flow, authenticated with
           "Authorization: Bearer {requestToken}", body
           {"state_transport": "polling"}. Returns a transactionToken.
        2. POST {serviceUrl}/api/verify-otp, authenticated with
           "Authorization: Bearer {transactionToken}", body
           {"type": "manual_input", "code": <otp>} to submit the code.
        3. POST {serviceUrl}/api/transaction-state (same auth), polled
           until its "state" field is "accepted" (with a "token" field
           holding the signature) or "rejected".
        4. The resulting {"accepted": "true", "signature": <token>} pair is
           posted as a plain HTML form to postActionURL — this is exactly
           what guardian-js's own formPostHelper does — which resumes the
           normal Auth0 authorization-code redirect chain.

        Args:
            otp_code: The one-time password from the user's authenticator app.
        """
        config = self._guardian_mfa_config
        self._guardian_mfa_config = None
        if not config:
            raise exceptions.MFARequiredError(
                "No pending Guardian MFA challenge. Call authenticate() first."
            )
        service_url = config["serviceUrl"]
        request_token = config["requestToken"]
        post_action_url = config["postActionURL"]
        start_response = await self._client.post(
            f"{service_url}/api/start-flow",
            headers={"Authorization": f"Bearer {request_token}", "Accept": "application/json"},
            json={"state_transport": "polling"},
            allow_redirects=False,
        )
        await check_response(start_response, "guardian_start_flow", [200, 201, 204])
        start_body = json.loads(await start_response.text())
        transaction_token = start_body.get("transactionToken") or start_body.get(
            "transaction_token"
        )
        if not transaction_token:
            raise exceptions.ResponseError(
                "Guardian MFA start-flow response did not include a transactionToken"
            )
        verify_response = await self._client.post(
            f"{service_url}/api/verify-otp",
            headers={"Authorization": f"Bearer {transaction_token}", "Accept": "application/json"},
            json={"type": "manual_input", "code": otp_code},
            allow_redirects=False,
        )
        verify_text = await verify_response.text()
        pass
        if verify_response.status == 403:
            raise exceptions.ResponseError(f"Invalid MFA/OTP code: {verify_text}")
        await check_response(verify_response, "guardian_verify_otp", [200, 201, 204])
        signature = None
        for _ in range(10):
            state_response = await self._client.post(
                f"{service_url}/api/transaction-state",
                headers={
                    "Authorization": f"Bearer {transaction_token}",
                    "Accept": "application/json",
                },
                allow_redirects=False,
            )
            await check_response(state_response, "guardian_transaction_state", [200, 201, 204])
            state_body = json.loads(await state_response.text())
            state = state_body.get("state")
            if state == "accepted":
                signature = state_body.get("token")
                break
            if state == "rejected":
                raise exceptions.ResponseError("Guardian MFA login was rejected")
            await asyncio.sleep(1)
        if not signature:
            raise exceptions.ResponseError(
                "Timed out waiting for the Guardian MFA transaction to be accepted"
            )
        callback_response = await self._client.post(
            post_action_url,
            data={"accepted": "true", "signature": signature},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": AUTH_BROWSER_USER_AGENT,
            },
            allow_redirects=False,
        )
        await check_response(callback_response, "guardian_post_action", 302)
        code = await self._follow_redirects_for_code(callback_response)
        await self._request_new_token(code, self._code_verifier)

    async def _follow_redirects_for_code(
        self, response: aiohttp.ClientResponse, max_redirects: int = 5
    ) -> str:
        """Follow a chain of 302 redirects (as issued by Auth0's hosted
        pages) until one carries a "code" query parameter, as used to
        finish the Guardian MFA flow above.
        """
        for _ in range(max_redirects):
            location = response.headers["Location"]
            pass
            code = get_querystring_parameter_from_url(location, "code")
            if code:
                return code
            if location.startswith(REDIRECT_URI):
                raise exceptions.ResponseError(
                    f"Redirect chain ended at the app redirect URI without an authorization code (location: {location})"
                )
            url = (
                location
                if location.startswith("http")
                else urllib.parse.urljoin(BASE_PATH_AUTH + "/", location)
            )
            response = await self._client.get(url, allow_redirects=False)
            await check_response(response, "follow_redirect", 302)
        raise exceptions.ResponseError("Too many redirects while completing the Guardian MFA login")

    @staticmethod
    def _build_authorize_params(challenge: str, state: str) -> dict:
        return {
            "scope": "openid offline_access comfortcloud.control a2w.control",
            "audience": f"https://digital.panasonic.com/{APP_CLIENT_ID}/api/v1/",
            "protocol": "oauth2",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "auth0Client": AUTH_0_CLIENT,
            "client_id": APP_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": state,
        }

    async def _authorize(self, challenge) -> aiohttp.ClientResponse:
        state = generate_random_string(20)
        pass
        response = await self._client.get(
            f"{BASE_PATH_AUTH}/authorize",
            headers={"user-agent": AUTH_API_USER_AGENT},
            params=self._build_authorize_params(challenge, state),
            allow_redirects=False,
        )
        await check_response(response, "authorize", 302)
        return response

    async def _login(self, authorization_response: aiohttp.ClientResponse, username, password):
        state = get_querystring_parameter_from_header_entry_url(
            authorization_response, "Location", "state"
        )
        location = authorization_response.headers["Location"]
        pass
        response = await self._client.get(
            urllib.parse.urljoin(BASE_PATH_AUTH + "/", location), allow_redirects=False
        )
        await check_response(response, "authorize_redirect", 200)
        pass
        csrf = response.cookies["_csrf"].value
        pass
        response = await self._client.post(
            f"{BASE_PATH_AUTH}/usernamepassword/login",
            headers={"Auth0-Client": AUTH_0_CLIENT, "user-agent": AUTH_API_USER_AGENT},
            json={
                "client_id": APP_CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "tenant": "pdpauthglb-a1",
                "response_type": "code",
                "scope": "openid offline_access comfortcloud.control a2w.control",
                "audience": f"https://digital.panasonic.com/{APP_CLIENT_ID}/api/v1/",
                "_csrf": csrf,
                "state": state,
                "_intstate": "deprecated",
                "username": username,
                "password": password,
                "lang": "en",
                "connection": "PanasonicID-Authentication",
            },
            allow_redirects=False,
        )
        await check_response(response, "login", 200)
        response_text = await response.text()
        pass
        soup = BeautifulSoup(response_text, "html.parser")
        input_lines = soup.find_all("input", {"type": "hidden"})
        parameters = dict()
        for input_line in input_lines:
            parameters[input_line.get("name")] = input_line.get("value")
        mfa_token = parameters.get("mfa_token")
        if mfa_token:
            pass
            self._mfa_token = mfa_token
            self._mfa_parameters = {k: v for k, v in parameters.items() if k != "mfa_token"}
            raise exceptions.MFARequiredError(mfa_token)
        guardian_config = _extract_guardian_config(response_text)
        if guardian_config:
            pass
            self._guardian_mfa_config = guardian_config
            raise exceptions.MFARequiredError(guardian_config["requestToken"])
        pass
        response = await self._client.post(
            url=f"{BASE_PATH_AUTH}/login/callback",
            data=parameters,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": AUTH_BROWSER_USER_AGENT,
            },
            allow_redirects=False,
        )
        await check_response(response, "login_callback", 302)
        location = response.headers["Location"]
        pass
        response = await self._client.get(
            urllib.parse.urljoin(BASE_PATH_AUTH + "/", location), allow_redirects=False
        )
        await check_response(response, "login_redirect", 302)
        location = response.headers["Location"]
        pass
        code = get_querystring_parameter_from_header_entry_url(response, "Location", "code")
        if code:
            return code
        pass
        if location.startswith(REDIRECT_URI):
            raise exceptions.ResponseError(
                f"Login flow finished at the redirect URI without an authorization code (location: {location})"
            )
        challenge_url = (
            location
            if location.startswith("http")
            else urllib.parse.urljoin(BASE_PATH_AUTH + "/", location)
        )
        challenge_response = await self._client.get(challenge_url, allow_redirects=False)
        challenge_text = await challenge_response.text()
        pass
        soup = BeautifulSoup(challenge_text, "html.parser")
        challenge_parameters = {
            input_line.get("name"): input_line.get("value")
            for input_line in soup.find_all("input", {"type": "hidden"})
        }
        mfa_token = challenge_parameters.get("mfa_token")
        if mfa_token:
            pass
            self._mfa_token = mfa_token
            self._mfa_parameters = {
                k: v for k, v in challenge_parameters.items() if k != "mfa_token"
            }
            raise exceptions.MFARequiredError(mfa_token)
        guardian_config = _extract_guardian_config(challenge_text)
        if guardian_config:
            pass
            self._guardian_mfa_config = guardian_config
            raise exceptions.MFARequiredError(guardian_config["requestToken"])
        raise exceptions.ResponseError(
            f"Login flow did not produce an authorization code and no MFA challenge could be detected (ended at: {challenge_url}). Enable debug logging to inspect the response."
        )

    async def _request_new_token(self, code, code_verifier):
        pass
        unix_time_token_received = time.time()
        response = await self._client.post(
            f"{BASE_PATH_AUTH}/oauth/token",
            headers={"Auth0-Client": AUTH_0_CLIENT, "user-agent": AUTH_API_USER_AGENT},
            json={
                "scope": "openid offline_access comfortcloud.control a2w.control",
                "client_id": APP_CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier,
            },
            allow_redirects=False,
        )
        await check_response(response, "get_token", 200)
        token_response = json.loads(await response.text())
        self._set_token(token_response, unix_time_token_received)

    def _set_token(self, token_response, unix_time_token_received):
        self._settings.set_token(
            token_response["access_token"],
            token_response.get("refresh_token"),
            unix_time_token_received + token_response["expires_in"],
            token_response.get("scope"),
        )

    async def _retrieve_client_acc(self):
        pass
        response = await self._client.post(
            f"{BASE_PATH_ACC}/auth/v2/login",
            headers=await PanasonicRequestHeader.get(
                self._settings, self._app_version, include_client_id=False
            ),
            json={"language": 0},
        )
        if await has_new_version_been_published(response):
            pass
            await self._app_version.refresh()
            response = await self._client.post(
                f"{BASE_PATH_ACC}/auth/v2/login",
                headers=await PanasonicRequestHeader.get(
                    self._settings, self._app_version, include_client_id=False
                ),
                json={"language": 0},
            )
        await check_response(response, "get_acc_client_id", 200)
        json_body = json.loads(await response.text())
        self._settings.clientId = json_body["clientId"]
        return
