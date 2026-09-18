"""Expand user-supplied positional paths into an ordered list of video jobs."""

from pathlib import Path

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v"}


def expand_inputs(raw: list[Path], *, recursive: bool = False) -> list[Path]:
    """Expand files and directories into unique video job paths.

    - If a path is an existing directory: collect files whose suffix
      (case-insensitive) is in VIDEO_SUFFIXES. Skip names starting with '.'.
      Non-recursive: only the directory itself (Path.iterdir).
      Recursive: all descendants (Path.rglob("*")).
      Sort with key=lambda p: p.as_posix().lower() so nested dirs stay grouped.
    - Otherwise (existing file OR missing path OR non-dir): append that path
      as a single job. Do not filter by suffix (user may pass foo.webm).
    - Dedup by Path.expanduser().resolve() when the path exists; for missing
      paths use expanduser() absolute-normalized string. Keep first occurrence.
    - Return the list. Do not raise if empty.
    """
    jobs: list[Path] = []
    seen: set[str] = set()

    def _key_for(p: Path) -> str:
        expanded = p.expanduser()
        if expanded.exists():
            return str(expanded.resolve())
        return str(Path(expanded).absolute())

    def _push(p: Path) -> None:
        key = _key_for(p)
        if key in seen:
            return
        seen.add(key)
        jobs.append(p)

    for entry in raw:
        expanded = entry.expanduser()
        if expanded.exists() and expanded.is_dir():
            if recursive:
                candidates = expanded.rglob("*")
            else:
                candidates = expanded.iterdir()
            collected = [
                p
                for p in candidates
                if p.is_file()
                and not p.name.startswith(".")
                and p.suffix.lower() in VIDEO_SUFFIXES
            ]
            collected.sort(key=lambda p: p.as_posix().lower())
            for p in collected:
                _push(p)
        else:
            _push(entry)

    return jobs


def directory_inputs(raw: list[Path]) -> list[Path]:
    """Resolved paths of positional inputs that are existing directories."""
    dirs: list[Path] = []
    seen: set[str] = set()
    for entry in raw:
        expanded = entry.expanduser()
        if expanded.exists() and expanded.is_dir():
            resolved = expanded.resolve()
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                dirs.append(resolved)
    return dirs


def uses_out_directory(raw: list[Path], jobs: list[Path]) -> bool:
    """True when --out should be treated as an output directory."""
    return bool(directory_inputs(raw)) or len(jobs) > 1


def markdown_destination(video: Path, out_dir: Path, raw: list[Path]) -> Path:
    """Map a video job to a markdown path under out_dir.

    A video found under a directory input keeps its relative path. When more
    than one directory was given, prefix with that directory's name so two
    folders both containing 01.mp4 do not collide. Loose files use stem.md.
    """
    dirs = directory_inputs(raw)
    expanded = video.expanduser()
    video_res = expanded.resolve() if expanded.exists() else expanded.absolute()

    matching = [d for d in dirs if _is_relative_to(video_res, d)]
    if matching:
        source = max(matching, key=lambda d: len(d.parts))
        rel = video_res.relative_to(source).with_suffix(".md")
        if len(dirs) > 1:
            return out_dir / source.name / rel
        return out_dir / rel
    return out_dir / f"{expanded.stem}.md"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

