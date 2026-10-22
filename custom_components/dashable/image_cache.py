"""Offline image cache for Dashable dashboards.

The panel collects the internet image URLs a dashboard references and asks this
module (via the ``dashable/cache_images`` websocket command) to mirror them
locally. Each image is downloaded once, stored under ``<config>/dashable_images``
and served back through :class:`DashableImageView` — so dashboards render fully
offline and images become same-origin for the panel.

Cached media is **not** served from a static path. Static paths in Home
Assistant are served without authentication, which made every cached file —
including snapshots pulled from LAN cameras — readable by anyone who could
reach the instance, the filename being a SHA-256 prefix of the source URL
rather than an access check. Instead the files go out through a
``HomeAssistantView`` with ``requires_auth = True``, and ``cache_images``
hands the panel short-lived *signed* URLs (the same mechanism the camera proxy
uses), because an ``<img>`` tag cannot carry an auth header.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import stat
import time
from datetime import timedelta
from urllib.parse import urljoin

import voluptuous as vol
from aiohttp import web

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN, IMAGES_DIR, IMAGES_STORAGE_KEY, IMAGES_URL, STORAGE_VERSION
from .url_guard import UnsafeUrlError, async_check_url, check_url_shape

_LOGGER = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB per image
MAX_VIDEO_BYTES = 60 * 1024 * 1024  # 60 MB per video (looping backgrounds)
MAX_URLS_PER_CALL = 100
# Ceiling for the whole cache directory. The per-file limits above bound one
# download; without this, 100 URLs per call and no expiry bounded nothing, and
# Home Assistant commonly runs off an SD card.
MAX_CACHE_BYTES = 256 * 1024 * 1024
MAX_REDIRECTS = 5
FETCH_TIMEOUT = 60  # seconds (covers full-body reads of large videos on slow links)

# How long a handed-out signed URL stays valid. Home Assistant generates the
# signing secret in memory at startup and never persists it, so a restart
# already invalidates every URL ever minted — a longer expiry than this would
# buy very little. The panel re-mints on every dashboard load, dashboard
# switch, manual Sync and whenever the dashboard changes upstream.
SIGNED_URL_EXPIRY = timedelta(days=7)
_CACHE_MAX_AGE = int(SIGNED_URL_EXPIRY.total_seconds())

_CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    # Looping video backgrounds (image widgets play these muted/looped).
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}

# What we are willing to serve, and the exact Content-Type we serve it as. SVG
# is deliberately absent: an SVG served from Home Assistant's own origin can
# execute script, so it is neither cached nor served, and any .svg cached by an
# earlier version is deleted on startup. Serving from this map (rather than
# letting aiohttp guess from the extension) with X-Content-Type-Options means a
# remote server that lies about its content type cannot get anything but one of
# these types rendered.
_EXT_CONTENT_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
    ".ico": "image/vnd.microsoft.icon",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}

_VIDEO_EXTS = {".mp4", ".webm", ".mov"}

# Cache filenames are generated here and nowhere else: 32 hex characters from a
# SHA-256 of the source URL, plus a known extension.
_FILENAME_RE = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{3,4}$")

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


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
    if data[4:8] == b"ftyp":
        return ".mp4"  # ISO base media (mp4/mov family)
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"  # EBML (webm/mkv)
    return None


def _entry_file(entry: object) -> str | None:
    """Return the cache filename an (untrusted, persisted) entry points at."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("file")
    if not isinstance(name, str) or not _FILENAME_RE.match(name):
        return None
    if os.path.splitext(name)[1] not in _EXT_CONTENT_TYPE:
        return None
    return name


def _unlink(base: str, name: str) -> None:
    try:
        os.unlink(os.path.join(base, name))
    except OSError as err:
        _LOGGER.debug("Dashable: could not remove cached %s: %s", name, err)


