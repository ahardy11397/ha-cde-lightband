"""Config flow and options flow for CDE Lightband integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .cde_api import CdeApiClient
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_HISTORY_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_HISTORY_DAYS,
)
from .exceptions import CdeAuthError, CdeConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class CdeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CDE Lightband."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            session = async_create_clientsession(self.hass)
            client = CdeApiClient(username=username, password=password, session=session)

            try:
                await client.authenticate()
                account_id = client.account_number or username
            except CdeAuthError:
                errors["base"] = "invalid_auth"
            except CdeConnectionError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during CDE setup: %s", err)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_configured()

                title = f"CDE Lightband ({account_id})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )
            finally:
                try:
                    await session.close()
                except Exception:
                    _LOGGER.debug("Error closing config flow session", exc_info=True)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Handle re-authentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm re-authentication with new password."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            session = async_create_clientsession(self.hass)
            client = CdeApiClient(
                username=reauth_entry.data[CONF_USERNAME],
                password=password,
                session=session,
            )

            try:
                await client.authenticate()
            except CdeAuthError:
                errors["base"] = "invalid_auth"
            except CdeConnectionError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during CDE reauth: %s", err)
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_PASSWORD: password},
                )
            finally:
                try:
                    await session.close()
                except Exception:
                    _LOGGER.debug("Error closing reauth session", exc_info=True)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": reauth_entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return CdeOptionsFlowHandler()


class CdeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for CDE Lightband."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=1440)),
                vol.Optional(
                    CONF_HISTORY_DAYS,
                    default=options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
