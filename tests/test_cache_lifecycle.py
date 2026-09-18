"""Tests for the cache lifecycle: safe removal, info, and clear."""

import pytest

import video2md.cache as cache_mod
from video2md.cache import (
    CACHE_MISSING,
    CACHE_REMOVED,
    CACHE_SKIPPED_OUTSIDE_ROOT,
    CACHE_SKIPPED_OUTPUT,
    cache_clear,
    cache_info,
    human_size,
    remove_work_cache,
)


@pytest.fixture
def cache_root(tmp_path, monkeypatch) -> "cache_mod":  # noqa: F821
    root = tmp_path / "cacheroot"
    root.mkdir()
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", root)
    return root


# ---------------------------------------------------------------------------
# remove_work_cache
# ---------------------------------------------------------------------------


def test_remove_work_cache_deletes_inside_root(tmp_path, cache_root):
    work = cache_root / "0123abcd"
    work.mkdir()
    (work / "audio.wav").write_bytes(b"x" * 10)
    (work / "frames").mkdir()
    (work / "frames" / "0001.jpg").write_bytes(b"x" * 4)

    status = remove_work_cache(work)
    assert status == CACHE_REMOVED
    assert not work.exists()
    assert cache_root.is_dir()  # root itself survives


def test_remove_work_cache_missing_dir_is_missing(tmp_path, cache_root):
    status = remove_work_cache(cache_root / "nope")
    assert status == CACHE_MISSING
    assert not (cache_root / "nope").exists()


def test_remove_work_cache_outside_root_is_skipped(tmp_path, cache_root):
    outside = tmp_path / "elsewhere" / "0123abcd"
    outside.mkdir(parents=True)
    (outside / "audio.wav").write_bytes(b"x")

    status = remove_work_cache(outside)
    assert status == CACHE_SKIPPED_OUTSIDE_ROOT
    assert outside.exists()


def test_remove_work_cache_refuses_root_itself(cache_root):
    status = remove_work_cache(cache_root)
    assert status == CACHE_SKIPPED_OUTSIDE_ROOT
    assert cache_root.is_dir()


def test_remove_work_cache_never_touches_final_outputs(tmp_path, cache_root):
    # Pathological case: outputs placed inside the work dir must prevent removal.
    work = cache_root / "0123abcd"
    work.mkdir()
    md = work / "lecture.md"
    md.write_text("# keep")
    sidecar = work / "lecture.transcript.json"
    sidecar.write_text("[]")
    frames = work / "lecture.frames"
    frames.mkdir()
    (frames / "0001.jpg").write_bytes(b"x")

    status = remove_work_cache(work, outputs=[md, sidecar, frames])
    assert status == CACHE_SKIPPED_OUTPUT
    assert md.exists() and sidecar.exists()
    assert (frames / "0001.jpg").exists()


def test_remove_work_cache_never_deletes_output_parent(tmp_path, cache_root):
    # If the output parent (== frames home) resolved to the work dir ancestor
    # ordering, the guard must still protect outputs.
    work = cache_root / "0123abcd"
    out_dir = cache_root / "0123abcd"
    out_dir.mkdir()
    md = out_dir / "lecture.md"
    md.write_text("# keep")

    status = remove_work_cache(work, outputs=[md])
    assert status == CACHE_SKIPPED_OUTPUT
    assert md.exists()


def test_remove_work_cache_detects_partial_failure(tmp_path, cache_root, monkeypatch):
    work = cache_root / "0123abcd"
    work.mkdir()
    (work / "f").write_bytes(b"x")

    def failing_rmtree(path, *a, **kw):
        raise OSError("permission denied")

    monkeypatch.setattr(cache_mod.shutil, "rmtree", failing_rmtree)
    status = remove_work_cache(work)
    assert status == cache_mod.CACHE_FAILED


# ---------------------------------------------------------------------------
# cache_info
# ---------------------------------------------------------------------------


def test_cache_info_missing_root(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", tmp_path / "nope")
    info = cache_info()
    assert info["size"] == 0
    assert info["entries"] == 0


def test_cache_info_counts_entries_and_bytes(cache_root):
    a = cache_root / "aaaa"
    a.mkdir()
    (a / "audio.wav").write_bytes(b"x" * 1000)
    (a / "frames").mkdir()
    (a / "frames" / "0001.jpg").write_bytes(b"y" * 500)
    b = cache_root / "bbbb"
    b.mkdir()
    (b / "f").write_bytes(b"z" * 10)

    info = cache_info()
    assert info["path"] == cache_root
    assert info["size"] == 1510
    assert info["entries"] == 2


# ---------------------------------------------------------------------------
# cache_clear
# ---------------------------------------------------------------------------


def test_cache_clear_removes_all_entries_but_keeps_root(cache_root):
    a = cache_root / "aaaa"
    a.mkdir()
    (a / "audio.wav").write_bytes(b"x" * 10)
    (a / "bbbb").mkdir()
    (cache_root / "stray.json").write_bytes(b"y" * 5)

    removed = cache_clear()
    assert removed == 2  # top-level entries only; b/ is inside a/
    assert cache_root.is_dir()
    assert list(cache_root.iterdir()) == []


def test_cache_clear_missing_root_succeeds(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", tmp_path / "nope")
    assert cache_clear() == 0


def test_cache_clear_empty_root_succeeds(cache_root):
    assert cache_clear() == 0
    assert cache_root.is_dir()


def test_cache_clear_never_touches_outside_root(cache_root, tmp_path):
    (cache_root / "aaaa").mkdir()
    sentinel = tmp_path / "lecture.md"
    sentinel.write_text("# keep")
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "keep.txt").write_text("keep")

    cache_clear()
    assert sentinel.exists()
    assert (sibling / "keep.txt").exists()


# ---------------------------------------------------------------------------
# human_size
# ---------------------------------------------------------------------------


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_size(3_700_000_000) == "3.4 GB"
    assert human_size(int(3.7 * 1024**3)) == "3.7 GB"
