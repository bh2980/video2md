"""Tests for cache helpers."""

import json
import os

from video2md.cache import (
    cache_key,
    fingerprint,
    load_manifest,
    read_json,
    save_manifest,
    work_dir_for,
    write_json,
)


def _touch(path, size=None, mtime_ns=None):
    path.write_bytes(b"x" * (size or 4))
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_cache_key_stable(tmp_path):
    v = _touch(tmp_path / "a.mp4", size=10, mtime_ns=1_000_000)
    k1 = cache_key(v)
    assert len(k1) == 16
    assert all(c in "0123456789abcdef" for c in k1)
    assert cache_key(v) == k1
    assert cache_key(tmp_path / ".".join(["a", "mp4"])) == k1


def test_cache_key_changes_with_size_or_mtime(tmp_path):
    v = _touch(tmp_path / "a.mp4", size=10, mtime_ns=1_000_000)
    base = cache_key(v)

    _touch(v, size=11, mtime_ns=1_000_000)
    assert cache_key(v) != base

    _touch(v, size=10, mtime_ns=1_000_000 + 5_000_000)
    assert cache_key(v) != base


def test_fingerprint_order_independent():
    a = fingerprint({"a": 1, "b": 2})
    b = fingerprint({"b": 2, "a": 1})
    assert a == b


def test_fingerprint_detects_ocr_min_chars():
    base = fingerprint({"ocr": {"ocr_min_chars": 5}})
    changed = fingerprint({"ocr": {"ocr_min_chars": 6}})
    assert base != changed


def test_write_read_json_roundtrip(tmp_path):
    obj = {"list": [1, 2], "nested": {"k": "value"}}
    p = tmp_path / "deep" / "data.json"
    write_json(p, obj)
    assert read_json(p) == obj


def test_read_json_invalid_or_missing(tmp_path):
    assert read_json(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert read_json(bad) is None


def test_save_then_load_manifest(tmp_path):
    manifest = {"stage": "ocr", "ocr_fp": {"ocr_min_chars": 5}}
    save_manifest(tmp_path, manifest)
    assert (tmp_path / "manifest.json").exists()
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    assert load_manifest(tmp_path) == manifest


def test_load_manifest_missing(tmp_path):
    assert load_manifest(tmp_path) == {}


def test_work_dir_override(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_text("")
    override = tmp_path / "custom"
    assert work_dir_for(video, override) == override / cache_key(video)
    assert work_dir_for(video, override) != override
    assert work_dir_for(video, None).name == cache_key(video)
    assert work_dir_for(video, None).parent.name == "video2md"
