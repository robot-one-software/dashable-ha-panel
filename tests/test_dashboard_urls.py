"""Tests for decoding synced dashboards and harvesting their URLs.

The premise this module rests on is that a synced dashboard is compressed, not
encrypted — so the first test is the one that would fail if that were ever
wrong, and the rest build on it.
"""
import base64
import json
import zlib

import pytest

from custom_components.dashable.dashboard_urls import (
    MAX_DECODED_BYTES,
    MAX_SEALED_VERSION,
    MAX_URLS,
    DashboardDecodeError,
    allowed_image_urls,
    collect_dashboard_urls,
    decode_sealed,
    normalize_candidate,
)

URL = "https://cdn.example/a.png"


def deflate_raw(data: bytes) -> bytes:
    """Compress headerless, the way ``DecompressionStream("deflate-raw")`` reads."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def seal(dashboard, version: int = 1) -> str:
    body = base64.b64encode(deflate_raw(json.dumps(dashboard).encode())).decode()
    return f"DSHB{version}:{body}"


# --- The decoder ---


def test_sealed_dashboard_is_readable_without_any_key():
    """No key participates: base64 + raw deflate is the whole of the encoding."""
    dashboard = {"widgets": [{"type": "image-widget", "imageAttribute": URL}]}
    assert decode_sealed(seal(dashboard)) == dashboard


def test_bare_json_branch():
    dashboard = {"widgets": []}
    assert decode_sealed(json.dumps(dashboard)) == dashboard
    assert decode_sealed("\n\t  " + json.dumps(dashboard)) == dashboard


def test_version_zero_is_readable():
    assert decode_sealed(seal({"widgets": []}, version=0)) == {"widgets": []}


def test_version_above_the_ceiling_is_a_decode_failure():
    """Not "skip the allowlist" — a failure, so the payload's URLs are refused."""
    sealed = seal({"widgets": []}, version=MAX_SEALED_VERSION + 1)
    with pytest.raises(DashboardDecodeError, match="version"):
        decode_sealed(sealed)


def test_base64_slack_is_tolerated():
    """Node's Buffer.from accepts the URL-safe alphabet and loose padding."""
    dashboard = {"widgets": [{"imageAttribute": URL}]}
    raw = deflate_raw(json.dumps(dashboard).encode())
    urlsafe = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert decode_sealed(f"DSHB1:{urlsafe}") == dashboard
    standard = base64.b64encode(raw).decode()
    assert decode_sealed("DSHB1:" + "\n".join([standard[:8], standard[8:]])) == dashboard


@pytest.mark.parametrize(
    "sealed",
    [
        "",
        "   ",
        "not a dashboard",
        "{oops",
        "DSHB:" + base64.b64encode(deflate_raw(b"{}")).decode(),  # no version digits
        "DSHB1:!!!!",
        "DSHB1:" + base64.b64encode(b"not deflate at all").decode(),
        "DSHB1:",  # empty body: not a complete stream
        # Valid deflate, but the payload inside is not JSON.
        "DSHB1:" + base64.b64encode(deflate_raw(b"<html>")).decode(),
    ],
)
def test_undecodable_payloads_raise(sealed):
    with pytest.raises(DashboardDecodeError):
        decode_sealed(sealed)


@pytest.mark.parametrize("blob", [None, 123, {}, b"DSHB1:AAAA"])
def test_non_string_payload_raises(blob):
    with pytest.raises(DashboardDecodeError):
        decode_sealed(blob)


def test_truncated_deflate_stream_raises():
    raw = deflate_raw(json.dumps({"widgets": []}).encode())
    sealed = "DSHB1:" + base64.b64encode(raw[: len(raw) // 2]).decode()
    with pytest.raises(DashboardDecodeError, match="truncated"):
        decode_sealed(sealed)


def test_compression_bomb_hits_the_size_ceiling():
    """The blob arrives from the network, so the inflate is bounded."""
    bomb = base64.b64encode(deflate_raw(b"\0" * (MAX_DECODED_BYTES + 1024))).decode()
    with pytest.raises(DashboardDecodeError, match="size ceiling"):
        decode_sealed(f"DSHB1:{bomb}")


# --- Normalizing a dashboard string the way the panel does ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (URL, URL),
        ("  " + URL + "  ", URL),
        ("http://cdn.example/a.png", "http://cdn.example/a.png"),
        ("HTTPS://cdn.example/a.png", "HTTPS://cdn.example/a.png"),
        # Scheme-less: the panel assumes https, and so must we or every
        # dashboard written that way stops being mirrored.
        ("cdn.example/a.png", "https://cdn.example/a.png"),
        # An attribute name, a relative path and a data URI are not fetches.
        ("entity_picture", None),
        ("/local/a.png", None),
        ("data:image/png;base64,AAAA", None),
        ("", None),
        ("   ", None),
    ],
)
def test_normalize_candidate(value, expected):
    assert normalize_candidate(value) == expected


# --- Harvesting URLs out of a decoded dashboard ---


