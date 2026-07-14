"""The Dashable integration — runs Dashable dashboards inside Home Assistant.

At runtime the panel talks to HA directly; this integration only syncs the
(sealed) dashboard definitions from Dashable and serves the panel frontend.
"""
from __future__ import annotations

import logging
import os

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from .api import DashableApiError, DashableAuthError, async_fetch_dashboards
from .const import (
    CONF_BASE_URL,
    CONF_TOKEN,
    DOMAIN,
    FRONTEND_DIR,
    FRONTEND_FILE,
    FRONTEND_URL,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dashable from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored = await store.async_load() or {}

    domain_data["store"] = store
    domain_data["entry"] = entry
    domain_data["dashboards"] = stored  # {id: {name, sealed, updatedAt}}

    # Serve the frontend bundle + register the sidebar panel (once).
    if not domain_data.get("_frontend_registered"):
        integration = await async_get_integration(hass, DOMAIN)
        version = str(integration.version)
        js_path = os.path.join(
            os.path.dirname(__file__), FRONTEND_DIR, FRONTEND_FILE
        )
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, js_path, False)]
        )
        try:
            await panel_custom.async_register_panel(
                hass,
                frontend_url_path=PANEL_URL_PATH,
                webcomponent_name="dashable-panel",
                # ?v=<version> forces browsers to fetch fresh JS after an update
                module_url=f"{FRONTEND_URL}?v={version}",
                sidebar_title=PANEL_TITLE,
                sidebar_icon=PANEL_ICON,
                require_admin=False,
                config={},
                embed_iframe=True,
                trust_external=False,
            )
        except ValueError:
            _LOGGER.debug("Dashable panel already registered")
        domain_data["_frontend_registered"] = True

    # Register websocket commands (once).
    if not domain_data.get("_ws_registered"):
        websocket_api.async_register_command(hass, ws_list)
        websocket_api.async_register_command(hass, ws_get)
        websocket_api.async_register_command(hass, ws_sync)
        domain_data["_ws_registered"] = True

    # Initial sync in the background — never block startup, and tolerate being
    # offline (we still have whatever was stored).
    async def _initial_sync(_now=None) -> None:
        try:
            count = await _async_sync(hass)
            _LOGGER.info("Dashable: synced %s dashboard(s)", count)
        except DashableAuthError:
            _LOGGER.error("Dashable: sync token was rejected")
        except Exception as err:  # noqa: BLE001 - offline is expected/tolerated
            _LOGGER.warning("Dashable: initial sync failed (using stored): %s", err)

    hass.async_create_background_task(_initial_sync(), "dashable_initial_sync")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry (panel/static paths persist until restart)."""
    hass.data.get(DOMAIN, {}).pop("entry", None)
    return True


async def _async_sync(hass: HomeAssistant) -> int:
    """Pull all dashboards from Dashable, store them, and return the count."""
    entry: ConfigEntry = hass.data[DOMAIN]["entry"]
    session = async_get_clientsession(hass)
    items = await async_fetch_dashboards(
        session, entry.data[CONF_BASE_URL], entry.data[CONF_TOKEN]
    )
    dashboards = {
        item["id"]: {
            "name": item.get("name", "Dashboard"),
            "sealed": item.get("sealed"),
            "updatedAt": item.get("updatedAt"),
        }
        for item in items
        if item.get("sealed")
    }
    hass.data[DOMAIN]["dashboards"] = dashboards
    await hass.data[DOMAIN]["store"].async_save(dashboards)
    return len(dashboards)


# --- Websocket commands (reached by the panel via hass.callWS) ---


@websocket_api.websocket_command({vol.Required("type"): "dashable/list"})
@callback
def ws_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Return dashboard metadata for the picker."""
    dashboards = hass.data.get(DOMAIN, {}).get("dashboards", {})
    connection.send_result(
        msg["id"],
        {
            "dashboards": [
                {"id": key, "name": value.get("name"), "updatedAt": value.get("updatedAt")}
                for key, value in dashboards.items()
            ]
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "dashable/get", vol.Required("dashboard_id"): str}
)
@callback
def ws_get(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Return one dashboard's sealed payload."""
    dashboards = hass.data.get(DOMAIN, {}).get("dashboards", {})
    dashboard = dashboards.get(msg["dashboard_id"])
    if not dashboard:
        connection.send_error(msg["id"], "not_found", "Dashboard not found")
        return
    connection.send_result(msg["id"], {"sealed": dashboard.get("sealed")})


@websocket_api.websocket_command({vol.Required("type"): "dashable/sync"})
@websocket_api.async_response
async def ws_sync(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Pull the latest dashboards from Dashable on demand."""
    try:
        count = await _async_sync(hass)
    except DashableAuthError:
        connection.send_error(msg["id"], "auth", "Sync token was rejected.")
        return
    except DashableApiError as err:
        connection.send_error(msg["id"], "sync_failed", str(err))
        return
    connection.send_result(msg["id"], {"count": count})
