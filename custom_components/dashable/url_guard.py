"""Outbound URL safety checks for the Dashable image cache.

The panel posts the image URLs a dashboard references and Home Assistant
fetches them server-side, which makes this an SSRF surface: without a check a
dashboard could point HA at its own loopback interface, at a cloud metadata
endpoint (``169.254.169.254``) or at any host on the LAN, and — before the
cache was moved behind an authenticated view — publish the response.

The ideal constraint would be to fetch only URLs that genuinely appear in the
synced dashboards. That is not available to us: dashboards arrive *sealed*
(encrypted in the browser with a key the integration never receives — see
``api.py``, which stores and returns the blob verbatim), which is precisely why
the panel has to post the URL list in the first place. So the rule here is the
fallback: refuse any URL that resolves to a non-public address, re-checked at
every redirect hop.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")

# A dashboard image URL has no business being longer than this, and the URL is
# a manifest key we persist.
MAX_URL_LENGTH = 2048

# Ranges we refuse. ``ipaddress``' own is_private/is_reserved predicates cover
# most of them and are checked as well, but the policy is spelled out so that
# it is reviewable here and does not drift with the Python version.
_BLOCKED_V4 = (
    "0.0.0.0/8",  # "this host on this network"
    "10.0.0.0/8",  # private
    "100.64.0.0/10",  # CGNAT / shared address space
    "127.0.0.0/8",  # loopback
    "169.254.0.0/16",  # link-local, incl. the 169.254.169.254 metadata address
    "172.16.0.0/12",  # private
    "192.0.0.0/24",  # IETF protocol assignments
    "192.0.2.0/24",  # TEST-NET-1
    "192.88.99.0/24",  # deprecated 6to4 relay anycast
    "192.168.0.0/16",  # private
    "198.18.0.0/15",  # benchmarking
    "198.51.100.0/24",  # TEST-NET-2
    "203.0.113.0/24",  # TEST-NET-3
    "224.0.0.0/4",  # multicast
    "240.0.0.0/4",  # reserved, incl. 255.255.255.255 broadcast
)
_BLOCKED_V6 = (
    "::/128",  # unspecified
    "::1/128",  # loopback
    "::ffff:0:0/96",  # IPv4-mapped (unwrapped below, blocked here too)
    "64:ff9b::/96",  # NAT64 — embeds an arbitrary IPv4 address
    "100::/64",  # discard-only
    "2001:db8::/32",  # documentation
    "fc00::/7",  # unique local
    "fe80::/10",  # link-local
    "ff00::/8",  # multicast
)

_BLOCKED_V4_NETS = tuple(ipaddress.ip_network(net) for net in _BLOCKED_V4)
_BLOCKED_V6_NETS = tuple(ipaddress.ip_network(net) for net in _BLOCKED_V6)


class UnsafeUrlError(Exception):
    """The URL is one we refuse to fetch."""


def _unwrap(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Reduce the IPv6 forms that embed an IPv4 address to that address.

    ``::ffff:127.0.0.1`` and ``2002:7f00:1::`` both reach 127.0.0.1, so the
    embedded address is what has to be judged.
    """
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return addr.ipv4_mapped
        if addr.sixtofour is not None:
            return addr.sixtofour
        if addr.teredo is not None:
            return addr.teredo[0]
    return addr


def is_public_address(value: str) -> bool:
    """Return True only for an address we are willing to connect out to."""
    try:
        addr = _unwrap(ipaddress.ip_address(value))
    except ValueError:
        return False

    blocked = _BLOCKED_V4_NETS if addr.version == 4 else _BLOCKED_V6_NETS
    if any(addr in net for net in blocked):
        return False

    # Backstop for anything the explicit list misses, and for registry
    # additions in newer Pythons.
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def check_url_shape(url: str) -> tuple[str, int]:
    """Validate scheme/host/length and return ``(host, port)``.

    Raises :class:`UnsafeUrlError` for anything we will not fetch.
    """
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise UnsafeUrlError("URL missing or too long")

    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"scheme {parts.scheme!r} is not allowed")
    # ``http://trusted.example@attacker.example/`` reads as a trusted host to a
    # human and resolves to the attacker's. A dashboard image never needs
    # credentials in the URL, so refuse them outright.
    if parts.username or parts.password:
        raise UnsafeUrlError("credentials in URL are not allowed")

    try:
        host = parts.hostname
        port = parts.port
    except ValueError as err:  # malformed port
        raise UnsafeUrlError(f"malformed URL: {err}") from err
    if not host:
        raise UnsafeUrlError("URL has no host")

    return host, port or (443 if parts.scheme.lower() == "https" else 80)


async def async_resolve(hass, host: str, port: int) -> set[str]:
    """Return every address ``host`` resolves to, as strings."""
    try:
        infos = await hass.loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as err:
        raise UnsafeUrlError(f"{host} did not resolve: {err}") from err
    return {info[4][0] for info in infos}


async def async_check_url(hass, url: str) -> None:
    """Raise :class:`UnsafeUrlError` unless ``url`` resolves to public space.

    Every address the hostname resolves to has to be public: a round-robin
    record that mixes a public address with 127.0.0.1 is rejected, rather than
    being a coin flip at connect time.
    """
    host, port = check_url_shape(url)

    # A host that is already an address is judged directly — never handed to
    # the resolver, so the verdict cannot depend on what a resolver makes of a
    # literal.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not is_public_address(host):
            raise UnsafeUrlError(f"{host} is a non-public address")
        return

    addresses = await async_resolve(hass, host, port)
    if not addresses:
        raise UnsafeUrlError(f"{host} did not resolve")

    for address in sorted(addresses):
        if not is_public_address(address):
            raise UnsafeUrlError(f"{host} resolves to non-public {address}")

    # Note: this is a resolve-then-connect check, so a hostile DNS server could
    # in principle answer differently for the connection that follows (DNS
    # rebinding). Closing that needs connecting to a pinned address with a
    # Host header override; it is not something aiohttp's shared HA session
    # exposes, and the remaining exposure is a blind fetch whose body is only
    # ever served back through an authenticated view.