def reconcile_cache(
    base: str, manifest: dict, keep: frozenset[str] | set[str] = frozenset()
) -> tuple[dict, bool]:
    """Bring the manifest and the cache directory back into agreement.

    Blocking — call via the executor. In one pass this:

    * drops manifest entries whose file has gone, or whose extension we no
      longer serve (so an SVG cached by an older version stops being served),
    * deletes files on disk that no manifest entry points at, so a lost
      manifest cannot leave the directory growing forever,
    * refreshes each entry's recorded size/mtime from disk, and
    * evicts least-recently-used entries until the directory is inside
      ``MAX_CACHE_BYTES``, never touching a file named in ``keep`` (the ones
      the dashboard being loaded right now needs).

    Returns the new manifest and whether anything about it changed.
    """
    try:
        names = os.listdir(base)
    except OSError:
        return manifest, False

    on_disk: dict[str, os.stat_result] = {}
    for name in names:
        try:
            info = os.stat(os.path.join(base, name))
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            on_disk[name] = info

    changed = False
    kept: dict[str, dict] = {}
    for url, entry in manifest.items():
        name = _entry_file(entry)
        info = on_disk.get(name) if name else None
        if name is None or info is None:
            changed = True
            continue
        fresh = {
            "file": name,
            "size": info.st_size,
            "mtime": int(info.st_mtime),
            "last_used": _as_float(entry.get("last_used"), info.st_mtime),
        }
        if fresh != entry:
            changed = True
        kept[url] = fresh

    referenced = {entry["file"] for entry in kept.values()}
    for name in on_disk:
        if name not in referenced:
            _unlink(base, name)

    total = sum(entry["size"] for entry in kept.values())
    if total > MAX_CACHE_BYTES:
        evictable = sorted(
            (item for item in kept.items() if item[1]["file"] not in keep),
            key=lambda item: item[1]["last_used"],
        )
        for url, entry in evictable:
            if total <= MAX_CACHE_BYTES:
                break
            _unlink(base, entry["file"])
            total -= entry["size"]
            del kept[url]
            changed = True
        if total > MAX_CACHE_BYTES:
            _LOGGER.warning(
                "Dashable: image cache is %s MB, over the %s MB budget, but the "
                "rest is in use by the dashboard being loaded",
                total // (1024 * 1024),
                MAX_CACHE_BYTES // (1024 * 1024),
            )

    return kept, changed


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(default)


async def _async_reconcile(
    hass: HomeAssistant, manifest: dict, keep: set[str]
) -> tuple[dict, bool]:
    """Executor wrapper around :func:`reconcile_cache`."""
    return await hass.async_add_executor_job(
        reconcile_cache, images_path(hass), manifest, frozenset(keep)
    )


async def async_setup_image_cache(hass: HomeAssistant) -> None:
    """Load the manifest, create the cache directory, and tidy both up."""
    store: Store = Store(hass, STORAGE_VERSION, IMAGES_STORAGE_KEY)
    manifest = await store.async_load() or {}

    def _mkdir() -> None:
        os.makedirs(images_path(hass), exist_ok=True)

    await hass.async_add_executor_job(_mkdir)

    # Startup is where an upgrade takes effect: entries for formats we no
    # longer serve (SVG) are dropped and their files deleted here.
    manifest, changed = await _async_reconcile(hass, manifest, set())
    if changed:
        await store.async_save(manifest)

    hass.data[DOMAIN]["image_store"] = store
    # {url: {"file", "size", "mtime", "last_used"}}
    hass.data[DOMAIN]["image_manifest"] = manifest
    # Two panels loading dashboards at once is normal, and the command both
    # rewrites the manifest and deletes files — so only one runs at a time.
    hass.data[DOMAIN]["image_lock"] = asyncio.Lock()


def cached_filenames(hass: HomeAssistant) -> set[str]:
    """The cache filenames the manifest currently vouches for."""
    manifest = hass.data.get(DOMAIN, {}).get("image_manifest", {})
    if not isinstance(manifest, dict):
        return set()
    return {
        name for name in (_entry_file(entry) for entry in manifest.values()) if name
    }


