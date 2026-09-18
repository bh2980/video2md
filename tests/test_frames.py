from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

from video2md.frames import extract_and_dedup, merge_frame_candidates


def _noise_image(seed: int, invert_first_block: bool = False) -> Image.Image:
    """Deterministic 2x2-block black/white noise: distinct seeds are visually
    different slides (phash distance ~30); a single inverted block keeps the
    picture a near-duplicate (phash distance ~0)."""
    rng = random.Random(seed)
    img = Image.new("RGB", (64, 64), (255, 255, 255))
    for x in range(0, 64, 2):
        for y in range(0, 64, 2):
            v = rng.choice([(0, 0, 0), (255, 255, 255)])
            if invert_first_block and (x, y) == (0, 0):
                v = (255, 255, 255) if v == (0, 0, 0) else (0, 0, 0)
            for dx in (0, 1):
                for dy in (0, 1):
                    img.putpixel((x + dx, y + dy), v)
    return img


def _save(path: Path, seed: int, invert_first_block: bool = False) -> Path:
    _noise_image(seed, invert_first_block).save(path)
    return path


def test_near_duplicates_dropped_different_slide_kept(tmp_path: Path):
    a = _save(tmp_path / "a.jpg", seed=0)
    b = _save(tmp_path / "b.jpg", seed=0, invert_first_block=True)  # near-dup of a
    c = _save(tmp_path / "c.jpg", seed=1)  # clearly different slide
    frames = [(0.0, a), (5.0, b), (10.0, c)]

    kept, warning = extract_and_dedup(
        frames, min_scene_interval=0.0, hash_threshold=8, max_frames=50
    )

    assert [p for _, p, _ in kept] == [a, c]
    assert warning is None
    # Every kept entry carries a 64-bit hex phash.
    for _, _, hexstr in kept:
        assert len(hexstr) == 16
        int(hexstr, 16)


def test_mid_sized_block_change_kept(tmp_path: Path):
    """Two slides differing by a clearly visible block (like an IDE code edit)
    must be KEPT at hash_threshold=8, not treated as near-duplicates."""
    a = _save(tmp_path / "a.jpg", seed=0)
    b_img = _noise_image(seed=0)  # same slide...
    # ...with a clearly visible code-like change: an inverted 16x32 block area
    # (not a 1-pixel / single-block invert).
    for x in range(8, 24):
        for y in range(8, 40):
            r, g, bl = b_img.getpixel((x, y))
            b_img.putpixel((x, y), (255 - r, 255 - g, 255 - bl))
    b = tmp_path / "b.jpg"
    b_img.save(b)

    frames = [(0.0, a), (5.0, b)]
    kept, warning = extract_and_dedup(
        frames, min_scene_interval=0.0, hash_threshold=8, max_frames=50
    )

    assert [p for _, p, _ in kept] == [a, b]
    assert warning is None


def test_min_interval_drops_close_frames_even_if_hashes_differ(tmp_path: Path):
    a = _save(tmp_path / "a.jpg", seed=0)
    b = _save(tmp_path / "b.jpg", seed=1)  # hash far from a
    frames = [(0.0, a), (0.5, b), (5.0, b)]

    kept, warning = extract_and_dedup(
        frames, min_scene_interval=1.0, hash_threshold=8, max_frames=50
    )

    assert [t for t, _, _ in kept] == [0.0, 5.0]
    assert warning is None


def test_max_frames_samples_and_warns(tmp_path: Path):
    # Five distinct slides, well spaced in time so only the cap trims them.
    paths = [_save(tmp_path / f"s{i}.jpg", seed=i) for i in range(5)]
    frames = [(float(i * 10), p) for i, p in enumerate(paths)]

    kept, warning = extract_and_dedup(
        frames, min_scene_interval=1.0, hash_threshold=8, max_frames=2
    )

    assert len(kept) == 2
    assert kept[0][0] == 0.0  # index 0 always kept
    assert warning is not None and "truncated to max-frames=" in warning


def test_single_frame_t0_kept(tmp_path: Path):
    a = _save(tmp_path / "a.jpg", seed=0)

    kept, warning = extract_and_dedup(
        [(0.0, a)], min_scene_interval=0.0, hash_threshold=8, max_frames=10
    )

    assert [t for t, _, _ in kept] == [0.0]
    assert warning is None


def test_merge_scene_t0_periodic_t0_keeps_scene_only(tmp_path: Path):
    scene = [(0.0, tmp_path / "scene.jpg")]
    periodic = [(0.0, tmp_path / "per.jpg")]
    merged = merge_frame_candidates(scene, periodic)
    assert merged == [(0.0, tmp_path / "scene.jpg")]


def test_merge_scene_t5_periodic_t5_04_within_eps_keeps_scene(tmp_path: Path):
    scene = [(5.00, tmp_path / "scene.jpg")]
    periodic = [(5.04, tmp_path / "per.jpg")]
    merged = merge_frame_candidates(scene, periodic)
    assert merged == [(5.00, tmp_path / "scene.jpg")]


def test_merge_disjoint_times_all_kept_in_order(tmp_path: Path):
    scene = [
        (0.0, tmp_path / "s0.jpg"),
        (12.0, tmp_path / "s12.jpg"),
    ]
    periodic = [(5.0, tmp_path / "p5.jpg")]
    merged = merge_frame_candidates(scene, periodic)
    assert [t for t, _ in merged] == [0.0, 5.0, 12.0]
    assert [p for _, p in merged] == [
        tmp_path / "s0.jpg",
        tmp_path / "p5.jpg",
        tmp_path / "s12.jpg",
    ]


def test_merge_does_not_drop_two_close_scene_frames(tmp_path: Path):
    scene = [
        (0.00, tmp_path / "s0.jpg"),
        (0.03, tmp_path / "s1.jpg"),
    ]
    merged = merge_frame_candidates(scene, [])
    assert [p for _, p in merged] == [tmp_path / "s0.jpg", tmp_path / "s1.jpg"]


def test_merge_empty_periodic_returns_scene(tmp_path: Path):
    scene = [(0.0, tmp_path / "s0.jpg"), (12.0, tmp_path / "s12.jpg")]
    assert merge_frame_candidates(scene, []) == scene
