"""Tests for cache reconciliation: pruning, orphan cleanup and LRU eviction."""
import os

from custom_components.dashable import image_cache
from custom_components.dashable.image_cache import MAX_CACHE_BYTES, reconcile_cache

NAME_A = "a" * 32 + ".png"
NAME_B = "b" * 32 + ".png"
NAME_C = "c" * 32 + ".png"
NAME_SVG = "d" * 32 + ".svg"


def _write(base, name, size=10, mtime=None):
    path = os.path.join(base, name)
    with open(path, "wb") as handle:
        handle.write(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_entries_gain_size_and_mtime(tmp_path):
    base = str(tmp_path)
    _write(base, NAME_A, size=123, mtime=1_700_000_000)

    manifest, changed = reconcile_cache(base, {"https://x/a.png": {"file": NAME_A}})

    assert changed is True
    entry = manifest["https://x/a.png"]
    assert entry["size"] == 123
    assert entry["mtime"] == 1_700_000_000
    assert entry["last_used"] == 1_700_000_000


def test_stable_manifest_reports_no_change(tmp_path):
    base = str(tmp_path)
    _write(base, NAME_A, size=10, mtime=1_700_000_000)
    manifest, _ = reconcile_cache(base, {"https://x/a.png": {"file": NAME_A}})

    again, changed = reconcile_cache(base, manifest)

    assert changed is False
    assert again == manifest


def test_entry_whose_file_is_gone_is_pruned(tmp_path):
    base = str(tmp_path)
    _write(base, NAME_A)

    manifest, changed = reconcile_cache(
        base,
        {
            "https://x/a.png": {"file": NAME_A},
            "https://x/b.png": {"file": NAME_B},  # never written
        },
    )

    assert changed is True
    assert set(manifest) == {"https://x/a.png"}


def test_orphan_files_are_deleted(tmp_path):
    """A file no manifest entry points at is removed, so a lost manifest cannot
    leave the directory growing forever."""
    base = str(tmp_path)
    _write(base, NAME_A)
    _write(base, NAME_B)

    manifest, _ = reconcile_cache(base, {"https://x/a.png": {"file": NAME_A}})

    assert set(manifest) == {"https://x/a.png"}
    assert os.path.exists(os.path.join(base, NAME_A))
    assert not os.path.exists(os.path.join(base, NAME_B))


def test_svg_entries_and_files_are_dropped(tmp_path):
    """SVG support was removed; anything an older version cached goes away."""
    base = str(tmp_path)
    _write(base, NAME_SVG)
    _write(base, NAME_A)

    manifest, changed = reconcile_cache(
        base,
        {
            "https://x/a.svg": {"file": NAME_SVG},
            "https://x/a.png": {"file": NAME_A},
        },
    )

    assert changed is True
    assert set(manifest) == {"https://x/a.png"}
    assert not os.path.exists(os.path.join(base, NAME_SVG))


def test_malformed_entries_are_dropped(tmp_path):
    base = str(tmp_path)
    _write(base, NAME_A)

    manifest, _ = reconcile_cache(
        base,
        {
            "https://x/a.png": {"file": NAME_A},
            "https://x/1": "not-a-dict",
            "https://x/2": {},
            "https://x/3": {"file": "../../../etc/passwd"},
            "https://x/4": {"file": "nothex.png"},
        },
    )

    assert set(manifest) == {"https://x/a.png"}


def test_lru_eviction_down_to_budget(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(image_cache, "MAX_CACHE_BYTES", 250)
    _write(base, NAME_A, size=100, mtime=1_000)  # oldest
    _write(base, NAME_B, size=100, mtime=2_000)
    _write(base, NAME_C, size=100, mtime=3_000)  # newest

    manifest, changed = reconcile_cache(
        base,
        {
            "https://x/a.png": {"file": NAME_A},
            "https://x/b.png": {"file": NAME_B},
            "https://x/c.png": {"file": NAME_C},
        },
    )

    assert changed is True
    assert set(manifest) == {"https://x/b.png", "https://x/c.png"}
    assert not os.path.exists(os.path.join(base, NAME_A))
    assert sum(e["size"] for e in manifest.values()) <= 250


def test_keep_set_is_never_evicted(tmp_path, monkeypatch):
    """Files the dashboard being loaded needs survive even when over budget."""
    base = str(tmp_path)
    monkeypatch.setattr(image_cache, "MAX_CACHE_BYTES", 150)
    _write(base, NAME_A, size=100, mtime=1_000)  # oldest, but in use
    _write(base, NAME_B, size=100, mtime=2_000)

    manifest, _ = reconcile_cache(
        base,
        {
            "https://x/a.png": {"file": NAME_A},
            "https://x/b.png": {"file": NAME_B},
        },
        keep={NAME_A},
    )

    assert set(manifest) == {"https://x/a.png"}
    assert os.path.exists(os.path.join(base, NAME_A))
    assert not os.path.exists(os.path.join(base, NAME_B))


def test_eviction_uses_last_used_not_mtime(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(image_cache, "MAX_CACHE_BYTES", 150)
    # A is the older file but was used most recently, so B is what goes.
    _write(base, NAME_A, size=100, mtime=1_000)
    _write(base, NAME_B, size=100, mtime=2_000)

    manifest, _ = reconcile_cache(
        base,
        {
            "https://x/a.png": {"file": NAME_A, "last_used": 9_000},
            "https://x/b.png": {"file": NAME_B, "last_used": 3_000},
        },
    )

    assert set(manifest) == {"https://x/a.png"}


def test_under_budget_evicts_nothing(tmp_path):
    base = str(tmp_path)
    _write(base, NAME_A, size=10)
    _write(base, NAME_B, size=10)

    manifest, _ = reconcile_cache(
        base,
        {
            "https://x/a.png": {"file": NAME_A},
            "https://x/b.png": {"file": NAME_B},
        },
    )

    assert set(manifest) == {"https://x/a.png", "https://x/b.png"}
    assert MAX_CACHE_BYTES > 20


def test_missing_directory_is_tolerated(tmp_path):
    manifest_in = {"https://x/a.png": {"file": NAME_A}}
    manifest, changed = reconcile_cache(str(tmp_path / "nope"), manifest_in)

    assert changed is False
    assert manifest == manifest_in
