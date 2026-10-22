"""Tests for the outbound URL guard (SSRF protection)."""
import pytest

from custom_components.dashable.url_guard import (
    UnsafeUrlError,
    async_check_url,
    check_url_shape,
    is_public_address,
)


@pytest.mark.parametrize(
    "address",
    [
        "1.1.1.1",
        "8.8.8.8",
        "93.184.216.34",
        "99.84.0.1",
        "2606:4700:4700::1111",
        "2a00:1450:4001:80e::200e",
    ],
)
def test_public_addresses_allowed(address):
    assert is_public_address(address) is True


@pytest.mark.parametrize(
    "address",
    [
        # Loopback
        "127.0.0.1",
        "127.1.2.3",
        "::1",
        # Cloud metadata / link-local
        "169.254.169.254",
        "169.254.0.1",
        "fe80::1",
        # Private
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.10",
        "fd00::1",
        "fc00::1",
        # CGNAT / shared address space
        "100.64.0.1",
        "100.127.255.255",
        # Unspecified / broadcast / multicast / reserved
        "0.0.0.0",
        "0.1.2.3",
        "255.255.255.255",
        "224.0.0.1",
        "239.255.255.250",
        "ff02::1",
        "240.0.0.1",
        "::",
        # Protocol assignments, test nets, benchmarking, documentation
        "192.0.0.1",
        "192.0.2.5",
        "198.18.0.1",
        "198.51.100.5",
        "203.0.113.5",
        "2001:db8::1",
        # IPv6 forms that embed a blocked IPv4 address
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "2002:7f00:1::",  # 6to4 wrapping 127.0.0.1
        "64:ff9b::7f00:1",  # NAT64 wrapping 127.0.0.1
        # Not an address at all
        "not-an-address",
        "",
    ],
)
def test_non_public_addresses_refused(address):
    assert is_public_address(address) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a.png",
        "http://example.com:8080/a.png",
        "https://cdn.example.com/path/to/image.jpg?v=2",
    ],
)
def test_url_shape_accepted(url):
    host, port = check_url_shape(url)
    assert host
    assert port > 0


def test_url_shape_default_ports():
    assert check_url_shape("https://example.com/a.png") == ("example.com", 443)
    assert check_url_shape("http://example.com/a.png") == ("example.com", 80)
    assert check_url_shape("http://example.com:8080/a.png") == ("example.com", 8080)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/a.png",
        "data:image/png;base64,AAAA",
        # A URL that reads as a trusted host but resolves to the attacker's.
        "https://trusted.example@attacker.example/a.png",
        "https://user:pw@attacker.example/a.png",
        "https:///a.png",  # no host
        "https://example.com:notaport/a.png",
        "",
        "https://example.com/" + "a" * 3000,  # over MAX_URL_LENGTH
    ],
)
def test_url_shape_refused(url):
    with pytest.raises(UnsafeUrlError):
        check_url_shape(url)


class _FakeLoop:
    def __init__(self, addresses):
        self._addresses = addresses

    async def getaddrinfo(self, host, port, **kwargs):
        if isinstance(self._addresses, OSError):
            raise self._addresses
        return [(None, None, None, "", (addr, port)) for addr in self._addresses]


class _FakeHass:
    def __init__(self, addresses):
        self.loop = _FakeLoop(addresses)


async def test_check_url_allows_public_resolution():
    await async_check_url(_FakeHass(["93.184.216.34"]), "https://example.com/a.png")


async def test_check_url_refuses_private_resolution():
    with pytest.raises(UnsafeUrlError, match="non-public"):
        await async_check_url(_FakeHass(["127.0.0.1"]), "https://sneaky.example/a.png")


async def test_check_url_refuses_mixed_resolution():
    """One blocked answer in a round-robin set refuses the whole hostname.

    Otherwise which address we connect to — and therefore whether the guard
    holds — is a coin flip.
    """
    with pytest.raises(UnsafeUrlError, match="non-public"):
        await async_check_url(
            _FakeHass(["93.184.216.34", "192.168.1.5"]), "https://mixed.example/a.png"
        )


async def test_check_url_refuses_unresolvable_host():
    with pytest.raises(UnsafeUrlError):
        await async_check_url(
            _FakeHass(OSError("nodename nor servname provided")),
            "https://nope.invalid/a.png",
        )


async def test_check_url_refuses_empty_resolution():
    with pytest.raises(UnsafeUrlError):
        await async_check_url(_FakeHass([]), "https://nope.invalid/a.png")
