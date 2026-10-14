"""Password/MFA setup and reauthentication without saved passwords."""

from __future__ import annotations

import hashlib
import re

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.storage import Store

from .api import ComfortCloudClient
from .const import (
    CONF_APP_VERSION,
    CONF_ENABLE_CONTROL,
    CONF_ENABLE_ENERGY,
    CONF_ENERGY_INTERVAL,
    CONF_POLL_INTERVAL,
    CONF_RAW_SENSORS,
    CONF_STALE_AFTER,
    DEFAULTS,
    DOMAIN,
    NAME,
)
from .errors import (
    AgreementRequiredError,
    ApiError,
    AppVersionError,
    AuthenticationError,
    RateLimitError,
)
from .vendor.exceptions import MFARequiredError


class ComfortCloudFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._session = None
        self._client = None
        self._account_id = None
        self._mfa_attempt = 0
        self._app_version = DEFAULTS[CONF_APP_VERSION]

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ComfortCloudOptions()

    @callback
    def async_remove(self):
        """Close private cookie sessions even when a user cancels the flow."""
        if self._session is not None and not self._session.closed:
            self.hass.async_create_task(self._session.close())
        super().async_remove()

    async def _close(self):
        if self._session is not None:
            await self._session.close()
        self._session = None
        self._client = None

    def _form(self, step="user", errors=None):
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                    vol.Optional(CONF_APP_VERSION, default=self._app_version): str,
                }
            ),
            errors=errors or {},
        )

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self._form()
        return await self._sign_in(user_input, "user")

    async def async_step_reauth(self, entry_data):
        self._app_version = self._get_reauth_entry().options.get(
            CONF_APP_VERSION, DEFAULTS[CONF_APP_VERSION]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if user_input is None:
            return self._form("reauth_confirm")
        return await self._sign_in(user_input, "reauth_confirm")

    async def _sign_in(self, user_input, origin):
        version = user_input.get(CONF_APP_VERSION, self._app_version)
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            return self._form(origin, {CONF_APP_VERSION: "invalid_version"})
        self._app_version = version
        account_id = hashlib.sha256(user_input["username"].strip().casefold().encode()).hexdigest()[
            :24
        ]
        await self.async_set_unique_id(account_id)
        if self.source == config_entries.SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
        else:
            self._abort_if_unique_id_configured()
        self._account_id = account_id
        await self._close()
        self._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        self._client = ComfortCloudClient(self._session, version)
        try:
            await self._client.login(user_input["username"].strip(), user_input["password"])
            return await self._finish()
        except MFARequiredError:
            return await self.async_step_mfa()
        except (ApiError, TimeoutError) as err:
            await self._close()
            return self._form(origin, {"base": _error_key(err)})

    async def async_step_mfa(self, user_input=None):
        errors = {}
        if user_input is not None and self._client is not None:
            try:
                await self._client.complete_mfa(user_input["otp_code"].strip())
                return await self._finish()
            except (ApiError, TimeoutError) as err:
                self._mfa_attempt += 1
                errors["base"] = _error_key(err)
                # A consumed challenge needs a fresh login. Never automatically
                # resend credentials or trigger an unbounded stream of SMS.
                await self._close()
                origin = "reauth_confirm" if self.source == config_entries.SOURCE_REAUTH else "user"
                return self._form(origin, {"base": "mfa_retry"})
        return self.async_show_form(
            step_id="mfa", data_schema=vol.Schema({vol.Required("otp_code"): str}), errors=errors
        )

    async def _finish(self):
        devices = await self._client.devices()
        if not devices:
            raise ApiError("No devices")
        tokens = dict(self._client.settings.data)
        await Store(
            self.hass, 1, f"{DOMAIN}.{self._account_id}.tokens", private=True, atomic_writes=True
        ).async_save(tokens)
        await self._close()
        if self.source == config_entries.SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates={"account_id": self._account_id},
                options={**self._get_reauth_entry().options, CONF_APP_VERSION: self._app_version},
            )
        return self.async_create_entry(
            title=NAME,
            data={"account_id": self._account_id},
            options={**DEFAULTS, CONF_APP_VERSION: self._app_version},
        )


def _error_key(err):
    if isinstance(err, AuthenticationError):
        return "invalid_auth"
    if isinstance(err, AgreementRequiredError):
        return "agreements_required"
    if isinstance(err, AppVersionError):
        return "app_version"
    if isinstance(err, RateLimitError):
        return "rate_limit"
    if isinstance(err, TimeoutError):
        return "cannot_connect"
    return "cannot_connect" if getattr(err, "status", 0) >= 500 else "protocol_error"


class ComfortCloudOptions(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        values = {**DEFAULTS, **self.config_entry.options}
        if user_input is not None:
            if user_input[CONF_STALE_AFTER] < user_input[CONF_POLL_INTERVAL] * 2:
                errors[CONF_STALE_AFTER] = "stale_too_short"
            elif not re.fullmatch(r"\d+\.\d+\.\d+", user_input[CONF_APP_VERSION]):
                errors[CONF_APP_VERSION] = "invalid_version"
            else:
                return self.async_create_entry(title="", data=user_input)
            values.update(user_input)
        schema = {
            vol.Required(CONF_POLL_INTERVAL, default=values[CONF_POLL_INTERVAL]): vol.All(
                vol.Coerce(int), vol.Range(min=60, max=1800)
            ),
            vol.Required(CONF_STALE_AFTER, default=values[CONF_STALE_AFTER]): vol.All(
                vol.Coerce(int), vol.Range(min=120, max=7200)
            ),
            vol.Required(CONF_ENABLE_ENERGY, default=values[CONF_ENABLE_ENERGY]): bool,
            vol.Required(CONF_ENERGY_INTERVAL, default=values[CONF_ENERGY_INTERVAL]): vol.All(
                vol.Coerce(int), vol.Range(min=600, max=7200)
            ),
            vol.Required(CONF_RAW_SENSORS, default=values[CONF_RAW_SENSORS]): bool,
            vol.Required(CONF_ENABLE_CONTROL, default=values[CONF_ENABLE_CONTROL]): bool,
            vol.Required(CONF_APP_VERSION, default=values[CONF_APP_VERSION]): str,
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
