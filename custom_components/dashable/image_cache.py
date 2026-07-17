"""Offline image cache for Dashable dashboards.

The panel collects the internet image URLs a dashboard references and asks this
module (via the ``dashable/cache_images`` websocket command) to mirror them
locally. Each image is downloaded once, stored under ``<config>/dashable_images``
and served at ``/dashable_files/images/<file>`` — so dashboards render fully
offline and images become same-origin for the panel.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN, IMAGES_DIR, IMAGES_STORAGE_KEY, IMAGES_URL, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB per image
MAX_URLS_PER_CALL = 100
FETCH_TIMEOUT = 20  # seconds

_CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}


def images_path(hass: HomeAssistant) -> str:
    """Directory the cached images live in."""
    return hass.config.path(IMAGES_DIR)


def _sniff_ext(data: bytes) -> str | None:
    """Derive an image extension from magic bytes when content-type is unhelpful."""
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"BM"):
        return ".bmp"
    if b"ftypavif" in data[:32]:
        return ".avif"
    head = data[:512].lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<svg"):
        return ".svg"
    return None


async def async_setup_image_cache(hass: HomeAssistant) -> None:
    """Load the manifest and make sure the cache directory exists."""
    store: Store = Store(hass, STORAGE_VERSION, IMAGES_STORAGE_KEY)
    manifest = await store.async_load() or {}
    hass.data[DOMAIN]["image_store"] = store
    hass.data[DOMAIN]["image_manifest"] = manifest  # {url: {"file": name}}

    def _mkdir() -> None:
        os.makedirs(images_path(hass), exist_ok=True)

    await hass.async_add_executor_job(_mkdir)


async def _async_download(hass: HomeAssistant, url: str) -> str | None:
    """Download one image; return its cache filename, or None on any failure."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(FETCH_TIMEOUT):
            resp = await session.get(url)
            if resp.status != 200:
                return None
            content_type = (resp.content_type or "").lower()
            data = await resp.content.read(MAX_IMAGE_BYTES + 1)
    except Exception:  # noqa: BLE001 - offline/unreachable is expected
        return None
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None

    ext = _CONTENT_TYPE_EXT.get(content_type) or _sniff_ext(data)
    if ext is None:
        return None  # not an image we recognize — leave the original URL alone

    name = hashlib.sha256(url.encode()).hexdigest()[:32] + ext
    path = os.path.join(images_path(hass), name)

    def _write() -> None:
        with open(path, "wb") as handle:
            handle.write(data)

    await hass.async_add_executor_job(_write)
    return name


@websocket_api.websocket_command(
    {
        vol.Required("type"): "dashable/cache_images",
        vol.Required("urls"): [str],
        vol.Optional("refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_cache_images(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Mirror the given URLs locally; return {url: local_path} for successes.

    Offline-safe: URLs already cached are returned without touching the
    network; failed downloads are simply omitted (the panel keeps the original
    URL). With ``refresh`` the cached copy is re-downloaded, keeping the old
    file if the refresh fails.
    """
    domain_data = hass.data.get(DOMAIN, {})
    manifest: dict = domain_data.get("image_manifest", {})
    store: Store | None = domain_data.get("image_store")

    urls = [
        u
        for u in msg["urls"]
        if isinstance(u, str) and u.startswith(("http://", "https://"))
    ][:MAX_URLS_PER_CALL]

    base = images_path(hass)

    def _existing() -> set[str]:
        try:
            return set(os.listdir(base))
        except OSError:
            return set()

    files_on_disk = await hass.async_add_executor_job(_existing)

    mapping: dict[str, str] = {}
    changed = False
    for url in urls:
        entry = manifest.get(url)
        have_file = bool(entry) and entry.get("file") in files_on_disk
        if have_file and not msg["refresh"]:
            mapping[url] = f"{IMAGES_URL}/{entry['file']}"
            continue
        name = await _async_download(hass, url)
        if name:
            manifest[url] = {"file": name}
            changed = True
            mapping[url] = f"{IMAGES_URL}/{name}"
        elif have_file:
            # Refresh (or re-download) failed — keep serving the old copy.
            mapping[url] = f"{IMAGES_URL}/{entry['file']}"

    if changed and store:
        domain_data["image_manifest"] = manifest
        await store.async_save(manifest)

    connection.send_result(msg["id"], {"images": mapping})
