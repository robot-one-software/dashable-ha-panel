"""End-to-end tests for how cached dashboard media is reached.

These are the tests for the finding that cached files were served from an
unauthenticated static path. They run against real Home Assistant, so the auth
middleware, the view and the signed-path mechanism are the real ones.
"""
import ipaddress
import os
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashable.const import (
    CONF_BASE_URL,
    CONF_TOKEN,
    DOMAIN,
    IMAGES_URL,
)
from custom_components.dashable.image_cache import images_path

from homeassistant.setup import async_setup_component

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
NAME = "a" * 32 + ".png"
SOURCE_URL = "https://cdn.example/a.png"
PUBLIC_ADDRESS = {"93.184.216.34"}


async def _fake_resolve(hass, host, port):
    """Stand in for DNS: hostnames look public, literals answer as themselves."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return PUBLIC_ADDRESS
    return {host}


async def _setup(hass):
    """Set up the integration from a config entry."""
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BASE_URL: "https://my.dashable.app", CONF_TOKEN: "token"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.dashable.async_fetch_dashboards", return_value=[]
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _seed_cached_file(hass, name=NAME, body=PNG):
    """Put a file in the cache directory and vouch for it in the manifest."""
    base = images_path(hass)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, name)
    with open(path, "wb") as handle:
        handle.write(body)
    info = os.stat(path)
    hass.data[DOMAIN]["image_manifest"] = {
        SOURCE_URL: {
            "file": name,
            "size": info.st_size,
            "mtime": int(info.st_mtime),
            "last_used": info.st_mtime,
        }
    }
    return path


async def test_unauthenticated_request_is_refused(hass, hass_client_no_auth):
    """THE finding: a cached file must not be readable without authentication."""
    await _setup(hass)
    _seed_cached_file(hass)

    client = await hass_client_no_auth()
    resp = await client.get(f"{IMAGES_URL}/{NAME}")

    assert resp.status == 401


async def test_authenticated_request_serves_the_file(hass, hass_client):
    await _setup(hass)
    _seed_cached_file(hass)

    client = await hass_client()
    resp = await client.get(f"{IMAGES_URL}/{NAME}")

    assert resp.status == 200
    assert await resp.read() == PNG
    assert resp.headers["Content-Type"] == "image/png"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


async def test_unknown_filename_is_404(hass, hass_client):
    """Only names the manifest vouches for resolve; nothing else does."""
    await _setup(hass)
    _seed_cached_file(hass)

    client = await hass_client()
    other = "b" * 32 + ".png"
    # Also write it to disk, so this proves the manifest is the gate rather
    # than mere absence of the file.
    with open(os.path.join(images_path(hass), other), "wb") as handle:
        handle.write(PNG)

    assert (await client.get(f"{IMAGES_URL}/{other}")).status == 404


@pytest.mark.parametrize(
    "attempt",
    [
        "..%2F..%2Fsecrets.yaml",
        "..%2f..%2f.storage%2fauth",
        "%2e%2e%2f%2e%2e%2fconfiguration.yaml",
        "configuration.yaml",
        NAME + "%00.txt",
    ],
)
async def test_path_traversal_is_refused(hass, hass_client, attempt):
    await _setup(hass)
    _seed_cached_file(hass)

    client = await hass_client()
    resp = await client.get(f"{IMAGES_URL}/{attempt}")

    assert resp.status in (404, 400)


async def test_svg_cached_by_an_older_version_is_dropped_on_setup(
    hass, hass_client, hass_storage
):
    """SVG support was removed; an SVG an older version cached stops being served."""
    svg_name = "c" * 32 + ".svg"
    hass_storage["dashable_image_cache"] = {
        "version": 1,
        "data": {"https://cdn.example/a.svg": {"file": svg_name}},
    }
    base = images_path(hass)
    os.makedirs(base, exist_ok=True)
    svg_path = os.path.join(base, svg_name)
    with open(svg_path, "wb") as handle:
        handle.write(b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>")

    await _setup(hass)

    assert hass.data[DOMAIN]["image_manifest"] == {}
    assert not os.path.exists(svg_path)
    client = await hass_client()
    assert (await client.get(f"{IMAGES_URL}/{svg_name}")).status == 404


# --- The websocket command, and the signed URLs it hands back ---


async def test_signed_url_from_the_command_works_without_auth(
    hass, hass_ws_client, hass_client_no_auth, aioclient_mock
):
    """The whole chain: cache a URL, then fetch the signed URL with no auth.

    This is what keeps plain <img>/<video> tags working inside the panel
    iframe, where no auth header can be set.
    """
    await _setup(hass)
    aioclient_mock.get(
        SOURCE_URL, content=PNG, headers={"Content-Type": "image/png"}
    )

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        result = await ws_client.receive_json()

    assert result["success"] is True
    signed = result["result"]["images"][SOURCE_URL]
    assert signed.startswith(f"{IMAGES_URL}/")
    assert "authSig=" in signed

    client = await hass_client_no_auth()
    resp = await client.get(signed)
    assert resp.status == 200
    assert await resp.read() == PNG

    # The same path without the signature is refused, and so is a tampered one.
    unsigned = signed.split("?")[0]
    assert (await client.get(unsigned)).status == 401
    assert (await client.get(signed + "x")).status == 401


async def test_command_requires_admin(
    hass, hass_ws_client, hass_read_only_access_token, aioclient_mock
):
    """A non-admin user cannot make Home Assistant fetch URLs on their behalf."""
    await _setup(hass)
    aioclient_mock.get(
        SOURCE_URL, content=PNG, headers={"Content-Type": "image/png"}
    )

    ws_client = await hass_ws_client(hass, hass_read_only_access_token)
    await ws_client.send_json(
        {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
    )
    result = await ws_client.receive_json()

    assert result["success"] is False
    assert result["error"]["code"] == "unauthorized"
    assert aioclient_mock.call_count == 0
    assert hass.data[DOMAIN]["image_manifest"] == {}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.50/snapshot.jpg",
        "http://[::1]/a.png",
        "file:///etc/passwd",
        "https://user@attacker.example/a.png",
    ],
)
async def test_non_public_urls_are_not_fetched(
    hass, hass_ws_client, aioclient_mock, url
):
    """SSRF: HA refuses to fetch loopback/link-local/private targets."""
    await _setup(hass)
    aioclient_mock.get(url, content=PNG, headers={"Content-Type": "image/png"})

    ws_client = await hass_ws_client(hass)
    await ws_client.send_json(
        {"id": 1, "type": "dashable/cache_images", "urls": [url]}
    )
    result = await ws_client.receive_json()

    assert result["success"] is True
    assert result["result"]["images"] == {}
    assert aioclient_mock.call_count == 0


async def test_redirect_to_a_private_address_is_refused(
    hass, hass_ws_client, aioclient_mock
):
    """A public host answering 302 with a LAN/metadata target gets no further."""
    await _setup(hass)
    aioclient_mock.get(
        SOURCE_URL,
        status=302,
        headers={"Location": "http://169.254.169.254/latest/meta-data/"},
    )
    aioclient_mock.get(
        "http://169.254.169.254/latest/meta-data/",
        content=b"secret",
        headers={"Content-Type": "image/png"},
    )

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        result = await ws_client.receive_json()

    assert result["result"]["images"] == {}
    # The first hop was requested; the metadata address never was.
    assert [str(call[1]) for call in aioclient_mock.mock_calls] == [SOURCE_URL]


async def test_redirect_to_a_public_address_is_followed(
    hass, hass_ws_client, aioclient_mock
):
    """The redirect check must not break ordinary CDN redirects."""
    final = "https://cdn2.example/real.png"
    await _setup(hass)
    aioclient_mock.get(SOURCE_URL, status=302, headers={"Location": final})
    aioclient_mock.get(final, content=PNG, headers={"Content-Type": "image/png"})

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        result = await ws_client.receive_json()

    assert SOURCE_URL in result["result"]["images"]
    assert aioclient_mock.call_count == 2


async def test_svg_is_not_cached(hass, hass_ws_client, aioclient_mock):
    """An SVG served from HA's origin can execute script, so we do not mirror it."""
    await _setup(hass)
    svg_url = "https://cdn.example/logo.svg"
    aioclient_mock.get(
        svg_url,
        content=b"<svg xmlns='http://www.w3.org/2000/svg'><script>x()</script></svg>",
        headers={"Content-Type": "image/svg+xml"},
    )

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [svg_url]}
        )
        result = await ws_client.receive_json()

    # Not cached, so the panel keeps the original remote URL for it.
    assert result["result"]["images"] == {}
    assert os.listdir(images_path(hass)) == []


