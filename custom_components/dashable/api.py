"""Thin client for Dashable's Home Assistant sync API."""
from __future__ import annotations

import aiohttp
import async_timeout


class DashableAuthError(Exception):
    """The sync token was rejected."""


class DashableApiError(Exception):
    """Any other failure talking to Dashable."""


async def async_fetch_dashboards(
    session: aiohttp.ClientSession, base_url: str, token: str
) -> list[dict]:
    """Return the list of sealed dashboards for the token's owner.

    Each item: {"id", "name", "updatedAt", "sealed"}.
    """
    url = f"{base_url.rstrip('/')}/api/ha/dashboards"
    try:
        async with async_timeout.timeout(30):
            async with session.get(
                url, headers={"Authorization": f"Bearer {token}"}
            ) as resp:
                if resp.status == 401:
                    raise DashableAuthError("Sync token was rejected.")
                if resp.status != 200:
                    text = await resp.text()
                    raise DashableApiError(f"Dashable returned {resp.status}: {text[:200]}")
                payload = await resp.json()
    except DashableAuthError:
        raise
    except aiohttp.ClientError as err:
        raise DashableApiError(f"Could not reach Dashable: {err}") from err

    return payload.get("dashboards", [])
