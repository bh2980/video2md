import argparse
import logging
import os
import platform
import shutil
import sys
from pathlib import Path

from video2md import __version__, pipeline
from video2md.cache import work_dir_for
from video2md.inputs import (
    expand_inputs,
    markdown_destination,
    uses_out_directory,
)
from video2md.models import Options
from video2md.config import (
    DEFAULT_WHISPER_MODEL,
    FRAME_EVERY,
    HASH_THRESHOLD,
    MAX_FRAMES,
    MIN_SCENE_INTERVAL,
    OCR_CONFIDENCE,
    OCR_MIN_CHARS,
    SCENE_THRESHOLD,
    resolve_whisper_model,
)
from video2md.errors import (
    FfmpegNotFoundError,
    InputNotFoundError,
    PlatformError,
    UsageError,
    Video2MdError,
)


def require_platform() -> None:
    """Ensure we are running on Apple Silicon macOS."""
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise PlatformError(
            "video2md requires macOS on Apple Silicon (arm64). "
            f"Found {sys.platform} / {platform.machine()}."
        )


def require_ffmpeg() -> None:
    """Ensure ffmpeg and ffprobe are available on PATH."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise FfmpegNotFoundError(
            "ffmpeg not found on PATH. Install with: brew install ffmpeg"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video2md")
    parser.add_argument("--version", action="version", version=f"video2md {__version__}")
    parser.add_argument("inputs", nargs="+", help="videos and/or directories of videos")
    parser.add_argument("--recursive", action="store_true",
                        help="recurse into directories when collecting videos")
    parser.add_argument("--fail-fast", action="store_true",
                        help="stop the batch at the first failed job and return its exit code")
    parser.add_argument(
        "--out",
        default=None,
        help="markdown file for a single video, or output directory for a folder / multiple videos",
    )
    parser.add_argument("--captions", default=None, help="existing captions file (single video only)")
    parser.add_argument("--work-dir", default=None, help="working directory")
    parser.add_argument("--language", default=None, help="spoken language hint")
    parser.add_argument("--whisper-model", default=DEFAULT_WHISPER_MODEL)
    parser.add_argument("--scene-threshold", type=float, default=SCENE_THRESHOLD)
    parser.add_argument("--min-scene-interval", type=float, default=MIN_SCENE_INTERVAL)
    parser.add_argument("--max-frames", type=int, default=MAX_FRAMES)
    parser.add_argument("--frame-every", type=float, default=FRAME_EVERY,
                        help="extract an extra frame every N seconds in addition to scene detection; 0 disables")
    parser.add_argument("--hash-threshold", type=int, default=HASH_THRESHOLD)
    parser.add_argument("--ocr-confidence", type=float, default=OCR_CONFIDENCE)
    parser.add_argument("--ocr-min-chars", type=int, default=OCR_MIN_CHARS)
    parser.add_argument("--force-stt", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--skip-speech", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--keep-cache",
        action="store_true",
        help="keep the per-video work cache even when the conversion succeeds "
        "(useful for debugging or regenerating results)",
    )
    parser.add_argument("--hash-source", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def _cache_main(rest: list[str]) -> int:
    """Handle `video2md cache info` / `video2md cache clear`.

    Cache management must work without ffmpeg or platform checks, so it is
    dispatched before those in main().
    """
    from video2md.cache import CACHE_ROOT, cache_clear, cache_info, human_size

    parser = argparse.ArgumentParser(prog="video2md cache")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="show cache path, total size, and entry count")
    sub.add_parser("clear", help="delete the entire video2md cache")
    args = parser.parse_args(rest)

    if args.command == "info":
        info = cache_info()
        print(f"Cache: {info['path']}")
        print(f"Size: {human_size(info['size'])}")
        print(f"Entries: {info['entries']}")
        return 0

    cleared = cache_clear()
    print(f"Cleared {cleared} entries under {CACHE_ROOT}")
    return 0


def _fail(e: Exception) -> int:
    print(f"video2md: error: {e}", file=sys.stderr)
    if isinstance(e, Video2MdError):
        return e.exit_code
    return 1


def _check_inputs_exist(video: Path, captions: Path | None) -> None:
    for label, path in (("video", video), ("captions", captions)):
        if path is not None and not os.access(path, os.R_OK):
            raise InputNotFoundError(f"input not found: {path}")


def _make_options(args, video: Path, out: Path, captions: Path | None, work: Path) -> Options:
    return Options(
        video=video,
        out=out,
        captions=captions,
        work_dir=work,
        language=args.language,
        whisper_model=args.whisper_model,
        scene_threshold=args.scene_threshold,
        min_scene_interval=args.min_scene_interval,
        max_frames=args.max_frames,
        hash_threshold=args.hash_threshold,
        frame_every=args.frame_every,
        ocr_confidence=args.ocr_confidence,
        ocr_min_chars=args.ocr_min_chars,
        force_stt=args.force_stt,
        skip_ocr=args.skip_ocr,
        skip_speech=args.skip_speech,
        force=args.force,
        clean=args.clean,
        hash_source=args.hash_source,
        keep_cache=args.keep_cache,
    )


def _run_one(args, video: Path, out: Path, captions: Path | None, override: Path | None):
    """Run a single job. Returns (exit_code, written_path_or_None)."""
    try:
        _check_inputs_exist(video, captions)
        work = work_dir_for(video, override)
        opts = _make_options(args, video, out, captions, work)
        written = pipeline.run(opts)
    except Video2MdError as e:
        print(f"video2md: error: {e}", file=sys.stderr)
        return e.exit_code, None
    except OSError as e:
        print(f"video2md: error: {e}", file=sys.stderr)
        return 1, None
    return 0, written


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)

    if len(args_list) >= 2 and args_list[0] == "cache" and args_list[1] in ("info", "clear"):
        try:
            return _cache_main(args_list[1:])
        except SystemExit as e:  # argparse usage errors
            code = e.code
            return code if isinstance(code, int) else (0 if code is None else 2)

    parser = build_parser()
    try:
        args = parser.parse_args(args_list)
    except SystemExit as e:
        # argparse raises SystemExit(0) for --help/--version and 2 for CLI errors.
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 2)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    try:
        if args.skip_ocr and args.skip_speech:
            raise UsageError("--skip-ocr and --skip-speech cannot be used together")

        if args.frame_every < 0:
            raise UsageError("`--frame-every` must be >= 0")

        resolve_whisper_model(args.whisper_model)

        require_platform()
        require_ffmpeg()

        raw = [Path(x) for x in args.inputs]
        jobs = expand_inputs(raw, recursive=args.recursive)
        if not jobs:
            raise UsageError("no videos found")

        if args.captions and len(jobs) != 1:
            raise UsageError("--captions is only valid for a single video")

        dir_out = uses_out_directory(raw, jobs)
        if args.out and dir_out:
            out_dir = Path(args.out).expanduser()
            if out_dir.exists() and not out_dir.is_dir():
                raise UsageError(
                    "--out must be a directory when the input is a directory "
                    "or multiple videos"
                )
            dests = [markdown_destination(v, out_dir, raw) for v in jobs]
            resolved = [d.resolve() for d in dests]
            if len(set(resolved)) != len(resolved):
                raise UsageError("duplicate output paths under --out")
    except Video2MdError as e:
        return _fail(e)
    except OSError as e:
        return _fail(e)

    override = Path(args.work_dir).expanduser() if args.work_dir else None
    raw = [Path(x) for x in args.inputs]
    dir_out = uses_out_directory(raw, jobs)

    def dest_for(video: Path) -> Path:
        if not args.out:
            return video.with_suffix(".md")
        if dir_out:
            return markdown_destination(video, Path(args.out).expanduser(), raw)
        return Path(args.out).expanduser()

    if len(jobs) == 1:
        video = jobs[0]
        out = dest_for(video)
        if not dir_out and out.resolve() == video.expanduser().resolve():
            print("video2md: error: --out cannot equal the input video", file=sys.stderr)
            return UsageError("output path must differ from the input video").exit_code
        captions = Path(args.captions).expanduser() if args.captions else None
        code, written = _run_one(args, video, out, captions, override)
        if code == 0 and written is not None:
            print(written)
        return code

    # Batch mode: sequential, one job at a time.
    ok = 0
    failed: list[tuple[Path, int]] = []
    n = len(jobs)
    for i, video in enumerate(jobs, start=1):
        out = dest_for(video)
        code, _ = _run_one(args, video, out, None, override)
        if code == 0:
            ok += 1
            print(f"[{i}/{n}] {video.name:<14} OK")
        else:
            failed.append((video, code))
            print(f"[{i}/{n}] {video.name:<14} FAILED (exit {code})")
            if args.fail_fast:
                break

    print()
    print(f"Done: {ok} succeeded, {len(failed)} failed")
    for video, _code in failed:
        print(str(video))

    if args.fail_fast and failed:
        return failed[-1][1]
    return 0 if not failed else 1