def test_urls_are_found_wherever_they_sit():
    dashboard = {
        "name": "Main",
        "widgets": [
            {"type": "image-widget", "imageAttribute": URL},
            {
                "type": "image-widget",
                "conditionalStylingConfigs": [
                    {
                        "overrideImageSourceType": "url",
                        "overrideImageUrlOrAttribute": "https://cdn.example/b.jpg",
                    }
                ],
            },
            {"type": "text-widget", "nested": {"deep": ["cdn.example/c.webp"]}},
        ],
    }
    assert collect_dashboard_urls(dashboard) == {
        URL,
        "https://cdn.example/b.jpg",
        "https://cdn.example/c.webp",
    }


def test_the_envelope_form_is_handled():
    """Dashable also ships ``{"dashboard": {...}}``; the walk does not care."""
    assert collect_dashboard_urls({"dashboard": {"widgets": [{"a": URL}]}}) == {URL}


@pytest.mark.parametrize(
    "value",
    [
        "A sentence. With a full stop.",  # prose: the host would hold spaces
        "entity_picture",  # no dot, so no scheme is assumed
        "/local/a.png",
        "data:image/png;base64,AAAA",
        "https://user:pw@cdn.example/a.png",  # credentials are refused outright
        "https://cdn.example/" + "a" * 3000,  # over MAX_URL_LENGTH
    ],
)
def test_strings_that_are_not_fetchable_urls_are_skipped(value):
    found = collect_dashboard_urls({"widgets": [{"field": value}]})
    assert value not in found
    assert normalize_candidate(value) not in found


@pytest.mark.parametrize(
    ("value", "harvested"),
    [
        # An entity id is dotted and host-shaped, so a scheme gets assumed.
        ("sensor.living_room", "https://sensor.living_room"),
        # So is any other scheme: the panel's normalizer only recognises
        # http/https, and prefixes everything else rather than rejecting it.
        ("ftp://cdn.example/a.png", "https://ftp://cdn.example/a.png"),
    ],
)
def test_the_allowlist_is_wider_than_urls_in_two_known_ways(value, harvested):
    """Worth stating plainly rather than leaving as a surprise.

    Both of these are what the panel's own normalizer produces, so matching it
    is the point — the posted URL has to line up with the harvested one. Both
    land in the allowlist and neither is reachable: ``sensor.living_room`` and
    ``ftp`` are single-label hosts that resolve to nothing, and if a search
    domain did resolve one, it would resolve to a LAN address that the address
    checks refuse. The allowlist bounds which strings may be *named*; it is
    not the thing that decides where a fetch may go.
    """
    assert collect_dashboard_urls({"widgets": [{"field": value}]}) == {harvested}


def test_non_string_leaves_are_ignored():
    dashboard = {"widgets": [{"x": 1, "y": None, "z": True, "w": 1.5}]}
    assert collect_dashboard_urls(dashboard) == set()


def test_deep_nesting_does_not_blow_the_stack():
    """A dashboard is user data, so the walk is iterative rather than recursive."""
    node: object = {"url": URL}
    for _ in range(50_000):
        node = {"child": [node]}
    assert collect_dashboard_urls(node) == {URL}


def test_the_harvest_is_bounded():
    urls = [f"https://cdn.example/{index}.png" for index in range(MAX_URLS + 50)]
    found = collect_dashboard_urls({"widgets": urls})
    assert len(found) <= MAX_URLS


# --- The store-wide allowlist ---


def test_allowlist_unions_every_dashboard():
    stored = {
        "a": {"sealed": seal({"widgets": [{"imageAttribute": URL}]})},
        "b": {"sealed": seal({"widgets": [{"imageAttribute": "cdn.example/b.png"}]})},
    }
    assert allowed_image_urls(stored) == {URL, "https://cdn.example/b.png"}


def test_a_dashboard_that_will_not_decode_contributes_nothing():
    """The deliberate failure mode: refuse its URLs, do not wave them through."""
    stored = {"broken": {"sealed": "DSHB1:!!!!"}}
    assert allowed_image_urls(stored) == set()


def test_a_broken_dashboard_does_not_disarm_the_rest():
    stored = {
        "broken": {"sealed": "DSHB1:!!!!"},
        "good": {"sealed": seal({"widgets": [{"imageAttribute": URL}]})},
    }
    assert allowed_image_urls(stored) == {URL}


@pytest.mark.parametrize("stored", [{}, None, [], "nope", {"a": None}, {"a": {}}])
def test_allowlist_of_nothing_is_empty(stored):
    assert allowed_image_urls(stored) == set()


def test_a_unicode_digit_version_is_not_read_as_a_number():
    """The bundle's ``\\d`` is ASCII-only, so ours has to be too.

    Python's ``\\d`` matches Arabic-Indic digits, which would have made this a
    readable version 1 here and an unreadable payload in the panel.
    """
    body = base64.b64encode(deflate_raw(json.dumps({"widgets": []}).encode())).decode()
    with pytest.raises(DashboardDecodeError):
        decode_sealed(f"DSHB١:{body}")
