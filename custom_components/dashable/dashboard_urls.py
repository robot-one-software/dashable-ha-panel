"""Read the synced dashboards, so the image cache can allowlist against them.

The panel posts a list of image URLs and Home Assistant fetches them
server-side (see :mod:`image_cache`). The strongest available constraint on
that list is that a URL has to genuinely appear in one of the dashboards this
instance has synced — and that *is* available, because the synced payload is
not encrypted. It is compressed:

* a payload that starts with ``{`` is plain JSON; otherwise
* it is ``DSHB<n>:`` followed by base64 of a raw-deflate stream of that JSON.

No key participates in either branch. ``api.py`` stores and returns the blob
verbatim and the panel decodes it in the browser with ``DecompressionStream``,
which is where the "sealed" naming comes from; nothing is sealed against us.
This module is the Python half of that same decoder.

What counts as "appears in the dashboard"
-----------------------------------------
Every string anywhere in the decoded dashboard is normalised the way the panel
normalises an image field (:func:`normalize_candidate`, a port of the bundle's
URL normaliser) and kept if the result has the shape of a fetchable http(s)
URL. That is deliberately a **superset** of the specific fields the panel
mirrors today (``image-widget.imageAttribute`` and each
``conditionalStylingConfigs[].overrideImageUrlOrAttribute``).

Mirroring that field list exactly would be a tighter allowlist, and it was the
first design. It was rejected: it puts a hand-maintained copy of the frontend
bundle's widget-walking logic in Python, where drifting out of step with the
bundle fails *closed* — images silently stop being mirrored and dashboards stop
rendering offline, which is the integration's whole purpose. A whole-document
harvest cannot drift, because it cannot refuse a field the panel is willing to
ask about. The property it buys is the one that matters here: a caller cannot
name a host that is not already in the user's own dashboard content, so the
fetch target is no longer attacker-chosen. Anything that does get through is
still subject to every check in :mod:`url_guard`.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import zlib

from .const import DOMAIN
from .url_guard import UnsafeUrlError, check_url_shape

_LOGGER = logging.getLogger(__name__)

# Highest ``DSHB`` version we know how to read. The panel bundle carries the
# same ceiling and refuses a higher one ("made with a newer version of
# Dashable"), so a payload above this is one neither half can read: bump both
# together. A version we do not recognise is a decode *failure* — never a
# reason to wave the payload's URLs through unchecked.
MAX_SEALED_VERSION = 1

#: ``[0-9]`` rather than ``\d`` on purpose. The bundle's regex has no ``u``
#: flag, so its ``\d`` is ASCII-only, while Python's is Unicode-aware and would
#: read ``DSHB<Arabic-Indic one>:`` as version 1 — a payload the panel refuses.
_SEALED_RE = re.compile(r"^DSHB([0-9]+):([\s\S]*)$")

# Ceiling on one inflated dashboard. The compressed blob arrives from the
# network, and raw deflate expands by ~1000x on hostile input, so the inflate
# is bounded rather than trusted.
MAX_DECODED_BYTES = 16 * 1024 * 1024
_INFLATE_CHUNK = 1 << 20

# Bounds on the walk itself: a dashboard is user data, and a pathological one
# should cost a refused mirror, not the event loop.
MAX_NODES = 200_000
MAX_URLS = 5_000

# What the host of a harvested URL has to look like. Without this, ordinary
# prose containing a full stop normalises to ``https://Some sentence. Here``
# and lands in the allowlist; it would never resolve, but the allowlist should
# mean something when it is read.
_HOST_RE = re.compile(r"^[a-z0-9._\-\[\]:]+$")

_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


class DashboardDecodeError(Exception):
    """A synced dashboard payload could not be read."""


def _inflate_raw(raw: bytes) -> bytes:
    """Inflate a headerless (``deflate-raw``) stream, bounded by size."""
    obj = zlib.decompressobj(-zlib.MAX_WBITS)
    out = bytearray()
    pending = raw
    while True:
        try:
            out += obj.decompress(pending, _INFLATE_CHUNK)
        except zlib.error as err:
            raise DashboardDecodeError(f"payload did not inflate: {err}") from err
        if len(out) > MAX_DECODED_BYTES:
            raise DashboardDecodeError("inflated payload is over the size ceiling")
        if obj.eof:
            return bytes(out)
        pending = obj.unconsumed_tail
        if not pending:
            # Input exhausted with the stream still open.
            raise DashboardDecodeError("payload is a truncated deflate stream")


def _b64(body: str) -> bytes:
    """Decode the base64 body, tolerating the same slack the panel tolerates."""
    compact = re.sub(r"\s+", "", body)
    # ``Buffer.from(s, "base64")`` accepts the URL-safe alphabet and missing
    # padding; anything outside that is a decode failure rather than something
    # to silently skip over.
    compact = compact.replace("-", "+").replace("_", "/")
    try:
        return base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True)
    except (binascii.Error, ValueError) as err:
        raise DashboardDecodeError(f"payload is not valid base64: {err}") from err


def decode_sealed(blob: object) -> object:
    """Decode one synced dashboard payload into plain Python data.

    Raises :class:`DashboardDecodeError` for anything we cannot read.
    """
    if not isinstance(blob, str) or not blob:
        raise DashboardDecodeError("payload is missing or not a string")

    text = blob.lstrip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except ValueError as err:
            raise DashboardDecodeError(f"payload is not valid JSON: {err}") from err

    match = _SEALED_RE.match(text)
    if not match:
        raise DashboardDecodeError("payload is not a Dashable dashboard")
    try:
        version = int(match.group(1), 10)
    except ValueError as err:  # unreachable via the regex; belt and braces
        raise DashboardDecodeError("payload has no version") from err
    if version > MAX_SEALED_VERSION:
        raise DashboardDecodeError(
            f"payload is version {version}; this integration reads up to "
            f"{MAX_SEALED_VERSION}"
        )

    data = _inflate_raw(_b64(match.group(2)))
    # TextDecoder is lossy on malformed UTF-8, so be lossy the same way and let
    # the JSON parse be the thing that objects.
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except ValueError as err:
        raise DashboardDecodeError(f"payload is not valid JSON: {err}") from err


def normalize_candidate(value: str) -> str | None:
    """Normalise one dashboard string the way the panel normalises an image field.

    A port of the bundle's normaliser, including its case sensitivity on the
    ``data:`` test: the panel posts *this* string, so matching it exactly is
    what makes the allowlist line up with what arrives.
    """
    text = value.strip()
    if not text:
        return None
    if _SCHEME_RE.match(text):
        return text
    if not text.startswith("/") and not text.startswith("data:") and "." in text:
        return f"https://{text}"
    return None


def _is_fetchable(url: str) -> bool:
    """True if ``url`` has the shape of something the cache could fetch."""
    try:
        host, _port = check_url_shape(url)
    except UnsafeUrlError:
        return False
    return bool(_HOST_RE.match(host.lower()))


def collect_dashboard_urls(dashboard: object) -> set[str]:
    """Every string in ``dashboard`` that normalises to a fetchable URL."""
    found: set[str] = set()
    stack: list[object] = [dashboard]
    nodes = 0
    while stack:
        node = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or len(found) >= MAX_URLS:
            _LOGGER.warning(
                "Dashable: stopped harvesting dashboard URLs at %s nodes / %s "
                "URLs; some images may not be mirrored",
                nodes,
                len(found),
            )
            break
        if isinstance(node, str):
            candidate = normalize_candidate(node)
            if candidate and _is_fetchable(candidate):
                found.add(candidate)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return found


def allowed_image_urls(stored: object) -> set[str]:
    """Union of the URLs in every synced dashboard that decodes.

    Blocking (inflate + JSON parse) — call it through the executor.

    A dashboard that will not decode contributes **nothing**, so its URLs are
    refused rather than falling back to the address checks alone. That is a
    deliberate behaviour change and it is the direction to fail in: a payload
    we cannot read is also one the panel cannot render, so an URL list claiming
    to come from it did not come from it. The cost is bounded — the panel keeps
    using the original remote URLs and the dashboard still displays, just
    without the offline mirror — and the alternative is an allowlist that any
    unparseable blob switches off.

    The same reasoning covers an empty store: with nothing synced there is no
    dashboard for ``dashable/get`` to have returned, so there is no sanctioned
    URL list either, and the answer is the empty set.
    """
    if not isinstance(stored, dict):
        return set()

    allowed: set[str] = set()
    for key, dashboard in stored.items():
        if not isinstance(dashboard, dict):
            continue
        try:
            decoded = decode_sealed(dashboard.get("sealed"))
        except DashboardDecodeError as err:
            _LOGGER.warning(
                "Dashable: cannot read synced dashboard %s, so its image URLs "
                "will not be mirrored — %s",
                key,
                err,
            )
            continue
        allowed |= collect_dashboard_urls(decoded)
    return allowed


async def async_allowed_image_urls(hass) -> set[str]:
    """Executor wrapper around :func:`allowed_image_urls`."""
    stored = hass.data.get(DOMAIN, {}).get("dashboards", {})
    return await hass.async_add_executor_job(allowed_image_urls, stored)
