"""Cache helpers: work dirs, fingerprints, JSON persistence, lifecycle."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from video2md.stt import json_default

CACHE_ROOT = Path.home() / "Library/Caches/video2md"

# Statuses returned by remove_work_cache().
CACHE_REMOVED = "removed"
CACHE_MISSING = "missing"
CACHE_SKIPPED_OUTSIDE_ROOT = "outside_cache_root"
CACHE_SKIPPED_OUTPUT = "would_touch_outputs"
CACHE_FAILED = "failed"


def cache_key(video: Path) -> str:
    """16 hex chars of SHA-256 over utf-8 '{resolved}|{size_bytes}|{mtime_ns}'."""
    resolved = video.resolve()
    stat = resolved.stat()
    payload = f"{resolved}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def work_dir_for(video: Path, override: Path | None) -> Path:
    """override / cache_key(video) if override given, else CACHE_ROOT / cache_key(video)."""
    if override is not None:
        return override / cache_key(video)
    return CACHE_ROOT / cache_key(video)


def _is_within(path: Path, root: Path) -> bool:
    """True when path equals root or lies strictly inside root."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def remove_work_cache(
    work: Path,
    outputs: list[Path] | None = None,
    root: Path | None = None,
) -> str:
    """Delete one per-video work cache dir, refusing anything unsafe to remove.

    Safety rules:
    - `work` must live inside `root` (default CACHE_ROOT). A `--work-dir`
      override outside the managed cache root is never auto-deleted.
    - `outputs` are final artifacts (.md, .transcript.json, .frames/). The
      removal is skipped if the work dir contains, equals, or is an ancestor
      of any of them.

    Returns one of the CACHE_* status constants. Never raises.
    """
    outputs = outputs or []
    root = (root if root is not None else CACHE_ROOT).resolve()
    try:
        resolved = work.resolve()
    except OSError:
        return CACHE_FAILED

    if not _is_within(resolved, root):
        return CACHE_SKIPPED_OUTSIDE_ROOT
    if resolved == root:
        return CACHE_SKIPPED_OUTSIDE_ROOT

    for out in outputs:
        try:
            out_resolved = out.resolve()
        except OSError:
            return CACHE_FAILED
        # work dir must not contain / equal / be an ancestor of an output.
        if _is_within(out_resolved, resolved):
            return CACHE_SKIPPED_OUTPUT

    if not resolved.exists():
        return CACHE_MISSING
    try:
        shutil.rmtree(resolved)
    except OSError:
        return CACHE_FAILED
    return CACHE_REMOVED


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_symlink():
                    continue
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def cache_info(root: Path | None = None) -> dict:
    """Summarize the managed cache: path, total bytes, entry count.

    An entry is a first-level subdirectory of the cache root (one per video).
    Missing root -> size 0, entries 0.
    """
    root = (root if root is not None else CACHE_ROOT).expanduser()
    if not root.is_dir():
        return {"path": root, "size": 0, "entries": 0}
    entries = [p for p in root.iterdir() if p.is_dir()]
    return {
        "path": root,
        "size": sum(_dir_size(p) for p in entries),
        "entries": len(entries),
    }


def cache_clear(root: Path | None = None) -> int:
    """Delete the entire managed cache root's contents; never touch anything
    outside it. Returns the number of removed entries. Never raises."""
    root = (root if root is not None else CACHE_ROOT).expanduser()
    if not root.is_dir():
        return 0
    count = 0
    for entry in root.iterdir():
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            count += 1
        except OSError:
            continue
    return count


def human_size(size: int) -> str:
    """Human-readable size, e.g. '3.7 GB'."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def fingerprint(obj: dict) -> str:
    """Canonical JSON then sha256 hex."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    """Load JSON from a file, or None if unreadable/invalid."""
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, obj: Any) -> None:
    """Write JSON to a file, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, default=json_default, ensure_ascii=False, indent=2) + "\n",
        "utf-8",
    )


def load_manifest(work: Path) -> dict:
    """Load the pipeline manifest from the work dir, or {} if absent/invalid."""
    data = read_json(work / "manifest.json")
    return data if isinstance(data, dict) else {}


def save_manifest(work: Path, manifest: dict) -> None:
    """Rewrite the whole manifest file for the given work dir."""
    write_json(work / "manifest.json", manifest)