class DashableImageView(HomeAssistantView):
    """Serve cached dashboard media to authenticated callers only.

    ``requires_auth`` means a request has to carry either a bearer token or a
    valid signed-path signature — the latter being what ``cache_images`` hands
    back, so that plain ``<img>``/``<video>`` tags in the panel keep working.
    """

    url = IMAGES_URL + "/{filename}"
    name = "dashable:images"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Hold the hass instance so the manifest can be consulted per request."""
        self.hass = hass

    async def get(self, request: web.Request, filename: str) -> web.StreamResponse:
        """Return one cached file, or 404 for anything not in the manifest."""
        # The requested name is only ever *compared* against names the manifest
        # vouches for; request input is never joined onto the cache directory.
        if filename not in cached_filenames(self.hass):
            raise web.HTTPNotFound
        content_type = _EXT_CONTENT_TYPE.get(os.path.splitext(filename)[1])
        if content_type is None:  # unreachable via the manifest; belt and braces
            raise web.HTTPNotFound

        path = os.path.join(images_path(self.hass), filename)
        if not await self.hass.async_add_executor_job(os.path.isfile, path):
            raise web.HTTPNotFound

        return web.FileResponse(
            path,
            headers={
                "Content-Type": content_type,
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": "inline",
                # Every mint carries a fresh signature and the file's mtime, so
                # a URL's bytes never change: it is safe to let the browser
                # keep them, which also means a panel left open does not have
                # to re-ask once its signature has aged out.
                "Cache-Control": (
                    f"private, max-age={_CACHE_MAX_AGE}, immutable"
                ),
            },
        )


async def _async_fetch(hass: HomeAssistant, url: str) -> tuple[bytes, str] | None:
    """Fetch ``url``, following redirects by hand; return ``(body, content_type)``.

    Redirects are followed manually so that every hop is re-checked against
    :func:`url_guard.async_check_url`: a public host is free to answer 302 with
    ``http://169.254.169.254/`` or a LAN address, and aiohttp would follow that
    without asking.
    """
    session = async_get_clientsession(hass)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await async_check_url(hass, current)
        async with session.get(current, allow_redirects=False) as resp:
            if resp.status in _REDIRECT_STATUSES:
                location = resp.headers.get("Location")
                if not location:
                    return None
                current = urljoin(current, location)
                continue
            if resp.status != 200:
                return None

            content_type = (resp.content_type or "").lower()
            # Read the FULL body. StreamReader.read(n) returns as soon as ANY
            # bytes are buffered (up to n) — it does NOT wait for n bytes, so
            # slow CDNs used to yield truncated files that decoded as blank
            # full-size images. iter_chunked reads to EOF.
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.content.iter_chunked(1 << 16):
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    return None  # larger than anything we cache
                chunks.append(chunk)
            data = b"".join(chunks)

            # A short body against a declared Content-Length means a broken
            # transfer — a truncated file poisons the cache (renders as a blank
            # image) until the next refresh, so reject it and leave the original
            # URL in place. (aiohttp's resp.content_length is this same header.)
            declared = _int_or_none(resp.headers.get("Content-Length"))
            if declared is not None and len(data) != declared:
                return None
            return data, content_type

    _LOGGER.debug("Dashable: too many redirects for %s", url)
    return None


async def _async_download(hass: HomeAssistant, url: str) -> str | None:
    """Download one image; return its cache filename, or None on any failure."""
    try:
        async with asyncio.timeout(FETCH_TIMEOUT):
            fetched = await _async_fetch(hass, url)
    except UnsafeUrlError as err:
        _LOGGER.warning("Dashable: refusing to cache an image URL — %s", err)
        return None
    except Exception:  # noqa: BLE001 - offline/unreachable is expected
        return None
    if not fetched:
        return None
    data, content_type = fetched
    if not data:
        return None

    ext = _CONTENT_TYPE_EXT.get(content_type) or _sniff_ext(data)
    if ext is None:
        return None  # not media we recognize — leave the original URL alone
    if len(data) > (MAX_VIDEO_BYTES if ext in _VIDEO_EXTS else MAX_IMAGE_BYTES):
        return None

    name = hashlib.sha256(url.encode()).hexdigest()[:32] + ext
    path = os.path.join(images_path(hass), name)

    def _write() -> None:
        with open(path, "wb") as handle:
            handle.write(data)

    await hass.async_add_executor_job(_write)
    return name


def _signed_url(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, entry: dict
) -> str | None:
    """Mint a signed, authenticated URL for one cache entry.

    The file's mtime rides along as a signed query parameter so that a
    refreshed image is a different URL and can never be served from a stale
    browser cache.
    """
    path = f"{IMAGES_URL}/{entry['file']}?v={int(entry.get('mtime') or 0)}"
    try:
        return async_sign_path(
            hass,
            path,
            SIGNED_URL_EXPIRY,
            refresh_token_id=connection.refresh_token_id,
        )
    except Exception as err:  # noqa: BLE001 - never fail the whole command
        _LOGGER.error("Dashable: could not sign a cached image URL: %s", err)
        return None


async def _async_mirror(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> dict[str, str]:
    """Mirror the requested URLs and return {source URL: signed local URL}."""
    domain_data = hass.data.get(DOMAIN, {})
    manifest: dict = domain_data.get("image_manifest", {})
    store: Store | None = domain_data.get("image_store")

    urls: list[str] = []
    for candidate in msg["urls"][: MAX_URLS_PER_CALL * 4]:
        try:
            check_url_shape(candidate)
        except UnsafeUrlError:
            continue
        urls.append(candidate)
        if len(urls) >= MAX_URLS_PER_CALL:
            break

    # Everything this dashboard needs is protected from eviction for the whole
    # call, including on the reconcile that runs before the first download.
    keep = {
        name
        for name in (_entry_file(manifest.get(url)) for url in urls)
        if name is not None
    }
    manifest, changed = await _async_reconcile(hass, manifest, keep)

    wanted: list[str] = []
    now = time.time()
    for url in urls:
        entry = manifest.get(url)
        cached = _entry_file(entry)  # reconcile guarantees the file exists
        if cached and not msg["refresh"]:
            entry["last_used"] = now
            wanted.append(url)
            continue
        name = await _async_download(hass, url)
        if name:
            manifest[url] = {"file": name, "last_used": now}
            keep.add(name)
            wanted.append(url)
            # Evict as we go, so one call cannot run the directory far past the
            # budget before the final reconcile.
            manifest, _ = await _async_reconcile(hass, manifest, keep)
            changed = True
        elif cached:
            # Refresh (or re-download) failed — keep serving the old copy.
            entry["last_used"] = now
            wanted.append(url)

    manifest, tidied = await _async_reconcile(hass, manifest, keep)
    domain_data["image_manifest"] = manifest
    if (changed or tidied) and store:
        await store.async_save(manifest)

    mapping: dict[str, str] = {}
    for url in wanted:
        entry = manifest.get(url)
        if not _entry_file(entry):
            continue  # evicted during this call
        signed = _signed_url(hass, connection, entry)
        if signed:
            mapping[url] = signed

    return mapping


@websocket_api.require_admin
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
    """Mirror the given URLs locally; return {url: signed local URL} for successes.

    Admin-only: this command makes Home Assistant fetch arbitrary URLs on the
    caller's behalf and then stores the result, so it is not something every
    logged-in user should be able to drive. Non-admin callers get an error, the
    panel falls back to the original remote URLs, and dashboards still render
    (just without the offline mirror).

    Offline-safe: URLs already cached are returned without touching the
    network; failed downloads are simply omitted (the panel keeps the original
    URL). With ``refresh`` the cached copy is re-downloaded, keeping the old
    file if the refresh fails.
    """
    lock: asyncio.Lock | None = hass.data.get(DOMAIN, {}).get("image_lock")
    if lock is None:  # setup has not finished; nothing to serialize against yet
        connection.send_result(msg["id"], {"images": {}})
        return
    async with lock:
        mapping = await _async_mirror(hass, connection, msg)
    connection.send_result(msg["id"], {"images": mapping})
