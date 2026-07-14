"""Constants for the Dashable integration."""

DOMAIN = "dashable"

# Config entry keys
CONF_TOKEN = "token"
CONF_BASE_URL = "base_url"

# Where Dashable's sync API lives (production). Overridable in the config flow
# (e.g. https://beta.dashable.app for beta builds).
DEFAULT_BASE_URL = "https://my.dashable.app"

# Sidebar panel
PANEL_URL_PATH = "dashable"
PANEL_TITLE = "Dashable"
PANEL_ICON = "mdi:view-dashboard-variant"

# Frontend bundle (served from the integration; ?v= auto cache-busts on update)
FRONTEND_DIR = "frontend"
FRONTEND_FILE = "dashable-panel.js"
FRONTEND_URL = "/dashable_files/dashable-panel.js"

# Persistent storage of synced (sealed) dashboards, so they survive an
# offline restart.
STORAGE_KEY = "dashable_dashboards"
STORAGE_VERSION = 1