async def test_refresh_mints_a_new_url_for_changed_bytes(
    hass, hass_ws_client, aioclient_mock
):
    """A refreshed image is a different URL, so no stale browser cache."""
    await _setup(hass)
    aioclient_mock.get(
        SOURCE_URL, content=PNG, headers={"Content-Type": "image/png"}
    )

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        first = (await ws_client.receive_json())["result"]["images"][SOURCE_URL]

        # Same file, bumped mtime: the signed "v" parameter has to change.
        path = os.path.join(images_path(hass), os.listdir(images_path(hass))[0])
        os.utime(path, (1_800_000_000, 1_800_000_000))
        await ws_client.send_json(
            {"id": 2, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        second = (await ws_client.receive_json())["result"]["images"][SOURCE_URL]

    assert "v=1800000000" in second
    assert first.split("authSig=")[0] != second.split("authSig=")[0]


async def test_cached_url_is_returned_without_refetching(
    hass, hass_ws_client, aioclient_mock
):
    """Offline-safe: a second call does not touch the network."""
    await _setup(hass)
    aioclient_mock.get(
        SOURCE_URL, content=PNG, headers={"Content-Type": "image/png"}
    )

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        await ws_client.receive_json()
        await ws_client.send_json(
            {"id": 2, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        result = await ws_client.receive_json()

    assert SOURCE_URL in result["result"]["images"]
    assert aioclient_mock.call_count == 1


async def test_truncated_download_is_rejected(hass, hass_ws_client, aioclient_mock):
    """A body shorter than its Content-Length poisons the cache; reject it."""
    await _setup(hass)
    aioclient_mock.get(
        SOURCE_URL,
        content=PNG,
        headers={"Content-Type": "image/png", "Content-Length": str(len(PNG) + 10)},
    )

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        result = await ws_client.receive_json()

    assert result["result"]["images"] == {}
    assert os.listdir(images_path(hass)) == []


async def test_concurrent_calls_are_serialized(hass, hass_ws_client, aioclient_mock):
    """Two panels loading at once must not both download, or race the eviction.

    The command rewrites the manifest and deletes files, so it holds a lock;
    the second call therefore finds the first call's work already done.
    """
    await _setup(hass)
    aioclient_mock.get(
        SOURCE_URL, content=PNG, headers={"Content-Type": "image/png"}
    )

    ws_client = await hass_ws_client(hass)
    with patch(
        "custom_components.dashable.url_guard.async_resolve",
        side_effect=_fake_resolve,
    ):
        await ws_client.send_json(
            {"id": 1, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        await ws_client.send_json(
            {"id": 2, "type": "dashable/cache_images", "urls": [SOURCE_URL]}
        )
        results = {}
        for _ in range(2):
            message = await ws_client.receive_json()
            results[message["id"]] = message

    assert results[1]["success"] is True
    assert results[2]["success"] is True
    assert SOURCE_URL in results[1]["result"]["images"]
    assert SOURCE_URL in results[2]["result"]["images"]
    assert aioclient_mock.call_count == 1
    assert len(os.listdir(images_path(hass))) == 1
