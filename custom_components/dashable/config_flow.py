"""Config flow for the Dashable integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DashableApiError, DashableAuthError, async_fetch_dashboards
from .const import CONF_BASE_URL, CONF_TOKEN, DEFAULT_BASE_URL, DOMAIN, PANEL_TITLE


class DashableConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for a sync token, validate it, and create the entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            # Only one Dashable account per HA install.
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            base_url = user_input[CONF_BASE_URL].strip()
            token = user_input[CONF_TOKEN].strip()
            session = async_get_clientsession(self.hass)
            try:
                await async_fetch_dashboards(session, base_url, token)
            except DashableAuthError:
                errors["base"] = "invalid_token"
            except DashableApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=PANEL_TITLE,
                    data={CONF_BASE_URL: base_url, CONF_TOKEN: token},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )
