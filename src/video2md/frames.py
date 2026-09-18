"""Frame selection and near-duplicate removal.

Consumes `(t, path)` frames already extracted by ffmpeg and returns a
deduplicated, time-spaced, size-capped list with perceptual hashes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import imagehash


def extract_and_dedup(
    frames: list[tuple[float, Path]],
    *,
    min_scene_interval: float,
    hash_threshold: int,
    max_frames: int,
) -> tuple[list[tuple[float, Path, str]], str | None]:
    """Return (kept as (t, path, phash_hex), warning_or_None)."""
    ordered = sorted(frames, key=lambda pair: pair[0])

    kept: list[tuple[float, Path, str]] = []
    last_t: float | None = None
    last_hash: imagehash.ImageHash | None = None

    for t, path in ordered:
        first = last_t is None
        if not first:
            # Min interval: keep a later frame only if far enough in time.
            if t - last_t < min_scene_interval:
                continue
            # Dedup: drop near-duplicates of the last kept hash.
            h = imagehash.phash(Image.open(path))
            if (h - last_hash) <= hash_threshold:
                continue
        else:
            h = imagehash.phash(Image.open(path))

        kept.append((t, path, str(h)))
        last_t = t
        last_hash = h

    warning: str | None = None
    if len(kept) > max_frames:
        # Keep index 0 and evenly sample the remainder (last frame included).
        n_before = len(kept)
        indices = [round(i * (n_before - 1) / max_frames) for i in range(max_frames)]
        indices = sorted(set(indices))
        if 0 not in indices:
            indices = [0] + indices[:-1]
        kept = [kept[i] for i in indices]
        warning = (
            f"frame cap: sampled down from {n_before} to {len(kept)} frames; "
            f"truncated to max-frames={max_frames}"
        )

    return kept, warning


def merge_frame_candidates(
    scene: list[tuple[float, Path]],
    periodic: list[tuple[float, Path]],
    *,
    same_time_eps: float = 0.05,
) -> list[tuple[float, Path]]:
    """Merge scene and periodic frame candidates, dropping near-duplicate times.

    Scene frames win over periodic frames within `same_time_eps` seconds.
    Returns time-ordered (t, path) with no near-duplicate timestamps.
    """
    scene_paths = {p for _, p in scene}
    # Periodic frames near a scene frame are dropped: scene frames win.
    scene_ts = sorted(t for t, _ in scene)
    periodic_kept = [
        (t, p) for t, p in periodic
        if all(abs(t - st) > same_time_eps for st in scene_ts)
    ]
    combined = sorted(scene + periodic_kept, key=lambda pair: pair[0])

    merged: list[tuple[float, Path]] = []
    last_kept_t: float | None = None
    for t, path in combined:
        if path not in scene_paths:
            # Drop periodic frames that crowd the previous kept frame.
            if last_kept_t is not None and t - last_kept_t <= same_time_eps:
                continue
        merged.append((t, path))
        last_kept_t = t
    return merged
